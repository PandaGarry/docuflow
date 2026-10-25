"""Анимация: походка на IK, покой с дыханием, смешивание движений.

Почему IK для ног
-----------------
Если двигать ноги только поворотами, стопа скользит по полу — глаз это ловит
мгновенно, и «мультфильм» превращается в «резинку». Поэтому здесь: цель для
стопы задаётся в МИРОВЫХ координатах (стоит на земле, идёт назад с той же
скоростью, что тело вперёд), а углы бедра и колена считаются двумя костями.

Тело при этом пока стоит на месте (бег на месте): сцена двигается относительно
персонажа. Так удобнее и дешевле: шаг можно ставить в любую точку кадра.

Соглашения скелета (проверены численно)
---------------------------------------
* поворот вокруг X — сагиттальная плоскость: +X наклоняет назад,
  для колена +X сгибает ногу назад;
* поворот вокруг Z — отведение в сторону: для левой руки +Z вверх-в сторону;
* поворот вокруг Y — скрутка.
"""

from __future__ import annotations

import math

import numpy as np

import rig3d as RIG


def _pitch(direction: np.ndarray) -> float:
    """Угол направления в сагиттальной плоскости: 0 — вниз, >0 — назад."""
    d = np.asarray(direction, np.float64)
    return math.atan2(-float(d[2]), -float(d[1])) if abs(d[1]) + abs(d[2]) > 1e-9 else 0.0


class Animation:
    """Базовый интерфейс: поза на момент времени t (секунды)."""

    duration: float = 1.0
    loop: bool = True

    def pose_at(self, t: float) -> RIG.Pose:            # pragma: no cover
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# IK ног в сагиттальной плоскости
# --------------------------------------------------------------------------- #

def leg_ik(pose: RIG.Pose, skel: RIG.Skeleton, side: str,
           ankle_target: np.ndarray, foot_pitch: float = 0.0,
           knee_forward: bool = True, passes: int = 3) -> RIG.Pose:
    """Поставить стопу в мировую точку: сагиттальный IK + боковая поправка.

    Плоское решение (плоскость Y-Z) не даёт выворотов колена. Но при
    покачивании таза бедро уезжает в сторону, и стопа скользит боком (до 6 см
    за шаг — это видно). Поэтому после сагиттального решения добавляется
    поворот бедра вокруг оси «вперёд» и решение повторяется: три прохода
    сводят ошибку к миллиметрам.
    """
    tgt = np.asarray(ankle_target, np.float64)
    lateral = 0.0
    for _ in range(max(1, passes)):
        fk = RIG.forward_kinematics(skel, pose)
        hip = fk[f"thigh.{side}"]["head"]
        l1 = skel.bones[f"thigh.{side}"].length
        l2 = skel.bones[f"shin.{side}"].length

        dy, dz = tgt[1] - hip[1], tgt[2] - hip[2]
        d = math.hypot(dy, dz)
        d = min(max(d, abs(l1 - l2) + 1e-3), (l1 + l2) * 0.9995)

        base = math.atan2(-dz, -dy)          # направление на цель: >0 — назад
        cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
        a = math.acos(float(np.clip(cos_a, -1.0, 1.0)))
        sign = -1.0 if knee_forward else 1.0
        thigh_world = base + sign * a

        # направление голени НЕ зеркально бедру: колено по треугольнику, затем
        # «колено → цель»; зеркальная формула давала недолёт стопы на 1–3 см
        knee_y = hip[1] - l1 * math.cos(thigh_world)
        knee_z = hip[2] - l1 * math.sin(thigh_world)
        tgt_y = hip[1] - d * math.cos(base)
        tgt_z = hip[2] - d * math.sin(base)
        shin_world = math.atan2(-(tgt_z - knee_z), -(tgt_y - knee_y))

        p1 = _pitch(skel.bones[f"thigh.{side}"].tail - skel.bones[f"thigh.{side}"].head)
        p2 = _pitch(skel.bones[f"shin.{side}"].tail - skel.bones[f"shin.{side}"].head)
        pelvis_pitch = _pitch(fk["pelvis"]["rot"] @ np.array([0.0, -1.0, 0.0]))

        thigh_local = thigh_world - p1 - pelvis_pitch
        acc = pelvis_pitch + thigh_local
        shin_local = shin_world - p2 - acc
        acc += shin_local
        foot_local = foot_pitch - acc

        pose.rot[f"thigh.{side}"] = RIG.euler(0.0, 0.0, lateral) @ \
            RIG.euler(thigh_local, 0, 0)
        pose.rot[f"shin.{side}"] = RIG.euler(shin_local, 0, 0)
        pose.rot[f"foot.{side}"] = RIG.euler(foot_local, 0, 0)

        fk2 = RIG.forward_kinematics(skel, pose)
        ex = float(tgt[0] - fk2[f"foot.{side}"]["head"][0])
        if abs(ex) < 5e-4:
            break
        hip2 = fk2[f"thigh.{side}"]["head"]
        L = float(np.linalg.norm(fk2[f"foot.{side}"]["head"] - hip2))
        lateral += math.asin(float(np.clip(ex / max(L, 1e-3), -0.5, 0.5)))
    return pose


