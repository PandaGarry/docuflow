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


def arm_ik(pose: RIG.Pose, skel: RIG.Skeleton, side: str,
           hand_target: np.ndarray, elbow_hint=None, wrist: float = 0.0,
           passes: int = 2) -> RIG.Pose:
    """Довести кисть в мировую точку: IK руки по цели.

    Без этого рука — маятник: жест «помаши», «покажи на», «руки в боки»
    поставить нечем. Решение: две кости аналитически, затем перевод мировых
    поворотов в локальные (минимальным поворотом, без скрутки).

    `elbow_hint` — куда смотрит локоть (по умолчанию вниз-назад): локоть
    задаётся полюсом, иначе рука «выворачивается».
    """
    tgt = np.asarray(hand_target, np.float64)
    for _ in range(max(1, passes)):
        fk = RIG.forward_kinematics(skel, pose)
        sh = fk[f"upperarm.{side}"]["head"]
        el = fk[f"forearm.{side}"]["head"]
        wr = fk[f"hand.{side}"]["head"]
        l1 = skel.bones[f"upperarm.{side}"].length
        l2 = skel.bones[f"forearm.{side}"].length

        if elbow_hint is None:
            hint = sh + np.array([0.0, -0.35, -0.55]) * (1.0 if side == "L" else 1.0)
        else:
            hint = np.asarray(elbow_hint, np.float64)

        mid, end = RIG.solve_two_bone(sh, el, wr, tgt, hint)

        # мировые направления в позе покоя
        def rest_dir(name):
            b = skel.bones[name]
            d = b.tail - b.head
            return d / max(np.linalg.norm(d), 1e-12)

        d_up, d_fore = rest_dir(f"upperarm.{side}"), rest_dir(f"forearm.{side}")

        # --- плечо
        rw_up = fk[f"upperarm.{side}"]["rot"]
        cur = rw_up @ d_up
        want = mid - sh
        if np.linalg.norm(want) > 1e-9:
            d_rot = RIG.rot_between(cur, want / np.linalg.norm(want))
            rw_up_new = d_rot @ rw_up
        else:
            rw_up_new = rw_up
        parent_up = fk[f"clavicle.{side}"]["rot"]
        pose.rot[f"upperarm.{side}"] = parent_up.T @ rw_up_new

        # --- предплечье (пересчитываем после поворота плеча)
        fk = RIG.forward_kinematics(skel, pose)
        rw_fore = fk[f"forearm.{side}"]["rot"]
        cur2 = rw_fore @ d_fore
        want2 = end - mid
        if np.linalg.norm(want2) > 1e-9:
            d2 = RIG.rot_between(cur2, want2 / np.linalg.norm(want2))
            rw_fore_new = d2 @ rw_fore
        else:
            rw_fore_new = rw_fore
        pose.rot[f"forearm.{side}"] = rw_up_new.T @ rw_fore_new

        # --- кисть: разворот вокруг оси предплечья + наклон
        pose.rot[f"hand.{side}"] = RIG.euler(0.0, wrist, 0.0)
    return pose


def toe_roll(pose: RIG.Pose, skel: RIG.Skeleton, side: str, angle: float) -> RIG.Pose:
    """Перекат с пятки на носок: носок работает как отдельный шарнир.

    Без этого стопа весь шаг «деревянная»: обувь поворачивается вокруг
    щиколотки и на отрыве задирает носок в воздух.
    """
    pose.rot[f"toe.{side}"] = RIG.euler(angle, 0, 0)
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
            # отрыв пятки: пятка поднимается, носок остаётся на земле,
            # поэтому щиколотка поднимается и чуть уходит вперёд
            heel = RIG.Ease.in_(max(0.0, (k - 0.68) / 0.32), 2.0)
            pitch = 0.55 * heel
            y += 0.055 * heel
            z += 0.02 * heel
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
            pitch = -0.16 * math.sin(math.pi * k)
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
            # на отрыве пятки носок догибается — перекат, а не «деревянная» стопа
            toe_roll(pose, self.skel, side, -max(0.0, pitch) * 0.9)
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
# вторичное движение
# --------------------------------------------------------------------------- #

class Secondary(Animation):
    """Вторичка: голова отстаёт от корпуса (follow-through).

    В живой анимации голова не едет жёстко с грудью: она запаздывает на 2–4
    кадра и чуть «перелетает». Здесь это считается честно — берётся поза в
    момент t − lag, и поворот шеи/головы смешивается с ней. Никакой магии:
    то же движение, но с задержкой, поэтому на разгонах и торможениях
    появляется естественный «хвост».
    """

    def __init__(self, base: Animation, lag: float = 0.07, gain: float = 0.65,
                 bones=("neck", "head")):
        self.base = base
        self.lag = lag
        self.gain = gain
        self.bones = bones
        self.duration = base.duration
        self.loop = base.loop

    def pose_at(self, t: float) -> RIG.Pose:
        now = self.base.pose_at(t)
        prev = self.base.pose_at(t - self.lag)
        out = now.copy()
        for b in self.bones:
            a = now.rot.get(b, np.eye(3))
            c = prev.rot.get(b, np.eye(3))
            out.rot[b] = RIG.slerp(a, c, self.gain)
        return out


