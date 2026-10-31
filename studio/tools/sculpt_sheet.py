"""Лист персонажа из SDF-ядра: оборот на 360°, профиль, лицо крупным планом.

    python studio/tools/sculpt_sheet.py --out studio/out/dad-p3-sheet.png

Отдельный инструмент, потому что SDF-сборка заметно дороже трубной: считаем
один раз, рендерим несколько ракурсов с одной геометрией.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "engine"))

import body3d as B      # noqa: E402
import character as CH  # noqa: E402
import render3d as R3   # noqa: E402
import sculpt as SC     # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=float, default=0.007)
    ap.add_argument("--size", type=int, nargs=2, default=[460, 820])
    ap.add_argument("--ss", type=int, default=3)
    ap.add_argument("--out", default="studio/out/dad-p3-sheet.png")
    ap.add_argument("--face", action="store_true",
                    help="вместо оборота — крупный план лица")
    args = ap.parse_args()

    p = B.Proportions()
    ch = CH.Character(p)
    t0 = time.time()
    parts = SC.sculpt_character(ch, cell=args.cell)
    dt = time.time() - t0
    tris = sum(len(m.tris) for m in parts)
    print(f"геометрия: {len(parts)} мешей, {tris} треугольников, {dt:.1f} с")

    H = p.height
    cy = H * 0.50
    dist = (H * 1.25) / (2 * np.tan(np.radians(15)))
    if args.face:
        cy = (p.neck_y + 0.55 * p.head_frac) * H
        cam = R3.Camera(eye=(0.30, cy + 0.015, 0.95), target=(0, cy, 0),
                        fov=26)
        w, h = args.size
        img = R3.render(parts, (w * 2, h), cam, ss=4,
                        background=(0.97, 0.95, 0.92))
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(img).save(out)
        print(f"готово: {out}")
        return

    views = [
        ("front", R3.Camera(eye=(0, cy, dist), target=(0, cy, 0), fov=30)),
        ("three_quarter", R3.Camera(eye=(dist * 0.55, cy, dist * 0.85),
                                    target=(0, cy, 0), fov=30)),
        ("side", R3.Camera(eye=(dist, cy, dist * 0.10), target=(0, cy, 0), fov=30)),
        ("back", R3.Camera(eye=(0, cy, -dist), target=(0, cy, 0), fov=30)),
    ]
    w, h = args.size
    sheet = Image.new("RGB", (w * len(views), h))
    t1 = time.time()
    for i, (name, cam) in enumerate(views):
        img = R3.render(parts, (w, h), cam, ss=args.ss, background=(0.97, 0.95, 0.92))
        sheet.paste(Image.fromarray(img), (w * i, 0))
        print(f"  {name}: {time.time() - t1:.1f} с")
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"готово: {out}")


if __name__ == "__main__":
    main()
