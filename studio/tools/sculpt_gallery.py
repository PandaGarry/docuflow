"""Витрина SDF-ядра: несколько ракурсов и поз одним листом.

    python studio/tools/sculpt_gallery.py --out studio/out/dad-p3-gallery.png

Геометрия в позе покоя собирается один раз; позы (шаг, взмах) пересобираются,
потому что поле зависит от суставов.
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

import animation as AN      # noqa: E402
import body3d as B          # noqa: E402
import character as CH      # noqa: E402
import render3d as R3       # noqa: E402
import sculpt as SC         # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cell", type=float, default=0.007)
    ap.add_argument("--pose-cell", type=float, default=0.010)
    ap.add_argument("--size", type=int, nargs=2, default=[560, 780])
    ap.add_argument("--ss", type=int, default=3)
    ap.add_argument("--out", default="studio/out/dad-p3-gallery.png")
    args = ap.parse_args()

    p = B.Proportions()
    ch = CH.Character(p)
    H = p.height
    cy = H * 0.50
    dist = (H * 1.25) / (2 * np.tan(np.radians(15)))
    w, h = args.size
    bg = (0.97, 0.95, 0.92)

    t0 = time.time()
    rest = SC.sculpt_character(ch, cell=args.cell)
    print(f"поза покоя: {sum(len(m.tris) for m in rest)} трёх, {time.time() - t0:.1f} с")

    walk = AN.Walk(ch.skel, cycle=0.92, stride=0.46, step_height=0.13,
                   bob=0.028, sway=0.024, arm_swing=0.46)
    wave = AN.Wave(ch.skel, cycle=3.0)

    panels = []

    def shot(name, parts, cam, size=None):
        t = time.time()
        img = R3.render(parts, size or (w, h), cam, ss=args.ss, background=bg)
        panels.append(Image.fromarray(img))
        print(f"  {name}: {time.time() - t:.1f} с")

    # полный рост вписываем по высоте: расстояние от роста, а не «на глаз»
    full_dist = (H * 1.06) / (2 * np.tan(np.radians(14)))
    fovea = (p.neck_y + 0.52 * p.head_frac) * H
    shot("три четверти", rest, R3.Camera(eye=(full_dist * 0.50, cy, full_dist * 0.87),
                                         target=(0, cy, 0), fov=28))
    shot("лицо", rest, R3.Camera(eye=(0.24, fovea + 0.010, 0.90),
                                 target=(0, fovea, 0), fov=24))
    shot("плечо и рукав", rest, R3.Camera(eye=(0.80, 1.40, 1.05),
                                          target=(0.10, 1.24, 0), fov=32))

    t = time.time()
    walk_parts = SC.sculpt_character(ch, walk.pose_at(0.23), cell=args.pose_cell)
    print(f"  шаг: геометрия {time.time() - t:.1f} с")
    shot("шаг", walk_parts, R3.Camera(eye=(full_dist * 0.62, 1.05, full_dist * 0.72),
                                      target=(0, 0.95, 0), fov=30))

    t = time.time()
    wave_parts = SC.sculpt_character(ch, wave.pose_at(0.35), cell=args.pose_cell)
    print(f"  взмах: геометрия {time.time() - t:.1f} с")
    shot("взмах", wave_parts, R3.Camera(eye=(full_dist * 0.48, cy, full_dist * 0.88),
                                        target=(0, cy, 0), fov=28))

    cols = 3
    rows = int(np.ceil(len(panels) / cols))
    sheet = Image.new("RGB", (w * cols, h * rows), tuple(int(c * 255) for c in bg))
    for i, im in enumerate(panels):
        sheet.paste(im, (w * (i % cols), h * (i // cols)))
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(f"готово: {out}  всего {time.time() - t0:.1f} с")


if __name__ == "__main__":
    main()