# --------------------------------------------------------------------------- #
# жесты (руки по цели)
# --------------------------------------------------------------------------- #

class Gesture(Idle):
    """Жест поверх покоя: рука доводится IK-ом до цели в мире.

    Смысл: комедия играется руками — «помаши», «покажи», «руки в боки»,
    «хлопни себя по лбу». Без IK рук эти позы поставить нечем.
    """

    def __init__(self, skel: RIG.Skeleton, *, cycle: float = 3.2):
        super().__init__(skel, cycle=cycle)

    def reach(self, pose: RIG.Pose, side: str, target, hint=None,
              wrist: float = 0.0) -> RIG.Pose:
        return arm_ik(pose, self.skel, side, np.asarray(target, np.float64),
                      elbow_hint=hint, wrist=wrist)

    def _shoulder(self, fk, side):
        return fk[f"upperarm.{side}"]["head"]


class Wave(Gesture):
    """Машет рукой: кисть ходит дугой, корпус и голова слегка в такт."""

    duration = 3.0

    def __init__(self, skel, *, side: str = "L", cycle: float = 3.0,
                 height: float = 1.60, out: float = 0.42):
        super().__init__(skel, cycle=cycle)
        self.side, self.height, self.out = side, height, out

    def pose_at(self, t: float) -> RIG.Pose:
        pose = super().pose_at(t)
        sgn = 1.0 if self.side == "L" else -1.0
        sway = math.sin(2 * math.pi * t / 0.55)          # 0.55 с на взмах
        fk = RIG.forward_kinematics(self.skel, pose)
        sh = fk[f"upperarm.{self.side}"]["head"]
        target = np.array([sgn * (self.out + 0.075 * sway),
                           self.height + 0.03 * math.cos(2 * math.pi * t / 0.55),
                           0.10 + 0.03 * sway])
        # полюс локтя — низко и наружу: иначе локоть уходит вверх и рука
        # складывается над головой вместо «помахать»
        hint = sh + np.array([sgn * 0.30, -1.10, -0.30])
        self.reach(pose, self.side, target, hint, wrist=0.25 * sway)
        pose.euler("spine", x=-0.03, z=-sgn * 0.04)
        pose.euler("chest", y=sgn * 0.04)
        pose.euler("head", x=-0.04, z=sgn * 0.05)
        return pose


class HandsOnHips(Gesture):
    """Руки в боки — «ну и что это было?»."""

    def __init__(self, skel, *, cycle: float = 4.0):
        super().__init__(skel, cycle=cycle)

    def pose_at(self, t: float) -> RIG.Pose:
        pose = super().pose_at(t)
        fk = RIG.forward_kinematics(self.skel, pose)
        for side, sgn in (("L", 1.0), ("R", -1.0)):
            sh = fk[f"upperarm.{side}"]["head"]
            target = np.array([sgn * 0.245, 0.92, -0.005])
            hint = sh + np.array([sgn * 0.80, -0.25, -0.50])
            self.reach(pose, side, target, hint, wrist=sgn * 0.5)
        pose.euler("spine", x=-0.02)
        pose.euler("chest", x=-0.03)
        pose.euler("head", x=-0.03)
        return pose


class PointArm(Gesture):
    """Показывает рукой вперёд-вверх (в камеру)."""

    def __init__(self, skel, *, cycle: float = 3.4, side: str = "R"):
        super().__init__(skel, cycle=cycle)
        self.side = side

    def pose_at(self, t: float) -> RIG.Pose:
        pose = super().pose_at(t)
        sgn = 1.0 if self.side == "L" else -1.0
        fk = RIG.forward_kinematics(self.skel, pose)
        sh = fk[f"upperarm.{self.side}"]["head"]
        breathe = 0.01 * math.sin(2 * math.pi * t / 1.6)
        target = np.array([sgn * 0.235, sh[1] + 0.06 + breathe, 0.60])
        hint = sh + np.array([sgn * 0.40, -0.80, -0.20])
        self.reach(pose, self.side, target, hint, wrist=0.1)
        pose.euler("chest", y=-sgn * 0.05)
        pose.euler("head", y=-sgn * 0.06, x=-0.02)
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
