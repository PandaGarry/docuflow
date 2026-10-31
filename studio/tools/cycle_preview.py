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
from PIL import Image, ImageDraw, ImageFilter

import inbetween as ib
import poselib as pl

ROOT = HERE.parents[2]

# Тайминг и скорость больше НЕ задаются «на глаз».
#
# Скорость земли обязана совпадать со скоростью ног, иначе персонаж
# «едет на скутере»: стопа стоит на месте, а пол под ней уезжает. Поэтому:
#   скорость = длина шага / длительность полуцикла,
# где длина шага берётся из самих кадров (расстояние между стопами в контакте,
# в долях роста), а длительность — из таблицы тайминга.
#
# `timing` — сколько кадров держится каждая фаза. Держим по-мультяшному:
# контакт дольше (вес и удар), пронос короче (он быстрый).
CYCLES = {
    "walk": {
        "keys": ["walk-contact", "walk-down", "walk-passing", "walk-up",
                 "walk-contact-R", "walk-down-R", "walk-passing-R", "walk-up-R"],
        "fps": 12,
        "timing": {"contact": 2, "down": 2, "passing": 1, "up": 1},
        "step": 0.26,        # длина шага из замеров кадров, в долях роста
        "bob": {"contact": 0.0, "down": -8.0, "passing": 4.0, "up": 6.0},
    },
    "run": {
        "keys": ["run-contact", "run-down", "run-passing",
                 "run-contact-R", "run-down-R", "run-passing-R"],
        "fps": 12,
        "timing": {"contact": 2, "down": 1, "passing": 2},
        "step": 0.40,
        # в беге фаза проноса — это полёт: тело выше всего, тень отрывается
        "bob": {"contact": 0.0, "down": -10.0, "passing": 26.0},
    },
}


def phase_of(key: str) -> str:
    """«run-contact-R» → «contact». Нужно, чтобы тайминг не дублировать."""
    base = key.lower().split("-")
    for ph in ("contact", "down", "passing", "up"):
        if ph in base:
            return ph
    return base[-1]


def timeline(spec: dict) -> list[str]:
    """Развернуть фазы в покадровый список с учётом держаний."""
    out: list[str] = []
    for key in spec["keys"]:
        out += [key] * spec["timing"].get(phase_of(key), 1)
    return out

W, H = 720, 900          # кадр 4:5, под вертикаль 9:16 обрежем в монтаже
GROUND = H - 130
BODY_H = 0.72 * H


def ground(fig: Image.Image, x_center: float, y_ground: float) -> tuple[Image.Image, float]:
    """Вписать фигуру по высоте мастера и поставить подошвой на линию пола."""
    return fig, 0.0


def align_sprites(frames: list[pl.Frame]) -> tuple[list[Image.Image], tuple[int, int]]:
    """Положить кадры на общий холст по якорям: стопа на низу, корпус по центру.

    Нужно для промежуточных кадров: оптический поток считает смещение по
    картинке, и если один кадр шире другого на 4 px, «движение» уйдёт в
    горизонтальный сдвиг всего тела вместо движения ног.
    """
    placed = []
    for fr in frames:
        img = fr.img
        scale = BODY_H / fr.anchor.get("height_px", img.height)
        size = (max(int(img.width * scale), 2), max(int(img.height * scale), 2))
        small = img.convert("RGBA").resize(size, Image.LANCZOS)
        placed.append((small,
                       fr.anchor.get("body_cx", img.width / 2) * scale,
                       fr.anchor.get("foot_y", img.height) * scale))
    w = int(max(p[0].width for p in placed)) + 8
    h = int(max(p[0].height for p in placed)) + 8
    out = []
    for small, bx, by in placed:
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        canvas.alpha_composite(small, (int(w / 2 - bx), int(h - 4 - by)))
        out.append(canvas)
    return out, (w, h)


def sprite_chain(sprites: list[Image.Image], seq: list[str], keys: list[str],
                 sub: int = 1) -> list[tuple[Image.Image, float]]:
    """Лента спрайтов с промежуточными кадрами и покадровым bob.

    `seq` — покадровый список ключей (с держаниями), `keys` — порядок ключей
    в цикле. Промежуточные кадры вставляются только МЕЖДУ РАЗНЫМИ ключами:
    внутри держания кадр не меняется, там движение замирает по замыслу.
    """
    by_key = {k: sprites[i] for i, k in enumerate(keys)}
    bob_by_key = {k: 0.0 for k in keys}
    out: list[tuple[Image.Image, float]] = []
    for i, key in enumerate(seq):
        nxt = seq[(i + 1) % len(seq)]
        cur_img = by_key[key]
        out.append((cur_img, bob_by_key[key]))
        if nxt != key and sub > 0:
            for k in range(1, sub + 1):
                out.append((ib.blend(cur_img, by_key[nxt], k / (sub + 1)),
                            bob_by_key[key]))
    return out


