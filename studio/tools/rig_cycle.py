"""Цикл шага/бега из рига: не кадры библиотеки, а непрерывные кривые.

    python studio/tools/rig_cycle.py dad walk
    python studio/tools/rig_cycle.py dad run --out studio/out/dad-run-rig.mp4

Чем отличается от `cycle_preview.py`
------------------------------------
`cycle_preview.py` берёт готовые кадры из библиотеки поз и добивает промежутки
оптическим потоком. Это дало рывки: поток растягивает картинку, силуэт
«раздувается», а на быстрых фазах нога вытягивается.

Здесь поза считается формулой от фазы. Углы в шарнирах меняются по синусам,
поэтому кадров может быть сколько угодно и любая частота — движение гладкое
по построению. Так работают мультяшные циклы: не 8 рисунков с подгонкой, а
кривые (см. Thomas & Johnston, «The Illusion of Life», про walk cycle).

Фазы
----
θ пробегает 0..2π за цикл. Ближняя нога задаёт фазу, дальняя идёт в
противофазе, ближняя рука — в противофазе к ближней ноге.

Скорость земли берётся не «на глаз», а из самих кривых: на опорной фазе
стопа едет назад относительно корпуса, и ровно с этой скоростью должен
прокручиваться пол. Считаем позицию стопы через FK (или через конец
голени, если отдельного шарнира стопы нет) и берём модуль её скорости.
"""

from __future__ import annotations

import argparse
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


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease(t: float) -> float:
    """Мягкое сглаживание 0..1 (smoothstep) — для не-синусоидальных фаз."""
    return t * t * (3 - 2 * t)


# Кривые цикла. Всё в градусах, положительное — поворот по часовой на экране
# (ось Y вниз). Знаки подобраны по оверлею: отрицательный hip выносит бедро
# вперёд, положительный knee сгибает голень назад.
CYCLES = {
    "walk": dict(
        hip=21.0, knee_stance=6.0, knee_swing=42.0,
        arm=10.0, elbow=8.0,
        flight=0.0,
        lean=3.0, head=2.0,
        frames=24, cycle_s=1.0,
    ),
    "run": dict(
        hip=30.0, knee_stance=14.0, knee_swing=74.0,
        arm=20.0, elbow=32.0,
        flight=42.0,
        lean=9.0, head=4.0,
        frames=16, cycle_s=0.56,
    ),
}


def pose(kind: str, t: float) -> dict[str, float]:
    """Углы шарниров на фазе t∈[0,1)."""
    p = CYCLES[kind]
    th = 2 * math.pi * t
    s, c = math.sin(th), math.cos(th)

    # Бедро: отрицательное — вперёд.
    hip_n = -p["hip"] * s
    hip_f = p["hip"] * s

    # Колено сгибается только при выносе ноги (перенос), в опоре почти прямое.
    def knee(cos_th: float) -> float:
        swing = clamp(cos_th) ** 1.3          # 0..1, максимум в середине переноса
        stance = clamp(-cos_th) ** 1.5        # подседание на опоре
        return p["knee_stance"] + p["knee_swing"] * swing + 8.0 * stance

    knee_n = knee(c)
    knee_f = knee(-c)

    # Руки: ближняя в противофазе к ближней ноге, локоть чуть сгибается.
    arm_n = p["arm"] * s
    arm_f = -p["arm"] * s
    # Локоть сгибается ВПЕРЁД (отрицательный угол), поэтому знак минус:
    # иначе предплечье уходит назад вместе с плечом и рука «выпрямляется
    # в обратную сторону» — на цикле это читается как вывих.
    elb_n = -(p["elbow"] + 6.0 * clamp(s))
    elb_f = -(p["elbow"] + 6.0 * clamp(-s))

    angles = {
        "spine": -p["lean"],          # корпус вперёд, ноги не тянет
        "chest": p["lean"] * 0.35,
        "neck": p["head"] * math.cos(2 * th) - p["lean"] * 0.25,
        "shoulder": arm_n,
        "elbow": elb_n,
        "shoulder_far": arm_f,
        "elbow_far": elb_f,
        "hip": hip_n,
        "knee": knee_n,
        "hip_far": hip_f,
        "knee_far": knee_f,
    }
    return angles


