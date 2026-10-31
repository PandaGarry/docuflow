"""Проверка якорей: поставить все кадры на общую линию пола и общий центр.

    python studio/tools/anchor_check.py dad

Если библиотека снята ровно, у всех кадров совпадают: линия подошв, высота
макушки, высота таза. Разъезд виден сразу — это и есть «плывёт масштаб».

Результат: studio/out/<персонаж>-anchor-check.png
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

from PIL import Image, ImageDraw

import characters as ch
import poselib as pl

ROOT = HERE.parents[2]


def build(char_key: str, cell: int = 560, per_row: int = 7) -> Path:
    lib = pl.Library(char_key)
    frames = []
    for spec in ch.POSES:
        fr = lib.pose(spec.key)
        if fr is not None:
            frames.append((spec.key, fr))
    if not frames:
        raise SystemExit("нет кадров")

    # Масштаб ОДИН на весь персонаж (по мастеру), а не по кадру. Иначе
    # присевший и бегущий автоматически «раздуваются» до одного роста, и
    # ошибка съёмки прячется. Один масштаб — сразу видно, где персонаж
    # нарисован мельче, чем в мастере.
    master = lib.pose("front")
    ref_h = master.anchor["height_px"] if master else frames[0][1].anchor["height_px"]
    scale = (cell * 0.82) / ref_h

    rows = [frames[i:i + per_row] for i in range(0, len(frames), per_row)]
    W = per_row * cell
    H = len(rows) * (cell + 26)
    sheet = Image.new("RGB", (W, H), (250, 248, 244))
    draw = ImageDraw.Draw(sheet)

    for r, row in enumerate(rows):
        y0 = r * (cell + 26) + 20
        ground = y0 + cell - 20                     # общая линия пола
        draw.line([(0, ground), (W, ground)], fill=(210, 205, 198), width=1)
        for c, (key, fr) in enumerate(row):
            img = fr.img
            w = max(int(img.width * scale), 1)
            h = max(int(img.height * scale), 1)
            small = img.resize((w, h), Image.LANCZOS)
            foot_x = fr.anchor.get("foot_cx", img.width / 2) * scale
            cx = c * cell + cell // 2
            x = int(cx - foot_x)
            y = int(ground - h)
            sheet.paste(small, (x, y), small)
            draw.text((c * cell + 8, y0 - 16), key, fill=(90, 88, 84))
    out = ROOT / "studio" / "out" / f"{char_key}-anchor-check.png"
    sheet.save(out)
    return out


if __name__ == "__main__":
    print(build(sys.argv[1] if len(sys.argv) > 1 else "dad"))