def compose(sprites: list[Image.Image], bob: list[float], fps: int,
            speed: float) -> list[np.ndarray]:
    """Собрать клип: прокрутка пола + спрайт персонажа в кадре.

    Спрайты уже приведены к одному росту и стоят на общей линии пола, поэтому
    здесь остаются только прокрутка фона, покачивание и тень. Никакого
    масштабирования по кадру: фигура всегда одного размера.
    """
    out = []
    for i, sp in enumerate(sprites):
        canvas = Image.new("RGB", (W, H), (236, 234, 229))
        d = ImageDraw.Draw(canvas)
        # пол и «полосы» — чтобы читалась скорость
        d.rectangle([0, GROUND, W, H], fill=(214, 210, 202))
        d.line([(0, GROUND), (W, GROUND)], fill=(150, 146, 138), width=3)
        shift = (i * speed) % 120
        for x in range(-120, W + 120, 120):
            d.line([(x + shift, GROUND + 4), (x + shift - 40, GROUND + 60)],
                   fill=(196, 191, 182), width=4)

        cx = W * 0.42
        rise = bob[i]
        sw = int(sp.width * 0.55)
        sh_h = 16
        shadow = Image.new("L", (sw, sh_h), 0)
        ImageDraw.Draw(shadow).ellipse([0, 0, sw, sh_h],
                                       fill=40 if rise > 2 else 90)
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        canvas.paste((168, 163, 154),
                     (int(cx - sw / 2), GROUND - sh_h // 2 - 4), shadow)

        x = int(cx - sp.width / 2)
        y = int(GROUND - sp.height + 4 - rise)
        canvas.paste(sp, (x, y), sp.getchannel("A"))
        out.append(np.asarray(canvas))
    return out


def main(char_key: str, cycle: str, out: Path | None = None,
         sub: int | None = None) -> Path:
    import imageio.v2 as imageio

    spec = CYCLES[cycle]
    sub = spec.get("sub", 1) if sub is None else sub
    lib = pl.Library(char_key)
    frames = []
    for k in spec["keys"]:
        fr = lib.pose(k)
        if fr is None:
            raise SystemExit(f"нет кадра {k}")
        frames.append(fr)

    sprites, _ = align_sprites(frames)
    seq = timeline(spec)
    # скорость земли: за полуцикл пол должен уехать ровно на длину шага
    # ...и считать её надо по числу кадров ПОСЛЕ вставки промежуточных,
    # иначе при переходе с «двоек» на «единицы» земля поедет вдвое быстрее


    # лента: ключи с держаниями + промежуточные кадры между разными ключами
    by_key = {k: sprites[i] for i, k in enumerate(spec["keys"])}
    ribbon: list[tuple[Image.Image, float]] = []
    for i, key in enumerate(seq):
        nxt = seq[(i + 1) % len(seq)]
        ribbon.append((by_key[key], spec["bob"].get(phase_of(key), 0.0)))
        if nxt != key and sub > 0:
            for k in range(1, sub + 1):
                t = k / (sub + 1)
                b0 = spec["bob"].get(phase_of(key), 0.0)
                b1 = spec["bob"].get(phase_of(nxt), 0.0)
                ribbon.append((ib.blend(by_key[key], by_key[nxt], t),
                               b0 * (1 - t) + b1 * t))

    # на каждую промежуточную вставку частота кадров растёт так, чтобы
    # длительность цикла не менялась (это «на двойках» → «на единицах»)
    # частота считается от ДЛИТЕЛЬНОСТИ: промежуточные кадры добавляются только
    # между разными ключами (внутри держаний кадр не меняется), поэтому просто
    # умножить fps на (sub+1) нельзя — цикл станет короче и «ускорится»
    duration = len(seq) / spec["fps"]
    fps = len(ribbon) / duration
    # скорость земли — по числу кадров ленты, а не по числу ключей:
    # иначе при вставке промежуточных пол поедет в (sub+1) раз быстрее
    speed = spec["step"] * BODY_H / max(len(ribbon) // 2, 1)
    imgs = compose([r[0] for r in ribbon], [r[1] for r in ribbon], fps, speed)
    imgs = imgs * 2
    out = out or (ROOT / "studio" / "out" / f"{char_key}-{cycle}.mp4")
    w = imageio.get_writer(out, fps=fps, quality=8, macro_block_size=8)
    for im in imgs:
        w.append_data(im)
    w.close()
    print(f"{out}  кадров {len(imgs)}, цикл {len(ribbon)}, fps {fps}, "
          f"земля {speed * fps:.0f} px/с, промежуточных {len(ribbon) - len(seq)}")
    return out


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    cyc = sys.argv[2] if len(sys.argv) > 2 else "walk"
    print(main(key, cyc))