def build(kind: str, size=(768, 1400), *, scene: bool = True,
          ) -> tuple[list[Image.Image], float]:
    """Отрисовать цикл. Возвращает кадры и скорость земли (пикс/с)."""
    master = cutout.key_green(
        Image.open(ROOT / "studio/2p5d/dad/master-side-v2.png").convert("RGB"))
    spec = rig2d.load_rig("dad", "side")
    pup = rig2d.Puppet(master, spec)
    p = CYCLES[kind]
    n = p["frames"]
    H = size[1]
    hip_f = spec["joints"]["hip"]["pos"][1]
    anchor_y = hip_f                      # таз там же, где на рисунке
    anchor = (0.44, anchor_y)
    floor = H - 8
    SOLE = 90            # от шарнира стопы до подошвы, пиксели рисунка

    # 1) Геометрия всех кадров: где окажется подошва опорной ноги.
    poses, sole, ankle_x = [], [], []
    for i in range(n):
        angles = pose(kind, i / n)
        tot = pup._totals(angles)
        ny = tot["ankle"][0][1]
        fy = tot["ankle_far"][0][1]
        # подошва в координатах холста (без сдвига кадра)
        near = anchor_y * H + (ny - hip_f) * H + SOLE
        far = anchor_y * H + (fy - hip_f) * H + SOLE
        poses.append(angles)
        sole.append(max(near, far))
        ankle_x.append(tot["ankle"][0][0] * size[0])

    sole = np.array(sole)
    shift = floor - sole
    # 2) Полёт. Если на кадре обе стопы выше уровня опоры, держать ноги
    #    на полу нельзя: тело должно лететь по дуге. Находим опорные кадры
    #    и между ними подставляем параболу.
    lo = sole.max()
    air = sole < lo - 12
    if air.any() and not air.all():
        idx = np.where(~air)[0]
        for k in range(n):
            if not air[k]:
                continue
            prev = max([j for j in idx if j < k], default=idx[-1] - n)
            nxt = min([j for j in idx if j > k], default=idx[0] + n)
            span = (nxt - prev) or n
            u = (k - prev) / span
            base = shift[prev % n] + (shift[nxt % n] - shift[prev % n]) * u
            shift[k] = base - p["flight"] * math.sin(math.pi * u)

    frames, feet = [], []
    for i in range(n):
        out = pup.render(poses[i], canvas=size, anchor=anchor,
                         shift=(0.0, shift[i]))
        frames.append(out)
        tot = pup._totals(poses[i])
        feet.append(tot["ankle"][0] * np.array([size[0], size[1]])
                    + np.array([anchor[0] * size[0],
                                anchor_y * size[1] + shift[i] - hip_f * size[1]]))

    # Скорость земли: за опорный полуцикл стопа проходит путь шага.
    stride = max(ankle_x) - min(ankle_x)
    speed = stride / (p["cycle_s"] / 2)
    if scene:
        frames = [_scene(f, i / n, speed, p["cycle_s"], size, feet[i], floor)
                  for i, f in enumerate(frames)]
    return frames, speed


def _scene(frame: Image.Image, t: float, speed: float, cycle_s: float,
           size: tuple[int, int], foot: np.ndarray, floor: int,
           pad: int = 90) -> Image.Image:
    """Фон: пол, метки на полу (иначе ход не читается) и тень под ногой."""
    w, h = size[0] + 2 * pad, size[1]
    bg = Image.new("RGB", (w, h), (236, 240, 244))
    d = ImageDraw.Draw(bg)
    d.rectangle((0, floor, w, h), fill=(214, 220, 226))
    # Метки на полу едут навстречу — скорость обязана совпадать со стопой.
    span = 220
    off = (t * speed * cycle_s) % span
    for x in range(-span, w + span, span):
        xx = x - off
        d.rectangle((xx, floor, xx + 8, floor + 14), fill=(178, 186, 194))
    # тень: под опорной стопой, мягкая
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((foot[0] - 70, floor - 10, foot[0] + 90, floor + 26),
                               fill=(60, 70, 80, 70))
    sh = sh.filter(ImageFilter.GaussianBlur(9))
    bg = Image.alpha_composite(bg.convert("RGBA"), sh)
    bg.alpha_composite(frame, (pad, 0))
    return bg.convert("RGB")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("char", nargs="?", default="dad")
    ap.add_argument("kind", nargs="?", default="walk", choices=list(CYCLES))
    ap.add_argument("--out", default=None)
    ap.add_argument("--sheet", default=None)
    args = ap.parse_args()

    frames, speed = build(args.kind)
    out = Path(args.out or ROOT / "studio/out" / f"dad-{args.kind}-rig.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    p = CYCLES[args.kind]
    fps = len(frames) / p["cycle_s"]
    print(f"{args.kind}: кадров {len(frames)}, fps {fps:.1f}, "
          f"земля {speed:.0f} px/с")

    import imageio.v2 as iio
    rgb = [np.asarray(f.convert("RGB")) for f in frames]
    iio.mimwrite(out, rgb, fps=fps, macro_block_size=1)
    print(out)

    # Контрольный лист для проверки глазами.
    cols = 6
    rows = (len(frames) + cols - 1) // cols
    tw, th = 150, 273
    sheet = Image.new("RGB", (cols * tw, rows * th), "white")
    for i, f in enumerate(frames):
        tile = f.convert("RGB").resize((tw, th))
        sheet.paste(tile, ((i % cols) * tw, (i // cols) * th))
    sp = Path(args.sheet or "/tmp/z-rig-sheet.png")
    sheet.save(sp)
    print(sp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
