"""Цикл ходьбы из 12 рисованных ключей, «на двойках» — как в сериальной 2D-анимации.

    python studio/tools/drawing_walk.py dad        # 6 секунд (6 циклов)
    python studio/tools/drawing_walk.py dad 3      # 3 цикла

Почему именно так
-----------------
* 12 рисунков на цикл, каждый держится 2 кадра при 24 к/с → 24 кадра = 1.0 с.
  Это стандарт «на двойках»: «Симпсоны», «Футурама», «Гриффины»,
  «Гравити Фолз» и вообще телевизионная 2D-анимация. Учебники (Richard
  Williams, «The Animator's Survival Kit») дают для естественной ходьбы
  ровно 12 кадров на шаг / 24 на цикл.
* Промежуточные кадры НЕ считаются оптическим потоком: между contact и down
  меняется, какая нога впереди, и поток даёт «вторую ногу» призраком.
  В сериальной анимации in-between просто рисуют — здесь он и есть отдельный
  ключ (12 штук). Поэтому между кадрами нет ни перепрыгивания, ни плывуна.

Раскладка цикла (24 кадра, contact на 1 и 13):

    кадр 1  contact  near вперёд, far назад        (w3-01)
    кадр 3  breakdown после contact                (w3-02)
    кадр 5  down, тело внизу                       (w3-03)
    кадр 7  подъём к passing                       (w3-04)
    кадр 9  passing, near стоит                    (w3-05)
    кадр 11 up, near толкается, far в воздухе      (w3-06)
    кадр 13 contact  far вперёд, near назад        (w3-07)
    ...     зеркало второй половины                (w3-08…12)

Руки строго в противофазе ногам: нога вперёд — одноимённая рука назад.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import cutout

ROOT = HERE.parents[2]
POSES = ROOT / "studio/2p5d/dad/poses"
OUT = ROOT / "studio/out"
KEYS = [f"w3-{i:02d}" for i in range(1, 13)]
HOLD = 2          # «на двойках»
FPS = 24


def cut(name: str) -> Image.Image:
    return cutout.key_green(Image.open(POSES / f"{name}.png").convert("RGB"))


def body_box(img: Image.Image) -> tuple[int, int, int, int]:
    a = np.asarray(img)[..., 3] > 40
    ys, xs = np.where(a)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def head_anchor(img: Image.Image) -> tuple[float, int, int, int]:
    """(ширина головы, x центра головы, y макушки, y низа фигуры)."""
    x0, y0, x1, y1 = body_box(img)
    a = np.asarray(img)[..., 3] > 40

    def width_at(f: float) -> tuple[int, float]:
        row = y0 + int((y1 - y0) * f)
        xs = np.where(a[row])[0]
        if len(xs) == 0:
            return 0, (x0 + x1) / 2
        return int(xs.max() - xs.min()), float((xs.min() + xs.max()) / 2)

    w1, cx1 = width_at(0.06)
    w2, cx2 = width_at(0.09)
    return (w1 + w2) / 2, int(round((cx1 + cx2) / 2)), y0, y1


def build(names: list[str] | None = None) -> tuple[list[Image.Image], list[dict]]:
    names = names or KEYS
    imgs = [cut(n) for n in names]
    anchors = [head_anchor(im) for im in imgs]
    ref_w = anchors[0][0]
    pad = 30
    left = max(a[1] for a in anchors) + pad
    right = max(im.width - a[1] for im, a in zip(imgs, anchors)) + pad
    W = int(left + right)
    floor = max(a[3] for a in anchors) + pad
    H = int(floor + pad)

    placed, bottoms, info = [], [], []
    for n, im, (hw, cx, top, bot) in zip(names, imgs, anchors):
        sc = ref_w / hw if hw else 1.0          # масштаб ТОЛЬКО по голове
        if abs(sc - 1) > 0.002:
            im = im.resize((int(round(im.width * sc)), int(round(im.height * sc))),
                           Image.LANCZOS)
            cx, bot = int(cx * sc), int(bot * sc)
        c = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        c.paste(im, (int(left - cx), 0))
        placed.append(c)
        bottoms.append(bot)
        info.append({"key": n, "scale": round(sc, 4)})

    # вертикаль: сглаженный по кругу цикл, но стопа НИКОГДА не ниже пола
    floor_y = max(bottoms)
    exact = [floor_y - b for b in bottoms]
    n = len(exact)
    out = []
    for i, c in enumerate(placed):
        win = [exact[(i + k) % n] for k in (-1, 0, 1)]
        dy = int(min(np.median(win), exact[i]))
        f = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        f.paste(c, (0, dy))
        out.append(f)
        info[i]["dy"] = dy
    return out, info


def sequence(frames: list[Image.Image]) -> list[Image.Image]:
    seq = []
    for f in frames:
        seq.extend([f] * HOLD)
    return seq


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    loops = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    frames, info = build()
    seq = sequence(frames)
    w, h = seq[0].size
    w -= w % 2
    h -= h % 2
    bg = Image.new("RGBA", (w, h), (238, 235, 229, 255))
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{key}-walk.mp4"
    import imageio.v2 as imageio
    wr = imageio.get_writer(out, fps=FPS, quality=9, macro_block_size=1)
    for _ in range(loops):
        for f in seq:
            wr.append_data(np.asarray(
                Image.alpha_composite(bg, f.resize((w, h))).convert("RGB")))
    wr.close()
    print(f"{out}  цикл {len(seq)} кадров @ {FPS} к/с, всего {len(seq) * loops}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