# --------------------------------------------------------------------------- #
# ходьба
# --------------------------------------------------------------------------- #

class Walk(Animation):
    """Цикл шага: стопа фиксируется на земле, тело покачивается.

    Фазы (доля цикла): стопа на земле 0…`duty`, перенос `duty`…1.
    Правая нога сдвинута на полцикла — иначе это не ходьба, а прыжки.
    """

    def __init__(self, skel: RIG.Skeleton, *, cycle: float = 0.95,
                 stride: float = 0.38, step_height: float = 0.09,
                 bob: float = 0.022, sway: float = 0.020,
                 duty: float = 0.62, arm_swing: float = 0.40,
                 lean: float = 0.045, ground_z: float = 0.14,
                 crouch: float = 0.022):
        self.skel = skel
        self.duration = cycle
        self.cycle = cycle
        self.stride = stride
        self.step_height = step_height
        self.bob = bob
        self.sway = sway
        self.duty = duty
        self.arm_swing = arm_swing
        self.lean = lean
        self.ground_z = ground_z
        self.crouch = crouch
        fk0 = RIG.forward_kinematics(skel, RIG.Pose())
        self.ankle_y = float(fk0["foot.L"]["head"][1])
        self.ankle_x = float(abs(fk0["foot.L"]["head"][0]))
        self.shoulder_y = float(fk0["upperarm.L"]["head"][1])

    def foot_target(self, side: str, u: float):
        """Цель для стопы (мировые координаты) и наклон стопы.

        Скорости на стыке фаз СШИВАЮТСЯ. Раньше перенос описывался линейно, и в
        момент отрыва/касания скорость менялась скачком: ускорение доходило до
        50+ м/с², стопа визуально «щёлкала». Теперь горизонталь — кубическая
        кривая Эрмита с той же скоростью на концах, что и у опоры, а подъём —
        косинусная арка (нулевая вертикальная скорость на земле).
        """
        T = self.cycle
        Ts = self.duty * T              # длительность опоры
        Tw = (1 - self.duty) * T        # длительность переноса
        v_ground = self.stride / Ts     # скорость стопы на опоре, м/с
        phase = u % 1.0
        x = self.ankle_x * (1 if side == "L" else -1)
        if phase < self.duty:                       # опора
            k = phase / self.duty
            z = self.stride * (0.5 - k)
            y = self.ankle_y
            pitch = -0.40 * RIG.Ease.in_(max(0.0, (k - 0.70) / 0.30), 2.0)
        else:                                       # перенос
            k = (phase - self.duty) / (1 - self.duty)
            p0, p1 = -self.stride * 0.5, self.stride * 0.5
            v0n = v1n = -v_ground * Tw              # нормированные скорости
            k2, k3 = k * k, k * k * k
            h00 = 2 * k3 - 3 * k2 + 1
            h10 = k3 - 2 * k2 + k
            h01 = -2 * k3 + 3 * k2
            h11 = k3 - k2
            z = h00 * p0 + h10 * v0n + h01 * p1 + h11 * v1n
            y = self.ankle_y + self.step_height * 0.5 * (1 - math.cos(2 * math.pi * k))
            pitch = -0.42 * math.sin(math.pi * k) ** 1.5 * (1 - k)
        return np.array([x, y, z]), pitch


    def pose_at(self, t: float) -> RIG.Pose:
        u = (t / self.cycle) % 1.0
        ph = 2 * math.pi * u
        pose = RIG.Pose()

        # корпус: покачивание (2 подъёма за цикл), перенос веса, наклон вперёд
        # «приседание» на пару сантиметров: без него нога в крайней точке шага
        # выходит на полную длину и стопа отрывается от земли (тест это ловит)
        pose.root_offset = np.array([
            self.sway * math.sin(ph),
            -self.crouch - self.bob * (1 - math.cos(2 * ph)) * 0.5,
            0.0,
        ])
        pose.euler("pelvis", x=-0.02, y=0.10 * math.sin(ph), z=0.045 * math.sin(ph))
        pose.euler("spine", x=-self.lean, y=-0.05 * math.sin(ph),
                   z=-0.02 * math.sin(ph))
        pose.euler("chest", x=-self.lean * 0.5, y=-0.10 * math.sin(ph))
        pose.euler("neck", x=self.lean * 1.1)
        pose.euler("head", x=0.02 * math.sin(2 * ph), y=0.05 * math.sin(ph),
                   z=-0.012 * math.sin(ph))

        # руки: противофаза ногам. Отведение в сторону обязательно: без него
        # кисть на махе проходит сквозь бедро — сразу видно «куклу».
        swing = self.arm_swing * math.sin(ph)
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            sw = swing * sgn
            pose.euler(f"clavicle.{side}", x=-0.02 * sw)
            pose.euler(f"upperarm.{side}", x=sw, z=sgn * (0.21 + 0.03 * abs(sw)))
            pose.euler(f"forearm.{side}", x=-0.30 - 0.30 * max(0.0, -sw),
                       z=sgn * 0.06)

        # ноги через IK
        for side, off in (("L", 0.0), ("R", 0.5)):
            tgt, pitch = self.foot_target(side, u + off)
            # цель НЕ двигается вместе с корпусом: стопа стоит на земле,
            # а приседание корпуса компенсируется сгибом колена
            leg_ik(pose, self.skel, side, tgt, foot_pitch=pitch)
        return pose


