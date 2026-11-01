"""Один персонаж на всех кадрах? Проверка силуэта и цвета по библиотеке.

    python studio/tools/identity_qa.py dad

Зачем: генератор рисует «того же персонажа» по-разному — где-то он полнее,
где-то поджарый и «накачанный», где-то уже в плечах. Глазами это видно, но
выборочно; на 100+ кадрах нужен замер, иначе брак уходит в монтаж.

Что меряем
----------
1. **Пропорции силуэта.** Кадр вырезается по альфе, нормируется по высоте и
   по нему снимается ширина на 10 фиксированных относительных высотах
   (плечи, грудь, талия, бёдра, колени...). Это подпись фигуры: полный человек
   и накачанный дают разные подписи при одинаковом росте.
2. **Заполнение рамки** (площадь силуэта / площадь рамки) — общая «массивность».
3. **Цвет одежды** — средний цвет свитера и джинсов. Ловит смену одежды,
   которая не должна происходить сама.

Группы сравнения: портреты ракурса, позы ракурса, и внутри поз — шаг, бег,
стойки, жесты. Сравнивать позу с шагом бессмысленно: у них разный силуэт
по построению.

Честное ограничение этого замера: ширина силуэта зависит от позы. В цикле
шага расставленные ноги дают +20–30 % ширины на уровне бёдер, и такие кадры
попадут в «пересъёмку» ложно. Поэтому цифры — грубый фильтр, а решение по
кадру принимается глазами на полосе кадров, собранной в один рост
(`studio/out/dad-consistency-*.png`). Для портретов замер надёжен: там поза
почти не меняется, и вылеты настоящие.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import characters as ch
import cutout

ROOT = HERE.parents[2]
LEVELS = np.linspace(0.10, 0.85, 10)


def signature(img: Image.Image, *, portrait: bool = False) -> dict | None:
    """Подпись силуэта: ширины по высоте, заполнение, цвета одежды."""
    a = np.asarray(img.convert("RGBA"))
    al = a[..., 3] > 40
    ys, xs = np.where(al)
    if not len(ys):
        return None
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    if portrait:
        y1 = y0 + int((y1 - y0) * 0.5)
    h = max(1, y1 - y0)
    w = max(1, x1 - x0)
    widths = []
    for lv in LEVELS:
        row = int(y0 + lv * h)
        cols = np.where(al[row, x0:x1 + 1])[0]
        widths.append(len(cols) / h)
    area = al[y0:y1, x0:x1 + 1].mean()
    rgb = a[..., :3].astype(int)[y0:y1, x0:x1 + 1]
    sub = al[y0:y1, x0:x1 + 1]
    # свитер: светлый, почти нейтральный; джинсы: тёмно-синие
    sw = sub & (rgb.min(2) > 120) & (rgb.max(2) - rgb.min(2) < 40)
    jn = sub & (rgb[..., 2] > rgb[..., 0] + 10) & (rgb[..., 2] < 140)
    return {
        "widths": np.array(widths),
        "area": float(area),
        "aspect": float(w / h),
        "sweater": rgb[sw].mean(0) if sw.sum() > 50 else None,
        "jeans": rgb[jn].mean(0) if jn.sum() > 50 else None,
    }


def median_sig(sigs: list[dict]) -> dict:
    """Опорная подпись группы: медиана по кадрам (устойчива к выбросам)."""
    return {
        "widths": np.median(np.stack([s["widths"] for s in sigs]), axis=0),
        "area": float(np.median([s["area"] for s in sigs])),
        "aspect": float(np.median([s["aspect"] for s in sigs])),
    }


def compare(a: dict, b: dict) -> dict:
    """Отклонения кадра от опорной подписи группы, в долях."""
    dw = np.abs(a["widths"] - b["widths"]) / np.maximum(0.06, b["widths"])
    dw = np.where(b["widths"] > 0.05, dw, 0.0)
    return {
        "width_max": float(dw.max()),
        "width_at": float(LEVELS[int(dw.argmax())]),
        "area": float(abs(a["area"] / max(1e-6, b["area"]) - 1)),
        "aspect": float(abs(a["aspect"] / max(1e-6, b["aspect"]) - 1)),
    }


def groups(char):
    """Группы сравнения: сравнивать можно только похожее с похожим."""
    out = []
    for kind in ("poses", "emotions", "visemes"):
        for view in ("front", "three-quarter", "side"):
            if kind == "poses":
                continue
            d = char.dir / kind / view
            if d.exists():
                out.append((f"{kind}/{view}", sorted(d.glob("*.png")), True))
    # позы: ракурс берём из каталога поз
    by_view: dict[str, list[Path]] = {}
    for p in sorted((char.dir / "poses").glob("*.png")):
        spec = ch.POSE_BY_KEY.get(p.stem)
        view = "side" if spec and "side" in spec.view else (
            "three-quarter" if spec and "three-quarter" in spec.view else "front")
        by_view.setdefault(view, []).append(p)
    for view, files in by_view.items():
        buckets: dict[str, list[Path]] = {}
        for p in files:
            stem = p.stem
            key = "run" if stem.startswith("run") else (
                "walk" if stem.startswith("walk") else (
                    "idle" if stem.startswith("idle") else "action"))
            buckets.setdefault(key, []).append(p)
        for key, group in buckets.items():
            out.append((f"poses/{view}/{key}", group, False))
    return out


def run(char_key: str, limit: float = 0.20) -> int:
    char = {"dad": ch.DAD, "mom": ch.MOM, "son": ch.SON}[char_key]
    total_bad = 0
    for name, files, portrait in groups(char):
        sigs, keys = [], []
        for p in files:
            sig = signature(cutout.key_green(Image.open(p).convert("RGB")),
                            portrait=portrait)
            if sig:
                sigs.append(sig)
                keys.append(p.stem)
        if len(sigs) < 3:
            continue
        ref = median_sig(sigs)
        sweater = [s["sweater"] for s in sigs if s.get("sweater") is not None]
        ref_sw = np.median(np.stack(sweater), axis=0) if sweater else None
        bad = []
        for key, sig in zip(keys, sigs):
            c = compare(sig, ref)
            c["color"] = 0.0
            if ref_sw is not None and sig.get("sweater") is not None:
                c["color"] = float(np.abs(sig["sweater"] - ref_sw).max())
            if c["width_max"] > limit or c["area"] > 0.16 or c["aspect"] > 0.16 \
                    or c["color"] > 26:
                bad.append((key, c))
        print(f"\n{name}: {len(sigs)} кадров, к пересъёмке {len(bad)}")
        for key, c in sorted(bad, key=lambda r: -max(r[1]["width_max"], r[1]["area"])):
            print(f"  ✗ {key:14s} ширина +{c['width_max']:.0%} "
                  f"на {c['width_at']:.0%} высоты · масса {c['area']:+.0%} · "
                  f"кадр {c['aspect']:+.0%} · цвет свитера Δ{c['color']:.0f}")
        total_bad += len(bad)
    print(f"\nвсего к пересъёмке: {total_bad}")
    return total_bad


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("char", nargs="?", default="dad")
    a = ap.parse_args()
    raise SystemExit(1 if run(a.char) else 0)
