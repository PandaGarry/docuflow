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


def compose(frames: list[pl.Frame], fps: int, speed: float,
            lift: dict | None = None, keys: list[str] | None = None,
            foot_lock: bool = False, stride: float = 0.34,
            per_frame=None) -> list[np.ndarray]:
    """Кадр за кадром.

    `foot_lock` — попытка «запереть» опорную стопу. По умолчанию ВЫКЛЮЧЕНО:
    опорная стопа в кадрах генератора стоит где попало (179 px в контакте,
    78 px в фазе down на одном цикле), и привязка к её якорю даёт рывки —
    персонаж прыгает по кадру. Стабильная посадка по центру корпуса
    (`body_cx`) выглядит ровно: корпус стоит, фон едет.
    """
    lift = lift or {}
    by_key = {f.key.split(":")[-1]: f for f in frames}
    keys = keys or [list(by_key)[0]] * len(frames)
    # Масштаб ПО КАДРУ, а не один на клип.
    #
    # Кадры нарезаны с листов и нарисованы разной высоты (540 и 552 px при
    # одном персонаже). При общей шкале это даёт «дыхание» размера: фигура на
    # 2 % раздувается и сдувается между фазами — со стороны выглядит как
    # пульсация, а не как бег.
    # Нормировка по ширине головы не годится: в фазе «down» рука перекрывает
    # голову, и замер даёт +16 %. Поэтому приводим каждый кадр к одному росту
    # на экране; покачивание добавляет отдельная кривая `bob`.
    base_scale = BODY_H / max(f.anchor.get("height_px", f.img.height) for f in frames)
    out = []
    for i, key in enumerate(keys):
        fr = by_key.get(key) or by_key[list(by_key)[0]]
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
        scale = BODY_H / fr.anchor.get("height_px", fr.img.height)
        w, h = int(img.width * scale), int(img.height * scale)
        small = img.resize((w, h), Image.LANCZOS)
        # ставим по центру корпуса: взмах руки и вынос ноги не сдвигают
        # персонажа в кадре (раньше центрировали по стопам — «плавало»)
        foot_y = fr.anchor.get("foot_y", img.height) * scale
        cx = W * 0.42
        rise = 0.0
        if per_frame is not None:
            rise = per_frame[i] * scale / (BODY_H / 700)
        n = len(keys)
        if foot_lock and fr.anchor.get("plant_cx") is not None:
            half = max(n // 2, 1)
            t = i % half                       # позиция внутри половины цикла
            # цель: опорная стопа уезжает назад на один шаг за половину
            span = stride * BODY_H
            target = cx + 0.5 * span - (span * t / max(half - 1, 1))
            x = int(target - fr.anchor["plant_cx"] * scale)
        else:
            body_x = fr.anchor.get("body_cx", img.width / 2) * scale
            x = int(cx - body_x)
        y = int(GROUND - foot_y - rise)

        # мягкая тень привязывает к полу; в полёте она слабеет и отрывается
        sw = int(img.width * scale * 0.55)
        sh_h = 16
        shadow = Image.new("L", (sw, sh_h), 0)
        ImageDraw.Draw(shadow).ellipse([0, 0, sw, sh_h], fill=90 if not rise else 40)
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        canvas.paste((168, 163, 154), (int(cx - sw / 2), GROUND - sh_h // 2 - 4), shadow)

        # маска — явно канал альфы: с RGBA-маской PIL кладёт картинку целиком
        canvas.paste(small, (x, y), small.getchannel("A"))
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

    # покадровая лента: фаза повторяется столько раз, сколько задано в тайминге
    seq = timeline(spec)
    half = len(seq) // 2
    # скорость земли: за полуцикл пол должен уехать ровно на длину шага —
    # иначе стопа скользит по полу
    speed = spec["step"] * BODY_H / max(half, 1)
    imgs = compose(frames, spec["fps"], speed, spec.get("lift"), seq,
                   per_frame=[spec["bob"].get(phase_of(k), 0.0) for k in seq])
    imgs = imgs * 2
    out = out or (ROOT / "studio" / "out" / f"{char_key}-{cycle}.mp4")
    w = imageio.get_writer(out, fps=spec["fps"], quality=8, macro_block_size=8)
    for im in imgs:
        w.append_data(im)
    w.close()
    print(f"{out}  кадров {len(imgs)}, полуцикл {half}, "
          f"земля {speed * spec['fps']:.0f} px/с")
    return out


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    cyc = sys.argv[2] if len(sys.argv) > 2 else "walk"
    print(main(key, cyc))
