"""Проверка рига: лист поз + короткий клип.

    python studio/tools/pose_sheet.py            # лист + клип по умолчанию
    python studio/tools/pose_sheet.py --clip     # только клип

Кладёт `studio/out/dad-poses.png` и `studio/out/dad-wave.mp4`.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

from PIL import Image

import cutout as C

MASTER = HERE.parents[1] / "2p5d" / "dad" / "master-front-v2.png"
OUT = HERE.parents[1] / "out"

POSES = {
    "покой": {},
    "ладонь вперёд": {"upperarm.R": -0.90, "head": -0.02},
    "рука в сторону": {"upperarm.R": -1.35, "head": 0.05},
    "шаг": {"thigh.L": -0.35, "shin.L": 0.28, "thigh.R": 0.30,
            "shin.R": -0.08, "chest": -0.05, "upperarm.L": 0.18,
            "upperarm.R": -0.15},
    "наклон головы": {"head": 0.20, "neck": 0.10, "chest": -0.04},
}


def sheet() -> Path:
    puppet = C.load_master(str(MASTER))
    cw = (puppet.size[0] + 420, puppet.size[1] + 120)
    off = ((cw[0] - puppet.size[0]) // 2, (cw[1] - puppet.size[1]) // 2)
    tiles = [puppet.render(p, canvas=cw, offset=off) for p in POSES.values()]
    width = sum(t.width for t in tiles)
    height = max(t.height for t in tiles)
    out = Image.new("RGBA", (width, height), (250, 248, 244, 255))
    x = 0
    for t in tiles:
        out.alpha_composite(t, (x, 0))
        x += t.width
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "dad-poses.png"
    out.convert("RGB").save(path)
    return path


def clip(frames: int = 30, fps: int = 15) -> Path:
    """Взмах правой рукой: 2 секунды, с мягким входом/выходом."""
    import imageio.v2 as imageio

    puppet = C.load_master(str(MASTER))
    # x264 требует чётные размеры кадра
    cw = ((puppet.size[0] + 421) // 2 * 2, (puppet.size[1] + 121) // 2 * 2)
    off = ((cw[0] - puppet.size[0]) // 2, (cw[1] - puppet.size[1]) // 2)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "dad-wave.mp4"
    writer = imageio.get_writer(path, fps=fps, quality=8,
                                macro_block_size=1)
    for i in range(frames):
        t = i / (frames - 1)
        # 0…1…0 по косинусу — без рывка на концах
        s = 0.5 - 0.5 * math.cos(2 * math.pi * t)
        pose = {
            "upperarm.R": -1.45 * s,
            "head": 0.05 * s,
            "chest": -0.02 * s,
            "shin.L": 0.05 * s,
        }
        img = puppet.render(pose, canvas=cw, offset=off)
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        bg.alpha_composite(img)
        writer.append_data(__import__("numpy").asarray(bg.convert("RGB")))
    writer.close()
    return path


if __name__ == "__main__":
    if "--clip" not in sys.argv:
        print("лист:", sheet())
    print("клип:", clip())
