"""Цикл ходьбы из РИСОВАННЫХ фаз, без нарезки и без кроссфейдов.

    python studio/tools/drawing_cycle.py dad walk

Почему так
----------
Риг из одной картинки (нарезка кусков и «заплатки») на сгибах давал ступеньку:
за шарниром нет «мяса». Деформация целого полотна тоже не спасла — на сильном
повороте силуэт разъезжается. Поэтому ноги теперь РИСУЮТСЯ по фазам, а скрипт
только выравнивает фазы между собой:

* масштаб и сдвиг каждой фазы подбираются по ГОЛОВЕ (она не меняется от позы),
  поэтому комплекция и рост не гуляют от кадра к кадру;
* нижняя точка каждой фазы ставится на общий пол;
* кадры выкладываются «на двойках/тройках», без смешивания соседних фаз —
  так что рисунок не «плывёт», как при кроссфейде.

Фазы (в порядке ходьбы, near = ближняя к камере нога):

    a near вперёд, пятка  ·  b вес на near, far уходит назад
    c near вертикально, far вперёд  ·  d near назад, far вперёд в воздухе
    e far вперёд, пятка  ·  f вес на far, near назад
    g far вертикально, near вперёд  ·  h far назад, near вперёд в воздухе

Вторая половина (e–h) — зеркало первой по смыслу: ноги меняются ролями.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
import cv2
from PIL import Image

import cutout

ROOT = HERE.parents[2]
POSES = ROOT / "studio/2p5d/dad/poses"
OUT = ROOT / "studio/out"

# фазы по порядку цикла и число кадров на каждую («тройки» при 24 к/с = 1.0 с)
ORDER = list("abcdefgh")
HOLD = {"walk": 3, "run": 2}
FPS = 24


def cut(name: str) -> Image.Image:
    """Имя фазы: «a» = walk-a.png, иначе имя файла целиком."""
    f = POSES / (f"{name}.png" if len(name) > 1 else f"walk-{name}.png")
    img = Image.open(f).convert("RGB")
    return cutout.key_green(img)


def body_box(img: Image.Image) -> tuple[int, int, int, int]:
    a = np.asarray(img)[..., 3] > 40
    ys, xs = np.where(a)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def head_anchor(img: Image.Image) -> tuple[float, int, int]:
    """Точка привязки: (масштаб, x центра головы, y макушки).

    Замеры по сгенерированным фазам: макушка у всех на y=17–18, ширины головы
    отличаются на 1–2 px — то есть масштаб у всех один, а плавает только низ
    (насколько высоко нарисована нога). Поэтому и привязываемся к ГОЛОВЕ, иначе
    на ходьбе начнёт «прыгать» сам персонаж.
    """
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
    return (w1 + w2) / 2, int(round((cx1 + cx2) / 2)), y0


def prepare(names: list[str]) -> tuple[list[Image.Image], dict]:
    imgs = {n: cut(n) for n in names}
    anchors = {n: head_anchor(imgs[n]) for n in names}
    ref = anchors[names[0]]
    frames = []
    pose_info = {}
    for n in names:
        sc, cx, top = anchors[n]
        # масштаб — ТОЛЬКО по голове: комплекция и размер головы не должны
        # гулять. Вертикаль выравниваем потом по полу (низ фигуры), из-за
        # этого макушка немного качается — это и есть bob при ходьбе.
        scale = ref[0] / sc if sc else 1.0
        im = imgs[n]
        if abs(scale - 1.0) > 0.002:
            im = im.resize((int(round(im.width * scale)),
                            int(round(im.height * scale))), Image.LANCZOS)
            cx, top = int(cx * scale), int(top * scale)
        a = np.asarray(im)[..., 3] > 40
        bottom = int(np.where(a)[0].max())
        pose_info[n] = {"scale": round(scale, 3), "head_x": cx,
                        "head_y": top, "bottom": bottom}
        frames.append((im, cx, top, bottom))

    # Общая рамка. Голова — по центру кадра по X, стопы — по полу.
    pad = 24
    left = max(cx for im, cx, top, b in frames) + pad
    right = max(im.width - cx for im, cx, top, b in frames) + pad
    W = int(left + right)
    floor = max(b for *_, b in frames) + pad
    # Привязка «низ ровно на пол» давала рывок до 30 px между фазами: рисунки
    # нарисованы с разной высотой тела, и это не ритм, а разнобой. Сглаживаем
    # вертикальный сдвиг по кругу цикла и разрешаем стопе чуть висеть, но
    # НИКОГДА не проваливаться ниже пола.
    exact = [floor - b for *_, b in frames]
    n = len(exact)
    smooth = []
    for i in range(n):
        win = [exact[(i + k) % n] for k in (-1, 0, 1)]
        smooth.append(float(np.median(win)))
    use = [min(sm, ex) for sm, ex in zip(smooth, exact)]
    out = []
    for (im, cx, top, b), dy in zip(frames, use):
        c = Image.new("RGBA", (W, int(floor + pad)), (0, 0, 0, 0))
        c.paste(im, (int(left - cx), int(dy)))
        out.append(c)
    return out, pose_info


def build(what: str = "walk", names: list[str] | None = None
          ) -> tuple[list[Image.Image], int]:
    names = names or ORDER
    frames, _ = prepare(names)
    hold = HOLD.get(what, 3)
    seq = []
    for f in frames:
        for _ in range(hold):
            seq.append(f)
    return seq, FPS


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    what = sys.argv[2] if len(sys.argv) > 2 else "walk"
    names = None
    if len(sys.argv) > 3:
        names = []
        for chunk in sys.argv[3:]:
            names.extend([p for p in chunk.split(",") if p])
    frames, fps = build(what, names)
    # поля под кадр фиксированного размера
    w = max(f.width for f in frames)
    h = max(f.height for f in frames)
    w -= w % 2            # libx264 требует чётные размеры
    h -= h % 2
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{key}-{what}.mp4"
    import imageio.v2 as imageio
    wr = imageio.get_writer(out, fps=fps, quality=9, macro_block_size=1)
    bg = Image.new("RGBA", (w, h), (238, 235, 229, 255))   # нейтральный фон
    for f in frames:
        c = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        c.paste(f, ((w - f.width) // 2, (h - f.height) // 2))
        wr.append_data(np.asarray(
            Image.alpha_composite(bg, c).convert("RGB")))
    wr.close()
    print(f"{out}  кадров {len(frames)}, fps {fps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
