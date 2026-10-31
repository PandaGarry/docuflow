"""Скалярное поле формы (SDF) и построение меша из него.

Зачем это вместо труб
--------------------
Трубы и эллипсоиды дают набор отдельных оболочек: на стыке рукава и торса
виден шов, в подмышке — прокол, на кромке одежды — «зазубрины». Скульптурная
форма — это ОДНА функция `f(p) → расстояние до поверхности`; тело лепится из
примитивов гладкими объединениями, и поверхность получается цельной, без
швов и без наложений.

Устройство модуля
-----------------
1. **Примитивы** — функции `f(P)` для массива точек формы (..., 3). Все
   считаются векторно, поэтому поле оценивается на сетке за один проход.
2. **Операции** — `union`, `smooth_union`, `subtract`, `intersect`. Гладкое
   объединение (`smin`) и есть «скульптура»: из шаров и капсул получается
   мышца, из капсул — рукав, из вычитаний — складка.
3. **Деформации** — `bend`, `twist`, `relief`: искажают координаты до оценки
   поля. Ими делаются складки ткани и изгиб.
4. **Мешер** — surface nets (двойник marching cubes): одна вершина на ячейку,
   квады между ячейками. Не требует таблиц на 256 случаев, даёт ровную
   «квадовую» топологию, а нормали берём из градиента поля — тогда затенение
   гладкое даже на грубой сетке.
5. **Доводка** — проекция вершин на поверхность по Ньютону, сглаживание
   (тоже с проекцией), AO прямо из поля.

Соглашения: расстояние отрицательно внутри; единицы — метры.
"""

from __future__ import annotations

import math

import numpy as np

import render3d as R3


# --------------------------------------------------------------------------- #
# примитивы
# --------------------------------------------------------------------------- #

def _P(P) -> np.ndarray:
    return np.asarray(P, np.float64)


def sphere(center, radius: float):
    c = np.asarray(center, np.float64)
    return lambda P: np.linalg.norm(_P(P) - c, axis=-1) - radius


def box(center, half, round_r: float = 0.0):
    """Прямоугольный параллелепипед со скруглением `round_r`."""
    c = np.asarray(center, np.float64)
    h = np.asarray(half, np.float64) - round_r

    def f(P):
        q = np.abs(_P(P) - c) - h
        outside = np.linalg.norm(np.maximum(q, 0.0), axis=-1)
        inside = np.minimum(np.max(q, axis=-1), 0.0)
        return outside + inside - round_r

    return f


def ellipsoid(center, radii, power: float = 1.0):
    """Эллипсоид. `power` > 1 делает форму «квадратнее» (торс, ботинок)."""
    c = np.asarray(center, np.float64)
    r = np.asarray(radii, np.float64)

    def f(P):
        q = (_P(P) - c) / r
        k = np.linalg.norm(np.maximum(np.abs(q), 1e-9), axis=-1)
        if power == 1.0:
            return (k - 1.0) * float(r.min())
        # суперэллипсоид: сглаженный «кирпич» без рёбер
        n = 2.0 * power
        kk = np.power(np.sum(np.power(np.abs(q), n), axis=-1), 1.0 / n)
        return (kk - 1.0) * float(r.min())

    return f


