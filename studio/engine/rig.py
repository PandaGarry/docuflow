"""Движок рига: скелет, двухзвенный IK, кривые и вторичная анимация.

Идея: аниматор задаёт не углы суставов, а ЦЕЛИ (куда тянется кисть/стопа) и
тайминги. Скелет считает суставы сам, поэтому рука не выворачивается и
персонаж не «резиновый».

Модуль не зависит от PIL: это чистая математика, чтобы её можно было
тестировать без рендера.

Ключевые классы
---------------
Bone      — кость иерархии (родитель, локальная поза, длина).
Skeleton  — сборка + прямой кинематический проход (FK).
solve_ik2 — двухзвенный IK с полюсным вектором (локоть/колено).
Track     — ключи одного канала + интерполяция (linear/ease/back/spring).
Spring    — цепочка вторичной анимации (волосы, борода, капюшон).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# --------------------------------------------------------------------------- #
# базовое
# --------------------------------------------------------------------------- #


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return a if x < a else b if x > b else x


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


def smooth_step(k: float) -> float:
    k = clamp(k)
    return k * k * (3 - 2 * k)


def ease_in_out(k: float) -> float:
    k = clamp(k)
    return 0.5 - 0.5 * math.cos(math.pi * k)


def ease_out_back(k: float, s: float = 1.7) -> float:
    k = clamp(k) - 1.0
    return 1.0 + (s + 1.0) * k ** 3 + s * k ** 2


def ease_in_quad(k: float) -> float:
    k = clamp(k)
    return k * k


def ease_out_quad(k: float) -> float:
    k = clamp(k)
    return 1 - (1 - k) ** 2


EASINGS = {
    "linear": lambda k: clamp(k),
    "smooth": smooth_step,
    "ease": ease_in_out,
    "back": ease_out_back,
    "in": ease_in_quad,
    "out": ease_out_quad,
}


# --------------------------------------------------------------------------- #
# скелет
# --------------------------------------------------------------------------- #


@dataclass
class Bone:
    name: str
    parent: str | None = None
    length: float = 0.0
    # локальная поза (в системе родителя)
    angle: float = 0.0          # радианы, 0 = вправо
    origin: tuple[float, float] = (0.0, 0.0)
    scale: tuple[float, float] = (1.0, 1.0)
    # мировые значения — заполняются в solve()
    world_pos: tuple[float, float] = (0.0, 0.0)
    world_angle: float = 0.0
    world_scale: tuple[float, float] = (1.0, 1.0)


class Skeleton:
    """Иерархия костей с прямым кинематическим проходом."""

    def __init__(self, bones: Iterable[Bone] | None = None):
        self.bones: dict[str, Bone] = {}
        self.order: list[str] = []
        for b in bones or []:
            self.add(b)

    def add(self, bone: Bone) -> "Skeleton":
        self.bones[bone.name] = bone
        self.order.append(bone.name)
        return self

    def bone(self, name: str) -> Bone:
        return self.bones[name]

    def parent_world(self, name: str) -> tuple[tuple[float, float], float, tuple[float, float]]:
        """Мировые (позиция КОНЦА родительской кости, угол, масштаб).

        Скелетная конвенция: дочерняя кость начинается там, где заканчивается
        родительская. Раньше это не учитывалось — кости складывались в точку.
        """
        parent = self.bones[name].parent
        if parent is None:
            return (0.0, 0.0), 0.0, (1.0, 1.0)
        p = self.bones[parent]
        tail = (p.world_pos[0] + math.cos(p.world_angle) * p.length * p.world_scale[0],
                p.world_pos[1] + math.sin(p.world_angle) * p.length * p.world_scale[1])
        return tail, p.world_angle, p.world_scale

    def solve(self) -> "Skeleton":
        """FK-проход: мировые позиции из локальных поз."""
        for name in self.order:
            b = self.bones[name]
            (px, py), pa, ps = self.parent_world(name)
            cos_a, sin_a = math.cos(pa), math.sin(pa)
            ox, oy = b.origin
            # локальное смещение поворачивается системой родителя
            wx = px + (ox * ps[0]) * cos_a - (oy * ps[1]) * sin_a
            wy = py + (ox * ps[0]) * sin_a + (oy * ps[1]) * cos_a
            b.world_pos = (wx, wy)
            b.world_angle = pa + b.angle
            b.world_scale = (ps[0] * b.scale[0], ps[1] * b.scale[1])
        return self

    def tip(self, name: str) -> tuple[float, float]:
        """Концевая точка кости (позиция сустава на конце)."""
        b = self.bones[name]
        a = b.world_angle
        return (b.world_pos[0] + math.cos(a) * b.length * b.world_scale[0],
                b.world_pos[1] + math.sin(a) * b.length * b.world_scale[1])

    def set_pose(self, name: str, angle: float) -> None:
        self.bones[name].angle = angle

    def blend_pose(self, pose: dict[str, float], k: float,
                   easing: str = "ease") -> None:
        """Смешать текущие углы с целевой позой на долю k."""
        f = EASINGS[easing](k)
        for name, target in pose.items():
            if name in self.bones:
                self.bones[name].angle = lerp(self.bones[name].angle, target, f)


def solve_ik2(root: tuple[float, float],
              target: tuple[float, float],
              l1: float, l2: float,
              pole: tuple[float, float] = (0.0, -1.0)) -> tuple[float, float, float]:
    """Двухзвенный IK.

    Возвращает (угол_первого_звена, угол_второго_звена, достижимая_дальность).
    Поле pole задаёт, в какую сторону выгибается «локоть»/«колено»
    (0,-1) — вниз (рука), (0, 1) — вверх.

    Углы — мировые, в радианах, 0 = вправо.
    """
    (x0, y0) = root
    dx, dy = target[0] - x0, target[1] - y0
    dist = math.hypot(dx, dy)
    reach = l1 + l2
    if dist < 1e-6:
        return 0.0, 0.0, 0.0
    # за пределами досягаемости — тянемся по прямой, «не выворачиваясь»
    dist_c = clamp(dist, abs(l1 - l2) + 1e-4, reach - 1e-4)

    base_angle = math.atan2(dy, dx)

    # закон косинусов: угол между первым звеном и направлением на цель
    cos_a = (l1 * l1 + dist_c * dist_c - l2 * l2) / (2 * l1 * dist_c)
    a1 = math.acos(clamp(cos_a, -1.0, 1.0))
    # угол между звеном 1 и звеном 2
    cos_b = (l1 * l1 + l2 * l2 - dist_c * dist_c) / (2 * l1 * l2)
    b = math.acos(clamp(cos_b, -1.0, 1.0))

    # выбор стороны сгиба по полюсному вектору
    pole_angle = math.atan2(pole[1], pole[0])
    side = 1.0
    if math.cos(pole_angle - (base_angle + a1)) >= math.cos(pole_angle - (base_angle - a1)):
        side = -1.0

    angle1 = base_angle + side * a1
    angle2 = angle1 + side * (math.pi - b)
    return angle1, angle2, dist / reach


# --------------------------------------------------------------------------- #
# ключи и интерполяция
# --------------------------------------------------------------------------- #


@dataclass
class Key:
    t: float
    value: float
    ease: str = "ease"


class Track:
    """Канал одного параметра во времени."""

    def __init__(self, keys: Sequence[Key] | None = None, default: float = 0.0):
        self.keys: list[Key] = sorted(keys or [], key=lambda k: k.t)
        self.default = default

    def add(self, t: float, value: float, ease: str = "ease") -> "Track":
        self.keys.append(Key(t, value, ease))
        self.keys.sort(key=lambda k: k.t)
        return self

    def at(self, t: float) -> float:
        if not self.keys:
            return self.default
        if t <= self.keys[0].t:
            return self.keys[0].value
        if t >= self.keys[-1].t:
            return self.keys[-1].value
        for k0, k1 in zip(self.keys, self.keys[1:]):
            if k0.t <= t <= k1.t:
                span = max(k1.t - k0.t, 1e-6)
                k = (t - k0.t) / span
                f = EASINGS.get(k1.ease, ease_in_out)(k)
                return lerp(k0.value, k1.value, f)
        return self.keys[-1].value


# --------------------------------------------------------------------------- #
# вторичная анимация
# --------------------------------------------------------------------------- #


class Spring:
    """Пружинная цепочка: волосы, борода, капюшон, живот.

    Модель: масса на пружине с демпфированием, возбуждается ускорением корня.
    Так «вторичка» получается сама — не нужно ставить ей ключи.
    """

    def __init__(self, stiffness: float = 120.0, damping: float = 12.0,
                 gravity: float = 900.0, limit: float = 0.6):
        self.k = stiffness
        self.c = damping
        self.g = gravity
        self.limit = limit
        self.x = 0.0
        self.v = 0.0

    def reset(self) -> None:
        self.x = 0.0
        self.v = 0.0

    def step(self, dt: float, drive: float = 0.0) -> float:
        """drive — ускорение «корня» (например, смещение головы по X)."""
        accel = -self.k * self.x - self.c * self.v + self.g * drive
        self.v += accel * dt
        self.x += self.v * dt
        self.x = clamp(self.x, -self.limit, self.limit)
        return self.x

    def run(self, frames: int, fps: int, drives: Sequence[float]) -> list[float]:
        dt = 1.0 / fps
        out = []
        for i in range(frames):
            d = drives[i] if i < len(drives) else 0.0
            out.append(self.step(dt, d))
        return out


def damped_follow(values: Sequence[float], lag: float = 0.25) -> list[float]:
    """Простое «отставание» (follow-through) для вторичных элементов."""
    out, prev = [], values[0] if values else 0.0
    for v in values:
        prev = prev + (v - prev) * (1.0 - lag)
        out.append(prev)
    return out


# --------------------------------------------------------------------------- #
# движение по дуге и сквош-стретч
# --------------------------------------------------------------------------- #


def arc(p0: tuple[float, float], p1: tuple[float, float], k: float,
        bow: float = 0.18) -> tuple[float, float]:
    """Движение по дуге: линейная интерполяция + поперечное смещение."""
    k = clamp(k)
    x = lerp(p0[0], p1[0], k)
    y = lerp(p0[1], p1[1], k)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    n = math.hypot(dx, dy) or 1.0
    # нормаль к хорде
    nx, ny = -dy / n, dx / n
    bulge = math.sin(math.pi * k) * bow * n
    return x + nx * bulge, y + ny * bulge


def squash_stretch(impact: float, strength: float = 0.22) -> tuple[float, float]:
    """Возвращает (sx, sy) с сохранением объёма.

    impact: 0 — покой, 1 — максимальное сжатие по вертикали.
    """
    impact = clamp(impact)
    sy = 1.0 - strength * impact
    sx = 1.0 / sy
    # компенсируем «раздувание» по площади
    scale = 1.0 / math.sqrt(sx * sy)
    return sx * scale, sy * scale


def jump_curve(frames: int, height: float = 120.0, anticipation: int = 4) -> list[float]:
    """Траектория прыжка со сжатием перед отрывом.

    Возвращает смещение Y по кадрам (отрицательное — вверх).
    """
    out = []
    for i in range(frames):
        if i < anticipation:
            k = i / max(anticipation, 1)
            out.append(12.0 * ease_in_out(k))          # присед
            continue
        i2 = i - anticipation
        n = max(frames - anticipation, 1)
        k = i2 / n
        out.append(-4.0 * height * k * (1 - k))        # парабола вверх
    return out


# --------------------------------------------------------------------------- #
# утилиты для рендера
# --------------------------------------------------------------------------- #


def blink_times(duration: float, avg_interval: float = 3.2,
                seed: int = 1) -> list[float]:
    """Расписание мигания: 2–4 раза за 10 с, не чаще 0.6 с."""
    import random
    rnd = random.Random(seed)
    times, t = [], rnd.uniform(0.6, 1.4)
    while t < duration:
        times.append(t)
        t += max(0.6, rnd.gauss(avg_interval, 0.7))
    return times


def visemes_for_text(text: str) -> list[tuple[str, int]]:
    """Грубая машина визем для русского: возвращает (визема, вес).

    Правила упрощены: важны читаемость и «не судорога», а не точная фонетика.
    """
    vowels = {"а": "A", "о": "O", "у": "U", "ы": "I", "и": "I", "э": "E",
              "е": "E", "ё": "O", "ю": "U", "я": "A"}
    cons_m = "мьбп"
    cons_f = "фв"
    cons_l = "лр"
    out: list[tuple[str, int]] = []
    for ch in text.lower():
        if ch in vowels:
            out.append((vowels[ch], 3))
        elif ch in cons_m:
            out.append(("M", 2))
        elif ch in cons_f:
            out.append(("F", 2))
        elif ch in cons_l:
            out.append(("L", 2))
        elif ch.isalpha():
            out.append(("C", 1))     # нейтральная согласная
        elif ch in " ,.!?…—":
            out.append(("M", 2))     # пауза = закрытый рот
    return out
