"""Ассет-пайплайн: от мастер-референса героя до готового набора слоёв.

Задача модуля — убрать «каждый раз новое лицо». Идея в трёх правилах:

1. **Master-файлы неизменяемы.** Для каждого героя есть ровно два мастера:
   `master/turnaround.png` (три вида в ряд) и `master/face.png` (портрет).
   Всё остальное — производные, которые генерируются с мастерами в референсах.
2. **Реестр вместо памяти.** `characters/registry.json` хранит для каждого
   героя мастер-файлы, отпечаток внешности и список производных ассетов —
   с промптом и ключом (поза × эмоция × ракурс × комплект одежды).
   Ключ позволяет понять, какие ассеты устарели после правки персонажа.
3. **Всё проверяется.** После нарезки/вырезки ассет автоматически идёт в
   `qa.check_asset`; красный вердикт = ассет не попадает в рендер.

Команды:
  python studio/engine/artgen.py slice      # нарезать turnaround на виды
  python studio/engine/artgen.py cut        # chroma key + despill для всех PNG
  python studio/engine/artgen.py sheet      # contact-sheet производных ассетов
  python studio/engine/artgen.py registry   # пересобрать characters/registry.json
  python studio/engine/artgen.py verify     # проверка целостности + что устарело
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

# Набор заготовок: (папка/имя, поза, эмоция, ракурс).
# Промпты и ключи собирает kit.py — единый источник правды для арта и куклы.
DEFAULT_DERIVATIVES = [
    ("pose/idle", "idle", "calm", "full"),
    ("pose/wave", "wave", "joy", "full"),
    ("pose/point", "point", "smirk", "full"),
    ("pose/surprise", "surprise", "surprise", "full"),
    ("pose/think", "think", "think", "full"),
    ("pose/carry", "carry", "focused", "full"),
    ("pose/slump", "slump", "tired", "full"),
    ("pose/walk", "walk", "calm", "full"),
    ("face/talk_A", "idle", "talk_a", "close"),
    ("face/talk_O", "idle", "talk_o", "close"),
    ("face/blink", "idle", "blink", "close"),
    ("face/joy", "idle", "joy", "close"),
]


def build_registry() -> dict:
    """Собрать characters/registry.json из character.json + библиотек."""
    import kit

    reg: dict = {"style": "B-volumetric", "schema": 3,
                 "generated_by": "artgen.py", "characters": {}}
    for char_id in kit.list_characters():
        spec = kit.load_character(char_id)
        char_dir = kit.character_dir(char_id)
        entry = {
            "name": char_id,
            "label": spec.get("label", char_id),
            "desc": kit.character_text(spec),
            "schema": spec.get("schema"),
            "height_heads": spec.get("height_heads"),
            "outfit_default": (spec.get("wardrobe") or {}).get("default"),
            "outfits": sorted((spec.get("wardrobe") or {}).get("sets", {})),
            "hair": spec.get("hair"),
            "master": {
                "turnaround": _rel(os.path.join(char_dir, "master", "turnaround.png")),
                "face": _rel(os.path.join(char_dir, "master", "face.png")),
            },
            "identity_fingerprint": kit.spec_fingerprint(spec),
            "master_fingerprint": kit.master_fingerprint(char_id),
            "derivatives": [],
        }
        for asset, pose, expr, camera in DEFAULT_DERIVATIVES:
            path = os.path.join(char_dir, f"{asset}.png")
            entry["derivatives"].append({
                "asset": asset,
                "file": _rel(path),
                "status": "ready" if os.path.exists(path) else "todo",
                "pose": pose,
                "expression": expr,
                "camera": camera,
                "key": kit.asset_key(spec, pose=pose, expression=expr, camera=camera,
                                     set_name=entry["outfit_default"]),
                "prompt": kit.build_prompt(spec, pose=pose, expression=expr, camera=camera,
                                           set_name=entry["outfit_default"]),
            })
        reg["characters"][char_id] = entry
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
    import kit
    reg_path = os.path.join(CHARACTERS, "registry.json")
    if not os.path.exists(reg_path):
        cmd_registry()
    problems = kit.validate_all()
    for problem in problems:
        print("  ✗", problem)
    problems = len(problems)
    for item in kit.stale_assets():
        print(f"  ⚠️ {item['character']}/{item['asset']}: {item['reason']}")
    with open(reg_path, encoding="utf-8") as f:
        reg = json.load(f)
    for name, c in reg["characters"].items():
        fp = _fingerprint(os.path.join(STUDIO, c["master"]["turnaround"]))
        if fp != c.get("master_fingerprint"):
            print(f"  ⚠️ {name}: мастер изменился после сборки реестра — пересоберите registry")
            problems += 1
        for d in c["derivatives"]:
            if d["status"] == "ready":
                asset_path = os.path.join(STUDIO, d["file"])
                if not os.path.exists(asset_path):
                    print(f"  ❌ {name}/{d['asset']}: файла нет, хотя статус ready")
                    problems += 1
                    continue
                rep = qa.check_asset(asset_path, min_h=300)
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
