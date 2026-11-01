"""Проверка лица: моргание, взгляд, речь из базы + слоёв.

    python studio/tools/face_preview.py dad
    python studio/tools/face_preview.py dad side

Собирает studio/out/dad-face.mp4: нейтрально → моргание → фраза из виземов →
смайл, всё на статичной базе. Это проверка слоёв, а не сцены.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import facefx
import poselib as pl

ROOT = HERE.parents[2]
FPS = 12


VIEWS = ("front", "three-quarter", "side")
# Профиль требует переноса челюсти, фронт и 3/4 — только изменившихся пикселей.
MODE = {"front": "diff", "three-quarter": "diff", "side": "jaw"}


def frames_for(char_key: str, view: str = "front") -> list[np.ndarray]:
    lib = pl.Library(char_key)
    lm = lib.face(view)
    if not lm:
        raise SystemExit(f"нет face.json у {char_key}: разметь лицо по сетке")
    base = lib.emotion("neutral", view).img
    size = base.size

    def fit(img: Image.Image) -> Image.Image:
        """Все слои приводим к кадру базы: у эмоций разные размеры картинки."""
        if img.size == size:
            return img
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.alpha_composite(img, (0, 0))
        return canvas

    ec = lib.emotion("eyes-closed", view)
    hp = lib.emotion("happy", view)
    closed = fit(ec.img) if ec else base
    smile = fit(hp.img) if hp else base
    mode = MODE.get(view, "diff")

    out: list[Image.Image] = []

    def add(img: Image.Image, n: int = 1):
        for _ in range(n):
            out.append(img)

    # 0.5 с нейтрально, с дыханием
    for i in range(6):
        add(facefx.breathe(base, i / FPS))
    # моргание: 3 кадра вниз, 3 вверх
    for a in (0.35, 0.75, 1.0, 0.75, 0.35):
        add(facefx.blink(base, closed, lm=lm, amount=a))
    # фраза «мама мыла» — формы M A M A
    for v in ("M", "A", "M", "A", "O", "U"):
        fr = lib.viseme(v, view)
        if fr is None:
            continue
        add(facefx.morph_mouth(base, fit(fr.img), lm=lm, mode=mode), 1)
        add(base, 1)
    # смайл держим
    add(smile, 6)
    # взгляд в сторону
    add(facefx.look(base, lm, dx=0.35), 4)
    add(base, 3)
    # фон: прозрачность в mp4 превращается в чёрное, поэтому кладём на светлый
    bg = Image.new("RGBA", size, (250, 248, 244, 255))
    flats = []
    for im in out:
        flat = bg.copy()
        flat.alpha_composite(im if im.size == size else fit(im))
        flats.append(np.asarray(flat.convert("RGB")))
    return flats


def main(char_key: str = "dad", view: str = "front") -> Path:
    import imageio.v2 as imageio

    frames = frames_for(char_key, view)
    suffix = "" if view == "front" else f"-{view}"
    out = ROOT / "studio" / "out" / f"{char_key}-face{suffix}.mp4"
    w = imageio.get_writer(out, fps=FPS, quality=8, macro_block_size=2)
    for f in frames:
        w.append_data(f)
    w.close()
    return out


if __name__ == "__main__":
    print(main(sys.argv[1] if len(sys.argv) > 1 else "dad",
               sys.argv[2] if len(sys.argv) > 2 else "front"))
