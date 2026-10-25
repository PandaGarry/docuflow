"""Скелет и кинематика: 22 кости, прямой проход, IK, кривые анимации.

Зачем свой скелет, а не «повороты картинки»
-------------------------------------------
Плохой риг видно сразу: конечности меняют длину, колени выгибаются назад, стопа
«плывёт» по полу, плечо выворачивается. Поэтому здесь честная иерархия костей,
жёсткие длины, соглашения о знаках и IK, который не даёт стопе проскальзывать.

Соглашения
----------
* Метры, Y вверх, +Z — вперёд (лицом), +X — влево персонажа.
* Кость описывается головой (`head`) и хвостом (`tail`) в позе покоя.
* Локальный поворот кости задаётся в системе КООРДИНАТ РОДИТЕЛЯ и действует
  вокруг её головы. Мировые повороты накапливаются: R_b = R_parent · R_local.
* Позиции: head_b = head_parent + R_parent · (head_rest_b − head_rest_parent),
  tail_b = head_b + R_b · (tail_rest_b − head_rest_b).
  Отсюда следует главное свойство: **длины костей не меняются никогда**, а шарнир
  не разрывается — это то, из-за чего старый 2D-риг «ломался».

Что здесь есть
--------------
* `Skeleton` — скелет из пропорций персонажа (стандартные имена костей).
* `Pose` — словарь «кость → поворот» + смещение таза.
* `euler`, `quat`-подобные утилиты, `slerp` для интерполяции поворотов.
* `solve_two_bone` — аналитический IK для руки/ноги (цель + «полюс» сгиба).
* `aim_local` — повернуть кость так, чтобы она смотрела в точку (для IK).
* `Ease` — кривые (smoothstep, ease-in/out, overshoot) для «современного»
  движения: без линейных рывков.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# --------------------------------------------------------------------------- #
# математика поворотов
# --------------------------------------------------------------------------- #

def euler(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> np.ndarray:
    """Поворот из углов Эйлера (радианы), порядок Z·Y·X.

    Именно в таком порядке удобно думать про конечности: Z — «вперёд/назад»
    (сгиб в сагиттальной плоскости), X — «в сторону», Y — скрутка.
    """
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return rz @ ry @ rx


def axis_angle(axis, angle: float) -> np.ndarray:
    a = np.asarray(axis, np.float64)
    n = np.linalg.norm(a)
    if n < 1e-12:
        return np.eye(3)
    a = a / n
    c, s = math.cos(angle), math.sin(angle)
    t = 1 - c
    x, y, z = a
    return np.array([
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c],
    ])


def rot_between(a, b) -> np.ndarray:
    """Минимальный поворот, переводящий направление `a` в направление `b`."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return np.eye(3)
    a, b = a / na, b / nb
    c = float(np.clip(a @ b, -1.0, 1.0))
    if c > 1 - 1e-9:
        return np.eye(3)
    if c < -1 + 1e-9:                                    # строго противоположны
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        return axis_angle(axis, math.pi)
    axis = np.cross(a, b)
    return axis_angle(axis, math.acos(c))


def rot_to_quat(m: np.ndarray) -> np.ndarray:
    """Матрица → кватернион (w, x, y, z). Нужен для slerp."""
    m = np.asarray(m, np.float64)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z], np.float64)
    return q / np.linalg.norm(q)


