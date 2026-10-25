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
    # статика: rest-угол (поза сборки), группа пропорций и толщина для рендера
    rest: float = 0.0
    group: str = "root"
    width: float = 1.0
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

    def reset_pose(self) -> "Skeleton":
        """Вернуть все кости в rest-позу (поза сборки)."""
        for b in self.bones.values():
            b.angle = b.rest
            b.origin = (0.0, 0.0) if b.name == "root" else b.origin
        self.solve()
        return self

    def capture(self, round_to: int = 1) -> dict[str, float]:
        """Снять текущую позу как отклонения от rest в ГРАДУСАХ (для сохранения)."""
        out: dict[str, float] = {}
        for name, b in self.bones.items():
            delta = math.degrees(b.angle - b.rest)
            if abs(delta) >= 10 ** (-round_to):
                out[name] = round(delta, round_to)
        return out

    def mirror(self) -> "Skeleton":
        """Зеркалить текущую позу (стороны меняются, углы отражаются)."""
        pairs = [(n, n[:-2] + ".l" if n.endswith(".r") else n[:-2] + ".r")
                 for n in self.bones if n.endswith((".r", ".l"))]
        snapshot = {n: self.bones[n].angle - self.bones[n].rest for n, _ in pairs}
        for n, other in pairs:
            if other in self.bones:
                self.bones[n].angle = self.bones[n].rest - snapshot[other]
        self.solve()
        return self

    def to_dict(self) -> dict:
        return {"bones": [
            {"name": b.name, "parent": b.parent, "length": b.length,
             "angle": b.angle, "origin": list(b.origin), "scale": list(b.scale),
             "rest": b.rest, "group": b.group, "width": b.width}
            for b in (self.bones[n] for n in self.order)]}

    @classmethod
    def from_dict(cls, data: dict) -> "Skeleton":
        sk = cls()
        for b in data["bones"]:
            sk.add(Bone(b["name"], b.get("parent"), b.get("length", 0.0),
                        b.get("angle", 0.0), tuple(b.get("origin", (0, 0))),
                        tuple(b.get("scale", (1, 1))), b.get("rest", 0.0),
                        b.get("group", "root"), b.get("width", 1.0)))
        sk.solve()
        return sk

    def bounds(self) -> tuple[float, float, float, float]:
        """Габариты скелета в его единицах: (x0, y0, x1, y1) по костям и стопам."""
        xs, ys = [], []
        for name in self.order:
            b = self.bones[name]
            xs.append(b.world_pos[0])
            ys.append(b.world_pos[1])
            tx, ty = self.tip(name)
            xs.append(tx)
            ys.append(ty)
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs), max(ys)

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
              pole: tuple[float, float] = (0.0, 1.0)) -> tuple[float, float, float]:
    """Двухзвенный IK.

    Возвращает (угол_первого_звена, угол_второго_звена, достижимость 0..1).
    Углы мировые, в радианах, 0 = вправо, +pi/2 = вниз.

    Реализация через позицию локтя: считаем два положения локтя (по часовой и
    против), выбираем то, что лежит со стороны полюсного вектора, и направляем
    второе звено ровно в цель. Так не бывает «вывернутых» локтей и промахов,
    которые возникали при знаковой формуле.
    """
    (x0, y0) = root
    dx, dy = target[0] - x0, target[1] - y0
    dist = math.hypot(dx, dy)
    reach = max(l1 + l2, 1e-6)
    if dist < 1e-6:
        return 0.0, 0.0, 0.0

    d = clamp(dist, abs(l1 - l2) + 1e-4, reach - 1e-4)
    base = math.atan2(dy, dx)
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    a = math.acos(clamp(cos_a, -1.0, 1.0))

    candidates = []
    for sign in (1.0, -1.0):
        ang = base + sign * a
        ex, ey = x0 + math.cos(ang) * l1, y0 + math.sin(ang) * l1
        # насколько локоть «с той же стороны» от линии до цели, что и полюс
        cross_line = dx * (ey - y0) - dy * (ex - x0)
        cross_pole = dx * pole[1] - dy * pole[0]
        alignment = cross_line * cross_pole
        err = math.hypot(target[0] - ex, target[1] - ey)
        candidates.append((alignment, -err, ang, (ex, ey)))

    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    _align, _neg_err, a1, elbow = candidates[0]
    a2 = math.atan2(target[1] - elbow[1], target[0] - elbow[0])
    return a1, a2, min(dist / reach, 1.0)


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


