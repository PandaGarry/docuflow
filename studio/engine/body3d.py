"""Тело в 3D из ПРОПОРЦИЙ, а не «на глаз»: единая система координат и чисел.

Главная идея: все размеры — доли роста и «голов». Меняется один параметр
(например, `height_heads` 6.0 → 5.2), и персонаж пропорционально перестраивается
целиком. Это ровно то, чего не хватало 2D-ригу, где скелет сажался по силуэту.

Организация координат: пол — y = 0, макушка — y = height, +Z — лицом вперёд,
+X — влево персонажа (то есть вправо на экране при виде спереди).

ВАЖНО про единицы: все свойства `Proportions` возвращают **доли роста**
(безразмерные), а не метры. Метры появляются только на этапе сборки мешей
(умножение на `height`). Именно смешение единиц давало раньше «тело на
1.72 роста при заявленных 1.85» и микроскопическую голову.

Геометрия строится непрерывными оболочками (`loft` для торса, головы, бороды,
`tube` для конечностей), а не набором склеенных капсул: у оболочки одна
поверхность и одни нормали, поэтому на стыках нет z-fighting («шахматки»)
и белых швов. Все замкнутые тела прогоняются через `orient_outward()`, иначе
отсечение задних граней показывает изнанку — «призрак» вместо объёма.

Уровень — блокинг с грубой мимикой: нужен, чтобы проверить пропорции, силуэт
и посадку черт лица. Тонкая мимика (веки, виземы) — следующий этап.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

import render3d as R3


# шероховатость материалов (0 — глянец, 1 — матовый): нужна для мягкого блика
ROUGHNESS = {
    "head": 0.55, "skin": 0.55, "lid": 0.55, "lash": 0.62, "brow": 0.72,
    "nose": 0.50, "ear": 0.55, "neck": 0.55, "eye": 0.10, "iris": 0.16,
    "pupil": 0.08, "glint": 0.04, "hair": 0.62, "beard": 0.70,
    "mouth": 0.45, "lip": 0.42, "teeth": 0.25,
    "torso": 0.96, "collar": 0.96, "hem": 0.96, "hood": 0.96,
    "arm": 0.96, "cuff": 0.94, "deltoid": 0.96, "leg": 0.98,
    "hand": 0.55, "finger": 0.55, "shoe": 0.48, "sole": 0.75,
}


@dataclass
class Proportions:
    """Пропорции в долях роста. Значения по умолчанию — «средний взрослый»."""

    height: float = 1.85
    height_heads: float = 5.7          # рост в головах (стилизованно меньше 7.5)
    head_w: float = 0.82               # ширина головы / высота головы
    head_d: float = 0.96               # глубина / высота
    shoulder_w: float = 1.50           # ширина плеч в головах
    hip_w: float = 1.22                # ширина бёдер в головах
    chest_d: float = 0.62              # глубина грудной клетки в головах
    bulk: float = 1.0                  # общая плотность (толщина конечностей)
    belly: float = 1.0                 # живот
    arm_len: float = 0.42              # длина руки / рост (плечо → запястье)
    leg_len: float = 0.47              # высота тазобедренного сустава / рост
    neck_len: float = 0.042            # шея / рост
    hand_len: float = 0.105            # кисть / рост

    # --- производные (в долях роста) -------------------------------------
    @property
    def head_frac(self) -> float:
        """Высота головы в долях роста (1 / height_heads)."""
        return 1.0 / self.height_heads

    @property
    def head_h(self) -> float:
        """Высота головы в метрах (для удобства вызовов)."""
        return self.height * self.head_frac

    @property
    def hip_y(self) -> float:
        return self.leg_len

    @property
    def neck_y(self) -> float:
        """Низ головы (подбородок) — доля роста."""
        return 1.0 - self.head_frac

    @property
    def shoulder_y(self) -> float:
        """Верх торса: чуть ниже подбородка."""
        return self.neck_y - self.neck_len

    @property
    def head_cy(self) -> float:
        return 1.0 - self.head_frac / 2.0


def _head_profile(t: float) -> tuple[float, float]:
    """Полуширина/полугрудь головы на относительной высоте t (0 подбородок, 1 макушка)."""
    # узкий подбородок → широкие скулы → округлый череп
    keys = [(-0.20, 0.26, 0.30), (-0.12, 0.36, 0.42), (-0.05, 0.46, 0.54),
            (0.00, 0.52, 0.60), (0.03, 0.60, 0.68), (0.06, 0.66, 0.74),
            (0.10, 0.71, 0.79), (0.15, 0.76, 0.83), (0.20, 0.79, 0.86),
            (0.34, 0.89, 0.94), (0.48, 0.97, 1.00), (0.62, 1.00, 1.00),
            (0.76, 0.96, 0.97), (0.88, 0.80, 0.83), (0.96, 0.52, 0.56),
            (0.995, 0.06, 0.07), (1.00, 0.015, 0.017)]
    for (t0, x0, z0), (t1, x1, z1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return x0 + (x1 - x0) * k, z0 + (z1 - z0) * k
    return keys[-1][1], keys[-1][2]


def head_surface(p: Proportions, x: float, t: float) -> float:
    """Z поверхности головы в точке (x, высота t) — чтобы сажать черты лица.

    Без этого «на глаз» посаженные глаза и брови уходят внутрь черепа и
    становятся невидимыми (или, наоборот, висят в воздухе).
    """
    H = p.height
    hh = p.head_frac * H
    fx, fz = _head_profile(float(np.clip(t, 0.0, 1.0)))
    rx = p.head_w * hh / 2 * fx
    rz = p.head_d * hh / 2 * fz
    k = float(np.clip(1.0 - (x / max(rx, 1e-9)) ** 2, 0.0, 1.0))
    return rz * math.sqrt(k)


def head_point(p: Proportions, t: float, phi: float, scale: float = 1.0):
    """Точка на поверхности головы: t — относительная высота, phi — угол вокруг.

    phi = 0 → левый висок, phi = π/2 → лицо (перед), phi = -π/2 → затылок.
    Параметризация нужна, чтобы сажать ЛИЦО по поверхности, а не «на глаз».
    """
    H = p.height
    hh = p.head_frac * H
    fx, fz = _head_profile(float(np.clip(t, -0.2, 1.0)))
    x = p.head_w * hh / 2 * fx * scale * math.cos(phi)
    z = p.head_d * hh / 2 * fz * scale * math.sin(phi)
    y = (p.neck_y + t * p.head_frac) * H
    return np.array([x, y, z], np.float64)


def surf_arc(p: Proportions, pts, out: float = 1.02) -> np.ndarray:
    """Плотная дуга по поверхности головы: pts — список (t, phi)."""
    return np.array([head_point(p, t, ph, out) for t, ph in pts], np.float64)


def arc_points(t_mid: float, t_end: float, ph_mid: float, ph_end: float,
               n: int = 14):
    """Дуга с приподнятыми краями (улыбка, бровь): u от -1 до 1."""
    out = []
    for u in np.linspace(-1.0, 1.0, n):
        out.append((t_mid + (t_end - t_mid) * u * u, ph_mid + (ph_end - ph_mid) * u))
    return out


def oriented(mesh: R3.Mesh, center, ex, ey, ez) -> R3.Mesh:
    """Поставить меш в систему координат: локальные X/Y/Z → ex/ey/ez."""
    M = np.stack([ex, ey, ez], axis=1)
    m = R3.Mesh(mesh.verts, mesh.tris, mesh.normals, mesh.color, mesh.ao,
                mesh.rough, mesh.cull, mesh.name)
    m.verts = mesh.verts @ M.T + np.asarray(center, np.float64)
    m.normals = mesh.normals @ M.T
    if np.linalg.det(M) < 0:
        # левая система координат отражает меш: без переворота треугольников
        # тело вывернется наизнанку (и отсечение задних граней покажет пустоту)
        m.tris = m.tris[:, ::-1].copy()
        m.normals = R3.vertex_normals(m.verts, m.tris)
    return m


def head_shell(p: Proportions, t0: float, t1: float, phi0: float, phi1: float,
               out: float = 1.05, inner: float = 1.002, nt: int = 10,
               nphi: int = 40, top_pole: bool = False) -> R3.Mesh | None:
    """Накладка по поверхности головы: борода, волосы, веки, глазницы.

    Зачем так, а не «приклеенными» шарами: шар, пересекающий голову под острым
    углом, даёт рваную границу из треугольников (зубчатая кромка и z-fighting).
    Накладка повторяет форму головы, приподнята над ней на `out` и снабжена
    бортиком до `inner` — граница получается чистой линией, как у мультфильма.

    `phi0 == phi1` невозможно; если |phi1 - phi0| ≈ 2π, шов замыкается.
    """
    full = abs((phi1 - phi0) - 2 * math.pi) < 1e-6
    if full:
        phis = np.linspace(phi0, phi1, nphi, endpoint=False)
    else:
        phis = np.linspace(phi0, phi1, nphi)
    lo = t0 if callable(t0) else (lambda ph, _v=t0: _v)
    hi = t1 if callable(t1) else (lambda ph, _v=t1: _v)

    def grid(sc):
        rows = []
        for k in range(nt):
            u = k / (nt - 1)
            row = []
            for ph in phis:
                t = lo(ph) + (hi(ph) - lo(ph)) * u
                scv = sc(t, ph) if callable(sc) else sc
                row.append(head_point(p, t, ph, scv))
            rows.append(np.array(row))
        return np.array(rows)                       # (nt, nphi, 3)

    outer, inner_g = grid(out), grid(inner)
    verts = [outer.reshape(-1, 3), inner_g.reshape(-1, 3)]
    no, ni = 0, outer.size // 3
    nphi_pts = len(phis)
    tris = []

    def oid(i, j):
        return no + i * nphi_pts + (j % nphi_pts if full else j)

    def iid(i, j):
        return ni + i * nphi_pts + (j % nphi_pts if full else j)

    jmax = nphi_pts if full else nphi_pts - 1
    for i in range(nt - 1):
        for j in range(jmax):
            a, b = oid(i, j), oid(i, j + 1)
            c, d = oid(i + 1, j + 1), oid(i + 1, j)
            tris += [(a, b, c), (a, c, d)]
            a, b = iid(i, j), iid(i + 1, j)
            c, d = iid(i + 1, j + 1), iid(i, j + 1)
            tris += [(a, b, c), (a, c, d)]
    # бортики по открытым границам (низ, верх без полюса, бока)
    for j in range(jmax):
        # бортик рисуется с двух сторон: направление обхода на бортике зависит
        # от того, куда смотрит накладка, и «угадывать» его не нужно
        tris += [(oid(0, j), iid(0, j), iid(0, j + 1)),
                 (oid(0, j), iid(0, j + 1), oid(0, j + 1)),
                 (oid(0, j), iid(0, j + 1), iid(0, j)),
                 (oid(0, j), oid(0, j + 1), iid(0, j + 1))]
        if not top_pole:
            tris += [(oid(nt - 1, j), oid(nt - 1, j + 1), iid(nt - 1, j + 1)),
                     (oid(nt - 1, j), iid(nt - 1, j + 1), iid(nt - 1, j)),
                     (oid(nt - 1, j), iid(nt - 1, j + 1), oid(nt - 1, j + 1)),
                     (oid(nt - 1, j), iid(nt - 1, j), iid(nt - 1, j + 1))]
    if not full:
        for i in range(nt - 1):
            tris += [(oid(i, 0), oid(i + 1, 0), iid(i + 1, 0)),
                     (oid(i, 0), iid(i + 1, 0), iid(i, 0))]
            j = nphi_pts - 1
            tris += [(oid(i, j), iid(i, j), iid(i + 1, j)),
                     (oid(i, j), iid(i + 1, j), oid(i + 1, j))]
    mesh = R3.Mesh(np.vstack(verts), np.asarray(tris, np.int32))
    mesh.cull = True
    return mesh.orient_outward() if mesh.volume() else mesh


def head_spot(p: Proportions, t0: float, phi0: float, dt: float, dphi: float,
              out: float = 1.04, inner: float = 1.002, rings: int = 6,
              nphi: int = 40) -> R3.Mesh:
    """Эллиптическое «пятно» на голове: глаз, зрачок, бровь, блик."""
    ts, phis = [], []
    for r in np.linspace(0.0, 1.0, rings):
        for a in np.linspace(0, 2 * math.pi, nphi, endpoint=False):
            ts.append(t0 + dt * r * math.cos(a))
            phis.append(phi0 + dphi * r * math.sin(a))
    ts, phis = np.array(ts), np.array(phis)
    outer = np.array([head_point(p, t, ph, out) for t, ph in zip(ts, phis)])
    inner_g = np.array([head_point(p, t, ph, inner) for t, ph in zip(ts, phis)])
    verts = np.vstack([outer, inner_g])
    n = len(ts)
    tris = []
    for ring in range(rings - 1):
        for j in range(nphi):
            a = ring * nphi + j
            b = ring * nphi + (j + 1) % nphi
            c = (ring + 1) * nphi + (j + 1) % nphi
            d = (ring + 1) * nphi + j
            tris += [(a, b, c), (a, c, d)]
            a, b, c, d = a + n, d + n, c + n, b + n
            tris += [(a, b, c), (a, c, d)]
    # бортик по внешнему кольцу
    last = (rings - 1) * nphi
    for j in range(nphi):
        a = last + j
        b = last + (j + 1) % nphi
        tris += [(a, b, b + n), (a, b + n, a + n),
                 (a, b + n, b), (a, a + n, b + n)]
    return R3.Mesh(np.vstack(verts), np.asarray(tris, np.int32)).orient_outward()


def _head_sections(p: Proportions, scale: float = 1.0, bottom: float = -0.18,
                   top: float = 1.0, cz: float = 0.0) -> list[dict]:
    """Сечения головы в метрах. `bottom`/`top` срезают (для шапки волос)."""
    H = p.height
    hh = p.head_frac * H
    rx, rz = p.head_w * hh / 2 * scale, p.head_d * hh / 2 * scale
    ts = np.linspace(bottom, top, 18)
    out = []
    for t in ts:
        fx, fz = _head_profile(float(t))
        out.append({"y": (p.neck_y + float(t) * p.head_frac) * H,
                    "rx": max(rx * fx, 1e-4), "rz": max(rz * fz, 1e-4),
                    "cz": cz})
    return out


def _beard_sections(p: Proportions, top: float = 0.34) -> list[dict]:
    """Борода: снизу толще щёк, сверху уходит ВНУТРЬ головы.

    Так верхний торец бороды спрятан под кожей, и нет ни светлой «полки»
    (плоский торец ловит свет), ни z-fighting: поверхности не совпадают.
    """
    H = p.height
    hh = p.head_frac * H
    rx, rz = p.head_w * hh / 2, p.head_d * hh / 2
    # (t, множитель толщины): 0.94 сверху (внутри головы) → 1.12 на подбородке
    keys = [(-0.03, 1.09), (0.02, 1.12), (0.10, 1.12), (0.18, 1.08),
            (0.26, 1.02), (0.31, 0.95), (0.34, 0.86)]
    out = []
    for t, k in keys:
        fx, fz = _head_profile(float(np.clip(t, 0.0, 1.0)))
        out.append({"y": (p.neck_y + t * p.head_frac) * H,
                    "rx": rx * fx * k, "rz": rz * fz * k,
                    "cz": 0.004 * H * max(0.0, 1.0 - abs(t) / 0.34)})
    return out


def _torso_sections(p: Proportions) -> list[dict]:
    """Профиль торса в метрах: плечи шире таза, живот вперёд, спина ровная."""
    H = p.height
    hh = p.head_frac
    half_sh = p.shoulder_w * hh / 2
    depth = (0.50 * p.chest_d + 0.44) * p.hip_w * hh / 2 * 2.0
    belly = p.belly
    # (доля роста, ширина в «полу-плечах», сдвиг вперёд)
    prof = [
        (p.hip_y - 0.055, 1.04, -0.004, 0.94),   # край худи — по линии бёдер
        (p.hip_y - 0.035, 1.00, -0.006, 0.94),
        (p.hip_y - 0.010, 0.90, -0.010, 0.93),
        (p.hip_y + 0.020, 0.90, -0.008, 0.93),   # ягодицы
        (p.hip_y + 0.080, 0.875, 0.010 * belly, 0.95),   # живот
        (p.hip_y + 0.130, 0.865, 0.008 * belly, 0.97),
        (p.hip_y + 0.180, 0.915, 0.004, 0.99),
        (p.shoulder_y - 0.060, 0.975, 0.000, 0.99),
        (p.shoulder_y - 0.010, 0.985, 0.000, 0.98),
        (p.shoulder_y + 0.010, 0.900, -0.004, 0.95),
        (p.shoulder_y + 0.026, 0.640, -0.007, 0.90),
        (p.shoulder_y + 0.046, 0.300, -0.009, 0.82),
    ]
    out = []
    for y, wsh, cz, dsc in prof:
        out.append({"y": y * H, "rx": half_sh * wsh * H,
                    "rz": depth * H / 2 * dsc, "cz": cz * H})
    return out



def _skin_shading(p: Proportions, verts: np.ndarray, skin) -> np.ndarray:
    """Пер-вершинная окраска кожи: щёки, нос, глазницы, тень под челюстью.

    Плоская заливка цветом — главная причина «пластика». Здесь цвет плавно
    меняется по поверхности: тёплые щёки и нос, холодные глазницы, затемнение
    под челюстью и чуть более светлый лоб.
    """
    H = p.height
    hh = p.head_frac
    v = np.asarray(verts, np.float64)
    t = (v[:, 1] - p.neck_y * H) / max(hh * H, 1e-9)
    rx = max(p.head_w * hh * H / 2, 1e-9)
    rz = max(p.head_d * hh * H / 2, 1e-9)
    nx = v[:, 0] / rx
    nz = v[:, 2] / rz
    front = np.clip(nz, 0.0, 1.0)

    col = np.tile(np.asarray(skin, np.float64), (len(v), 1))

    for sgn in (-1.0, 1.0):                      # тёплые щёки
        d = np.exp(-(((nx - sgn * 0.52) / 0.40) ** 2
                     + ((t - 0.40) / 0.15) ** 2)) * front
        col *= 1.0 + np.stack([0.055 * d, -0.075 * d, -0.065 * d], axis=1)
    d = np.exp(-((nx / 0.19) ** 2 + ((t - 0.49) / 0.09) ** 2)) * front
    col *= 1.0 + np.stack([0.070 * d, -0.020 * d, -0.030 * d], axis=1)
    for sgn in (-1.0, 1.0):                      # глазницы — мягкая тень
        d = np.exp(-(((nx - sgn * 0.34) / 0.24) ** 2
                     + ((t - 0.575) / 0.085) ** 2)) * front
        col *= (1.0 - 0.085 * d)[:, None]
    low = np.clip((0.26 - t) / 0.50, 0.0, 1.0)   # под челюстью темнее
    col *= (1.0 - 0.16 * low)[:, None]
    high = np.clip((t - 0.72) / 0.26, 0.0, 1.0)  # лоб светлее
    col *= (1.0 + 0.05 * high)[:, None]
    return np.clip(col, 0.0, 1.0)



def _hair_shading(verts: np.ndarray, base, *, axis: float = 90.0,
                  depth: float = 0.10, strand: float = 0.07) -> np.ndarray:
    """Пер-вершинная штриховка волос: пряди, затемнение у корней.

    Волосы одним цветом выглядят как шлем. Здесь цвет «дышит»: тонкие полосы
    вдоль роста волос (синус по азимуту) плюс общий градиент от корней к
    кончикам — визуально это читается как пряди.
    """
    v = np.asarray(verts, np.float64)
    col = np.tile(np.asarray(base, np.float64), (len(v), 1))
    ang = np.arctan2(v[:, 0], v[:, 2])
    lum = (1.0 + strand * np.sin(ang * axis)
           + 0.5 * strand * np.sin(ang * axis * 2.3 + 1.7))
    col *= lum[:, None]
    # светлее к макушке/кончикам, темнее в глубине
    h = (v[:, 1] - v[:, 1].min()) / max(v[:, 1].max() - v[:, 1].min(), 1e-9)
    col *= (1.0 - depth + depth * h)[:, None]
    return np.clip(col, 0.0, 1.0)


def head_parts(p: Proportions, colors: dict | None = None, *,
               skin=(0.86, 0.62, 0.50), hair=(0.20, 0.14, 0.10),
               eyes: bool = True) -> list[R3.Mesh]:
    """Голова и всё лицо ЖЁСТКИМ блоком (череп не гнётся).

    Черты сажаются по поверхности головы (`head_point`), накладками
    (`head_shell`, `head_spot`) — поэтому границы чистые, без зубчатой кромки
    от пересечения шаров с головой.
    """
    if colors:
        skin, hair = colors.get("skin", skin), colors.get("hair", hair)
    H = p.height
    hh = p.head_frac
    parts: list[R3.Mesh] = []

    def put(m, color, name):
        m.color = np.asarray(color, np.float64)
        m.name = name
        m.rough = ROUGHNESS.get(name, 0.9)
        parts.append(m)

    def hy(t: float) -> float:
        return (p.neck_y + t * hh) * H

    put(R3.loft(_head_sections(p), seg=56), skin, "head")

    # волосы: линия роста спереди выше, сзади ниже; толщина растёт к макушке
    # линия роста волос: высоко надо лбом, ниже у висков, ещё ниже на затылке
    def hairline(ph: float) -> float:
        # у висков ниже, на затылке ещё ниже — линия роста волос не «обручем»
        c = math.cos(ph) ** 2
        return 0.795 - 0.075 * c - 0.115 * (1.0 - math.sin(ph)) / 2.0

    def hair_thickness(t: float, ph: float) -> float:
        k = float(np.clip((t - 0.66) / 0.34, 0.0, 1.0))
        front = 0.5 + 0.5 * math.sin(ph)
        base = 1.030 + 0.055 * k ** 1.3 + 0.022 * k * front ** 2
        # вихор: объёмная прядь, поднятая надо лбом и зачёсанная назад
        dph = (ph - math.pi / 2) / 0.62
        quiff = 0.300 * math.exp(-(((t - 0.905) / 0.125) ** 2 + dph ** 2))
        return base + quiff

    put(head_shell(p, t0=hairline, t1=1.0, phi0=0.0, phi1=2 * math.pi,
                   out=hair_thickness, inner=1.002, nt=14, nphi=56,
                   top_pole=True), hair, "hair")

    # борода: у рта низко, к вискам поднимается
    beard_top = lambda ph: 0.150 + 0.300 * (math.cos(ph) ** 2) ** 0.90

    def beard_out(t: float, ph: float) -> float:
        # борода толще у подбородка и тоньше к линии на щеке
        k = float(np.clip((t - 0.02) / 0.42, 0.0, 1.0))
        return 1.058 - 0.030 * k

    put(head_shell(p, t0=-0.135, t1=beard_top, phi0=0.36, phi1=math.pi - 0.36,
                   out=beard_out, inner=1.002, nt=12, nphi=40), hair, "beard")

    # --- кожа: мягкие градиенты вместо плоской заливки ---------------------
    head = parts[0]
    head.color = _skin_shading(p, head.verts, skin)

    # --- нос: спинка → кончик → ноздри ------------------------------------
    nose_col = tuple(float(c) for c in np.clip(
        np.asarray(skin) * np.array([1.05, 0.94, 0.93]), 0.0, 1.0))
    bridge = np.array([
        head_point(p, 0.645, math.pi / 2, 1.006) - np.array([0, 0, 0.003 * H]),
        head_point(p, 0.578, math.pi / 2, 1.012),
        head_point(p, 0.522, math.pi / 2, 1.026) + np.array([0, 0, 0.004 * H]),
    ])
    put(R3.tube(bridge, np.array([0.0045, 0.0085, 0.0125]) * H, seg=20),
        nose_col, "nose")
    tip = head_point(p, 0.512, math.pi / 2, 1.032) + np.array([0, 0, 0.002 * H])
    put(R3.sphere(1.0, seg=20, rings=14,
                  scale=(0.0118 * H, 0.0108 * H, 0.0105 * H), center=tip),
        nose_col, "nose")
    nostril_col = tuple(float(c) * 0.48 for c in nose_col)
    for s_ in (-1, 1):
        put(R3.sphere(1.0, seg=12, rings=9,
                      scale=(0.0040 * H, 0.0030 * H, 0.0032 * H),
                      center=tip + np.array([s_ * 0.0090 * H, -0.0080 * H,
                                             -0.0025 * H])), nostril_col, "nose")

    # --- уши ---------------------------------------------------------------
    for s_ in (-1, 1):
        ear_base = head_point(p, 0.455, 0.0 if s_ < 0 else math.pi, 0.975)
        ear = R3.sphere(1.0, seg=18, rings=12,
                        scale=(0.0055 * H, 0.0175 * H, 0.0110 * H))
        # наклон: верх уха отклонён назад, как у настоящего уха
        tilt = R3._rot_y(s_ * -0.18) @ R3._rot_x(0.10)
        ear = ear.transformed(tilt)
        ear.verts += ear_base + np.array([s_ * 0.0010 * H, 0.0015 * H,
                                          -0.0055 * H])
        put(ear, skin, "ear")

    # --- глаза -------------------------------------------------------------
    if eyes:
        t_eye, d_eye = 0.560, 0.415
        for side in (-1, 1):
            ph = math.pi / 2 + side * d_eye
            put(head_spot(p, t_eye, ph, 0.056, 0.180, out=1.024, rings=5, nphi=40),
                (0.96, 0.95, 0.93), "eye")
            put(head_spot(p, t_eye - 0.002, ph, 0.040, 0.112, out=1.034,
                          rings=4, nphi=32), (0.30, 0.18, 0.11), "iris")
            put(head_spot(p, t_eye - 0.002, ph, 0.020, 0.056, out=1.042,
                          rings=3, nphi=22), (0.05, 0.04, 0.04), "pupil")
            put(head_spot(p, t_eye + 0.014, ph - side * 0.040, 0.011, 0.028,
                          out=1.050, rings=2, nphi=16), (1.0, 1.0, 1.0), "glint")
            put(head_spot(p, t_eye + 0.066, ph, 0.034, 0.190, out=1.030,
                          rings=4, nphi=36), skin, "lid")
            put(head_spot(p, t_eye + 0.046, ph, 0.010, 0.186, out=1.032,
                          rings=3, nphi=32), (0.13, 0.09, 0.08), "lash")
            put(head_spot(p, t_eye - 0.058, ph, 0.014, 0.180, out=1.026,
                          rings=3, nphi=30), skin, "lid_lo")

            # бровь — дугой, толще у переносицы
            pts, rad = [], []
            for u in np.linspace(0.0, 1.0, 9):
                ph_b = math.pi / 2 + side * (0.150 + 0.450 * u)
                t_b = 0.706 + 0.022 * math.sin(math.pi * u) - 0.008 * u
                pts.append(head_point(p, t_b, ph_b, 1.030))
                rad.append((0.0060 - 0.0028 * u
                            + 0.0014 * math.sin(math.pi * u)) * H)
            put(R3.tube(np.array(pts), np.array(rad), seg=14), hair, "brow")

    # --- усы: две дуги над верхней губой (накладка-«пластырь» не годится) ---
    for s_ in (-1, 1):
        pts, rad = [], []
        for u in np.linspace(0.0, 1.0, 9):
            ph = math.pi / 2 + s_ * (0.020 + 0.400 * u)
            t = 0.386 - 0.026 * u - 0.012 * u * u
            pts.append(head_point(p, t, ph, 1.046))
            rad.append((0.0102 - 0.0070 * u) * H)
        put(R3.tube(np.array(pts), np.array(rad), seg=14), hair, "beard")

    # --- рот: улыбка линией, нижняя губа, без «наклеенного» пятна ----------
    t_m = 0.300
    pts, rad = [], []
    for u in np.linspace(-1.0, 1.0, 19):
        t = t_m + 0.030 * u * u
        ph = math.pi / 2 + u * 0.34
        pts.append(head_point(p, t, ph, 1.016))
        rad.append((0.0060 - 0.0038 * u * u) * H)
    put(R3.tube(np.array(pts), np.array(rad), seg=16), (0.33, 0.15, 0.14), "mouth")

    lip_pts, lip_rad = [], []
    for u in np.linspace(-0.78, 0.78, 13):
        t = t_m - 0.030 + 0.022 * u * u
        ph = math.pi / 2 + u * 0.28
        lip_pts.append(head_point(p, t, ph, 1.032))
        lip_rad.append((0.0086 - 0.0058 * u * u) * H)
    put(R3.tube(np.array(lip_pts), np.array(lip_rad), seg=14),
        (0.74, 0.47, 0.44), "lip")

    # штриховка волос и бороды — иначе они читаются как литой шлем
    for m in parts:
        if m.name in ("hair", "beard"):
            m.color = _hair_shading(m.verts, hair)
    return parts


def torso_parts(p: Proportions, colors: dict | None = None, *,
                top=(0.72, 0.73, 0.74)) -> list[R3.Mesh]:
    """Торс одной оболочкой + планка горловины и пояс (тёмные вставки)."""
    if colors:
        top = colors.get("top", top)
    top_dark = (colors or {}).get("top_dark") or tuple(c * 0.72 for c in top)
    H = p.height
    secs = _torso_sections(p)
    parts = [R3.loft(secs, seg=56)]
    parts[0].color = np.asarray(top, np.float64)
    parts[0].name = "torso"

    collar_r = secs[-1]["rx"] * 0.52
    collar = R3.loft([
        {"y": secs[-1]["y"] - 0.012 * H, "rx": collar_r, "rz": collar_r * 0.86},
        {"y": secs[-1]["y"] + 0.020 * H, "rx": collar_r * 0.96, "rz": collar_r * 0.82},
        {"y": secs[-1]["y"] + 0.040 * H, "rx": collar_r * 0.80, "rz": collar_r * 0.70},
    ], seg=40)
    collar.color = np.asarray(top_dark, np.float64)
    collar.name = "collar"
    parts.append(collar)

    # кромка худи: не отдельная «пачка», а затемнённый низ самой оболочки
    torso_mesh = parts[0]
    hem_y = secs[0]["y"]
    k = np.clip((torso_mesh.verts[:, 1] - hem_y) / (0.035 * H), 0.0, 1.0)
    base_col = np.asarray(top, np.float64)
    dark = np.asarray(top_dark, np.float64)
    torso_mesh.color = (dark[None, :] * (1.0 - k)[:, None]
                        + base_col[None, :] * k[:, None])

    # --- таз: единый объём джинсов, из которого выходят обе ноги ----------
    pelvis = R3.loft([
        {"y": (p.hip_y - 0.105) * H, "rx": 0.040 * H, "rz": 0.052 * H, "cz": -0.004 * H},
        {"y": (p.hip_y - 0.070) * H, "rx": 0.052 * H, "rz": 0.060 * H, "cz": -0.004 * H},
        {"y": (p.hip_y - 0.010) * H, "rx": 0.056 * H, "rz": 0.062 * H, "cz": -0.004 * H},
        {"y": (p.hip_y + 0.040) * H, "rx": 0.050 * H, "rz": 0.058 * H, "cz": -0.004 * H},
    ], seg=44)
    pelvis.color = np.asarray(colors.get("bottom", (0.22, 0.26, 0.34)), np.float64)
    pelvis.name = "pelvis"
    parts.append(pelvis)

    # --- капюшон: валик за шеей -------------------------------------------
    y0 = p.shoulder_y * H
    y1 = p.neck_y * H
    hood = R3.loft([
        {"y": y0 + 0.030 * H, "rx": 0.078 * H, "rz": 0.040 * H, "cz": -0.040 * H},
        {"y": y1 - 0.006 * H, "rx": 0.096 * H, "rz": 0.048 * H, "cz": -0.046 * H},
        {"y": y1 + 0.030 * H, "rx": 0.086 * H, "rz": 0.042 * H, "cz": -0.040 * H},
        {"y": y1 + 0.058 * H, "rx": 0.062 * H, "rz": 0.030 * H, "cz": -0.030 * H},
    ], seg=44)
    hood.color = np.asarray(top, np.float64)
    hood.name = "hood"
    parts.append(hood)

    # --- шнурки капюшона ---------------------------------------------------
    for sgn in (-1.0, 1.0):
        a = np.array([sgn * 0.028 * H, y1 + 0.006 * H, 0.062 * H])
        b = np.array([sgn * 0.032 * H, y1 - 0.055 * H, 0.086 * H])
        c_ = np.array([sgn * 0.034 * H, y1 - 0.080 * H, 0.090 * H])
        cord = R3.tube(np.array([a, b, c_]),
                       np.array([0.0050, 0.0046, 0.0042]) * H, seg=12)
        cord.color = np.asarray((0.93, 0.92, 0.90), np.float64)
        cord.name = "cuff"
        parts.append(cord)
    return parts



def shoe_mesh(p: Proportions, h: float = 1.0) -> R3.Mesh:
    """Колодка ботинка: единая оболочка от пятки к носку.

    Раньше обувь была одним скруглённым параллелепипедом — в профиль она
    читалась как «ласта». Здесь сечение меняется по длине: пятка круглая,
    подъём высокий, носок шире и ниже; получается честный объём.
    """
    H = p.height
    # (положение по длине вперёд от щиколотки, полуширина, полувысота, центр по высоте)
    # низ колодки всегда на 0.004H над землёй — обувь стоит, а не «висит»
    prof = [
        (-0.050, 0.019, 0.015, 0.019),
        (-0.040, 0.026, 0.023, 0.027),
        (-0.020, 0.031, 0.034, 0.038),
        (0.005, 0.032, 0.038, 0.042),
        (0.030, 0.032, 0.030, 0.034),
        (0.060, 0.031, 0.024, 0.028),
        (0.082, 0.028, 0.019, 0.023),
        (0.096, 0.021, 0.014, 0.018),
        (0.104, 0.011, 0.009, 0.013),
    ]
    sections = [{"y": -z * H * h, "rx": rx * H * h, "rz": rz * H * h,
                 "cz": cy * H * h} for z, rx, rz, cy in prof]
    mesh = R3.loft(sections, seg=30)
    # (x, длина, высота) -> (x, высота, вперёд): поворот на 90° вокруг X
    rot = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]])
    mesh.verts = mesh.verts @ rot.T
    mesh.normals = mesh.normals @ rot.T
    return mesh

def limb_parts(p: Proportions, colors: dict | None = None, joints: dict | None = None,
               rots: dict | None = None, rest: dict | None = None) -> list[R3.Mesh]:
    """Руки и ноги ПО ПОЗЕ: гладкая труба по суставам + жёсткие кисти и стопы.

    Труба строится через сплайн (см. `character.smooth_path`), поэтому локоть и
    колено на сгибе получают дугу и сохраняют объём — вместо «шарнира из двух
    цилиндров» и щели между ними.
    """
    from character import rigid, smooth_path

    colors = colors or {}
    skin = colors.get("skin", (0.86, 0.62, 0.50))
    top = colors.get("top", (0.72, 0.73, 0.74))
    top_dark = colors.get("top_dark") or tuple(c * 0.72 for c in top)
    bottom = colors.get("bottom", (0.22, 0.26, 0.34))
    shoes = colors.get("shoes", (0.18, 0.14, 0.12))

    if joints is None:
        import rig3d
        sk = rig3d.Skeleton.from_proportions(p)
        fk = rig3d.forward_kinematics(sk, rig3d.Pose())
        joints = {}
        for side in ("L", "R"):
            joints[f"shoulder.{side}"] = fk[f"upperarm.{side}"]["head"]
            joints[f"elbow.{side}"] = fk[f"forearm.{side}"]["head"]
            joints[f"wrist.{side}"] = fk[f"hand.{side}"]["head"]
            joints[f"hand_end.{side}"] = fk[f"hand.{side}"]["tail"]
            joints[f"hip.{side}"] = fk[f"thigh.{side}"]["head"]
            joints[f"knee.{side}"] = fk[f"shin.{side}"]["head"]
            joints[f"ankle.{side}"] = fk[f"foot.{side}"]["head"]
            joints[f"toe.{side}"] = fk[f"toe.{side}"]["head"]
            joints[f"toe_end.{side}"] = fk[f"toe.{side}"]["tail"]
    rest_j = rest if rest is not None else joints
    rots = rots or {}

    H = p.height
    hh = p.head_frac
    parts: list[R3.Mesh] = []

    def put(m, color, name):
        if m is None:
            return
        m.color = np.asarray(color, np.float64)
        m.name = name
        parts.append(m)

    for side in ("L", "R"):
        sgn = 1.0 if side == "L" else -1.0
        sh = np.asarray(joints[f"shoulder.{side}"], np.float64)
        el = np.asarray(joints[f"elbow.{side}"], np.float64)
        wr = np.asarray(joints[f"wrist.{side}"], np.float64)

        # рукав «реглан»: начинается внутри торса, поэтому линия плеча
        # получается наклонной, а не полкой с шаром сверху
        p0 = np.array([sh[0] - sgn * 0.095 * H, sh[1] - 0.034 * H,
                       sh[2] - 0.004 * H])
        path, rad = smooth_path([p0, sh, el, wr],
                                [0.052 * H * p.bulk, 0.055 * H * p.bulk,
                                 0.038 * H * p.bulk, 0.031 * H * p.bulk],
                                per_seg=8)
        # торцы трубы плоские: скруглённый торец вылезал бы из торса
        put(R3.tube(path, rad, seg=26, round_caps=False), top, "arm")

        # манжета рукава — ориентируется по предплечью
        fdir = wr - el
        fdir /= max(np.linalg.norm(fdir), 1e-9)
        cuff = R3.tube([wr - fdir * 0.028 * H, wr + fdir * 0.004 * H],
                       [0.035 * H * p.bulk, 0.033 * H * p.bulk], seg=22)
        put(cuff, top_dark, "cuff")

        # кисть: ладонь + пальцы (жёстко на кости кисти, как настоящая кисть)
        rest_w = np.asarray(rest_j[f"wrist.{side}"], np.float64)
        hrot = rots.get(side, {}).get("hand", np.eye(3))
        fdir = wr - el
        fdir = fdir / max(np.linalg.norm(fdir), 1e-9)
        # нормаль ладони смотрит внутрь: в покое ладонь обращена к бедру
        nrm = np.array([-sgn, 0.0, 0.0])
        nrm = nrm - fdir * float(nrm @ fdir)
        nrm = nrm / max(np.linalg.norm(nrm), 1e-9)
        lat = np.cross(fdir, nrm)
        lat = lat / max(np.linalg.norm(lat), 1e-9)
        if lat[2] < 0:                      # «вперёд» — туда, куда смотрит палец
            lat = -lat

        palm_len = 0.048 * H
        palm_c = rest_w + fdir * (palm_len * 0.52)
        palm = oriented(R3.roundbox((0.032 * H, palm_len, 0.0165 * H),
                                    roundness=2.4, seg=22, rings=14),
                        palm_c, lat, fdir, nrm)
        put(rigid(palm, rest_w, wr, hrot), skin, "hand")

        # четыре пальца: чуть согнуты, средний длиннее
        for off, ln, rr in ((0.0122, 0.038, 0.0070), (0.0042, 0.043, 0.0073),
                            (-0.0042, 0.041, 0.0069), (-0.0122, 0.033, 0.0061)):
            base = palm_c + fdir * (palm_len * 0.46) + lat * (off * H)
            d1 = fdir + nrm * 0.16 + lat * (off * 4.0)
            d1 = d1 / max(np.linalg.norm(d1), 1e-9)
            L = ln * H
            pts = np.array([base,
                            base + d1 * L * 0.50 + nrm * (0.0022 * H),
                            base + d1 * L * 0.86 + nrm * (0.0068 * H),
                            base + d1 * L * 1.02 + nrm * (0.0112 * H)])
            rad = np.array([rr, rr * 0.97, rr * 0.87, rr * 0.74]) * H
            put(rigid(R3.tube(pts, rad, seg=14), rest_w, wr, hrot), skin, "finger")

        # большой палец: от ладони вниз-вперёд, а не в сторону
        tb = (rest_w + fdir * (0.013 * H) + lat * (0.014 * H)
              + nrm * (0.0035 * H))
        td = fdir * 0.80 + lat * 0.44 + nrm * 0.40
        td = td / max(np.linalg.norm(td), 1e-9)
        tp = np.array([tb, tb + td * (0.014 * H),
                       tb + td * (0.029 * H) + nrm * (0.003 * H)])
        put(rigid(R3.tube(tp, np.array([0.0086, 0.0076, 0.0062]) * H, seg=14),
                  rest_w, wr, hrot), skin, "finger")

        # --- нога ---
        hip = np.asarray(joints[f"hip.{side}"], np.float64)
        kn = np.asarray(joints[f"knee.{side}"], np.float64)
        an = np.asarray(joints[f"ankle.{side}"], np.float64)
        leg_path, leg_rad = smooth_path(
            [hip + (hip - kn) * 0.02, hip, kn, an],
            [0.044 * H * p.bulk, 0.049 * H * p.bulk, 0.043 * H * p.bulk,
             0.033 * H * p.bulk], per_seg=7)
        put(R3.tube(leg_path, leg_rad, seg=26, round_caps=False), bottom, "leg")

        rest_a = np.asarray(rest_j[f"ankle.{side}"], np.float64)
        prost = rot_foot = rots.get(side, {}).get("foot", np.eye(3))
        # стопа строится от щиколотки вниз-вперёд
        shoe = shoe_mesh(p)
        # колодка строится от земли: ставим по x/z щиколотки, y — от пола
        shoe.verts = shoe.verts + np.array([rest_a[0], 0.0, rest_a[2]])
        put(rigid(shoe, rest_a, an, rot_foot), shoes, "shoe")

    return parts


def build_body(p: Proportions, *, skin=(0.86, 0.62, 0.50), top=(0.72, 0.73, 0.74),
               bottom=(0.22, 0.26, 0.34), shoes=(0.18, 0.14, 0.12),
               hair=(0.20, 0.14, 0.10), eyes=True,
               top_dark=None) -> list[R3.Mesh]:
    """Сборка в ПОЗЕ ПОКОЯ (для проверок пропорций и турнэраунда)."""
    colors = dict(skin=skin, top=top, bottom=bottom, shoes=shoes, hair=hair)
    if top_dark is not None:
        colors["top_dark"] = top_dark
    parts = (head_parts(p, colors, eyes=eyes) + torso_parts(p, colors)
             + limb_parts(p, colors))
    parts.append(_neck_rest(p, skin))
    return parts


def _neck_rest(p: Proportions, skin) -> R3.Mesh:
    H = p.height
    m = R3.tube([(0, p.shoulder_y * H - 0.02 * H, -0.004 * H),
                 (0, p.neck_y * H + 0.06 * H, -0.002 * H)],
                [0.056 * H * p.bulk, 0.045 * H * p.bulk], seg=24)
    m.color = np.asarray(skin, np.float64)
    m.name = "neck"
    return m


def turnaround(p: Proportions, out_prefix: str, size=(420, 700), ss=2,
               bg=(0.98, 0.96, 0.93), parts=None) -> list[str]:
    """Три ракурса: спереди, 3/4, сбоку. Для проверки силуэта и пропорций."""
    from PIL import Image

    parts = build_body(p) if parts is None else parts
    H = p.height
    cy = H * 0.52
    dist = (H * 1.18) / (2 * math.tan(math.radians(15)))
    views = {
        "front": R3.Camera(eye=(0.0, cy, dist), target=(0, cy, 0), fov=30),
        "three_quarter": R3.Camera(eye=(dist * 0.62, cy * 1.02, dist * 0.78),
                                   target=(0, cy, 0), fov=30),
        "side": R3.Camera(eye=(dist, cy, 0.0), target=(0, cy, 0), fov=30),
    }
    out = []
    for name, cam in views.items():
        img = R3.render(parts, size, cam, ss=ss, background=bg)
        path = f"{out_prefix}-{name}.png"
        Image.fromarray(img).save(path)
        out.append(path)
    return out


def face_closeup(p: Proportions, path: str, size=(560, 560), ss=2,
                 bg=(0.98, 0.96, 0.93), parts=None) -> str:
    """Крупный план головы: проверка посадки черт лица, а не только силуэта."""
    from PIL import Image

    parts = build_body(p) if parts is None else parts
    H = p.height
    cy = (p.neck_y + 0.5 * p.head_frac) * H
    dist = H * 0.62
    cam = R3.Camera(eye=(dist * 0.16, cy + H * 0.012, dist * 0.96),
                    target=(0, cy, 0), fov=26)
    img = R3.render(parts, size, cam, ss=ss, background=bg)
    Image.fromarray(img).save(path)
    return path