# --------------------------------------------------------------------------- #
# покой
# --------------------------------------------------------------------------- #

class Idle(Animation):
    """Стоять и дышать: перенос веса, дыхание, микро-движения головы.

    Именно эти мелкие несимметричные движения отличают «живого» персонажа от
    манекена; амплитуды намеренно небольшие.
    """

    def __init__(self, skel: RIG.Skeleton, *, cycle: float = 4.2,
                 breath: float = 1.0, shift: float = 1.0):
        self.skel = skel
        self.duration = cycle
        self.cycle = cycle
        self.breath = breath
        self.shift = shift
        fk0 = RIG.forward_kinematics(skel, RIG.Pose())
        self.ankle_y = float(fk0["foot.L"]["head"][1])
        self.ankle_x = float(abs(fk0["foot.L"]["head"][0]))

    def pose_at(self, t: float) -> RIG.Pose:
        u = (t / self.cycle) % 1.0
        ph = 2 * math.pi * u
        br = math.sin(ph * 2.0)                       # дыхание — вдвое чаще
        pose = RIG.Pose()
        pose.root_offset = np.array([0.012 * self.shift * math.sin(ph),
                                     0.006 * self.breath * br, 0.0])
        pose.euler("pelvis", z=0.02 * math.sin(ph))
        pose.euler("spine", x=-0.03 - 0.012 * br, z=-0.012 * math.sin(ph))
        pose.euler("chest", x=-0.015 - 0.020 * br)
        pose.euler("neck", x=0.02 + 0.006 * br)
        pose.euler("head", x=-0.01 * br, y=0.05 * math.sin(ph * 0.5),
                   z=0.01 * math.sin(ph))
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            pose.euler(f"upperarm.{side}", x=0.02 * br,
                       z=sgn * (0.10 + 0.012 * math.sin(ph) * sgn))
            pose.euler(f"forearm.{side}", x=-0.22 - 0.02 * br)
            tgt = np.array([sgn * self.ankle_x, self.ankle_y, 0.0])
            leg_ik(pose, self.skel, side, tgt, foot_pitch=0.0)
        return pose


# --------------------------------------------------------------------------- #
# смешивание
# --------------------------------------------------------------------------- #

class Blend(Animation):
    """Плавный переход между двумя анимациями (по времени, с кривой)."""

    def __init__(self, a: Animation, b: Animation, start: float, dur: float):
        self.a, self.b, self.start, self.dur = a, b, start, dur
        self.duration = max(a.duration, b.duration)

    def pose_at(self, t: float) -> RIG.Pose:
        pa, pb = self.a.pose_at(t), self.b.pose_at(t)
        k = 0.0 if self.dur <= 0 else min(max((t - self.start) / self.dur, 0.0), 1.0)
        return pa.blended(pb, RIG.Ease.smooth(k))
