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
    neck_len: float = 0.028            # шея / рост
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
    keys = [(-0.20, 0.30, 0.32), (-0.12, 0.40, 0.44), (-0.05, 0.50, 0.56),
            (0.00, 0.56, 0.62), (0.04, 0.66, 0.70), (0.10, 0.74, 0.78),
            (0.16, 0.80, 0.84), (0.20, 0.82, 0.86),
            (0.34, 0.92, 0.95), (0.48, 0.99, 1.00), (0.62, 1.00, 1.00),
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
    depth = (0.50 * p.chest_d + 0.30) * p.hip_w * hh / 2 * 2.0
    belly = p.belly
    # (доля роста, ширина в «полу-плечах», сдвиг вперёд)
    prof = [
        (p.hip_y - 0.030, 0.66, 0.000),
        (p.hip_y + 0.010, 0.76, 0.006),
        (p.hip_y + 0.070, 0.80, 0.012 * belly),
        (p.hip_y + 0.135, 0.84, 0.014 * belly),
        (p.hip_y + 0.200, 0.91, 0.010),
        (p.hip_y + 0.260, 0.97, 0.004),
        (p.shoulder_y - 0.030, 1.00, 0.000),
        (p.shoulder_y - 0.002, 0.93, -0.002),
        (p.shoulder_y + 0.012, 0.62, -0.006),
    ]
    out = []
    for y, wsh, cz in prof:
        out.append({"y": y * H, "rx": half_sh * wsh * H, "rz": depth * H / 2,
                    "cz": cz * H})
    return out


def build_body(p: Proportions, *, skin=(0.86, 0.62, 0.50), top=(0.72, 0.73, 0.74),
               bottom=(0.22, 0.26, 0.34), shoes=(0.18, 0.14, 0.12),
               hair=(0.20, 0.14, 0.10), eyes=True,
               top_dark=None) -> list[R3.Mesh]:
    """Собрать блокинг: голова, волосы, нос, уши, борода, шея, торс, руки, ноги.

    Все размеры считаются от `Proportions`, ни одного «магического» числа в
    метрах — при смене роста или числа голов перестраивается всё.
    """
    H = p.height
    hh = p.head_frac
    if top_dark is None:
        top_dark = tuple(c * 0.72 for c in top)
    parts: list[R3.Mesh] = []

    def put(m, color, name):
        m.color = np.asarray(color, np.float64)
        m.name = name
        parts.append(m)

    def hy(t: float) -> float:
        """Высота на относительной высоте головы t (метры)."""
        return (p.neck_y + t * hh) * H

    head_front = p.head_d * hh / 2       # глубина лица от центра (метры, без H)

    # --- голова ----------------------------------------------------------
    put(R3.loft(_head_sections(p), seg=56), skin, "head")

    # --- волосы: накладка по черепу с ровной линией роста волос -----------
    # линия роста волос: спереди выше (лоб), сзади ниже (затылок)
    hairline = lambda ph: 0.735 - 0.105 * (1.0 - math.sin(ph)) / 2.0
    # толщина растёт к макушке: получается объёмная причёска, а не шапочка.
    # Одна поверхность — ни стыков, ни лишних пересечений.
    def hair_thickness(t: float, ph: float) -> float:
        k = float(np.clip((t - 0.66) / 0.34, 0.0, 1.0))
        front = 0.5 + 0.5 * math.sin(ph)             # спереди объёма больше
        return 1.035 + 0.085 * k ** 1.4 + 0.030 * k * front ** 2

    put(head_shell(p, t0=hairline, t1=1.0, phi0=0.0, phi1=2 * math.pi,
                   out=hair_thickness, inner=1.002, nt=14, nphi=56,
                   top_pole=True), hair, "hair")
    # --- борода: накладка по нижней челюсти, овал лица открыт -------------
    # верх бороды: у рта низко, к вискам поднимается (бакенбарды)
    beard_top = lambda ph: 0.175 + 0.285 * (math.cos(ph) ** 2) ** 0.75
    put(head_shell(p, t0=-0.135, t1=beard_top, phi0=-2.30, phi1=2.30,
                   out=1.055, inner=1.002, nt=12, nphi=44),
        hair, "beard")

    # --- нос: небольшой объём по центру лица ------------------------------
    nose_base = head_point(p, 0.52, math.pi / 2)
    put(R3.sphere(1.0, seg=22, rings=16,
                  scale=(0.017 * H, 0.021 * H, 0.024 * H),
                  center=nose_base - np.array([0, 0, 0.013 * H])), skin, "nose")

    # --- уши --------------------------------------------------------------
    for side in (-1, 1):
        ear_base = head_point(p, 0.50, 0.0 if side < 0 else math.pi)
        put(R3.sphere(1.0, seg=16, rings=12,
                      scale=(0.009 * H, 0.020 * H, 0.014 * H),
                      center=ear_base + np.array([side * 0.001 * H, 0, -0.008 * H])),
            skin, "ear")

    if eyes:
        t_eye, d_eye = 0.560, 0.44          # высота и разлёт глаз в радианах
        for side in (-1, 1):
            ph = math.pi / 2 + side * d_eye
            # белок глаза (миндалевидная накладка)
            put(head_spot(p, t_eye, ph, 0.062, 0.200, out=1.026, rings=5, nphi=40),
                (0.97, 0.96, 0.94), "eye")
            # радужка почти во весь глаз — так у мастеров стиля B
            put(head_spot(p, t_eye - 0.004, ph, 0.047, 0.125, out=1.038,
                          rings=4, nphi=32), (0.32, 0.19, 0.12), "iris")
            put(head_spot(p, t_eye - 0.004, ph, 0.026, 0.066, out=1.048,
                          rings=3, nphi=22), (0.06, 0.05, 0.05), "pupil")
            put(head_spot(p, t_eye + 0.016, ph - side * 0.050, 0.013, 0.032,
                          out=1.058, rings=2, nphi=16), (1.0, 1.0, 1.0), "glint")
            # верхнее веко: кожная накладка ПЕРЕД глазом, срезает его верх
            put(head_spot(p, t_eye + 0.075, ph, 0.036, 0.208, out=1.034,
                          rings=4, nphi=36), skin, "lid")
            # нижнее веко — узкая полоска под глазом
            put(head_spot(p, t_eye - 0.062, ph, 0.018, 0.190, out=1.030,
                          rings=3, nphi=30), skin, "lid_lo")
            # бровь: толстая, с наклоном наружу
            put(head_spot(p, t_eye + 0.108, ph - side * 0.012, 0.028, 0.200,
                          out=1.042, rings=4, nphi=30), hair, "brow")

    # --- рот: пока «линия губ» (мимика и вижемы — отдельным этапом) --------
    put(head_spot(p, 0.300, math.pi / 2, 0.0110, 0.200, out=1.028, rings=3,
                  nphi=28), (0.36, 0.17, 0.15), "mouth")

    # --- шея --------------------------------------------------------------
    put(R3.tube([(0, p.shoulder_y * H - 0.02 * H, -0.004 * H),
                 (0, p.neck_y * H + 0.04 * H, -0.002 * H)],
                [0.052 * H * p.bulk, 0.044 * H * p.bulk], seg=24), skin, "neck")

    # --- торс -------------------------------------------------------------
    torso_secs = _torso_sections(p)
    put(R3.loft(torso_secs, seg=56), top, "torso")
    # горловина: узкое кольцо-«планка» отделяет голову от туловища
    collar_r = torso_secs[-1]["rx"] * 0.52
    put(R3.loft([{"y": torso_secs[-1]["y"] - 0.012 * H, "rx": collar_r, "rz": collar_r * 0.86},
                 {"y": torso_secs[-1]["y"] + 0.020 * H, "rx": collar_r * 0.96,
                  "rz": collar_r * 0.82},
                 {"y": torso_secs[-1]["y"] + 0.040 * H, "rx": collar_r * 0.80,
                  "rz": collar_r * 0.70}], seg=40), top_dark, "collar")
    # пояс худи — тёмная полоса по низу торса
    put(R3.loft([{"y": torso_secs[0]["y"] - 0.012 * H, "rx": torso_secs[0]["rx"] * 1.02,
                  "rz": torso_secs[0]["rz"] * 1.02},
                 {"y": torso_secs[0]["y"] + 0.028 * H, "rx": torso_secs[1]["rx"] * 1.01,
                  "rz": torso_secs[1]["rz"] * 1.01}], seg=48), top_dark, "hem")

    # --- руки и ноги ------------------------------------------------------
    sh_y = (p.shoulder_y - 0.006) * H
    sh_x = p.shoulder_w * hh * 0.37 * H
    arm = p.arm_len * H
    hip_x = p.hip_w * hh * 0.27 * H

    for side in (-1, 1):
        sx = side * sh_x
        # дельтовидная «шапка» — закрывает стык руки и торса
        put(R3.sphere(1.0, seg=26, rings=18,
                      scale=(0.048 * H * p.bulk, 0.045 * H * p.bulk,
                             0.046 * H * p.bulk),
                      center=(sx * 0.86, sh_y - 0.010 * H, 0.002 * H)), top,
            "deltoid")
        elbow = (sx * 1.12, sh_y - arm * 0.52, 0.004 * H)
        wrist = (sx * 1.18, sh_y - arm, 0.014 * H)
        put(R3.tube([(sx, sh_y, 0.0), (sx * 1.04, sh_y - 0.10 * H, 0.0),
                     elbow, wrist],
                    [0.050 * H * p.bulk, 0.046 * H * p.bulk,
                     0.038 * H * p.bulk, 0.031 * H * p.bulk], seg=28), top, "arm")
        put(R3.tube([(wrist[0] * 0.99, wrist[1] + 0.020 * H, wrist[2]),
                     (wrist[0] * 1.01, wrist[1] - 0.012 * H, wrist[2] + 0.002 * H)],
                    [0.035 * H * p.bulk, 0.033 * H * p.bulk], seg=24), top_dark,
            "cuff")
        put(R3.sphere(1.0, seg=22, rings=16,
                      scale=(0.030 * H, p.hand_len * H * 0.55,
                             0.024 * H * p.bulk),
                      center=(wrist[0] * 1.01, wrist[1] - p.hand_len * H * 0.44,
                              wrist[2] + 0.003 * H)), skin, "hand")

        hx = side * hip_x
        knee = (hx * 1.05, 0.255 * H, 0.006 * H)
        ankle = (hx * 1.07, 0.085 * H, -0.002 * H)
        put(R3.tube([(hx, p.hip_y * H + 0.05 * H, 0.0), (hx, p.hip_y * H, 0.0),
                     knee, ankle],
                    [0.062 * H * p.bulk, 0.064 * H * p.bulk,
                     0.050 * H * p.bulk, 0.036 * H * p.bulk], seg=28), bottom,
            "leg")
        put(R3.roundbox((0.096 * H, 0.062 * H, 0.172 * H),
                        center=(hx * 1.07, 0.031 * H, 0.036 * H),
                        roundness=3.0, seg=28, rings=16), shoes, "shoe")

    return parts


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
