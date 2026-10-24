"""Ассет-пайплайн: от мастер-референса героя до готового набора слоёв.

Задача модуля — убрать «каждый раз новое лицо». Идея в трёх правилах:

1. **Master-файлы неизменяемы.** Для каждого героя есть ровно два мастера:
   `master/turnaround.png` (три вида в ряд) и `master/face.png` (портрет).
   Всё остальное — производные, которые генерируются с мастерами в референсах.
2. **Реестр вместо памяти.** `characters/registry.json` хранит для каждого
   героя промпт-шаблон, мастер-файлы, палитру и список производных ассетов.
   Любой ассет можно пересобрать из реестра.
3. **Всё проверяется.** После нарезки/вырезки ассет автоматически идёт в
   `qa.check_asset`; красный вердикт = ассет не попадает в рендер.

Команды:
  python studio/engine/artgen.py slice      # нарезать turnaround на виды
  python studio/engine/artgen.py cut        # chroma key + despill для всех PNG
  python studio/engine/artgen.py sheet      # contact-sheet производных ассетов
  python studio/engine/artgen.py registry   # пересобрать characters/registry.json
  python studio/engine/artgen.py verify     # проверка целостности пайплайна
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
CHARACTERS = os.path.join(STUDIO, "characters")
sys.path.insert(0, HERE)

import qa  # noqa: E402

GREEN = np.array([0, 177, 64], np.float32)

# --------------------------------------------------------------------------- #
# хромакей с despill (общий для всех ассетов)
# --------------------------------------------------------------------------- #


def chroma_key(img: Image.Image, tol: float = 0.10, soft: float = 1.2) -> Image.Image:
    """Убрать плоский зелёный фон, погасить зелёный ореол на кромке."""
    rgb = np.asarray(img.convert("RGB"), np.float32)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    green_dom = g - np.maximum(r, b)
    mask = (green_dom > 255 * tol) & (g > 60)

    alpha = np.where(mask, 0.0, 1.0).astype(np.float32)
    a_img = Image.fromarray((alpha * 255).astype(np.uint8))
    a_img = a_img.filter(ImageFilter.MinFilter(3))
    a_img = a_img.filter(ImageFilter.GaussianBlur(soft))
    a = np.asarray(a_img, np.float32) / 255.0
    a = np.clip((a - 0.18) / 0.82, 0, 1)
    a = np.where(a > 0.55, 1.0, a)

    # despill: на кромке вычитаем зелёный сдвиг
    edge = (a > 0.02) & (a < 0.98)
    spill = np.clip(g - np.maximum(r, b), 0, 255)
    g_out = g.copy()
    g_out[edge] = np.clip(g[edge] - spill[edge] * 0.92, 0, 255)

    rgba = np.dstack([r, g_out, b, a * 255]).astype(np.uint8)
    out = Image.fromarray(rgba, "RGBA")
    bbox = out.split()[3].point(lambda v: 255 if v > 8 else 0).getbbox()
    return out.crop(bbox) if bbox else out


def trim(img: Image.Image) -> Image.Image:
    bbox = img.split()[3].point(lambda v: 255 if v > 8 else 0).getbbox()
    return img.crop(bbox) if bbox else img


# --------------------------------------------------------------------------- #
# нарезка turnaround на отдельные виды
# --------------------------------------------------------------------------- #


def slice_turnaround(path: str, views: tuple = ("front", "three_quarter", "side")) -> dict[str, Image.Image]:
    """Разделить лист на 3 вида по вертикальным «провалам» силуэта.

    Работает и на зелёном фоне (сначала вырезаем), и на прозрачном.
    """
    img = Image.open(path).convert("RGBA")
    # если фон зелёный — вырезаем, чтобы считать силуэт
    arr = np.asarray(img.convert("RGB"), np.int16)
    greenish = ((arr[..., 1] - np.maximum(arr[..., 0], arr[..., 2])) > 25).mean()
    if greenish > 0.15:
        img = chroma_key(img)
    else:
        img = trim(img)

    mask = np.asarray(img.split()[3]) > 24
    cols = mask.sum(axis=0)
    # столбцы без содержимого = границы между фигурами
    empty = cols < max(3, mask.shape[0] * 0.004)

    segments, start = [], None
    for i, e in enumerate(empty):
        if not e and start is None:
            start = i
        elif e and start is not None:
            if i - start > mask.shape[1] * 0.05:
                segments.append((start, i))
            start = None
    if start is not None:
        segments.append((start, len(empty)))

    # если сегментов больше трёх — склеиваем ближайшие по ширине к среднему
    if len(segments) > len(views):
        segments.sort(key=lambda s: s[1] - s[0], reverse=True)
        segments = sorted(segments[: len(views)])

    out: dict[str, Image.Image] = {}
    for name, (x0, x1) in zip(views, segments):
        part = img.crop((x0, 0, x1, img.height))
        out[name] = trim(part)
    return out


# --------------------------------------------------------------------------- #
# реестр персонажей
# --------------------------------------------------------------------------- #

BASE_PROMPT = (
    "Modern stylized volumetric 3D cartoon style (sculpted forms, soft painterly "
    "textures, appealing caricature proportions). Character: {desc}. "
    "POSE: {pose}. EXPRESSION: {expr}. CAMERA: {camera}. "
    "Exactly two arms, two legs, one head, two eyes, five fingers per open palm, "
    "no extra limbs, no duplicate features. Perfectly flat chroma key green "
    "background (#00B140), even studio lighting, no text, no watermark."
)

DEFAULT_DERIVATIVES = [
    # (имя, поза, эмоция, ракурс)
    ("pose/idle", "relaxed standing, arms hanging naturally", "neutral, calm", "full body, front"),
    ("pose/wave", "right arm raised and waving, left arm relaxed", "happy, wide smile", "full body, front"),
    ("pose/point", "right index finger pointing straight at the camera, other hand on hip",
     "cheeky confident smirk, one eyebrow raised", "full body, front"),
    ("pose/surprise", "both arms thrown up, leaning slightly back", "shocked, eyes wide, mouth open",
     "full body, front"),
    ("pose/think", "one hand on chin, head tilted", "curious, thinking", "full body, three-quarter"),
    ("pose/carry", "both arms forward carrying a box", "focused, slight strain", "full body, front"),
    ("face/talk_A", "head and shoulders", "talking, mouth open wide", "close-up, front"),
    ("face/talk_O", "head and shoulders", "talking, round mouth", "close-up, front"),
    ("face/blink", "head and shoulders", "eyes closed, relaxed", "close-up, front"),
]


def build_registry() -> dict:
    reg: dict = {"style": "B-volumetric", "version": 2, "characters": {}}
    for path in sorted(glob.glob(os.path.join(CHARACTERS, "*"))):
        if not os.path.isdir(path):
            continue
        name = os.path.basename(path)
        master_dir = os.path.join(path, "master")
        manifesto = os.path.join(path, "character.json")
        info = {}
        if os.path.exists(manifesto):
            with open(manifesto, encoding="utf-8") as f:
                info = json.load(f)
        entry = {
            "name": name,
            "label": info.get("label", name),
            "desc": info.get("desc", ""),
            "master": {
                "turnaround": _rel(os.path.join(master_dir, "turnaround.png")),
                "face": _rel(os.path.join(master_dir, "face.png")),
            },
            "derivatives": [],
        }
        for dname, pose, expr, cam in DEFAULT_DERIVATIVES:
            entry["derivatives"].append({
                "asset": dname,
                "file": _rel(os.path.join(path, f"{dname}.png")),
                "status": "ready" if os.path.exists(os.path.join(path, f"{dname}.png")) else "todo",
                "prompt": BASE_PROMPT.format(desc=entry["desc"], pose=pose, expr=expr, camera=cam),
            })
        entry["fingerprint"] = _fingerprint(os.path.join(master_dir, "turnaround.png"))
        reg["characters"][name] = entry
    return reg


def _rel(path: str) -> str:
    return os.path.relpath(path, STUDIO).replace(os.sep, "/")


def _fingerprint(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# команды
# --------------------------------------------------------------------------- #


def cmd_slice() -> None:
    ok = 0
    for path in sorted(glob.glob(os.path.join(CHARACTERS, "*", "master", "turnaround.png"))):
        char_dir = os.path.dirname(os.path.dirname(path))
        views_dir = os.path.join(char_dir, "views")
        os.makedirs(views_dir, exist_ok=True)
        parts = slice_turnaround(path)
        for name, img in parts.items():
            img.save(os.path.join(views_dir, f"{name}.png"))
            print(f"  {os.path.basename(char_dir)}/{name}.png  {img.size}")
        ok += 1
    print(f"✓ нарезано листов: {ok}")


def cmd_cut() -> None:
    for path in sorted(glob.glob(os.path.join(CHARACTERS, "**", "*.png"), recursive=True)):
        if "/master/" in path.replace(os.sep, "/") and "turnaround" in path:
            continue          # мастер-лист не трогаем, он источник истины
        img = Image.open(path)
        if img.mode == "RGBA" and np.asarray(img.split()[3]).min() == 0:
            continue          # уже вырезан
        out = chroma_key(img) if _is_green(img) else img.convert("RGBA")
        out.save(path)
        print(f"  вырезан {os.path.relpath(path, STUDIO)} {out.size}")


def _is_green(img: Image.Image) -> bool:
    a = np.asarray(img.convert("RGB"), np.int16)
    return ((a[..., 1] - np.maximum(a[..., 0], a[..., 2])) > 25).mean() > 0.15


def cmd_sheet() -> None:
    """Contact sheet всех производных ассетов — быстрый визуальный контроль."""
    for char_dir in sorted(glob.glob(os.path.join(CHARACTERS, "*"))):
        if not os.path.isdir(char_dir):
            continue
        files = sorted(glob.glob(os.path.join(char_dir, "**", "*.png"), recursive=True))
        if not files:
            continue
        cell = 260
        cols = 5
        rows = (len(files) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell + 20, rows * (cell + 26) + 20), (250, 246, 238))
        d = ImageDraw.Draw(sheet)
        for i, f in enumerate(files):
            im = Image.open(f).convert("RGBA")
            im.thumbnail((cell - 14, cell - 14), Image.LANCZOS)
            x = 10 + (i % cols) * cell + (cell - im.width) // 2
            y = 10 + (i // cols) * (cell + 26)
            sheet.paste(im, (x, y), im)
            d.text((10 + (i % cols) * cell + 4, y + cell - 18),
                   os.path.relpath(f, char_dir)[:34], fill=(60, 50, 45))
        out = os.path.join(char_dir, "_sheet.png")
        sheet.save(out)
        print("  →", os.path.relpath(out, STUDIO))


def cmd_registry() -> None:
    reg = build_registry()
    path = os.path.join(CHARACTERS, "registry.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    ready = sum(1 for c in reg["characters"].values() for d in c["derivatives"] if d["status"] == "ready")
    total = sum(len(c["derivatives"]) for c in reg["characters"].values())
    print(f"✓ {_rel(path)}: героев {len(reg['characters'])}, производных {ready}/{total}")


def cmd_verify() -> None:
    reg_path = os.path.join(CHARACTERS, "registry.json")
    if not os.path.exists(reg_path):
        cmd_registry()
    with open(reg_path, encoding="utf-8") as f:
        reg = json.load(f)
    problems = 0
    for name, c in reg["characters"].items():
        fp = _fingerprint(os.path.join(STUDIO, c["master"]["turnaround"]))
        if fp != c["fingerprint"]:
            print(f"  ⚠️ {name}: мастер изменился после сборки реестра — пересоберите registry")
            problems += 1
        for d in c["derivatives"]:
            if d["status"] == "ready":
                p = os.path.join(STUDIO, d["file"])
                rep = qa.check_asset(p, min_h=300)
                if not rep.ok:
                    print(f"  ❌ {name}/{d['asset']}: QA не пройден")
                    problems += 1
    print(f"✓ проверка завершена, проблем: {problems}")


def main() -> None:
    cmds = {"slice": cmd_slice, "cut": cmd_cut, "sheet": cmd_sheet,
            "registry": cmd_registry, "verify": cmd_verify}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        print("команды:", ", ".join(cmds))
        return
    cmds[sys.argv[1]]()


if __name__ == "__main__":
    main()
