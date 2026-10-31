"""Ходьба и бег из 2D-рига: каждая нога двигается по-настоящему.

    python studio/tools/stride_cycle.py dad walk
    python studio/tools/stride_cycle.py dad run

Почему бот, а не кадры библиотеки
---------------------------------
Восемь нарисованных фаз шага давали «меняющиеся ноги»: каждая фаза нарисована
отдельно, ноги в них разной формы и разного масштаба, а между фазами ноги
просто перепрыгивали. Руки читались нормально (они двигаются заметно), ноги —
нет.

Здесь рисунок ОДИН (`master-side-spread.png`, ноги разведены, каждая видна
целиком). Из него вырезаны: дальнее бедро/голень/стопа, ближнее
бедро/голень/стопа, торс, голова, рука. Каждая часть поворачивается вокруг
своего шарнира, поэтому нога не меняет форму — она поворачивается. Кадров
столько, сколько нужно, движение гладкое по построению.

Что делает этот скрипт:
1. считает углы шарниров по кривым (синусы + сглаживание, без «дёрганья»);
2. через FK ищет самую низкую точку стопы и ставит её на линию пола —
   поэтому нога не проваливается под пол и не парит;
3. двигает фон со скоростью опорной ноги: стопа на опоре едет назад ровно
   так же, как уезжает пол, — иначе получается «бег на месте на льду»;
4. пишет mp4 на 24 кадрах в секунду, «на двойках»: каждый посчитанный кадр
   держится два кадра видео.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import cutout
import rig2d

ROOT = HERE.parents[2]
W, H = 720, 900
GROUND = H - 110
FPS = 24
BG = (238, 235, 229)
FLOOR = (216, 212, 204)

# Кривые. Знаки: отрицательный hip выносит бедро вперёд (ось Y вниз).
CYCLES = {
    "walk": dict(
        hip=17.0,          # размах бедра
        knee_swing=36.0,   # сгиб колена в переносе
        knee_stance=6.0,   # подседание на опоре
        ankle=10.0,        # работа стопы
        arm=9.0, elbow=7.0,
        lean=2.0,
        frames=12, cycle_s=1.0,
        bob=1.0,
    ),
    "run": dict(
        hip=32.0, knee_swing=86.0, knee_stance=18.0, ankle=16.0,
        arm=14.0, elbow=24.0, lean=10.0,
        frames=10, cycle_s=0.62,
        bob=4.0,      # подъём в полёте, px
    ),
}


def ease(t: float) -> float:
    return t * t * (3 - 2 * t)


def pose(kind: str, t: float) -> dict[str, float]:
    """Углы шарниров на фазе t∈[0,1)."""
    p = CYCLES[kind]
    th = 2 * math.pi * t
    s, c = math.sin(th), math.cos(th)

    hip_near = -p["hip"] * s
    hip_far = p["hip"] * s

    def knee(cos_th: float) -> float:
        swing = max(0.0, cos_th) ** 1.4
        stance = max(0.0, -cos_th) ** 2.0
        return p["knee_stance"] + p["knee_swing"] * swing + 5.0 * stance

    knee_near, knee_far = knee(c), knee(-c)

    def ankle(hip: float, kn: float, stance: float) -> float:
        """Стопа.

        На опоре подошва должна лежать плоско: суммарный поворот цепочки
        бедро+колено+стопа гасим полностью, оставляя чуть-чуть «пятка раньше
        носка». В переносе стопа не доворачивается до конца — носок смотрит
        вниз, как в жизни. Раньше стопа просто качалась синусом и в опоре
        стояла на носке — в ролике читалось как «плывущая» нога.
        """
        flat = -(hip + kn)
        return flat * (0.92 if stance else 0.45) + 4.0 * (1.0 - stance)

    return {
        # корпус: наклон вперёд, плечи и голова гасят наклон
        "spine": -p["lean"],
        "chest": p["lean"] * 0.4,
        "neck": p["lean"] * 0.5 + 1.2 * math.cos(2 * th),
        # ноги
        "hip_near": hip_near,
        "knee_near": knee_near,
        "ankle_near": ankle(hip_near, knee_near, 1.0 if c < 0 else 0.0),
        "hip_far": hip_far,
        "knee_far": knee_far,
        "ankle_far": ankle(hip_far, knee_far, 1.0 if c > 0 else 0.0),
        # рука: в противофазе к ближней ноге
        "shoulder": p["arm"] * s,
        "elbow": -(p["elbow"] + 5.0 * max(0.0, s)),
    }


def _contact_width(fig: Image.Image) -> int:
    """Ширина следа: сколько пикселей подошвы лежит на самой нижней линии."""
    a = np.asarray(fig)[..., 3] > 40
    ys = np.where(a.any(1))[0]
    if not len(ys):
        return 0
    row = np.where(a[ys.max() - 2])[0]
    if not len(row):
        return 0
    segs, start, prev = [], row[0], row[0]
    for x in row[1:]:
        if x - prev > 2:
            segs.append(prev - start)
            start = x
        prev = x
    segs.append(row[-1] - start)
    return int(max(segs))


def flatten_stance(pup, ang: dict, size, lo: int = -42, hi: int = 42,
                   step: int = 6) -> dict:
    """Довернуть стопу опорной ноги так, чтобы подошва легла плоско.

    Геометрическое правило «сумма поворотов = 0» не работает: у ботинка в
    рисунке своя форма, а самая низкая точка может принадлежать другой ноге.
    Поэтому угол подбирается по факту — по ширине следа на самой нижней
    строке кадра. Так подошва всегда лежит на полу, а не стоит на носке.
    """
    best, best_w = None, -1
    for a in range(lo, hi + 1, step):
        trial = dict(ang)
        # подбираем стопу той ноги, которая сейчас ниже
        trial["ankle_near"] = a
        w = _contact_width(pup.render(trial, canvas=size))
        if w > best_w:
            best, best_w = a, w
    out = dict(ang)
    out["ankle_near"] = best
    return out


def build(kind: str) -> tuple[list[Image.Image], float]:
    src = cutout.key_green(
        Image.open(ROOT / "studio/2p5d/dad/master-side-spread.png").convert("RGB"))
    spec = rig2d.load_rig("dad", "stride")
    pup = rig2d.Puppet(src, spec)
    p = CYCLES[kind]
    n = p["frames"]
    scale = 0.80 * H / src.height
    cw, ch = int(src.width * scale), int(src.height * scale)

    frames: list[Image.Image] = []
    soles: list[float] = []
    hip_x: list[float] = []
    for i in range(n):
        ang = pose(kind, i / n)
        ang = flatten_stance(pup, ang, src.size)
        fig = pup.render(ang, canvas=src.size)
        # кадр рига → масштаб сцены
        small = fig.resize((cw, ch), Image.LANCZOS)
        a = np.asarray(small)[..., 3] > 40
        ys = np.where(a.any(1))[0]
        soles.append(float(ys.max() if len(ys) else ch))
        frames.append(small)
        hip = pup._totals(ang)["hip"][0]
        hip_x.append(float(hip[0] * cw))

    # Скорость: опорная стопа уезжает назад относительно корпуса. Берём
    # медиану по опорной половине цикла — это и есть скорость шага.
    sole_shift = []
    for i in range(n):
        j = (i + 1) % n
        sole_shift.append(hip_x[j] - hip_x[i])
    stance = [abs(v) for k, v in enumerate(sole_shift)
              if math.cos(2 * math.pi * k / n) < 0]
    step_px = float(np.median(stance)) * 2 if stance else 8.0
    speed = step_px / (p["cycle_s"] / n)

    out_frames = []
    for i, fig in enumerate(frames):
        canvas = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, GROUND, W, H], fill=FLOOR)
        d.line([(0, GROUND), (W, GROUND)], fill=(150, 146, 138), width=3)
        shift = int(i * speed * p["cycle_s"] / n) % 140
        for x in range(-140, W + 140, 140):
            d.line([(x + shift, GROUND + 6), (x + shift - 46, GROUND + 64)],
                   fill=(198, 193, 184), width=4)

        # ставим по подошве: низ содержимого = линия пола
        y = GROUND - int(round(soles[i]))
        x = int(W * 0.45 - fig.width * 0.5)
        # подъём на беге: в переносе тело выше (полёт)
        if kind == "run":
            # полёт: тело выше всего в переносе (дважды за цикл)
            lift = p["bob"] * max(0.0, math.cos(4 * math.pi * i / n))
            y -= int(round(lift))
        canvas.paste(fig, (x, y), fig.getchannel("A"))
        out_frames.append(canvas)

    # «на двойках»: каждый кадр держим два кадра видео
    doubled = [f for f in out_frames for _ in (0, 1)]
    return doubled, FPS


def main() -> int:
    import imageio.v2 as imageio
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    kind = sys.argv[2] if len(sys.argv) > 2 else "walk"
    frames, fps = build(kind)
    out = ROOT / "studio" / "out" / f"{key}-{kind}.mp4"
    w = imageio.get_writer(out, fps=fps, quality=9, macro_block_size=1)
    for f in frames:
        w.append_data(np.asarray(f))
    w.close()
    print(f"{out}  кадров {len(frames)}, fps {fps}, "
          f"цикл {CYCLES[kind]['cycle_s']} с")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
