"""Программный 3D-рендерер (numpy): объём, свет, скиннинг — без внешних зависимостей.

Зачем свой
----------
Blender в песочнице не запускается (bpy требует системных X11-библиотек, apt
недоступен), а нужен именно ОБЪЁМ: сетка в 3D, честная деформация по костям,
нормали и свет. Поэтому здесь маленький, но настоящий растеризатор:

* треугольники с z-буфером (перекрытия честные, не «порядок слоёв»);
* пер-вершинные нормали + интерполяция по барицентрике;
* свет: заполняющий «небесный»/«земляной» (hemisphere), ключевой с wrap-диффузом
  (мягкий переход как в стилизованном 3D), контровой rim;
* пер-вершинное AO (запекается грубо по «складкам» геометрии), чтобы под
  подбородком и в подмышке не было пластиковой плоскости;
* суперсэмплинг (ss) с уменьшением → сглаженные края без «лесенки»;
* RGBA-выход с прозрачным фоном — кадр сразу кладётся на сцену.

Производительность: растеризация батчами по размеру треугольника (как в
`toon.py`): мелкие треугольники не тянут за собой буфер на весь кадр.

Стиль: никакой фотореалистичности. Диффуз с wrap-освещением, тёплый ключевой
свет, синеватый подсвет снизу — это и даёт «объёмную» картинку стиля B.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# --------------------------------------------------------------------------- #
# сетка
# --------------------------------------------------------------------------- #

@dataclass
class Mesh:
    """Треугольная сетка: вершины, треугольники, нормали и цвет вершин."""

    verts: np.ndarray                  # (N, 3) float64
    tris: np.ndarray                   # (M, 3) int32
    normals: np.ndarray | None = None  # (N, 3); None → считаем гладкие
    color: np.ndarray | np.ndarray | None = None   # (N,3) или (3,)
    ao: np.ndarray | None = None       # (N,) 0..1, пер-вершинная затенённость
    rough: float = 1.0                 # 0 — глянец, 1 — матовый (для блика)
    cull: bool = True                  # отсекать задние грани (для открытых — False)
    name: str = ""

    def __post_init__(self) -> None:
        self.verts = np.asarray(self.verts, np.float64)
        self.tris = np.asarray(self.tris, np.int32)
        if self.normals is None:
            self.normals = vertex_normals(self.verts, self.tris)
        else:
            self.normals = np.asarray(self.normals, np.float64)
        if self.color is None:
            self.color = np.array([0.8, 0.8, 0.8])
        self.color = np.asarray(self.color, np.float64)
        if self.ao is None:
            self.ao = np.ones(len(self.verts))
        self.ao = np.asarray(self.ao, np.float64)

    def copy(self) -> "Mesh":
        return Mesh(self.verts.copy(), self.tris.copy(), self.normals.copy(),
                    self.color.copy(), self.ao.copy(), self.rough, self.cull, self.name)

    def transformed(self, m: np.ndarray) -> "Mesh":
        """Аффинное преобразование (4×4). Нормали — по обратно-транспонированной."""
        out = self.copy()
        v = np.c_[self.verts, np.ones(len(self.verts))] @ np.asarray(m).T
        out.verts = v[:, :3] / v[:, 3:4]
        n = np.asarray(m, np.float64)[:3, :3]
        try:
            nm = np.linalg.inv(n).T
        except np.linalg.LinAlgError:
            nm = np.eye(3)
        nn = out.normals @ nm.T
        out.normals = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
        return out

    def volume(self) -> float:
        """Знаковый объём замкнутой сетки: > 0 — обход наружу, < 0 — внутрь."""
        c = self.verts.mean(axis=0)
        v0, v1, v2 = (self.verts[self.tris[:, k]] - c for k in range(3))
        return float(np.einsum("ij,ij->i", v0, np.cross(v1, v2)).sum() / 6.0)

    def orient_outward(self) -> "Mesh":
        """Гарантировать наружный обход и наружные нормали (для замкнутых тел).

        Это защита от целого класса багов: если нормали смотрят внутрь, то
        отсечение задних граней оставляет ИЗНАНКУ — тело выглядит полупрозрачным
        «призраком» с внутренними рёбрами. Проверка по знаку объёма не зависит
        от того, как именно был сгенерирован меш.
        """
        if self.volume() < 0:
            self.tris = self.tris[:, ::-1].copy()
            self.normals = vertex_normals(self.verts, self.tris)
        return self

    def flipped(self) -> "Mesh":
        """Вывернуть нормали (для внутренних полостей — рот, веки)."""
        out = self.copy()
        out.tris = out.tris[:, ::-1].copy()
        out.normals = -out.normals
        return out


def vertex_normals(verts: np.ndarray, tris: np.ndarray) -> np.ndarray:
    """Гладкие нормали: сумма по площадям примыкающих треугольников."""
    v0, v1, v2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    fn = np.cross(v1 - v0, v2 - v0)
    n = np.zeros_like(verts)
    for k in range(3):
        np.add.at(n, tris[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.maximum(ln, 1e-12)


def merge(meshes: list[Mesh]) -> Mesh:
    """Склеить несколько мешей в один (для одного прохода растеризации)."""
    meshes = [m for m in meshes if m is not None and len(m.tris)]
    if not meshes:
        raise ValueError("нечего склеивать: пустой список мешей")
    verts, tris, nrm, col, ao, rough, cull = [], [], [], [], [], [], []
    off = 0
    for m in meshes:
        verts.append(m.verts)
        tris.append(m.tris + off)
        nrm.append(m.normals)
        c = np.asarray(m.color, np.float64)
        col.append(np.broadcast_to(c, (len(m.verts), 3)) if c.ndim == 1 else c)
        ao.append(np.broadcast_to(m.ao, (len(m.verts),)))
        rough.append(np.full(len(m.tris), float(m.rough)))
        cull.append(np.full(len(m.tris), bool(m.cull)))
        off += len(m.verts)
    out = Mesh(np.vstack(verts), np.vstack(tris), np.vstack(nrm),
               np.vstack(col), np.concatenate(ao), name="+".join(m.name for m in meshes))
    out._cull_mask = np.concatenate(cull)
    return out


# --------------------------------------------------------------------------- #
# примитивы
# --------------------------------------------------------------------------- #

def sphere(radius: float = 1.0, seg: int = 24, rings: int = 16,
           center=(0, 0, 0), scale=(1, 1, 1)) -> Mesh:
    """Сфера (UV-развёртка). Основа головы, глаз, носа, суставов."""
    u = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    v = np.linspace(0, math.pi, rings)
    uu, vv = np.meshgrid(u, v, indexing="ij")
    x = np.sin(vv) * np.cos(uu)
    y = np.cos(vv)
    z = np.sin(vv) * np.sin(uu)
    verts = np.stack([x, y, z], -1).reshape(-1, 3) * np.asarray(scale) * radius
    verts += np.asarray(center, np.float64)

    def idx(i, j):
        return (i % seg) * rings + j

    tris = []
    for i in range(seg):
        for j in range(rings - 1):
            a, b = idx(i, j), idx(i + 1, j)
            c, d = idx(i + 1, j + 1), idx(i, j + 1)
            tris.append((a, c, b))
            tris.append((a, d, c))
    tri = np.array(tris, np.int32)
    m = Mesh(verts, tri).orient_outward()
    # у полюсов нормали вырождаются — поправим на радиальные
    rad = (m.verts - np.asarray(center, np.float64)) * np.sign(radius or 1.0)
    ln = np.linalg.norm(rad, axis=1, keepdims=True)
    m.normals = np.where(ln > 1e-9, rad / np.maximum(ln, 1e-12), m.normals)
    return m


def capsule(radius: float = 0.2, length: float = 1.0, seg: int = 16, rings: int = 12,
            r_top: float | None = None) -> Mesh:
    """Капсула вдоль +Y от 0 до length; r_top — конусность (рука к запястью)."""
    r_top = radius if r_top is None else r_top
    y = np.linspace(0, length, rings)
    t = y / max(length, 1e-9)
    r = radius + (r_top - radius) * t
    u = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    uu, tt = np.meshgrid(u, t, indexing="ij")
    rr = (radius + (r_top - radius) * tt)
    verts = np.stack([rr * np.cos(uu), tt * length, rr * np.sin(uu)], -1).reshape(-1, 3)
    # скруглённые торцы
    cap_n = max(4, seg // 2)
    caps = []
    for sign, y0, rr0 in ((+1.0, length, r_top), (-1.0, 0.0, radius)):
        for k in range(1, cap_n + 1):
            ang = (math.pi / 2) * (1 - k / (cap_n + 1))
            yy = y0 + sign * rr0 * math.cos(ang)
            rad = rr0 * math.sin(ang)
            caps.append(np.stack([rad * np.cos(u), np.full(seg, yy),
                                  rad * np.sin(u)], -1))
    # полюса: без них торец остаётся открытым кольцом — по краю капсулы
    # появляется рваная «гребёнка» из щелей
    poles = np.array([[0.0, length + r_top, 0.0], [0.0, -radius, 0.0]])
    allv = np.vstack([verts] + [c.reshape(-1, 3) for c in caps] + [poles])
    n_body = seg * rings
    cap_pts = cap_n * seg
    pole_top = len(allv) - 2
    pole_bot = len(allv) - 1

    def bid(i, j):
        return (i % seg) * rings + j

    tris = []
    for i in range(seg):
        for j in range(rings - 1):
            a, b = bid(i, j), bid(i + 1, j)
            c, d = bid(i + 1, j + 1), bid(i, j + 1)
            tris.append((a, b, c))
            tris.append((a, c, d))
    # верхний купол
    for k in range(cap_n - 1):
        for i in range(seg):
            a = n_body + k * seg + i
            b = n_body + k * seg + (i + 1) % seg
            c = n_body + (k + 1) * seg + (i + 1) % seg
            d = n_body + (k + 1) * seg + i
            tris += [(a, b, c), (a, c, d)]
    # нижний купол (обратный порядок)
    base = n_body + cap_pts
    for k in range(cap_n - 1):
        for i in range(seg):
            a = base + k * seg + i
            b = base + k * seg + (i + 1) % seg
            c = base + (k + 1) * seg + (i + 1) % seg
            d = base + (k + 1) * seg + i
            tris += [(a, c, b), (a, d, c)]
    # веера к полюсам
    top_ring = n_body + (cap_n - 1) * seg
    bot_ring = base + (cap_n - 1) * seg
    for i in range(seg):
        tris.append((pole_top, top_ring + i, top_ring + (i + 1) % seg))
        tris.append((pole_bot, bot_ring + (i + 1) % seg, bot_ring + i))
    return Mesh(allv, np.array(tris, np.int32)).orient_outward()


def loft(sections: list[dict], seg: int = 32, caps: bool = True) -> Mesh:
    """Непрерывная «оболочка» через набор поперечных сечений.

    Сечение: {"y": высота, "rx": радиус по X, "rz": радиус по Z,
              "cx": сдвиг по X (по умолчанию 0), "cz": сдвиг по Z}.

    Зачем вместо склеенных капсул: две почти одинаковые поверхности, вложенные
    друг в друга, дают z-fighting — «шахматку» на стыке. Одно непрерывное тело
    с корректными нормалями такой проблемы не имеет и выглядит как объём, а не
    как набор колбас.
    """
    ys = [float(s["y"]) for s in sections]
    rows = []
    for s in sections:
        u = np.linspace(0, 2 * math.pi, seg, endpoint=False)
        rx, rz = float(s["rx"]), float(s["rz"])
        cx, cz = float(s.get("cx", 0.0)), float(s.get("cz", 0.0))
        rows.append(np.stack([cx + rx * np.cos(u), np.full(seg, float(s["y"])),
                              cz + rz * np.sin(u)], -1))
    body = np.vstack(rows)
    n = len(sections)

    def vid(i, j):
        # вершины сложены по сечениям: индекс = сечение * seg + точка по кругу
        return j * seg + (i % seg)

    tris = []
    for j in range(n - 1):
        for i in range(seg):
            a, b = vid(i, j), vid(i + 1, j)
            c, d = vid(i + 1, j + 1), vid(i, j + 1)
            tris += [(a, b, c), (a, c, d)]
    verts = [body]
    extra = []
    if caps:
        for s, flip in ((sections[0], True), (sections[-1], False)):
            pole = np.array([[float(s.get("cx", 0.0)), float(s["y"]),
                              float(s.get("cz", 0.0))]])
            extra.append(pole)
    allv = np.vstack(verts + extra) if extra else body
    if caps:
        bot = len(body)
        top = len(body) + 1
        for i in range(seg):
            tris.append((bot, vid(i + 1, 0), vid(i, 0)))
            tris.append((top, vid(i, n - 1), vid(i + 1, n - 1)))
    return Mesh(allv, np.array(tris, np.int32)).orient_outward()


def tube(points, radii, seg: int = 24, round_caps: bool = True,
         cap_rings: int = 4) -> Mesh:
    """Непрерывная труба переменного радиуса по ломаной (руки, ноги, шея).

    В отличие от набора капсул, у трубы нет внутренних стыков: одна оболочка,
    одни нормали, никакого z-fighting в местах соединения сегментов.
    Стыки направляются параллельным переносом (parallel transport), поэтому
    труба не «закручивается» на изгибах.
    """
    pts = np.asarray(points, np.float64)
    rad = np.broadcast_to(np.asarray(radii, np.float64), (len(pts),))
    n = len(pts)
    if n < 2:
        raise ValueError("tube: нужно минимум 2 точки")

    # касательные: центральные разности, концы — односторонние
    tang = np.zeros_like(pts)
    tang[0] = pts[1] - pts[0]
    tang[-1] = pts[-1] - pts[-2]
    if n > 2:
        tang[1:-1] = pts[2:] - pts[:-2]
    tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-12)

    # параллельный перенос опорного вектора
    ref = np.array([0.0, 0.0, 1.0]) if abs(tang[0][1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = ref - tang[0] * float(ref @ tang[0])
    u /= max(np.linalg.norm(u), 1e-12)
    frames_u = []
    for i in range(n):
        u = u - tang[i] * float(u @ tang[i])
        nu = np.linalg.norm(u)
        if nu < 1e-9:                                  # вырожденный случай
            alt = np.array([1.0, 0.0, 0.0]) if abs(tang[i][1]) > 0.9 else np.array([0.0, 1.0, 0.0])
            u = alt - tang[i] * float(alt @ tang[i])
            nu = max(np.linalg.norm(u), 1e-12)
        u = u / nu
        frames_u.append(u.copy())
    ang = np.linspace(0.0, 2 * math.pi, seg, endpoint=False)

    def ring(center, uu, vv, r):
        return center + r * (np.cos(ang)[:, None] * uu + np.sin(ang)[:, None] * vv)

    rows = []
    if round_caps:
        for k in range(cap_rings, 0, -1):
            phi = (math.pi / 2) * k / (cap_rings + 1)
            c = pts[0] - tang[0] * rad[0] * math.sin(phi)
            rows.append(ring(c, frames_u[0], np.cross(tang[0], frames_u[0]),
                             rad[0] * math.cos(phi)))
    for i in range(n):
        v = np.cross(tang[i], frames_u[i])
        rows.append(ring(pts[i], frames_u[i], v, rad[i]))
    if round_caps:
        for k in range(1, cap_rings + 1):
            phi = (math.pi / 2) * k / (cap_rings + 1)
            c = pts[-1] + tang[-1] * rad[-1] * math.sin(phi)
            rows.append(ring(c, frames_u[-1], np.cross(tang[-1], frames_u[-1]),
                             rad[-1] * math.cos(phi)))

    verts = np.vstack(rows)
    nr = len(rows)
    idx = np.arange(seg)
    tris = []
    for j in range(nr - 1):
        a = j * seg + idx
        b = (j + 1) * seg + idx
        an = j * seg + (idx + 1) % seg
        bn = (j + 1) * seg + (idx + 1) % seg
        tris.append(np.stack([a, b, bn], 1))
        tris.append(np.stack([a, bn, an], 1))
    tris = np.vstack(tris)
    if round_caps:
        # полюса
        p0 = pts[0] - tang[0] * (rad[0] * 1.0001)
        p1 = pts[-1] + tang[-1] * (rad[-1] * 1.0001)
        verts = np.vstack([verts, p0[None], p1[None]])
        i0, i1 = len(verts) - 2, len(verts) - 1
        top, bot = 0, (nr - 1) * seg
        for k in range(seg):
            tris = np.vstack([tris, [[i0, top + k, top + (k + 1) % seg]]])
            tris = np.vstack([tris, [[i1, bot + (k + 1) % seg, bot + k]]])
    return Mesh(verts, np.asarray(tris, np.int32)).orient_outward()


def roundbox(size=(1, 1, 1), center=(0, 0, 0), roundness: float = 4.0,
             seg: int = 32, rings: int = 18) -> Mesh:
    """Скруглённый параллелепипед (суперэллипсоид) — обувь, коробки, детали.

    Резкие рёбра куба в стиле B смотрятся «пластиково», поэтому базовая форма —
    суперэллипсоид: чем больше `roundness`, тем ближе к кубу.
    """
    if roundness <= 2.0:
        raise ValueError("roundness должно быть > 2")
    e = 2.0 / roundness
    th = np.linspace(-math.pi / 2, math.pi / 2, rings)
    ph = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    TH, PH = np.meshgrid(th, ph, indexing="ij")

    def sg(x):
        return np.sign(x) * np.abs(x) ** e

    x = sg(np.cos(TH)) * sg(np.cos(PH)) * size[0] / 2
    y = sg(np.sin(TH)) * size[1] / 2
    z = sg(np.cos(TH)) * sg(np.sin(PH)) * size[2] / 2
    verts = np.stack([x.ravel(), y.ravel(), z.ravel()], 1)
    # полюса сплющиваются сами: на |sin(th)|=1 кольцо вырождается в точку
    verts = verts + np.asarray(center, np.float64)
    tris = []
    for j in range(rings - 1):
        for i in range(seg):
            a = j * seg + i
            b = j * seg + (i + 1) % seg
            c = (j + 1) * seg + (i + 1) % seg
            d = (j + 1) * seg + i
            tris += [(a, b, c), (a, c, d)]
    return Mesh(verts, np.asarray(tris, np.int32)).orient_outward()


def box(size=(1, 1, 1), center=(0, 0, 0)) -> Mesh:
    sx, sy, sz = (s / 2 for s in size)
    v = np.array([[-sx, -sy, -sz], [sx, -sy, -sz], [sx, sy, -sz], [-sx, sy, -sz],
                  [-sx, -sy, sz], [sx, -sy, sz], [sx, sy, sz], [-sx, sy, sz]],
                 np.float64) + np.asarray(center, np.float64)
    f = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7],
                  [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                  [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], np.int32)
    return Mesh(v, f).orient_outward()


# --------------------------------------------------------------------------- #
# камера и свет
# --------------------------------------------------------------------------- #

@dataclass
class Camera:
    """Перспективная камера. Смотрит из eye в target, up — «верх» кадра."""

    eye: tuple = (0.0, 0.0, 5.0)
    target: tuple = (0.0, 0.0, 0.0)
    up: tuple = (0.0, 1.0, 0.0)
    fov: float = 32.0                  # по вертикали, градусы
    near: float = 0.05
    far: float = 100.0

    def view_matrix(self) -> np.ndarray:
        eye = np.asarray(self.eye, np.float64)
        tgt = np.asarray(self.target, np.float64)
        up = np.asarray(self.up, np.float64)
        f = tgt - eye
        f /= max(np.linalg.norm(f), 1e-9)
        s = np.cross(f, up)
        s /= max(np.linalg.norm(s), 1e-9)
        u = np.cross(s, f)
        m = np.eye(4)
        m[0, :3], m[1, :3], m[2, :3] = s, u, -f
        m[:3, 3] = -m[:3, :3] @ eye
        return m

    def projection(self, aspect: float) -> np.ndarray:
        f = 1.0 / math.tan(math.radians(self.fov) / 2.0)
        n, fa = self.near, self.far
        m = np.zeros((4, 4))
        m[0, 0] = f / max(aspect, 1e-9)
        m[1, 1] = f
        m[2, 2] = (fa + n) / (n - fa)
        m[2, 3] = 2 * fa * n / (n - fa)
        m[3, 2] = -1.0
        return m


@dataclass
class Lights:
    """Три источника, которых достаточно для стилизованного объёма."""

    key_dir: tuple = (-0.45, 0.75, 0.65)     # от камеры слева сверху
    key_color: tuple = (1.0, 0.97, 0.92)
    key_power: float = 0.62
    fill_dir: tuple = (0.75, 0.15, 0.35)     # холодный подсвет справа
    fill_color: tuple = (0.62, 0.72, 0.95)
    fill_power: float = 0.20
    rim_dir: tuple = (0.35, 0.55, -0.75)     # контровой сзади
    rim_color: tuple = (1.0, 0.96, 0.88)
    rim_power: float = 0.26
    sky: tuple = (0.86, 0.90, 1.0)           # «небо» сверху
    ground: tuple = (0.62, 0.56, 0.52)       # отражения снизу
    wrap: float = 0.38                        # мягкость терминатора
    ambient: float = 0.30
    # мягкий «фонарь от камеры»: без него вид сзади уходил в чёрный силуэт,
    # хотя сцена та же. Это не заливка в упор — всего 18% яркости ключевого.
    camera_fill: float = 0.20


# --------------------------------------------------------------------------- #
# растеризация
# --------------------------------------------------------------------------- #

def _trans(x: float = 0.0, y: float = 0.0, z: float = 0.0) -> np.ndarray:
    """Матрица переноса 4×4."""
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _rot_x(a: float) -> np.ndarray:
    """Поворот вокруг оси X на угол `a` (радианы)."""
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]])


def _rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1]])


def _rot_z(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]])


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, np.float64)
    return v / max(np.linalg.norm(v), 1e-12)


def _shade(n: np.ndarray, albedo: np.ndarray, ao: np.ndarray,
           L: Lights, view: np.ndarray, rough: np.ndarray | None = None) -> np.ndarray:
    """`view` — направление из камеры в точку; `rough` — шероховатость 0..1.

    Без блика материал читается «пластилиновым»: у кожи, губ, глаз и обуви в
    референсе есть мягкое отражение ключевого света. Поэтому здесь
    Blinn-Phong с шириной, зависящей от шероховатости (шерсть/худи — матовые,
    кожа и глаза — с мягким бликом).
    """
    n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    up = n[:, 1:2] * 0.5 + 0.5
    amb = (np.asarray(L.sky) * up + np.asarray(L.ground) * (1 - up)) * L.ambient
    amb = amb * ao[:, None]

    def lam(direction):
        d = _normalize(direction)
        ndl = n @ d
        w = L.wrap
        return np.clip((ndl + w) / (1 + w), 0.0, 1.0)

    key = lam(L.key_dir)[:, None] * np.asarray(L.key_color) * L.key_power
    fill = lam(L.fill_dir)[:, None] * np.asarray(L.fill_color) * L.fill_power
    vdir = _normalize(view[0])
    # view — направление ИЗ камеры в точку, значит свет «у камеры» = −view.
    # (Перепутанный знак давал ровно обратное: вид сзади чернел.)
    cam_light = lam(-vdir)[:, None] * np.asarray(L.key_color) * L.camera_fill
    rim = np.clip(1.0 - np.abs(n @ vdir), 0, 1) ** 3.0
    rim = (rim * L.rim_power)[:, None] * np.asarray(L.rim_color)
    lit = albedo * (amb + key + fill + cam_light) + rim

    if rough is not None:
        # блик: половинный вектор между светом и наблюдателем
        h = L.key_dir - vdir
        h = h / max(float(np.linalg.norm(h)), 1e-9)
        spec = np.clip(n @ h, 0.0, 1.0) ** (4.0 + 140.0 * (1.0 - rough) ** 2)
        gain = 0.30 * (1.0 - rough) ** 1.6
        lit = lit + (spec * gain)[:, None] * np.asarray(L.key_color)
        # узкая «искра» от контрового света: оживляет контур головы и плеч
        h2 = L.rim_dir - vdir
        h2 = h2 / max(float(np.linalg.norm(h2)), 1e-9)
        spec2 = np.clip(n @ h2, 0.0, 1.0) ** (6.0 + 160.0 * (1.0 - rough) ** 2)
        lit = lit + (spec2 * (0.16 * (1.0 - rough) ** 2))[:, None] * np.asarray(
            L.rim_color)
    return lit


def _grade(rgb: np.ndarray, alpha: np.ndarray, *, exposure: float = 1.02,
           bloom: float = 0.08, vignette: float = 0.12,
           saturation: float = 1.12, contrast: float = 1.08) -> np.ndarray:
    """Финальный грейд кадра: тональная кривая, мягкое свечение, виньетка.

    Без этого честно посчитанный цвет выглядит «сырым»: света выбиваются в
    белое, тени плоские, картинка кажется пластиковой. Кривая ACES-типа
    (сжатие светов), слабое свечение от ярких участков и лёгкая виньетка —
    это ровно то, что отличает «рендер» от «картинки».
    """
    x = np.clip(rgb * exposure, 0.0, 1.0)
    # мягкая кино-кривая: света поджимаются, тени чуть «приподняты», середина
    # получает небольшой S-изгиб. Без этого кадр выглядит либо «сырым», либо
    # вымытым (ACES на уже сжатый цвет выбеливает кожу).
    x = np.clip(x, 0.0, 1.0) ** (1.0 / 1.04)
    lum = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2])[..., None]
    x = np.clip(lum + (x - lum) * saturation, 0.0, 1.0)
    x = np.clip((x - 0.5) * contrast + 0.5, 0.0, 1.0)

    if bloom > 0:
        from PIL import Image
        h, w = x.shape[:2]
        lum = (0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2])
        hot = np.clip(lum - 0.78, 0.0, 1.0)[..., None] * x
        bw, bh = max(1, w // 6), max(1, h // 6)
        small = np.asarray(Image.fromarray((np.clip(hot, 0, 1) * 255).astype(np.uint8))
                           .resize((bw, bh), Image.BILINEAR), np.float32) / 255.0
        glow = np.asarray(Image.fromarray((small * 255).astype(np.uint8))
                          .resize((w, h), Image.BILINEAR), np.float32) / 255.0
        x = np.clip(x + glow * bloom * np.clip(alpha, 0, 1)[..., None], 0.0, 1.0)

    if vignette > 0:
        yy, xx = np.mgrid[0:x.shape[0], 0:x.shape[1]]
        ny = (yy - x.shape[0] / 2) / max(x.shape[0] / 2, 1)
        nx = (xx - x.shape[1] / 2) / max(x.shape[1] / 2, 1)
        r = np.sqrt(nx * nx + ny * ny) / 1.414
        x = x * (1.0 - vignette * r[..., None] ** 2)
    return np.clip(x, 0.0, 1.0)


def render(meshes: list[Mesh] | Mesh, size: tuple[int, int], camera: Camera,
           lights: Lights | None = None, *, ss: int = 2,
           background: tuple[float, float, float] | None = None,
           near_cull: float = 0.02) -> np.ndarray:
    """Отрисовать меш(и) → RGBA-массив (H, W, 4) uint8.

    `background=None` — прозрачный фон (кадр кладётся на сцену сверху).
    `ss` — суперсэмплинг (2 — хорошее качество, 1 — быстрее вчетверо).
    """
    L = lights or Lights()
    m = merge(meshes) if isinstance(meshes, list) else meshes
    W, H = int(size[0]), int(size[1])
    ss = max(int(ss), 1)
    RW, RH = W * ss, H * ss

    view = camera.view_matrix()
    proj = camera.projection(RW / RH)
    mvp = proj @ view

    v = np.c_[m.verts, np.ones(len(m.verts))]
    clip = v @ mvp.T
    w = clip[:, 3]
    ok_v = w > 1e-6
    ndc = np.where(ok_v[:, None], clip[:, :3] / np.maximum(w[:, None], 1e-9), 0.0)
    sx = (ndc[:, 0] * 0.5 + 0.5) * RW
    sy = (0.5 - ndc[:, 1] * 0.5) * RH
    sz = ndc[:, 2]

    tri = m.tris
    tri_ok = ok_v[tri].all(axis=1) & (sz[tri].max(axis=1) < 1.0)
    tri = tri[tri_ok]
    if not len(tri):
        return np.zeros((H, W, 4), np.uint8)

    # Отсечение задних граней по ГЕОМЕТРИИ, а не по знаку площади на экране:
    # иначе в 1-px щелях между треугольниками задняя стенка проходит z-тест и
    # вылезает тёмными «осколками» внутрь силуэта.
    # Направление грани берём из СГЛАЖЕННЫХ нормалей вершин, а не из порядка
    # обхода: у примитивов обход бывает «внутрь», и тогда отсечение показывает
    # изнанку шара (тёмный центр вместо освещённой передней части).
    cen = m.verts[tri].mean(axis=1)
    # Геометрическая нормаль грани. Корректность обхода гарантирует
    # Mesh.orient_outward(), поэтому знак площади в 3D — надёжный признак
    # «смотрит на камеру». Сглаженные нормали для этого не годятся: на бортиках
    # накладок они скошены вбок, и отсечение начинает «мигать» целыми
    # треугольниками — на лице проступают пятна кожи сквозь волосы.
    e01 = m.verts[tri[:, 1]] - m.verts[tri[:, 0]]
    e02 = m.verts[tri[:, 2]] - m.verts[tri[:, 0]]
    fn = np.cross(e01, e02)
    eye = np.asarray(camera.eye, np.float64)
    front = np.einsum("ij,ij->i", fn, eye - cen) > 0
    cull_mask = getattr(m, "_cull_mask", None)
    if cull_mask is not None:                 # открытые меши (веки, нутро рта)
        front |= ~np.asarray(cull_mask, bool)[np.asarray(tri_ok, bool)]
    tri = tri[front]
    if not len(tri):
        return np.zeros((H, W, 4), np.uint8)

    ax, ay = sx[tri[:, 0]], sy[tri[:, 0]]
    bx, by = sx[tri[:, 1]], sy[tri[:, 1]]
    cx_, cy_ = sx[tri[:, 2]], sy[tri[:, 2]]
    area = (bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax)
    alive = np.abs(area) > 1e-6
    tri, area = tri[alive], area[alive]
    if not len(tri):
        return np.zeros((H, W, 4), np.uint8)

    P = np.stack([sx[tri], sy[tri], sz[tri]], axis=-1)          # (M,3,3)
    N = m.normals[tri]                                          # (M,3,3)
    C = np.broadcast_to(np.asarray(m.color, np.float64), (len(m.verts), 3))[tri]
    A = np.broadcast_to(np.asarray(m.ao, np.float64), (len(m.verts),))[tri]
    R = np.broadcast_to(np.asarray(m.rough, np.float64), (len(m.tris),))[tri]

    # Перспективно-корректная глубина: интерполируем 1/w, а не z. Иначе на
    # крупных треугольниках глубина врёт сильнее, чем расстояние между
    # поверхностями, и в местах наложения появляется «шахматка» z-fighting.
    invw = 1.0 / np.maximum(clip[:, 3], 1e-9)
    IW = invw[tri]

    x0 = np.clip(np.floor(P[..., 0].min(1)).astype(np.int32), 0, RW)
    x1 = np.clip(np.ceil(P[..., 0].max(1)).astype(np.int32) + 1, 0, RW)
    y0 = np.clip(np.floor(P[..., 1].min(1)).astype(np.int32), 0, RH)
    y1 = np.clip(np.ceil(P[..., 1].max(1)).astype(np.int32) + 1, 0, RH)
    bw = x1 - x0
    bh = y1 - y0
    keep = (bw > 0) & (bh > 0)
    tri, P, N, C, A, area = tri[keep], P[keep], N[keep], C[keep], A[keep], area[keep]
    IW = IW[keep]
    x0, y0, bw, bh = x0[keep], y0[keep], bw[keep], bh[keep]
    if not len(tri):
        return np.zeros((H, W, 4), np.uint8)

    zbuf = np.zeros((RH, RW), np.float32)      # 1/w: больше — ближе к камере
    cbuf = np.zeros((RH, RW, 3), np.float32)
    abuf = np.zeros((RH, RW), np.float32)

    msz = np.maximum(bw, bh)
    order = np.argsort(msz)                      # мелкие позже: точнее по краю
    BUDGET = 900_000
    batches: list[np.ndarray] = []
    cur: list[int] = []
    tw = th = 0
    for idx in order:
        w_, h_ = int(bw[idx]), int(bh[idx])
        if cur and (len(cur) + 1) * max(tw, w_) * max(th, h_) > BUDGET:
            batches.append(np.array(cur, np.int64))
            cur, tw, th = [], 0, 0
        cur.append(int(idx))
        tw, th = max(tw, w_), max(th, h_)
    if cur:
        batches.append(np.array(cur, np.int64))

    view_dir = -np.asarray(camera.view_matrix()[2, :3], np.float64)

    for sel in batches:
        tw_, th_ = int(bw[sel].max()), int(bh[sel].max())
        shape = (len(sel), th_, tw_)
        px = np.broadcast_to(x0[sel][:, None, None] +
                             np.arange(tw_, dtype=np.float32)[None, None, :] + 0.5, shape)
        py = np.broadcast_to(y0[sel][:, None, None] +
                             np.arange(th_, dtype=np.float32)[None, :, None] + 0.5, shape)
        p = P[sel]
        a_ = area[sel][:, None, None]
        # барицентрика через площади подтреугольников
        def edge(i, j):
            return ((p[:, j, 0] - p[:, i, 0])[:, None, None] * (py - p[:, i, 1][:, None, None]) -
                    (p[:, j, 1] - p[:, i, 1])[:, None, None] * (px - p[:, i, 0][:, None, None]))

        e0, e1, e2 = edge(1, 2), edge(2, 0), edge(0, 1)
        sgn = np.sign(a_)
        inside = (e0 * sgn >= 0) & (e1 * sgn >= 0) & (e2 * sgn >= 0)
        if not inside.any():
            continue
        b0 = (e0 / a_)[inside]
        b1 = (e1 / a_)[inside]
        b2 = (e2 / a_)[inside]
        gxi = np.broadcast_to(x0[sel][:, None, None] + np.arange(tw_, dtype=np.int32)[None, None, :],
                             shape)[inside]
        gyi = np.broadcast_to(y0[sel][:, None, None] + np.arange(th_, dtype=np.int32)[None, :, None],
                             shape)[inside]
        sel_f = np.broadcast_to(sel[:, None, None], shape)[inside]
        iw = b0 * IW[sel_f, 0] + b1 * IW[sel_f, 1] + b2 * IW[sel_f, 2]
        valid = (gxi >= 0) & (gxi < RW) & (gyi >= 0) & (gyi < RH) & np.isfinite(iw) & (iw > 0)
        if not valid.any():
            continue
        gxi, gyi, iw = gxi[valid], gyi[valid], iw[valid]
        b0, b1, b2, sel_f = b0[valid], b1[valid], b2[valid], sel_f[valid]
        # перспективно-корректные веса для нормалей/цвета
        p0, p1, p2 = b0 * IW[sel_f, 0], b1 * IW[sel_f, 1], b2 * IW[sel_f, 2]
        den = np.maximum(p0 + p1 + p2, 1e-9)
        b0, b1, b2 = p0 / den, p1 / den, p2 / den
        nz = (N[sel_f, 0] * b0[:, None] + N[sel_f, 1] * b1[:, None] + N[sel_f, 2] * b2[:, None])
        alb = (C[sel_f, 0] * b0[:, None] + C[sel_f, 1] * b1[:, None] + C[sel_f, 2] * b2[:, None])
        ao = (A[sel_f, 0] * b0 + A[sel_f, 1] * b1 + A[sel_f, 2] * b2)
        rg = (R[sel_f, 0] * b0 + R[sel_f, 1] * b1 + R[sel_f, 2] * b2)

        # ---------------------------------------------------------------- #
        # z-тест с ЧЕСТНЫМ разрешением конфликтов ВНУТРИ батча.
        #
        # Тонкость, на которой всё ломалось: фрагменты одного батча пишутся
        # «россыпью» (np fancy indexing), поэтому при двух фрагментах на один
        # пиксель побеждал не ближний, а тот, что случайно оказался последним
        # в массиве. Там, где поверхности близко (волосы поверх головы, рука в
        # торсе), это давало «осколки» — случайные треугольники чужого цвета.
        #
        # Решение: сначала максимум глубины по каждому пикселю (np.maximum.at),
        # затем оставляем по одному фрагменту на пиксель — с этой максимальной
        # глубиной.
        flat = gyi.astype(np.int64) * RW + gxi.astype(np.int64)
        best = np.full(RH * RW, -np.inf, np.float64)
        np.maximum.at(best, flat, iw.astype(np.float64))
        prev = zbuf.ravel()
        win = (iw >= best[flat] - 1e-12) & (best[flat] > prev[flat])
        if not win.any():
            continue
        # по одному фрагменту на пиксель (equality по глубине — выбор любой)
        order = np.argsort(flat[win], kind="stable")
        fw = np.flatnonzero(win)[order]
        _, first = np.unique(flat[fw], return_index=True)
        pick = fw[first]
        gxi, gyi, iw = gxi[pick], gyi[pick], iw[pick]
        nz, alb, ao = nz[pick], alb[pick], ao[pick]
        rg = rg[pick]
        lit = _shade(nz, alb, ao, L, np.broadcast_to(view_dir, (len(iw), 3)),
                     rough=np.clip(rg, 0.0, 1.0))
        zbuf[gyi, gxi] = iw
        cbuf[gyi, gxi] = np.clip(lit, 0.0, 1.0)
        abuf[gyi, gxi] = 1.0

    alpha = abuf
    rgb = cbuf
    # финальный грейд — до квантования в 8 бит
    rgb = _grade(rgb, alpha)

    if ss > 1:
        from PIL import Image
        rgb8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
        a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
        # премультиплицируем, чтобы при уменьшении не было тёмной каймы
        pm = (rgb8.astype(np.float32) * (a8[..., None].astype(np.float32) / 255.0))
        img = np.dstack([pm, a8[..., None].astype(np.float32)])
        out = np.zeros((H, W, 4), np.float32)
        for c in range(4):
            out[..., c] = np.asarray(
                Image.fromarray(img[..., c].astype(np.uint8), "L").resize((W, H), Image.LANCZOS),
                np.float32)
        a = out[..., 3:4]
        rgb8 = np.where(a > 1e-6, out[..., :3] / np.maximum(a / 255.0, 1e-9), 0)
        result = np.dstack([np.clip(rgb8, 0, 255), np.clip(a, 0, 255)]).astype(np.uint8)
    else:
        result = np.dstack([np.clip(rgb * 255, 0, 255),
                            np.clip(alpha * 255, 0, 255)]).astype(np.uint8)

    if background is not None:
        bg = np.array(background, np.float32) * 255.0
        a = result[..., 3:4].astype(np.float32) / 255.0
        comp = result[..., :3].astype(np.float32) * a + bg * (1 - a)
        result = np.dstack([comp, np.full(comp.shape[:2], 255)]).astype(np.uint8)
    return result
