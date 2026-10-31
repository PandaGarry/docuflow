"""Автоматический QA ассетов студии.

Ловит то, что обычно ловят глазами уже после рендера:
  • низкое разрешение и «мыло»;
  • дырки в силуэте и мусор по краю;
  • зелёный ореол после хромакея;
  • подозрительное число конечностей (профиль ширины силуэта);
  • выпадающую палитру (ΔE к эталону из арт-библии);
  • перегруз деталями (слишком много цветовых кластеров).

Часть проверок эвристическая: скрипт не заменяет просмотр, а сужает его.
Каждый флаг в отчёте — повод посмотреть конкретный ассет, а не приговор.

Запуск:
  python studio/engine/qa.py                       # проверить style-tests и characters
  python studio/engine/qa.py --assets studio/characters --min-h 900
  python studio/engine/qa.py --assets x.png --json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))   # корень репозитория
SEARCH = os.path.dirname(HERE)                  # studio/

# эталонная палитра из docs/03-CHARACTER-BIBLE.md
PALETTE = {
    "line": (59, 42, 38),
    "skin": (232, 180, 143),
    "skin_shadow": (210, 150, 111),
    "dad_hoodie": (201, 199, 194),
    "dad_hair": (74, 51, 42),
    "mom_vest": (91, 64, 52),
    "mom_hair": (154, 120, 86),
    "mom_top": (245, 241, 232),
    "son_hoodie": (107, 74, 58),
    "son_cap": (207, 232, 200),
    "accent_coral": (255, 96, 84),
    "accent_mustard": (240, 187, 76),
    "bg_cream": (255, 248, 236),
    "bg_sage": (138, 168, 138),
}


# --------------------------------------------------------------------------- #
# цветовые утилиты
# --------------------------------------------------------------------------- #
def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0..255) -> CIE Lab (D65). Векторизовано."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124, 0.3576, 0.1805],
                  [0.2126, 0.7152, 0.0722],
                  [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, xyz ** (1 / 3), 7.787 * xyz + 16 / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def delta_e(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    return np.linalg.norm(lab1 - lab2, axis=-1)


def nearest_palette(rgb_pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Для каждого пикселя — ближайший цвет палитры и его ΔE."""
    names = list(PALETTE)
    pal = np.array([PALETTE[n] for n in names], dtype=np.float64)
    lab_px = rgb_to_lab(rgb_pixels)[:, None, :]
    lab_pal = rgb_to_lab(pal)[None, :, :]
    d = np.linalg.norm(lab_px - lab_pal, axis=-1)
    idx = d.argmin(axis=1)
    return np.array(names)[idx], d.min(axis=1)


# --------------------------------------------------------------------------- #
# проверки
# --------------------------------------------------------------------------- #
@dataclass
class Report:
    path: str
    ok: bool = True
    checks: list[dict] = field(default_factory=list)

    def add(self, name: str, ok: bool | None, detail: str, level: str = "error") -> None:
        if ok is False and level == "error":
            self.ok = False
        self.checks.append({"check": name, "ok": ok, "detail": detail, "level": level})


def silhouette(alpha: np.ndarray) -> np.ndarray:
    return alpha > 24


def count_holes(mask: np.ndarray) -> int:
    """Число замкнутых «дырок» внутри силуэта (транзитивность, scipy-free)."""
    h, w = mask.shape
    seen = np.zeros((h, w), bool)
    stack: list[tuple[int, int]] = []

    def push(y, x):
        if 0 <= y < h and 0 <= x < w and not mask[y, x] and not seen[y, x]:
            seen[y, x] = True
            stack.append((y, x))

    for x in range(w):
        push(0, x)
        push(h - 1, x)
    for y in range(h):
        push(y, 0)
        push(y, w - 1)

    while stack:
        y, x = stack.pop()
        push(y - 1, x)
        push(y + 1, x)
        push(y, x - 1)
        push(y, x + 1)

    # остались только внутренние пустоты: считаем компоненты
    holes = 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] or seen[y, x]:
                continue
            holes += 1
            st = [(y, x)]
            seen[y, x] = True
            while st:
                cy, cx = st.pop()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        st.append((ny, nx))
    return holes


def green_fringe(rgb: np.ndarray, mask: np.ndarray) -> float:
    """Доля пикселей по краю силуэта с заметным зелёным сдвигом."""
    if not mask.any():
        return 0.0
    # край = пиксели силуэта, у которых есть прозрачный сосед
    inner = mask.copy()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        inner &= np.roll(mask, (dy, dx), axis=(0, 1))
    edge = mask & ~inner
    if edge.sum() < 10:
        edge = mask
    px = rgb[edge].astype(np.float32)
    dom = px[:, 1] - np.maximum(px[:, 0], px[:, 2])
    return float((dom > 18).mean())