def quat_to_rot(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    """Плавная интерполяция поворотов (кратчайшей дугой)."""
    qa, qb = rot_to_quat(a), rot_to_quat(b)
    d = float(qa @ qb)
    if d < 0:                       # кратчайший путь
        qb, d = -qb, -d
    d = float(np.clip(d, -1.0, 1.0))
    if d > 0.9995:
        q = qa + (qb - qa) * t
        return quat_to_rot(q / np.linalg.norm(q))
    th = math.acos(d)
    q = (math.sin((1 - t) * th) * qa + math.sin(t * th) * qb) / math.sin(th)
    return quat_to_rot(q)


# --------------------------------------------------------------------------- #
# кривые движения
# --------------------------------------------------------------------------- #

class Ease:
    """Кривые для тайминга: линейное движение — главный признак «дёшево»."""

    @staticmethod
    def smooth(t: float) -> float:
        t = min(max(t, 0.0), 1.0)
        return t * t * (3 - 2 * t)

    @staticmethod
    def in_out(t: float, p: float = 2.4) -> float:
        t = min(max(t, 0.0), 1.0)
        return 0.5 * (2 * t) ** p if t < 0.5 else 1 - 0.5 * (2 - 2 * t) ** p

    @staticmethod
    def out(t: float, p: float = 3.0) -> float:
        t = min(max(t, 0.0), 1.0)
        return 1 - (1 - t) ** p

    @staticmethod
    def in_(t: float, p: float = 3.0) -> float:
        t = min(max(t, 0.0), 1.0)
        return t ** p

    @staticmethod
    def overshoot(t: float, s: float = 1.30) -> float:
        t = min(max(t, 0.0), 1.0)
        t -= 1
        return t * t * ((s + 1) * t + s) + 1

    @staticmethod
    def bounce(t: float) -> float:
        t = min(max(t, 0.0), 1.0)
        return 1 - abs(math.cos(t * math.pi * 1.5)) * (1 - t) ** 2


# --------------------------------------------------------------------------- #
# скелет
# --------------------------------------------------------------------------- #

@dataclass
class Bone:
    name: str
    parent: str | None
    head: np.ndarray          # поза покоя, метры
    tail: np.ndarray

    @property
    def length(self) -> float:
        return float(np.linalg.norm(self.tail - self.head))


#: порядок важен: родители раньше детей
BONE_ORDER = [
    "pelvis", "spine", "chest", "neck", "head",
    "clavicle.L", "upperarm.L", "forearm.L", "hand.L",
    "clavicle.R", "upperarm.R", "forearm.R", "hand.R",
    "thigh.L", "shin.L", "foot.L", "toe.L",
    "thigh.R", "shin.R", "foot.R", "toe.R",
]


@dataclass
class Skeleton:
    bones: dict[str, Bone]
    order: list[str] = field(default_factory=lambda: list(BONE_ORDER))

    @classmethod
    def from_proportions(cls, p) -> "Skeleton":
        """Построить скелет ровно по тем же числам, что и тело."""
        H = p.height
        hh = p.head_frac * H
        hip_y = p.hip_y * H
        sh_y = (p.shoulder_y - 0.006) * H
        neck_y = p.neck_y * H
        sh_x = p.shoulder_w * p.head_frac * 0.37 * H
        hip_x = p.hip_w * p.head_frac * 0.27 * H
        arm = p.arm_len * H

        v = lambda x, y, z=0.0: np.array([x, y, z], np.float64)
        bones: dict[str, Bone] = {}

        def add(name, parent, head, tail):
            bones[name] = Bone(name, parent, np.asarray(head, np.float64),
                               np.asarray(tail, np.float64))

        add("pelvis", None, v(0, hip_y, 0), v(0, hip_y + 0.10 * H, 0))
        add("spine", "pelvis", v(0, hip_y + 0.10 * H, 0), v(0, sh_y - 0.14 * H, 0))
        add("chest", "spine", v(0, sh_y - 0.14 * H, 0), v(0, sh_y - 0.01 * H, 0))
        add("neck", "chest", v(0, sh_y - 0.01 * H, 0), v(0, neck_y + 0.02 * H, 0))
        add("head", "neck", v(0, neck_y + 0.02 * H, 0), v(0, H, 0))

        for side, sname in ((1, "L"), (-1, "R")):
            sx = side * sh_x
            add(f"clavicle.{sname}", "chest",
                v(side * 0.03 * H, sh_y - 0.02 * H, 0), v(sx, sh_y, 0))
            add(f"upperarm.{sname}", f"clavicle.{sname}",
                v(sx, sh_y, 0), v(sx * 1.12, sh_y - arm * 0.52, 0.004 * H))
            add(f"forearm.{sname}", f"upperarm.{sname}",
                v(sx * 1.12, sh_y - arm * 0.52, 0.004 * H),
                v(sx * 1.18, sh_y - arm, 0.014 * H))
            add(f"hand.{sname}", f"forearm.{sname}",
                v(sx * 1.18, sh_y - arm, 0.014 * H),
                v(sx * 1.20, sh_y - arm - p.hand_len * H * 0.85, 0.016 * H))

            hx = side * hip_x
            # колено чуть вперёд: в позе покоя нога не выпрямлена «в струну»,
            # иначе IK нечего сгибать и колени «щёлкают» на шаге
            add(f"thigh.{sname}", "pelvis", v(hx, hip_y, 0),
                v(hx * 1.03, 0.262 * H, 0.030 * H))
            add(f"shin.{sname}", f"thigh.{sname}",
                v(hx * 1.03, 0.262 * H, 0.030 * H),
                v(hx * 1.07, 0.075 * H, -0.002 * H))
            add(f"foot.{sname}", f"shin.{sname}",
                v(hx * 1.07, 0.075 * H, -0.002 * H),
                v(hx * 1.07, 0.020 * H, 0.055 * H))
            add(f"toe.{sname}", f"foot.{sname}",
                v(hx * 1.07, 0.020 * H, 0.055 * H),
                v(hx * 1.07, 0.016 * H, 0.115 * H))
        return cls(bones)

    # ------------------------------------------------------------------ #
    def parent_of(self, name: str) -> str | None:
        return self.bones[name].parent

    def bone(self, name: str) -> Bone:
        return self.bones[name]

    def rest_head(self, name: str) -> np.ndarray:
        return self.bones[name].head.copy()

    def rest_dir(self, name: str) -> np.ndarray:
        b = self.bones[name]
        return (b.tail - b.head) / max(b.length, 1e-12)

    def check(self) -> list[str]:
        """Санитарная проверка скелета: иерархия, длины, нулевые кости."""
        problems = []
        for name in self.order:
            b = self.bones[name]
            if b.parent is not None and b.parent not in self.bones:
                problems.append(f"{name}: нет родителя {b.parent}")
            if b.length < 1e-6:
                problems.append(f"{name}: нулевая длина")
            if not np.all(np.isfinite(b.head)) or not np.all(np.isfinite(b.tail)):
                problems.append(f"{name}: NaN в позе покоя")
        # индексы родителей должны идти раньше детей
        seen = set()
        for name in self.order:
            par = self.bones[name].parent
            if par is not None and par not in seen:
                problems.append(f"{name}: родитель {par} позже ребёнка")
            seen.add(name)
        return problems


@dataclass
class Pose:
    """Поза: локальные повороты + смещение таза (корень).

    `rot[name]` — поворот 3×3 в системе родителя. `root_offset` — смещение
    таза в метрах (прыжок, приседание, шаг в сторону).
    """

    rot: dict[str, np.ndarray] = field(default_factory=dict)
    root_offset: np.ndarray = field(default_factory=lambda: np.zeros(3))

    def set(self, name: str, m: np.ndarray) -> "Pose":
        self.rot[name] = np.asarray(m, np.float64)
        return self

    def euler(self, name: str, x=0.0, y=0.0, z=0.0) -> "Pose":
        self.rot[name] = euler(x, y, z)
        return self

    def copy(self) -> "Pose":
        return Pose({k: v.copy() for k, v in self.rot.items()},
                    self.root_offset.copy())

    def blended(self, other: "Pose", t: float) -> "Pose":
        """Плавно смешать две позы (по всем костям скелета)."""
        out = Pose(root_offset=self.root_offset * (1 - t) + other.root_offset * t)
        names = set(self.rot) | set(other.rot)
        ident = np.eye(3)
        for n in names:
            a = self.rot.get(n, ident)
            b = other.rot.get(n, ident)
            out.rot[n] = slerp(a, b, t)
        return out


def forward_kinematics(skel: Skeleton, pose: Pose) -> dict[str, dict]:
    """Мировые головы/хвосты/повороты для всех костей.

    Возвращает `{имя: {"head": (…), "tail": (…), "rot": 3×3}}`.
    Длины костей берутся из позы покоя и не меняются.
    """
    out: dict[str, dict] = {}
    ident = np.eye(3)
    for name in skel.order:
        b = skel.bones[name]
        local = pose.rot.get(name, ident)
        if b.parent is None:
            rot = local
            head = b.head + np.asarray(pose.root_offset, np.float64)
        else:
            par = out[b.parent]
            rot = par["rot"] @ local
            head = par["head"] + par["rot"] @ (b.head - skel.bones[b.parent].head)
        tail = head + rot @ (b.tail - b.head)
        out[name] = {"head": head, "tail": tail, "rot": rot}
    return out


# --------------------------------------------------------------------------- #
# IK
# --------------------------------------------------------------------------- #

def solve_two_bone(root: np.ndarray, mid: np.ndarray, end: np.ndarray,
                   target: np.ndarray, pole: np.ndarray):
    """Аналитический IK для двух костей (рука/нога).

    `pole` — точка, задающая плоскость сгиба (колено вперёд, локоть назад).
    Возвращает новые позиции (mid, end); если цель недостижима — тянется
    максимально близко, но длина костей остаётся прежней.
    """
    root = np.asarray(root, np.float64)
    mid = np.asarray(mid, np.float64)
    end = np.asarray(end, np.float64)
    target = np.asarray(target, np.float64)
    l1 = float(np.linalg.norm(mid - root))
    l2 = float(np.linalg.norm(end - mid))
    to_t = target - root
    d = float(np.linalg.norm(to_t))
    if d < 1e-9:
        return mid, end
    maxd = (l1 + l2) * 0.9995
    mind = abs(l1 - l2) + 1e-4
    d = min(max(d, mind), maxd)
    u = to_t / np.linalg.norm(to_t)

    # угол между первой костью и направлением на цель
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    a = math.acos(float(np.clip(cos_a, -1.0, 1.0)))

    # ось сгиба: перпендикуляр к плоскости «цель — полюс»
    n = np.cross(u, np.asarray(pole, np.float64) - root)
    if np.linalg.norm(n) < 1e-6:
        n = np.cross(u, np.array([0.0, 0.0, 1.0]))
        if np.linalg.norm(n) < 1e-6:
            n = np.cross(u, np.array([1.0, 0.0, 0.0]))
    n /= np.linalg.norm(n)

    new_mid = root + (axis_angle(n, a) @ u) * l1
    to_end = target - new_mid
    ne = np.linalg.norm(to_end)
    new_end = new_mid + (to_end / ne if ne > 1e-9 else np.zeros(3)) * l2
    return new_mid, new_end


def aim_rotation(current_dir: np.ndarray, want_dir: np.ndarray,
                 current_rot: np.ndarray) -> np.ndarray:
    """Дополнительный поворот, чтобы кость смотрела в нужную сторону."""
    cur = current_rot @ current_dir
    want = np.asarray(want_dir, np.float64)
    nw = np.linalg.norm(want)
    if nw < 1e-9:
        return current_rot
    return rot_between(cur, want / nw) @ current_rot