# --------------------------------------------------------------------------- #
# сборка человечка из профиля (данные, а не хардкод)
# --------------------------------------------------------------------------- #


def head_diameter(sk: Skeleton) -> float:
    """Диаметр головы в единицах скелета (то, в чём меряется рост «в головах»)."""
    b = sk.bones.get("head")
    return 2.0 * b.length * HEAD_RADIUS_K if b else 1.0


HEAD_RADIUS_K = 1.05      # радиус черепа относительно длины кости головы (см. puppet)


def build_humanoid(height_heads: float = 6.5,
                   proportions: dict | None = None,
                   rig_id: str = "humanoid_v1") -> Skeleton:
    """Собрать скелет по профилю `library/rigs.json`.

    Главное правило: **голова не масштабируется** — она задаёт единицу. Тело
    подгоняется так, чтобы рост в головах был ровно `height_heads`. Поэтому
    ребёнок (5.5 голов) автоматически получает крупную голову и короткие ноги,
    а взрослый (6.5) — обычные пропорции, без ручной подгонки длин.

    proportions — множители групп: {"leg": 1.05, "arm": 0.95, "torso": 1.0, "head": 0.95}.
    """
    import library as L

    profile = L.rig_profile(rig_id)
    props = {"leg": 1.0, "arm": 1.0, "torso": 1.0, "head": 1.0}
    props.update({k: float(v) for k, v in (proportions or {}).items()
                  if k in ("leg", "arm", "torso", "head")})

    def assemble(body_scale: float) -> Skeleton:
        sk = Skeleton()
        for spec in profile["bones"]:
            group = spec.get("group", "root")
            mult = props.get(group, 1.0) if group in props else 1.0
            if group != "head":
                mult *= body_scale
            rest = math.radians(spec.get("rest", 0.0))
            origin = spec.get("origin", (0.0, 0.0))
            sk.add(Bone(
                name=spec["name"], parent=spec.get("parent"),
                length=spec.get("length", 0.0) * mult,
                angle=rest,
                origin=(origin[0] * mult, origin[1] * mult),
                rest=rest, group=group, width=spec.get("width", 1.0),
            ))
        sk.solve()
        return sk

    # тело линейно зависит от body_scale, поэтому двух замеров достаточно
    h1 = stature(assemble(1.0))
    h2 = stature(assemble(2.0))
    slope = h2 - h1
    target = max(head_diameter(assemble(1.0)) * height_heads, 1e-6)
    body_scale = 1.0 + (target - h1) / slope if abs(slope) > 1e-9 else 1.0
    body_scale = clamp(body_scale, 0.25, 4.0)
    return assemble(body_scale)


def stature(sk: Skeleton) -> float:
    """Рост персонажа в единицах скелета: от ступней до макушки.

    Y растёт вниз, поэтому низ — максимум Y, верх — конец кости `head` минус
    полголовы (череп выше оси кости).
    """
    ys = []
    for name in sk.order:
        ys.append(sk.bones[name].world_pos[1])
        ys.append(sk.tip(name)[1])
    if not ys:
        return 1e-6
    bottom = max(ys)
    top = min(ys)
    if "head" in sk.bones:
        top = sk.tip("head")[1] - sk.bones["head"].length * HEAD_RADIUS_K
    return max(bottom - top, 1e-6)