def capsule(a, b, radius: float):
    """Капсула между точками a и b (скруглённый цилиндр)."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)

    def f(P):
        pa = _P(P) - a
        ba = b - a
        denom = float(ba @ ba)
        t = np.clip((pa @ ba) / max(denom, 1e-12), 0.0, 1.0)[..., None]
        return np.linalg.norm(pa - t * ba, axis=-1) - radius

    return f


def _round_cone_dist(P, a, b, r1, r2):
    """Точное расстояние до усечённого конуса со скруглением (iq)."""
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    ba = b - a
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / max(l2, 1e-12)

    pa = _P(P) - a
    y = pa @ ba
    z = y - l2
    xv = pa * l2 - y[..., None] * ba
    x2 = np.sum(xv * xv, axis=-1)
    y2 = y * y * l2
    z2 = z * z * l2

    k = math.copysign(1.0, rr) * rr * rr * x2
    d_mid = (np.sqrt(np.maximum(x2 * a2 * il2, 0.0)) + y * rr) * il2 - r1
    d_b = np.sqrt(np.maximum(x2 + z2, 0.0)) * il2 - r2
    d_a = np.sqrt(np.maximum(x2 + y2, 0.0)) * il2 - r1
    out = np.where(np.sign(y) * a2 * y2 < k, d_a, d_mid)
    out = np.where(np.sign(z) * a2 * z2 > k, d_b, out)
    return out


def round_cone(a, b, r1: float, r2: float):
    return lambda P: _round_cone_dist(P, a, b, r1, r2)


def chain(points, radii, k: float = 0.0, samples: int = 0):
    """Цепочка усечённых конусов по ломаной — «мышца», «рукав», «палец».

    С `k > 0` стыки сглаживаются: получается непрерывная форма без
    «шариков» в суставах.
    """
    pts = np.asarray(points, np.float64)
    rad = np.asarray(radii, np.float64)
    spans = [(pts[i], pts[i + 1], float(rad[i]), float(rad[i + 1]))
             for i in range(len(pts) - 1)]

    def f(P):
        P = _P(P)
        if k <= 0.0:
            return np.minimum.reduce([_round_cone_dist(P, *s) for s in spans])
        d = _round_cone_dist(P, *spans[0])
        for s in spans[1:]:
            d = _smin(d, _round_cone_dist(P, *s), k)
        return d

    return f


def sweep(points, radii, k: float = 0.0):
    """Заметание с НЕПРЕРЫВНЫМ радиусом по длине ломаной.

    Отличие от `chain`: там каждая пара узлов — усечённый конус со
    скруглёнными торцами, и на каждом узле получается бугор («сардельки»).
    Здесь радиус берётся по дуговой координате, поэтому рукав — это гладкая
    конусная труба, а не гирлянда шариков.
    """
    pts = np.asarray(points, np.float64)
    rad = np.asarray(radii, np.float64)
    segs = []
    acc = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ln = float(np.linalg.norm(b - a))
        segs.append((a, b, ln, acc))
        acc += max(ln, 1e-9)
    total = max(acc, 1e-9)

    def f(P):
        P = _P(P)
        best = None
        for (a, b, ln, s0) in segs:
            ab = b - a
            denom = max(float(ab @ ab), 1e-12)
            t = np.clip(((P - a) @ ab) / denom, 0.0, 1.0)
            d = np.linalg.norm(P - (a + t[..., None] * ab), axis=-1)
            s = (s0 + t * ln) / total
            r = np.interp(s, np.linspace(0.0, 1.0, len(rad)), rad)
            di = d - r
            if best is None:
                best = di
            elif k <= 0.0:
                best = np.minimum(best, di)
            else:
                best = _smin(best, di, k)
        return best

    return f


def plane_y(y0: float, down: bool = True):
    """Полупространство: отсечь всё выше/ниже плоскости."""
    s = -1.0 if down else 1.0
    return lambda P: s * (_P(P)[..., 1] - y0)


def torus(center, major: float, minor: float, axis: int = 1):
    c = np.asarray(center, np.float64)

    def f(P):
        q = _P(P) - c
        i, j = [x for x in (0, 1, 2) if x != axis]
        ring = np.sqrt(q[..., i] ** 2 + q[..., j] ** 2) - major
        return np.sqrt(ring ** 2 + q[..., axis] ** 2) - minor

    return f


# --------------------------------------------------------------------------- #
# операции
# --------------------------------------------------------------------------- #

def union(*fields):
    fs = [f for f in fields if f is not None]
    return lambda P: np.minimum.reduce([f(P) for f in fs])


def smooth_union(*fields, k: float = 0.02):
    """Гладкое объединение: главный инструмент скульптора."""
    fs = [f for f in fields if f is not None]
    k = max(float(k), 1e-9)

    def f(P):
        d = fs[0](P)
        for g in fs[1:]:
            d = _smin(d, g(P), k)
        return d

    return f


def _smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1.0 - h) + a * h - k * h * (1.0 - h)


def _smax(a, b, k):
    """Гладкий максимум: -smin(-a, -b, k). Через него — вычитание и пересечение."""
    h = np.clip(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1.0 - h) + a * h + k * h * (1.0 - h)


def smooth_subtract(a, b, k: float = 0.01):
    """Вырезать из `a` форму `b` с мягкой кромкой (борозда, складка, пройма).

    Именно `smax(a, −b)`, а не `smin(a, −b)`: у минимума вдали от выреза
    побеждает `−b`, и «внутри» оказывается всё пространство вокруг детали.
    На этом легко потерять мешер — поле уходит в минус до границ объёма.
    """
    k = max(float(k), 1e-9)
    return lambda P: _smax(a(P), -b(P), k)


def smooth_intersect(a, b, k: float = 0.01):
    k = max(float(k), 1e-9)
    return lambda P: -_smin(-a(P), -b(P), k)


def displace(field, amount: float, freq, seed: int = 0, axes=(0, 1, 2),
             octaves: int = 2, squash=None):
    """Мелкий рельеф поверхности — складки ткани, неровность кожи.

    `freq` — либо одно число, либо частота по каждой оси (1/м). Для складок
    вдоль рукава нужно высокое разрешение по окружности и низкое вдоль оси:
    `freq=(0, 40, 180)`.
    """
    rng = np.random.default_rng(seed)
    phi = rng.uniform(0, 2 * math.pi, size=(octaves, 3))
    w = np.array([1.0 / (2 ** i) for i in range(octaves)])
    w /= w.sum()
    f0 = np.broadcast_to(np.asarray(freq, np.float64), (3,)).copy()
    ax = np.array([1.0 if a in axes else 0.0 for a in (0, 1, 2)])
    sq = np.asarray(squash, np.float64) if squash is not None else np.ones(3)
    dirs = np.stack([np.array([math.cos(phi[i, 0]), math.sin(phi[i, 1]),
                               math.sin(phi[i, 2]) * 0.5]) for i in range(octaves)])

    def f(P):
        P = _P(P)
        n = np.zeros(P.shape[:-1])
        for i in range(octaves):
            arg = (P * (f0 * (2 ** i)) * sq).dot(dirs[i] * ax * 3.0) + phi[i].sum()
            n += w[i] * np.sin(arg)
        return field(P) - amount * n

    return f


def _resample_profile(prof: np.ndarray, sub: int = 6) -> np.ndarray:
    """Катмулл–Ром по узлам профиля: радиусы меняются без изломов."""
    n = len(prof)
    if n < 3:
        return prof
    ext = np.vstack([prof[0] * 2 - prof[1], prof, prof[-1] * 2 - prof[-2]])
    out = []
    for i in range(n - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        ts = np.linspace(0.0, 1.0, sub, endpoint=(i == n - 2))
        seg = []
        for t in ts:
            v = 0.5 * ((2 * p1) + (-p0 + p2) * t +
                       (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                       (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
            # Катмулл–Ром «выбрасывает» за опорные значения на редких узлах:
            # корпус раздувался шире заданного. Возвращаем внутрь отрезка.
            lo_ = np.minimum(p1, p2)
            hi_ = np.maximum(p1, p2)
            v[1:] = np.clip(v[1:], lo_[1:] - 1e-9, hi_[1:] + 1e-9)
            seg.append(v)
        out.extend(seg)
    return np.array(out)


def _mono_profile(prof: np.ndarray, sub: int = 6) -> np.ndarray:
    """Монотонная кубическая интерполяция профиля (без выбросов)."""
    ys = prof[:, 0]
    dense = np.linspace(ys[0], ys[-1], (len(ys) - 1) * sub + 1)
    out = np.empty((len(dense), prof.shape[1]))
    out[:, 0] = dense
    for c in range(1, prof.shape[1]):
        vals = prof[:, c]
        d = np.diff(vals) / np.maximum(np.diff(ys), 1e-12)
        m = np.zeros(len(vals))
        m[1:-1] = 0.5 * (d[:-1] + d[1:])
        m[0], m[-1] = d[0], d[-1]
        # ограничитель Фрича–Карлсона: никаких выбросов за опорные значения
        for i in range(len(m) - 1):
            if d[i] == 0.0:
                m[i] = m[i + 1] = 0.0
            else:
                a, b = m[i] / d[i], m[i + 1] / d[i]
                h = np.hypot(a, b)
                if h > 3.0:
                    m[i] = 3.0 * a / h * d[i]
                    m[i + 1] = 3.0 * b / h * d[i]
        out[:, c] = _hermite(ys, vals, m, dense)
    return out


def _hermite(xs, ys, ms, q):
    i = np.clip(np.searchsorted(xs, q) - 1, 0, len(xs) - 2)
    h = xs[i + 1] - xs[i]
    t = (q - xs[i]) / np.maximum(h, 1e-12)
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * ys[i] + h10 * h * ms[i] + h01 * ys[i + 1] + h11 * h * ms[i + 1]


def loft(profile, *, round_cap: float = 0.0, power: float = 2.0):
    """Протяжка профиля вдоль Y: сечения (y, rx, rz, cz[, cx]).

    Это «скульптурный» вариант трубы: радиусы интерполируются между
    сечениями, поэтому силуэт точно следует заданному профилю (горловина,
    грудь, талия, бёдра), но поверхность остаётся одной функцией и не имеет
    «перетяжек» между срезами, как у набора эллипсоидов.

    `power` > 1 делает поперечное сечение ближе к прямоугольнику (торс
    человека не круглый), `round_cap` скругляет верх и низ.
    """
    prof = np.array(profile, np.float64)
    if prof.shape[1] == 3:                     # (y, rx, rz) → без сдвига
        prof = np.hstack([prof, np.zeros((len(prof), 1))])
    prof = prof[np.argsort(prof[:, 0])]
    # сглаживание профиля: без него на каждом узле излом и видимые «полосы»
    prof = _mono_profile(prof, sub=6)
    ys = prof[:, 0]
    y_lo, y_hi = ys[0], ys[-1]

    def f(P):
        P = _P(P)
        y = P[..., 1]
        # интерполяция ПО ФАКТИЧЕСКИМ y узлов (шаг после сглаживания
        # неравномерный — индексация «как будто ровно» давала мелкую пилу)
        i0 = np.clip(np.searchsorted(ys, y) - 1, 0, len(ys) - 2)
        y0_, y1_ = ys[i0], ys[i0 + 1]
        fr = np.clip((y - y0_) / np.maximum(y1_ - y0_, 1e-9), 0.0, 1.0)
        rx = prof[i0, 1] * (1 - fr) + prof[i0 + 1, 1] * fr
        rz = prof[i0, 2] * (1 - fr) + prof[i0 + 1, 2] * fr
        cz = prof[i0, 3] * (1 - fr) + prof[i0 + 1, 3] * fr
        cx = (prof[i0, 4] * (1 - fr) + prof[i0 + 1, 4] * fr) if prof.shape[1] > 4 else 0.0
        qx = np.abs(P[..., 0] - cx) / np.maximum(rx, 1e-6)
        qz = np.abs(P[..., 2] - cz) / np.maximum(rz, 1e-6)
        n = 2.0 * power
        k = np.power(np.power(qx, n) + np.power(qz, n), 1.0 / n)
        dr = (k - 1.0) * np.minimum(rx, rz)     # 0 на боковой поверхности
        # Скругление только торцов: к «расстоянию до поверхности» добавляем
        # радиус и вычитаем его в конце. Иначе round_cap раздувает ВСЁ тело —
        # именно из-за этого торс пух, а руки утопали внутри.
        qx = dr + round_cap
        q1 = y - y_hi + round_cap
        q2 = y_lo - y + round_cap
        outside = np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(q1, 0.0) ** 2 +
                          np.maximum(q2, 0.0) ** 2)
        inside = np.minimum(np.maximum(qx, np.maximum(q1, q2)), 0.0)
        return outside + inside - round_cap

    return f


def _frame(a, b):
    a = np.asarray(a, np.float64)
    b = np.asarray(b, np.float64)
    ax = b - a
    ln = float(np.linalg.norm(ax))
    ax = ax / max(ln, 1e-12)
    ref = np.array([0.0, 1.0, 0.0]) if abs(ax[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(ax, ref)
    u /= max(np.linalg.norm(u), 1e-12)
    v = np.cross(ax, u)
    return a, ax, u, v, max(ln, 1e-12)


def waves_around(field, a, b, n: int, amp: float, *, taper=(0.08, 0.92),
                 phase: float = 0.0, axis_shift: float = 0.0):
    """Кольцевые складки вокруг оси a→b — сборка ткани у локтя, манжеты.

    Смещение радиальное, число складок `n`, амплитуда гаснет к концам
    (`taper`), поэтому на стыках со соседними деталями шва не появляется.
    """
    a0, ax, u, v, ln = _frame(a, b)
    t0, t1 = taper

    def f(P):
        P = _P(P)
        rel = P - a0
        along = rel @ ax                 # метры вдоль оси
        t = along / ln                   # доля длины
        r = rel - along[..., None] * ax  # радиус-вектор от оси
        ang = np.arctan2(r @ v, r @ u)
        env = np.sin(np.pi * np.clip((t - t0) / max(t1 - t0, 1e-6), 0.0, 1.0)) ** 0.5
        d = amp * env * np.cos(n * ang + phase)
        rn = np.linalg.norm(r, axis=-1, keepdims=True)
        dirv = r / np.maximum(rn, 1e-9)
        return field(P + dirv * d[..., None] - ax * axis_shift)

    return f


def wrinkles(field, a, b, amp: float, freq=(60.0, 6.0), seed: int = 0,
             octaves: int = 2):
    """Мягкая неровность ткани в цилиндрической системе «вдоль/вокруг».

    В отличие от мирового шума складки идут вдоль конечности, а не режут её
    поперёк — так ведёт себя трикотаж.
    """
    a0, ax, u, v, ln = _frame(a, b)
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi, size=(octaves, 3))
    w = np.array([1.0, 0.55, 0.3][:octaves])
    w /= w.sum()

    def f(P):
        P = _P(P)
        rel = P - a0
        along = rel @ ax
        t = along / ln
        r = rel - along[..., None] * ax
        ang = np.arctan2(r @ v, r @ u)
        d = np.zeros_like(t)
        for i in range(octaves):
            k = 2 ** i
            d += w[i] * np.sin(freq[0] * k * t + freq[1] * k * ang + ph[i].sum())
        env = np.sin(np.pi * np.clip(t, 0.0, 1.0)) ** 0.6
        rn = np.linalg.norm(r, axis=-1, keepdims=True)
        dirv = r / np.maximum(rn, 1e-9)
        return field(P + dirv * (amp * d * env)[..., None])

    return f


def bend_y(field, y0: float, amount: float, axis: int = 2):
    """Плавный изгиб относительно горизонта `y0` (для позы и ткани)."""

    def f(P):
        P = _P(P)
        Q = P.copy()
        d = P[..., 1] - y0
        Q[..., axis] -= amount * d * d
        return field(Q)

    return f


def mirror_x(field):
    """Симметрия по X: лепим половину — вторая получается сама."""
    return lambda P: field(np.stack([np.abs(_P(P)[..., 0]), _P(P)[..., 1],
                                     _P(P)[..., 2]], axis=-1))


def scale_about(field, center, scale):
    """Неравномерный масштаб вокруг точки (с поправкой на искажение поля)."""
    c = np.asarray(center, np.float64)
    s = np.asarray(scale, np.float64)
    factor = float(s.min())

    def f(P):
        Q = (_P(P) - c) / s
        return field(Q + c) * factor

    return f


# --------------------------------------------------------------------------- #
# оценка поля и выборка по сетке
# --------------------------------------------------------------------------- #

def grid(field, lo, hi, res, chunk: int = 16):
    """Значения поля на равномерной сетке (по слоям, чтобы не жечь память)."""
    lo = np.asarray(lo, np.float64)
    hi = np.asarray(hi, np.float64)
    res = np.asarray(res, int)
    axes = [np.linspace(lo[i], hi[i], int(res[i])) for i in range(3)]
    F = np.empty(tuple(int(r) for r in res), np.float64)
    Y, Z = np.meshgrid(axes[1], axes[2], indexing="ij")
    for i0 in range(0, res[0], chunk):
        i1 = min(i0 + chunk, res[0])
        X = axes[0][i0:i1][:, None, None]
        P = np.stack(np.broadcast_arrays(X, Y[None], Z[None]), axis=-1)
        F[i0:i1] = np.asarray(field(P), np.float64)
    return F, axes


def gradient(field, P, h: float = 1e-3):
    """Центральная разность по полю — нормаль поверхности."""
    P = _P(P)
    g = np.zeros_like(P)
    for i in range(3):
        d = np.zeros(3)
        d[i] = h
        g[..., i] = (field(P + d) - field(P - d)) / (2 * h)
    return g


class Sampled:
    """Поле, посчитанное на сетке: дальше всё берётся трилинейной выборкой.

    Один проход по функции поля на сетке (это дорого) и дальше любое число
    запросов — дешёвое. Отсюда скорость: нормали, AO и проекция вершин не
    требуют повторных вызовов поля.
    """

    def __init__(self, field, lo, hi, res, chunk: int = 16):
        self.lo = np.asarray(lo, np.float64)
        self.hi = np.asarray(hi, np.float64)
        self.res = np.asarray(res, int)
        self.F, _ = grid(field, self.lo, self.hi, self.res, chunk=chunk)
        self.F = self.F.astype(np.float32)   # для выборки хватает; вдвое меньше памяти
        self.h = (self.hi - self.lo) / np.maximum(self.res - 1, 1)
        # градиент по сетке (нормаль), в тех же единицах
        g = np.gradient(self.F, *self.h)
        self.G = [np.asarray(a, np.float64) for a in g]
        self._shape = np.array(self.F.shape)
        self._strides = np.array([self.F.shape[1] * self.F.shape[2],
                                  self.F.shape[2], 1])

    # ------------------------------------------------------------------ #
    def _idx(self, p):
        u = (p - self.lo) / self.h
        i0 = np.clip(np.floor(u).astype(np.int64), 0, self._shape - 2)
        f = np.clip(u - i0, 0.0, 1.0)
        return i0, f

    def _gather(self, arr, i0, f):
        ax, ay, az = i0[..., 0], i0[..., 1], i0[..., 2]
        arr = np.asarray(arr, np.float32)
        f = f.astype(np.float32)
        fx, fy, fz = f[..., 0], f[..., 1], f[..., 2]
        sy, sz = self._shape[1] * self._shape[2], self._shape[2]
        base = ax * sy + ay * sz + az
        flat = arr.reshape(-1)
        c000 = flat[base]
        c100 = flat[base + sy]
        c010 = flat[base + sz]
        c110 = flat[base + sy + sz]
        c001 = flat[base + 1]
        c101 = flat[base + sy + 1]
        c011 = flat[base + sz + 1]
        c111 = flat[base + sy + sz + 1]
        c00 = c000 * (1 - fx) + c100 * fx
        c10 = c010 * (1 - fx) + c110 * fx
        c01 = c001 * (1 - fx) + c101 * fx
        c11 = c011 * (1 - fx) + c111 * fx
        c0 = c00 * (1 - fy) + c10 * fy
        c1 = c01 * (1 - fy) + c11 * fy
        return c0 * (1 - fz) + c1 * fz

    def at(self, p):
        """Значение поля в точках (трилинейно)."""
        p = _P(p)
        i0, f = self._idx(p)
        return self._gather(self.F, i0, f)

    def grad(self, p):
        """Нормаль поверхности (нормированная) в точках."""
        p = _P(p)
        i0, f = self._idx(p)
        g = np.stack([self._gather(a, i0, f) for a in self.G], axis=-1)
        ln = np.linalg.norm(g, axis=-1, keepdims=True)
        return g / np.maximum(ln, 1e-12), ln[..., 0]


def auto_bounds(field, center, radius, res=40, pad_cells=2.0):
    """Точный габарит формы по грубой сетке: (lo, hi) с запасом в пару ячеек.

    Нужен, чтобы не гадать с объёмом и не обрезать поверхность границей —
    обрезанный меш не замкнут, и это ломает и скиннинг, и AO.
    """
    c = np.asarray(center, np.float64)
    r = float(radius)
    F, axes = grid(field, c - r, c + r, (res,) * 3)
    inside = F < 0
    if not inside.any():
        raise ValueError("форма не найдена в заданном объёме")
    lo = np.empty(3)
    hi = np.empty(3)
    for i in range(3):
        others = tuple(d for d in range(3) if d != i)
        prof = inside.any(axis=others)
        idxs = np.where(prof)[0]
        lo[i], hi[i] = axes[i][idxs[0]], axes[i][idxs[-1]]
    step = (2 * r) / max(res - 1, 1)
    # запас, чтобы поверхность гарантированно была внутри
    return lo - pad_cells * step, hi + pad_cells * step


# --------------------------------------------------------------------------- #
# мешер: surface nets
# --------------------------------------------------------------------------- #

_CORNERS = [(di, dj, dk) for di in (0, 1) for dj in (0, 1) for dk in (0, 1)]
_CI = {c: i for i, c in enumerate(_CORNERS)}

_EDGES = []
for axis in range(3):
    for other in [c for c in _CORNERS if c[axis] == 0]:
        b = list(other)
        b[axis] = 1
        _EDGES.append((_CI[other], _CI[tuple(b)], np.array(b) - np.array(other)))


def _cell_corners(F: np.ndarray) -> list[np.ndarray]:
    """8 массивов значений поля в углах каждой ячейки (сетка ячеек n-1)."""
    nx, ny, nz = F.shape
    return [F[di:nx - 1 + di, dj:ny - 1 + dj, dk:nz - 1 + dk]
            for (di, dj, dk) in _CORNERS]


def mesh_from_sdf(field, lo, hi, res=64, *, newton: int = 2, smooth: int = 1,
                  smooth_ratio: float = 0.45, ao: bool = True,
                  color=(0.8, 0.8, 0.8), rough: float = 0.9,
                  name: str = "sdf", cull: bool = True,
                  ao_radius: float = 3.0, sample: "Sampled | None" = None,
                  allow_clipped: bool = False, verbose: bool = False) -> R3.Mesh:
    """Построить меш из поля: surface nets + проекция + нормали из градиента."""
    import time
    t0 = time.time()
    S = sample if sample is not None else Sampled(field, lo, hi, res)
    F, lo, h = S.F, S.lo, S.h
    if (F < 0).all() or not (F < 0).any():
        raise ValueError("поле не пересекает границы объёма — пустой меш")
    if not allow_clipped:
        on_edge = ((F[0] < 0).any() or (F[-1] < 0).any() or
                   (F[:, 0] < 0).any() or (F[:, -1] < 0).any() or
                   (F[:, :, 0] < 0).any() or (F[:, :, -1] < 0).any())
        if on_edge:
            raise ValueError("поверхность выходит за границы объёма — меш был бы "
                             "незамкнутым; расширьте lo/hi (см. auto_bounds)")

    corners = _cell_corners(F)
    shape = tuple(F.shape[i] - 1 for i in range(3))

    # вершина ячейки — среднее точек пересечения на её 12 рёбрах
    acc = np.zeros(shape + (3,), np.float32)
    cnt = np.zeros(shape, np.float32)
    for i0, i1, delta in _EDGES:
        f0, f1 = corners[i0], corners[i1]
        cross = (f0 < 0.0) != (f1 < 0.0)
        if not cross.any():
            continue
        t = np.where(cross, f0 / np.where(cross, f0 - f1, 1.0), 0.0)
        base = np.array(_CORNERS[i0], np.float64)
        for a in range(3):
            acc[..., a] += np.where(cross, base[a] + t * delta[a], 0.0)
        cnt += cross

    has_v = cnt > 0
    if not has_v.any():
        raise ValueError("нет ни одного пересечения — пустой меш")
    local = acc / np.maximum(cnt, 1.0)[..., None]

    idx = np.full(shape, -1, np.int64)
    idx[has_v] = np.arange(int(has_v.sum()))
    ii, jj, kk = np.nonzero(has_v)
    verts = lo + (np.stack([ii, jj, kk], axis=-1) + local[has_v]) * h

    # квады вокруг рёбер сетки: для каждой ячейки — её каноническое ребро
    # вдоль оси; четыре соседние ячейки вокруг ребра образуют квад.
    quads = []

    def shift(a, axis, amount):
        """a[idx] = a[idx − amount], за границей −1 (не оборачивать!)."""
        out = np.full_like(a, -1)
        src = [slice(None)] * 3
        dst = [slice(None)] * 3
        if amount > 0:
            src[axis] = slice(0, a.shape[axis] - amount)
            dst[axis] = slice(amount, a.shape[axis])
        else:
            src[axis] = slice(-amount, a.shape[axis])
            dst[axis] = slice(0, a.shape[axis] + amount)
        out[tuple(dst)] = a[tuple(src)]
        return out

    for axis in range(3):
        a0 = [slice(None)] * 3
        a1 = [slice(None)] * 3
        a0[axis] = slice(0, F.shape[axis] - 1)
        a1[axis] = slice(1, F.shape[axis])
        m = (F[tuple(a0)] < 0) != (F[tuple(a1)] < 0)
        crop = [slice(0, F.shape[d] - 1) if d != axis else slice(None)
                for d in range(3)]
        m = m[tuple(crop)]
        if not m.any():
            continue
        d1, d2 = [d for d in range(3) if d != axis]
        q1 = shift(idx, d1, 1)
        cells = [idx, q1, shift(q1, d2, 1), shift(idx, d2, 1)]
        ok = m.copy()
        for cid in cells:
            ok &= cid >= 0
        if ok.any():
            quads.append(np.stack([cid[ok] for cid in cells], axis=-1))

    if not quads:
        raise ValueError("нет квадов — поверхность не замкнута в объёме")
    Q = np.concatenate(quads, axis=0)
    tris = np.concatenate([Q[:, [0, 1, 2]], Q[:, [0, 2, 3]]], axis=0)

    # сглаживание и проекция на поверхность (по сетке, без вызовов поля)
    for _ in range(max(int(smooth), 0)):
        verts = _laplacian(verts, tris, smooth_ratio)
        verts = _project(S, verts, steps=1)
    for _ in range(max(int(newton), 0)):
        verts = _project(S, verts, steps=1)

    normals, _ = S.grad(verts)

    # ориентация треугольников по градиенту поля: изнанки быть не должно
    c = verts[tris].mean(axis=1)
    tn = np.cross(verts[tris[:, 1]] - verts[tris[:, 0]],
                  verts[tris[:, 2]] - verts[tris[:, 0]])
    g, _ = S.grad(c)
    flip = np.sum(tn * g, axis=1) < 0
    tris[flip] = tris[flip][:, [0, 2, 1]]

    ao_v = None
    if ao:
        ao_v = _ao_from_sampled(S, verts, normals, float(np.min(h)), ao_radius)

    if verbose:
        print(f"  меш {name}: {len(verts)} верт / {len(tris)} тр, {time.time()-t0:.2f} с")

    return R3.Mesh(verts, tris, normals, np.asarray(color, np.float64), ao_v,
                   rough, cull, name)


def _laplacian(verts, tris, ratio):
    """Одна итерация сглаживания по рёбрам треугольника."""
    n = len(verts)
    acc = np.zeros((n, 3))
    cnt = np.zeros(n)
    # bincount вместо np.add.at: в разы быстрее на больших мешах
    for a, b in ((0, 1), (1, 2), (2, 0)):
        i, j = tris[:, a], tris[:, b]
        ii = np.concatenate([i, j])
        jj = np.concatenate([j, i])
        for k in range(3):
            acc[:, k] += np.bincount(ii, weights=verts[jj, k], minlength=n)
        cnt += np.bincount(ii, minlength=n)
    avg = acc / np.maximum(cnt, 1.0)[:, None]
    return verts * (1.0 - ratio) + avg * ratio


def _project(S: "Sampled", verts, steps=1, max_move_cells: float = 1.5):
    """Проекция на поверхность по Ньютону: p ← p − f·∇f/|∇f|²."""
    h = float(np.min(S.h))
    for _ in range(max(steps, 1)):
        f = S.at(verts)
        g, g2 = S.grad(verts)
        step = (f / np.maximum(g2 ** 2, 1e-12))[:, None] * g
        ln = np.linalg.norm(step, axis=1, keepdims=True)
        step *= np.minimum(1.0, (h * max_move_cells) / np.maximum(ln, 1e-12))
        verts = verts - step
    return verts


def _ao_from_sampled(S: "Sampled", verts, normals, cell, radius_cells):
    """AO из поля: сколько «материала» рядом вдоль нормали.

    Честное затенение по геометрии, а не по треугольникам: впадины
    (подбородок, подмышка, складка ткани) темнеют сами.
    """
    dists = np.linspace(0.4, 1.0, 4) * (radius_cells * cell)
    occ = np.zeros(len(verts))
    for t in dists:
        f = S.at(verts + normals * t)
        occ += np.clip((t - f) / t, 0.0, 1.0)
    occ /= len(dists)
    return np.clip(1.0 - occ * 1.6, 0.0, 1.0)


# --------------------------------------------------------------------------- #
# диагностика
# --------------------------------------------------------------------------- #

def stats(mesh: R3.Mesh) -> dict:
    """Проверка меша: замкнутость, ориентация, объём, габарит."""
    f = mesh.tris
    v = mesh.verts
    e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    vol = float(np.sum(np.einsum("ij,ij->i", v[f[:, 0]],
                                 np.cross(v[f[:, 1]], v[f[:, 2]]))) / 6.0)
    return {"verts": int(len(v)), "tris": int(len(f)),
            "closed": bool((counts == 2).all()),
            "edges_not_2": int((counts != 2).sum()),
            "volume": vol,
            "outward": vol > 0,
            "bounds": (v.min(axis=0), v.max(axis=0))}