def _runs(row: np.ndarray, min_frac: float = 0.06) -> int:
    """Число «существенных» отрезков силуэта в строке.

    Мелкие отрезки (прядь волос, блик, зазор у капюшона) не считаются:
    берём только отрезки шире ``min_frac`` от ширины силуэта в этой строке.
    """
    r = row.astype(np.int8)
    total = int(r.sum())
    if total == 0:
        return 0
    min_w = max(4, total * min_frac)
    runs, cur = [], 0
    for v in r:
        if v:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return sum(1 for x in runs if x >= min_w)


def limb_profile(mask: np.ndarray) -> dict:
    """Оценка числа конечностей по «отрезкам» силуэта.

    Логика: руки разведены → в зоне корпуса строка распадается на 3 отрезка
    (рука / корпус / рука); стоя → в зоне ног 2 отрезка. Считаем медиану по
    строкам (устойчиво к выбросам) и ловим только грубые аномалии.
    """
    h, w = mask.shape
    ys = np.nonzero(mask.sum(axis=1))[0]
    if len(ys) < 10:
        return {"ok": False, "reason": "пустой силуэт"}
    top, bottom = int(ys[0]), int(ys[-1])
    height = max(bottom - top, 1)

    if h / max(w, 1) < 1.8:
        return {"ok": True, "portrait": True, "legs": None, "arms": None, "height": height}

    def median_runs(y0: float, y1: float) -> int:
        vals = []
        for y in range(int(top + y0 * height), int(top + y1 * height) + 1, 4):
            if 0 <= y < h and mask[y].any():
                vals.append(_runs(mask[y]))
        if not vals:
            return 0
        vals.sort()
        return vals[len(vals) // 2]

    legs = median_runs(0.74, 1.0)
    arms = median_runs(0.32, 0.60)
    return {"ok": True, "portrait": False, "legs": legs, "arms": arms, "height": height}


STYLE_THRESHOLDS = {
    # плоский 2D: жёсткие пороги по кластерам цвета, широкая палитра
    "flat": {"clusters": 22, "dE": 14.0},
    # объёмный painterly: мягкие тени и подсветка дают много оттенков
    "volumetric": {"clusters": 48, "dE": 18.0},
}


def check_asset(path: str, min_h: int = 600, max_clusters: int | None = None,
                palette_dE: float | None = None, style: str = "volumetric") -> Report:
    th = STYLE_THRESHOLDS.get(style, STYLE_THRESHOLDS["volumetric"])
    max_clusters = th["clusters"] if max_clusters is None else max_clusters
    palette_dE = th["dE"] if palette_dE is None else palette_dE
    rep = Report(path=os.path.basename(path))
    img = Image.open(path)
    w, h = img.size
    rep.add("разрешение", h >= min_h, f"{w}×{h} (порог по высоте {min_h})")

    has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba)
    rgb = arr[..., :3]
    alpha = arr[..., 3]
    filled = (alpha > 24).mean()
    rep.add("прозрачность", has_alpha or filled < 0.995,
            "альфа есть" if has_alpha else f"альфы нет (заполнение {filled:.0%})")

    is_scene = (not has_alpha) or filled > 0.995
    mask = silhouette(alpha) if not is_scene else np.ones((h, w), bool)
    if mask.sum() < 100:
        rep.add("силуэт", False, "силуэт почти пуст")
        return rep

    if is_scene:
        # фон/сцена: проверяем только техничность и палитру
        px = rgb[mask]
        step = max(1, len(px) // 20000)
        names, dE = nearest_palette(px[::step])
        rep.add("палитра", float(np.median(dE)) < 20.0,
                f"медианный ΔE={np.median(dE):.1f} (для сцен порог 20)", level="warn")
        q = rgba.convert("RGB").quantize(colors=64, method=Image.MEDIANCUT)
        clusters = len(q.getcolors())
        rep.add("перегруз деталями", clusters <= 60,
                f"{clusters} цветовых кластеров (для сцен порог 60)", level="warn")
        rep.add("тип ассета", None, "сцена/фон: проверка конечностей не применима",
                level="manual")
        return rep

    area = mask.sum() / (w * h)
    rep.add("площадь силуэта", 0.04 <= area <= 0.92,
            f"{area:.0%} кадра", level="warn")

    holes = count_holes(mask) if has_alpha else 0
    rep.add("дырки в силуэте", holes <= 2,
            f"замкнутых пустот: {holes}", level="warn")

    fringe = green_fringe(rgb, mask)
    rep.add("зелёный ореол", fringe < 0.08,
            f"{fringe:.1%} краевых пикселей с зелёным сдвигом")

    prof = limb_profile(mask)
    if not prof.get("ok"):
        rep.add("конечности (грубо)", False, prof.get("reason", "не посчитан"), level="warn")
    elif prof.get("portrait"):
        rep.add("конечности (грубо)", None, "портретный ассет: проверяется глазами",
                level="manual")
    else:
        legs, arms = prof["legs"], prof["arms"]
        ok = 1 <= legs <= 3 and 1 <= arms <= 4
        rep.add("конечности (грубо)", ok,
                f"медиана отрезков в строке: ноги {legs} (норма 1–3), "
                f"корпус {arms} (норма 1–4)")

    # палитра и «перегруз деталями»
    px = rgb[mask]
    if len(px) > 2000:
        step = max(1, len(px) // 20000)
        px = px[::step]
    names, dE = nearest_palette(px)
    rep.add("палитра", float(np.median(dE)) < palette_dE,
            f"медианный ΔE={np.median(dE):.1f}, выбросов(>25): {(dE > 25).mean():.1%}",
            level="warn")

    q = rgba.convert("RGB").quantize(colors=32, method=Image.MEDIANCUT)
    clusters = len(q.getcolors())
    rep.add("перегруз деталями", clusters <= max_clusters,
            f"{clusters} цветовых кластеров (порог {max_clusters})", level="warn")

    rep.add("текст в кадре", None, "проверяется глазами (шлюз 2 чек-листа)", level="manual")
    rep.add("число рук/ног", None, "проверяется глазами по кадру", level="manual")
    return rep


# --------------------------------------------------------------------------- #
# отчёт
# --------------------------------------------------------------------------- #
def collect(paths: list[str]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            for ext in ("*.png", "*.webp", "*.jpg"):
                out.extend(sorted(glob.glob(os.path.join(p, "**", ext), recursive=True)))
        elif os.path.exists(p):
            out.append(p)
    return out


def write_report(reports: list[Report], path: str) -> None:
    errors = sum(1 for r in reports for c in r.checks if c["ok"] is False and c["level"] == "error")
    warns = sum(1 for r in reports for c in r.checks if c["ok"] is False and c["level"] == "warn")
    lines = ["# QA-отчёт по ассетам", "",
             f"Проверено файлов: **{len(reports)}** · ошибок: **{errors}** · "
             f"предупреждений: **{warns}**", "",
             "Автопроверки не заменяют просмотр: пункты с пометкой *manual* "
             "смотрите глазами по чек-листу `docs/06-QA-CHECKLIST.md`.", ""]
    for r in reports:
        status = "✅" if r.ok else "❌"
        lines.append(f"## {status} {r.path}")
        lines.append("")
        lines.append("| Проверка | Статус | Детали |")
        lines.append("|----------|--------|--------|")
        for c in r.checks:
            if c["ok"] is True:
                mark = "✅"
            elif c["ok"] is False:
                mark = "❌" if c["level"] == "error" else "⚠️"
            else:
                mark = "👁"
            lines.append(f"| {c['check']} | {mark} | {c['detail']} |")
        lines.append("")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", nargs="*", default=None)
    ap.add_argument("--min-h", type=int, default=600)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--report", default=os.path.join(SEARCH, "out", "qa-report.md"))
    args = ap.parse_args()

    paths = args.assets or [os.path.join(SEARCH, "style-tests"),
                            os.path.join(SEARCH, "characters"),
                            os.path.join(SEARCH, "assets")]
    files = [f for f in collect(paths) if not os.path.basename(f).startswith("_")]
    if not files:
        print("нет файлов для проверки")
        return

    reports = [check_asset(f, min_h=args.min_h) for f in files]
    if args.json:
        print(json.dumps([{"path": r.path, "ok": r.ok, "checks": r.checks}
                          for r in reports], ensure_ascii=False, indent=2))
        return

    write_report(reports, args.report)
    bad = [r.path for r in reports if not r.ok]
    print(f"✓ отчёт: {os.path.relpath(args.report, ROOT)}")
    print(f"  файлов: {len(reports)}, с ошибками: {len(bad)}")
    for p in bad:
        print("   ❌", p)


if __name__ == "__main__":
    main()
