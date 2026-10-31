"""Ходьба и бег из 2D-рига: каждая нога делает честный мах вперёд-назад.

    python studio/tools/stride_cycle.py dad walk
    python studio/tools/stride_cycle.py dad run

Почему так, а не кадрами библиотеки
-----------------------------------
Восемь нарисованных фаз шага «не читались»: в каждой фазе нога нарисована
заново, своей формы, а между фазами она перепрыгивала. Руки читались, потому
что двигаются грубее. Заказчик сказал точнее: «руки отлично меняются, ноги
нет».

Здесь рисунок ОДИН — `master-side-stand.png`, ровная стойка. Из него вырезаны
части: бедро, голень, стопа, таз, торс, голова, рука, кисть. Каждая часть
поворачивается вокруг своего шарнира. Нога не меняет форму — она
поворачивается, значит ноги можно чередовать как угодно.

Главная тонкость: угол задаётся АБСОЛЮТНЫЙ
------------------------------------------
Поворот шарнира в риге складывается с углом, под которым нога нарисована.
Поэтому «повернуть бедро на −20°» и «поставить ногу под углом −20°» — разные
вещи: на рисунке бедро уже наклонено. Если задавать поворот напрямую, нога
почти не уходит назад — именно этот баг и был в прошлой версии.

Здесь для каждого кадра решается обратная задача: подбирается такой поворот
шарнира, при котором АБСОЛЮТНЫЙ угол бедра равен нужному. Решение — двоичный
поиск по монотонной функции, 30 итераций, это дёшево.

Опора
-----
Стопа опорной ноги доворачивается так, чтобы подошва лежала плоско: угол
подбирается по факту (самый широкий след на самой нижней строке кадра).
Кадр ставится на пол по этой же нижней строке.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image, ImageDraw

import cutout
import rig2d

ROOT = HERE.parents[2]
W, H = 720, 900
GROUND = H - 110
FPS = 24
BG = (238, 235, 229)
FLOOR = (216, 212, 204)

CYCLES = {
    "walk": dict(
        thigh=20.0,      # амплитуда абсолютного угла бедра, градусы
        knee_swing=44.0, # сгиб колена в переносе
        knee_stance=4.0,
        arm=9.0, elbow=6.0, lean=2.0,
        frames=12, cycle_s=1.0, lift=0.0,
    ),
    "run": dict(
        thigh=30.0, knee_swing=72.0, knee_stance=10.0,
        arm=16.0, elbow=24.0, lean=9.0,
        frames=10, cycle_s=0.62, lift=6.0,
    ),
}


class Rigger:
    """Риг + обратная задача «поворот по нужному абсолютному углу»."""

    def __init__(self) -> None:
        src = cutout.key_green(
            Image.open(ROOT / "studio/2p5d/dad/master-side-stand.png").convert("RGB"))
        self.src = src
        self.spec = rig2d.load_rig("dad", "stride")
        self.pup = rig2d.Puppet(src, self.spec)
        self.w, self.h = src.size

    def absang(self, j1: str, j2: str, angles: dict) -> float:
        tot = self.pup._totals(angles)
        p1, p2 = tot[j1][0], tot[j2][0]
        return math.degrees(math.atan2((p2[0] - p1[0]) * self.w,
                                       (p2[1] - p1[1]) * self.h))

    def rotate_to(self, j1: str, j2: str, target: float,
                  lo: float = -130.0, hi: float = 150.0) -> float:
        """Поворот шарнира j1, при котором угол j1→j2 равен target."""
        for _ in range(30):
            mid = (lo + hi) / 2
            if self.absang(j1, j2, {j1: mid}) > target:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def contact(self, fig: Image.Image) -> int:
        """Самая нижняя строка содержимого."""
        a = np.asarray(fig)[..., 3] > 40
        ys = np.where(a.any(1))[0]
        return int(ys.max()) if len(ys) else 0

    def trace(self, fig: Image.Image) -> int:
        """Ширина следа подошвы на самой нижней строке."""
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

    def flatten(self, ang: dict, lo: int = -40, hi: int = 40, step: int = 4) -> dict:
        """Довернуть стопу так, чтобы подошва легла плоско."""
        best, best_w = ang.get("ankle_near", 0.0), -1
        for a in range(lo, hi + 1, step):
            trial = dict(ang)
            trial["ankle_near"] = float(a)
            w = self.trace(self.pup.render(trial, canvas=self.src.size))
            if w > best_w:
                best, best_w = float(a), w
        out = dict(ang)
        out["ankle_near"] = best
        return out


def frame_angles(rg: Rigger, kind: str, t: float) -> dict:
    """Углы на фазе t∈[0,1)."""
    p = CYCLES[kind]
    th = 2 * math.pi * t
    c, s = math.cos(th), math.sin(th)

    # АБСОЛЮТНЫЕ углы бедра: ноги строго в противофазе.
    # 0° — вертикально, плюс — вперёд (в сторону лица).
    a_near = p["thigh"] * c
    a_far = -p["thigh"] * c

    r_near = rg.rotate_to("hip_near", "knee_near", a_near)
    r_far = rg.rotate_to("hip_far", "knee_far", a_far)

    # Колено сгибается в переносе: когда бедро идёт вперёд.
    sw_near = max(0.0, -s) ** 1.2
    sw_far = max(0.0, s) ** 1.2
    k_near = p["knee_stance"] + p["knee_swing"] * sw_near
    k_far = p["knee_stance"] + p["knee_swing"] * sw_far

    return {
        # Стопа: в опоре доворачивается до плоскости (это делает flatten),
        # в переносе — чуть вниз носком, но БЕЗ полного выравнивания: иначе
        # сапог крутится вокруг голени и выглядит сломанным.
        "hip_near": r_near, "knee_near": k_near,
        "ankle_near": -(r_near + k_near) * 0.55,
        "hip_far": r_far, "knee_far": k_far,
        "ankle_far": -(r_far + k_far) * 0.55,
        "shoulder": -p["arm"] * c, "elbow": -p["elbow"],
        "spine": -p["lean"], "neck": p["lean"] * 0.6,
    }


def build(kind: str) -> tuple[list[Image.Image], float]:
    rg = Rigger()
    p = CYCLES[kind]
    n = p["frames"]
    scale = 0.80 * H / rg.src.height
    cw, ch = int(rg.src.width * scale), int(rg.src.height * scale)

    figs, soles = [], []
    for i in range(n):
        ang = frame_angles(rg, kind, i / n)
        ang = rg.flatten(ang)
        fig = rg.pup.render(ang, canvas=rg.src.size)
        fig = fig.resize((cw, ch), Image.LANCZOS)
        figs.append(fig)
        soles.append(rg.contact(fig))

    # Скорость земли: опорная стопа проходит за полуцикл путь шага.
    step = 2 * p["thigh"] / 90.0 * (cw * 0.42)
    speed = step / (p["cycle_s"] / 2)

    frames = []
    for i, fig in enumerate(figs):
        canvas = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, GROUND, W, H], fill=FLOOR)
        d.line([(0, GROUND), (W, GROUND)], fill=(150, 146, 138), width=3)
        shift = int(i * speed * p["cycle_s"] / n) % 140
        for x in range(-140, W + 140, 140):
            d.line([(x + shift, GROUND + 6), (x + shift - 46, GROUND + 64)],
                   fill=(198, 193, 184), width=4)

        lift = 0
        if p["lift"]:
            lift = int(round(p["lift"] * max(0.0, math.cos(4 * math.pi * i / n))))
        y = GROUND - soles[i] - lift
        x = int(W * 0.45 - fig.width * 0.5)
        canvas.paste(fig, (x, y), fig.getchannel("A"))
        frames.append(canvas)

    doubled = [f for f in frames for _ in (0, 1)]
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
