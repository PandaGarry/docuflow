"""Сборка клипа из библиотеки поз: проверка циклов и первый шаг движка.

    python studio/tools/cycle_preview.py dad walk
    python studio/tools/cycle_preview.py dad run --out studio/out/dad-run.mp4

Как собирается кадр:
- персонаж масштабируется один раз по росту мастера (не по кадру!);
- подошвы ставятся на общую линию пола, центр стопы — в заданную точку;
- фон прокручивается, чтобы движение читалось (персонаж шагает на месте).

Это ещё не движок сцены, а его нижний слой: проверка, что библиотека даёт
живой цикл и что якоря держат персонажа на полу.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image, ImageDraw

import poselib as pl

ROOT = HERE.parents[2]

CYCLES = {
    "walk": {
        "keys": ["walk-contact", "walk-down", "walk-passing", "walk-up",
                 "walk-contact-R", "walk-down-R", "walk-passing-R", "walk-up-R"],
        "fps": 12,
        "speed": 26.0,      # px/кадр прокрутки фона: шаг ~2.2 кадра на ключ
    },
    "run": {
        "keys": ["run-contact", "run-contact-R", "run-passing", "run-passing-R"],
        "fps": 12,
        "speed": 60.0,
    },
}

W, H = 720, 900          # кадр 4:5, под вертикаль 9:16 обрежем в монтаже
GROUND = H - 130
BODY_H = 0.72 * H


def ground(fig: Image.Image, x_center: float, y_ground: float) -> tuple[Image.Image, float]:
    """Вписать фигуру по высоте мастера и поставить подошвой на линию пола."""
    return fig, 0.0


def compose(frames: list[pl.Frame], fps: int, speed: float) -> list[np.ndarray]:
    master = frames[0]
    # один масштаб на весь клип
    scale = BODY_H / max(f.anchor.get("height_px", f.img.height) for f in frames)
    out = []
    for i, fr in enumerate(frames):
        canvas = Image.new("RGB", (W, H), (236, 234, 229))
        d = ImageDraw.Draw(canvas)
        # пол и «полосы» — чтобы читалась скорость
        d.rectangle([0, GROUND, W, H], fill=(214, 210, 202))
        d.line([(0, GROUND), (W, GROUND)], fill=(150, 146, 138), width=3)
        shift = (i * speed) % 120
        for x in range(-120, W + 120, 120):
            d.line([(x + shift, GROUND + 4), (x + shift - 40, GROUND + 60)],
                   fill=(196, 191, 182), width=4)
        # персонаж
        img = fr.img
        w, h = int(img.width * scale), int(img.height * scale)
        small = img.resize((w, h), Image.LANCZOS)
        foot_x = fr.anchor.get("foot_cx", img.width / 2) * scale
        foot_y = fr.anchor.get("foot_y", img.height) * scale
        cx = W * 0.42
        canvas.paste(small, (int(cx - foot_x), int(GROUND - foot_y)), small)
        out.append(np.asarray(canvas))
    return out


def main(char_key: str, cycle: str, out: Path | None = None) -> Path:
    import imageio.v2 as imageio

    spec = CYCLES[cycle]
    lib = pl.Library(char_key)
    frames = []
    for k in spec["keys"]:
        fr = lib.pose(k)
        if fr is None:
            raise SystemExit(f"нет кадра {k}")
        frames.append(fr)
    imgs = compose(frames, spec["fps"], spec["speed"])
    # два круга подряд, чтобы видеть стык
    imgs = imgs * 2
    out = out or (ROOT / "studio" / "out" / f"{char_key}-{cycle}.mp4")
    w = imageio.get_writer(out, fps=spec["fps"], quality=8, macro_block_size=8)
    for im in imgs:
        w.append_data(im)
    w.close()
    return out


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    cyc = sys.argv[2] if len(sys.argv) > 2 else "walk"
    print(main(key, cyc))