def apply_pose(sk: Skeleton, pose: str | dict, weight: float = 1.0,
               additive: bool = False, reset: bool = True) -> Skeleton:
    """Поставить позу из библиотеки (или словарь) на скелет.

    pose   — id позы ('wave') либо {"bones": {...}, "root": [dx, dy]}.
    weight — сила позы 0..1, удобно для переходов между позами.
    additive — наложить поверх текущей позы (для дыхания и «слоёв»).
    reset  — сначала вернуть rest-позу, чтобы поза не «накапливалась».
    """
    import library as L

    data = L.pose(pose) if isinstance(pose, str) else pose
    if reset and not additive:
        sk.reset_pose()

    for name, degrees in (data.get("bones") or {}).items():
        b = sk.bones.get(name)
        if b is None:
            raise KeyError(f"в скелете нет кости '{name}' (поза просит её повернуть)")
        delta = math.radians(float(degrees)) * weight
        b.angle = (b.angle + delta) if additive else (b.rest + delta)

    root = data.get("root")
    if root and weight > 0:
        rb = sk.bones.get("root")
        if rb is not None:
            dx, dy = root
            if additive or not reset:
                rb.origin = (rb.origin[0] + dx * weight, rb.origin[1] + dy * weight)
            else:
                rb.origin = (dx * weight, dy * weight)
    sk.solve()
    return sk


def pose_graph(sk: Skeleton, poses: Sequence[str], k: float) -> Skeleton:
    """Переход между позами: k=0 — первая, k=1 — последняя (по индексу в списке)."""
    import library as L

    if not poses:
        return sk
    n = len(poses) - 1
    pos = clamp(k) * n
    i = min(int(pos), max(n - 1, 0))
    local = pos - i
    a = L.pose(poses[i])
    b = L.pose(poses[min(i + 1, n)])

    def val(p: dict, bone: str) -> float:
        return float((p.get("bones") or {}).get(bone, 0.0))

    for name, bb in sk.bones.items():
        bb.angle = bb.rest + math.radians(lerp(val(a, name), val(b, name), local))
    ra = a.get("root", [0.0, 0.0])
    rb_ = b.get("root", [0.0, 0.0])
    sk.bones["root"].origin = (lerp(ra[0], rb_[0], local), lerp(ra[1], rb_[1], local))
    sk.solve()
    return sk


def look_at(sk: Skeleton, target: tuple[float, float], weight: float = 1.0,
            max_deg: float = 18.0, bones: Sequence[str] = ("neck", "head")) -> Skeleton:
    """Повернуть шею/голову в сторону цели (взгляд в собеседника, на предмет)."""
    for name in bones:
        b = sk.bones.get(name)
        if b is None:
            continue
        sk.solve()                     # мировые координаты актуальны на каждом шаге
        want = math.atan2(target[1] - b.world_pos[1], target[0] - b.world_pos[0])
        delta = math.atan2(math.sin(want - b.world_angle), math.cos(want - b.world_angle))
        limit = math.radians(max_deg)
        delta = clamp(delta, -limit, limit)
        b.angle += delta * weight
    sk.solve()
    return sk


def foot_ik(sk: Skeleton, side: str, target: tuple[float, float],
            pole: tuple[float, float] = (1.0, 0.0)) -> Skeleton:
    """Поставить стопу в точку: колено считается IK (не «ломается» при шаге и приседе)."""
    sk.solve()
    thigh = sk.bones[f"thigh.{side}"]
    shin = sk.bones[f"shin.{side}"]
    root = thigh.world_pos
    a1, a2, _ = solve_ik2(root, target, thigh.length, shin.length, pole=pole)
    thigh.angle = a1 - sk.parent_world(thigh.name)[1]
    shin.angle = a2 - a1
    return sk.solve()


def hand_ik(sk: Skeleton, side: str, target: tuple[float, float],
            pole: tuple[float, float] | None = None) -> Skeleton:
    """Дотянуть кисть до цели: локоть решается IK. Цель — мировые координаты."""
    sk.solve()
    upper = sk.bones[f"upper_arm.{side}"]
    fore = sk.bones[f"forearm.{side}"]
    if pole is None:
        pole = (0.0, 1.0) if side == "r" else (0.0, -1.0)
    a1, a2, _ = solve_ik2(upper.world_pos, target, upper.length, fore.length, pole=pole)
    upper.angle = a1 - sk.parent_world(upper.name)[1]
    sk.solve()
    fore.angle = a2 - a1
    return sk.solve()
