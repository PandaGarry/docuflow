"""2.5D-риг: сгенерированный персонаж как кукла на костях.

Зачем
-----
Качество внешнего вида даёт сгенерированная графика (мастер-лист), а движение
даёт этот модуль: картинка режется на сетку, сетка деформируется костями, как
кожа на 3D-модели, и слегка «дышит» вторичной анимацией. Отсюда — «2.5D»:
плоская картинка, но с настоящим ригом и честной деформацией на сгибах.

Устройство
----------
1. `key_green` — вырезание по хромакею с мягкой кромкой и подавлением
   зелёного «ободка» (despill).
2. `Rig` — скелет в долях высоты персонажа: таз → талия → грудь → шея → голова,
   плечи → локти → кисти, бёдра → колени → стопы.
3. `CutoutPuppet` — разрез силуэта на крупные детали (торс, голова, руки,
   бедро, голень со стопой) и жёсткий перенос каждой детали вокруг своего
   сустава, сплэтом в один общий буфер.

Почему НЕ скиннинг сетки (проверено, тупик): на плоской картинке смешанные
веса «жуют» рукав — поднятая рука растягивает полотно вместо поворота, а
меш-варп даёт щели между ячейками и «призраки» при наложении спрайтов.
Жёсткие крупные детали + сплэт в один буфер дают непрерывный кадр.

Позы задаются углами в радианах и сдвигом корня; всё в плоскости картинки.

Важно про ограничения: это экранная анимация. Поворот персонажа «в объёме» тут
не делается — виды берутся из мастер-листа (фронт/три четверти/профиль/спина),
а внутри вида работают наклоны, повороты головы и корпуса, жесты и шаг.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------- #
# хромакей
# --------------------------------------------------------------------------- #

def key_green(img: Image.Image, *,
              soft: float = 0.16, despill: float = 0.55) -> Image.Image:
    """Вырезать зелёный фон: мягкая альфа по «зелёности» + подавление ободка."""
    rgb = np.asarray(img.convert("RGB"), np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    # «зелёность»: насколько канал G доминирует над средним из R и B
    greenness = g - (r + b) * 0.5
    # фон — заметно зелёный; тело — нет. Порог с мягким переходом.
    alpha = np.clip(1.0 - (greenness - soft * 0.15) / max(soft, 1e-6), 0.0, 1.0)
    alpha[greenness < 0.02] = 1.0

    # убрать зелёный ободок: на кромке подтягиваем G к среднему R и B
    spill = np.clip(g - np.maximum(r, b), 0.0, 1.0) * despill
    g2 = g - spill
    out = np.stack([r, g2, b], axis=-1)
    rgba = np.dstack([np.clip(out, 0.0, 1.0), alpha]).astype(np.float32)
    return Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")


def trim(img: Image.Image, pad: int = 6) -> Image.Image:
    """Обрезать прозрачные поля, оставив отступ."""
    a = np.asarray(img)[..., 3]
    ys, xs = np.where(a > 8)
    if not len(ys):
        return img
    # Координаты обязательно зажимаем в границы картинки: PIL при
    # отрицательном сдвиге дополняет кадр чёрным (0,0,0,0), а чёрное прозрачное
    # потом «оживает» при повторном хромакее и даёт чёрную рамку вокруг кадра.
    x0 = max(int(xs.min()) - pad, 0)
    y0 = max(int(ys.min()) - pad, 0)
    x1 = min(int(xs.max()) + pad + 1, img.width)
    y1 = min(int(ys.max()) + pad + 1, img.height)
    return img.crop((x0, y0, x1, y1))


# --------------------------------------------------------------------------- #
# скелет
# --------------------------------------------------------------------------- #

@dataclass
class Bone2D:
    name: str
    parent: str | None
    head: tuple[float, float]   # в долях высоты фигуры, x от центра
    tail: tuple[float, float]
    depth: float = 0.0          # порядок отрисовки: меньше — ближе к камере


DAD_BONES: list[Bone2D] = [
    # Замерено по studio/2p5d/dad/master-front-v2.png (H=1382 px):
    # плечи 0.30 (±0.171), грудь 0.42 (±0.220), талия 0.50 (±0.124),
    # таз 0.655 (±0.116), ноги 0.70–0.985, кисти 0.63–0.685.
    Bone2D("root", None, (0.0, 0.655), (0.0, 0.60)),
    Bone2D("hip", "root", (0.0, 0.655), (0.0, 0.56)),
    Bone2D("chest", "hip", (0.0, 0.56), (0.0, 0.30)),
    Bone2D("neck", "chest", (0.0, 0.30), (0.0, 0.215)),
    Bone2D("head", "neck", (0.0, 0.215), (0.0, 0.02)),

    Bone2D("upperarm.L", "chest", (-0.135, 0.300), (-0.195, 0.500)),
    Bone2D("forearm.L", "upperarm.L", (-0.195, 0.500), (-0.235, 0.625)),
    Bone2D("hand.L", "forearm.L", (-0.235, 0.625), (-0.250, 0.685)),

    Bone2D("upperarm.R", "chest", (0.135, 0.300), (0.195, 0.500)),
    Bone2D("forearm.R", "upperarm.R", (0.195, 0.500), (0.235, 0.625)),
    Bone2D("hand.R", "forearm.R", (0.235, 0.625), (0.250, 0.685)),

    Bone2D("thigh.L", "root", (-0.058, 0.655), (-0.062, 0.800)),
    Bone2D("shin.L", "thigh.L", (-0.062, 0.800), (-0.068, 0.930)),
    Bone2D("foot.L", "shin.L", (-0.068, 0.930), (-0.072, 0.985)),

    Bone2D("thigh.R", "root", (0.058, 0.655), (0.062, 0.800)),
    Bone2D("shin.R", "thigh.R", (0.062, 0.800), (0.068, 0.930)),
    Bone2D("foot.R", "shin.R", (0.068, 0.930), (0.072, 0.985)),
]


class Rig:
    """Скелет в координатах картинки + кинематика позы."""

    def __init__(self, bones: list[Bone2D], height_px: float,
                 origin: tuple[float, float]):
        self.bones = {b.name: b for b in bones}
        self.order = [b.name for b in bones]
        self.h = height_px            # высота фигуры в пикселях
        self.origin = origin          # пиксельная точка (x центра, y верха)

    # ---------------------------------------------------------------- #
    def to_px(self, pt: tuple[float, float]) -> np.ndarray:
        """Доли высоты → пиксели картинки."""
        return np.array([self.origin[0] + pt[0] * self.h,
                         self.origin[1] + pt[1] * self.h])

    def rest(self, name: str) -> tuple[np.ndarray, np.ndarray]:
        b = self.bones[name]
        return self.to_px(b.head), self.to_px(b.tail)

    def posed(self, name: str, pose: dict, cache: dict) -> tuple[np.ndarray, np.ndarray]:
        """Мировая поза кости: голова и хвост в пикселях.

        Прямая кинематика: world_rot = rot_родителя · R(угол кости),
        world_head = world_head_родителя + rot_родителя · (rest_head − rest_head_родителя).
        Так угол каждой кости ЗАДАЁТ поворот относительно родителя и не гасит
        движения цепочки — на этом ломались жесты (рука не поднималась выше
        заданного угла).
        """
        if name in cache:
            return cache[name]
        b = self.bones[name]
        r_head, r_tail = self.rest(name)
        own = float(pose.get(name, 0.0))
        c, s = math.cos(own), math.sin(own)
        own_rot = np.array([[c, -s], [s, c]])

        if b.parent is None:
            rot = own_rot
            head = r_head.copy()
        else:
            p_head, p_tail = self.posed(b.parent, pose, cache)
            rp_head, rp_tail = self.rest(b.parent)
            pv = p_tail - p_head
            rv = rp_tail - rp_head
            ang = math.atan2(pv[1], pv[0]) - math.atan2(rv[1], rv[0])
            pc, ps = math.cos(ang), math.sin(ang)
            parent_rot = np.array([[pc, -ps], [ps, pc]])
            head = p_head + parent_rot @ (r_head - rp_head)
            rot = parent_rot @ own_rot

        tail = head + rot @ (r_tail - r_head)
        world = (head, tail)
        cache[name] = world
        return world


# --------------------------------------------------------------------------- #
# кукла
# --------------------------------------------------------------------------- #



# --------------------------------------------------------------------------- #
# детали
# --------------------------------------------------------------------------- #

# Крупные жёсткие детали. Меньше деталей — меньше швов. Кисть едет вместе с
# рукавом, стопа вместе с голенью. Локоть не сгибается (осознанно: тонкий сгиб
# на плоской картинке всегда рвётся), плечо/бедро/колено/шея — да.
RIGID_PARTS = {
    "torso":   {"bone": "chest"},
    "head":    {"bone": "head"},
    "arm.R":   {"bone": "upperarm.R"},
    "arm.L":   {"bone": "upperarm.L"},
    "thigh.R": {"bone": "thigh.R"},
    "thigh.L": {"bone": "thigh.L"},
    "shin.R":  {"bone": "shin.R"},
    "shin.L":  {"bone": "shin.L"},
}

# Порядок отрисовки: дальние (ноги) → корпус → голова → руки сверху.
PAINT_ORDER = ["shin.R", "shin.L", "thigh.R", "thigh.L",
               "torso", "head", "arm.L", "arm.R"]


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(max(int(r), 0)):
        out = (out | np.roll(out, 1, 0) | np.roll(out, -1, 0) |
               np.roll(out, 1, 1) | np.roll(out, -1, 1))
    return out


def _main_blob(mask: np.ndarray, seed: tuple[float, float]) -> np.ndarray:
    """Оставить компоненту связности маски, ближайшую к точке `seed`.

    Нужна, чтобы от детали не отрывались тонкие «нити» теней (кромка подмышки,
    шов): в позе такие куски висят в воздухе чёрточками. PIL-овский floodfill
    на режиме L не сработал, scipy в окружении нет, поэтому обход в ширину
    делается по сетке, уменьшенной в 4 раза, — быстро и без зависимостей.
    """
    if not mask.any():
        return mask
    ys, xs = np.where(mask)
    d = (xs - seed[0]) ** 2 + (ys - seed[1]) ** 2
    k = int(np.argmin(d))
    sx, sy = int(xs[k]), int(ys[k])

    f = 4
    h, w = mask.shape
    ch, cw = (h + f - 1) // f, (w + f - 1) // f
    pad = np.zeros((ch * f, cw * f), bool)
    pad[:h, :w] = mask
    coarse = pad.reshape(ch, f, cw, f).any(axis=(1, 3))

    from collections import deque
    seen = np.zeros_like(coarse)
    q = deque()
    sy_, sx_ = sy // f, sx // f
    if not coarse[sy_, sx_]:
        return mask
    seen[sy_, sx_] = True
    q.append((sy_, sx_))
    while q:
        y, x = q.popleft()
        for dy_, dx_ in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy_, x + dx_
            if 0 <= ny < ch and 0 <= nx < cw and coarse[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    full = np.repeat(np.repeat(seen, f, axis=0), f, axis=1)[:h, :w]
    return mask & full


def _spread_color(rgb: np.ndarray, known: np.ndarray, steps: int = 12) -> np.ndarray:
    """Разнести цвет за кромку силуэта (для мягкой кромки и стыков)."""
    col = rgb.copy()
    k = known.copy()
    for _ in range(steps):
        for dy_, dx_ in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sh = np.roll(col, (dy_, dx_), axis=(0, 1))
            shk = np.roll(k, (dy_, dx_), axis=(0, 1))
            take = (~k) & shk
            col[take] = sh[take]
            k = k | take
    return col


class CutoutPuppet:
    """Кукла из крупных жёстких деталей.

    Силуэт режется по анатомическим линиям (доли роста), каждая деталь
    переносится жёстко — поворот вокруг своего сустава плюс перенос родителя.
    Кадр собирается сплэтом в ОДИН буфер: детали перекрыты на `overlap`
    пикселей, рисуются с 2× запасом и уменьшаются — кромка гладкая, швов и
    двойных контуров нет.
    """

    def __init__(self, image: Image.Image, rig: Rig, *, overlap: int = 5,
                 feather: float = 0.7, paint: bool = True):
        self.img = trim(image)
        self.rig = rig
        self.overlap = overlap
        self.feather = feather
        w, h = self.img.size
        self.size = (w, h)

        rgba = np.asarray(self.img.convert("RGBA"), np.float32)
        self.rgb = rgba[..., :3]
        self.alpha = rgba[..., 3] / 255.0
        self.sil = self.alpha > 0.55
        # цвет, разнесённый за силуэт: нужен, чтобы кромка и стыки брали
        # настоящую ткань, а не зелёный фон
        self.soft_col = _spread_color(self.rgb, self.sil, 14)

        Y, X = np.mgrid[0:h, 0:w]
        self.label = self._label_geom(X, Y)
        # Перекрытие — ТОЛЬКО у сустава, а не по всей границе детали.
        # Иначе корпус «отращивает» 5 px рукава вдоль всей руки, и при подъёме
        # руки эта бахрома остаётся висеть там, где рукав был (наблюдалось
        # как обрывки ткани в воздухе).
        Y2, X2 = np.mgrid[0:h, 0:w]
        cx0, top0 = rig.origin[0], rig.origin[1]
        self.parts = {}
        for i, nm in enumerate(PAINT_ORDER):
            m = (self.label == i) & self.sil
            head, tail = rig.rest(RIGID_PARTS[nm]["bone"])
            # только главная связная область детали: иначе от маски отрываются
            # тонкие «нити» теней (кромка подмышки, шов) и в позе висят в
            # воздухе чёрточками
            m = _main_blob(m, (head + tail) / 2)
            r = 0.055 * rig.h
            near = (X2 - head[0]) ** 2 + (Y2 - head[1]) ** 2 <= r * r
            part = m | (_dilate(m, overlap) & near)
            if nm == "torso":
                # плечи: когда рука поднимается, корпус не должен показывать
                # отвесный обрез. Достраиваем плечевые скругления эллипсами
                # (цвет берётся разнесённый — то есть рукав/плечо мастера).
                for sx in (-1.0, 1.0):
                    # «бок корпуса»: то, что в мастере закрыто рукавом. Без
                    # этой заливки поднятая рука открывает дыру в фоне, потому
                    # что внутренней поверхности в картинке просто нет.
                    ex = cx0 + sx * 0.152 * rig.h
                    ey = top0 + 0.400 * rig.h
                    rx, ry = 0.055 * rig.h, 0.115 * rig.h
                    part |= (((X2 - ex) / rx) ** 2 + ((Y2 - ey) / ry) ** 2 <= 1.0) & self.sil
                # бёдра: закрываем пах, чтобы шаг не открывал дыру
                # таз: по силуэту мастера (полуширина ~0.105H на v=0.66).
                # Пока таз уже бедра, при шаге снаружи открывается клин фона.
                hy = top0 + 0.660 * rig.h
                part |= (((X2 - cx0) / (0.120 * rig.h)) ** 2 +
                         ((Y2 - hy) / (0.080 * rig.h)) ** 2 <= 1.0) & self.sil
            self.parts[nm] = part

    # ---------------------------------------------------------------- #
    def _cut_u(self, v: np.ndarray) -> np.ndarray:
        """Граница «рука / корпус» по высоте: где кончается торс латерально."""
        return np.interp(v, [0.0, 0.465, 0.66, 0.76, 1.0],
                         [0.150, 0.132, 0.132, 0.165, 0.165])

    def _label_geom(self, X: np.ndarray, Y: np.ndarray) -> np.ndarray:
        """Разрезать силуэт по анатомическим линиям (в долях роста).

        Ближайшая кость не годится: внутренняя кромка рукава ближе к корпусу,
        и при подъёме руки за ней остаётся полоса-призрак. Режем линиями:
        шея 0.215; рука — всё латеральнее `_cut_u`; ноги — всё медиальнее,
        ниже паха 0.60; колено 0.82. Правила дополняют друг друга, поэтому
        ни один пиксель силуэта не остаётся «ничьим» (иначе отрезанные куски
        висят в воздухе на прежнем месте).
        """
        idx = {k: i for i, k in enumerate(PAINT_ORDER)}
        cx, top, H = self.rig.origin[0], self.rig.origin[1], self.rig.h
        u = (X - cx) / H
        v = (Y - top) / H
        cut = self._cut_u(v)
        arm = (np.abs(u) > cut) & (v >= 0.265) & (v <= 0.70)
        # Ноги режем ровно по суставу (бедро 0.655), а не ниже: иначе верх
        # бедра свисает над осью вращения и при шаге вылезает углом из силуэта.
        leg = (~arm) & (v >= 0.652)

        lab = np.full(X.shape, idx["torso"], np.int32)
        lab[v < 0.215] = idx["head"]
        lab[arm & (u > 0)] = idx["arm.R"]
        lab[arm & (u < 0)] = idx["arm.L"]
        lab[leg] = idx["thigh.R"]
        lab[leg & (u < 0)] = idx["thigh.L"]
        low = leg & (v >= 0.82)
        lab[low] = idx["shin.R"]
        lab[low & (u < 0)] = idx["shin.L"]

        # Сустав «по кругу»: у каждой подвижной детали вырезаем из её маски
        # круг вокруг собственной оси вращения и отдаём родителю. Тогда при
        # повороте граница остаётся на той же окружности — стык не расходится
        # и не появляется ступенька. Видна только круглая площадка родителя,
        # то есть читается как шарнир/плечо.
        for nm, parent, rad in (("head", "torso", 0.048),
                                ("arm.R", "torso", 0.052), ("arm.L", "torso", 0.052),
                                ("thigh.R", "torso", 0.060), ("thigh.L", "torso", 0.060),
                                ("shin.R", "thigh.R", 0.055), ("shin.L", "thigh.L", 0.055)):
            head, _ = self.rig.rest(RIGID_PARTS[nm]["bone"])
            disc = ((X - head[0]) ** 2 + (Y - head[1]) ** 2) <= (rad * self.rig.h) ** 2
            lab[disc & (lab == idx[nm])] = idx[parent]
        return lab

    def _part_transform(self, name: str, pose: dict, cache: dict):
        bone = RIGID_PARTS[name]["bone"]
        p_head, p_tail = self.rig.posed(bone, pose, cache)
        r_head, r_tail = self.rig.rest(bone)
        v, w_ = r_tail - r_head, p_tail - p_head
        ang = math.atan2(w_[1], w_[0]) - math.atan2(v[1], v[0])
        return p_head, r_head, ang

    def render(self, pose: dict | None = None, *,
               root: tuple[float, float] = (0.0, 0.0),
               canvas: tuple[int, int] | None = None,
               offset: tuple[float, float] = (0.0, 0.0),
               ss: int = 2) -> Image.Image:
        pose = pose or {}
        cache: dict = {}
        for n in self.rig.order:
            self.rig.posed(n, pose, cache)

        w, h = self.size
        canvas = (int(canvas[0]), int(canvas[1])) if canvas else (w + 120, h + 120)
        cw, ch = int(canvas[0] * ss), int(canvas[1] * ss)
        ox = (offset[0] + 60.0 + root[0]) * ss
        oy = (offset[1] + 60.0 + root[1]) * ss

        col = np.clip(self.soft_col, 0, 255)
        buf_c = np.zeros((ch, cw, 3), np.float32)
        buf_a = np.zeros((ch, cw), np.float32)

        for nm in PAINT_ORDER:
            m = self.parts.get(nm)
            if m is None or not m.any():
                continue
            ys, xs = np.where(m)
            p_head, r_head, ang = self._part_transform(nm, pose, cache)
            c, s_ = math.cos(ang), math.sin(ang)
            rx, ry = xs - r_head[0], ys - r_head[1]
            tx = p_head[0] + c * rx - s_ * ry
            ty = p_head[1] + s_ * rx + c * ry
            dx = np.rint(tx * ss + ox).astype(np.int32)
            dy = np.rint(ty * ss + oy).astype(np.int32)
            ok = (dx >= 0) & (dx < cw) & (dy >= 0) & (dy < ch)
            if not ok.any():
                continue
            dx, dy = dx[ok], dy[ok]
            buf_c[dy, dx] = col[ys[ok], xs[ok]]
            buf_a[dy, dx] = np.maximum(buf_a[dy, dx], self.alpha[ys[ok], xs[ok]])

        # проколы от округления: две итерации «взять у соседа».
        # Сдвиги — срезами, а не np.roll: roll заворачивает кадр по краям и
        # оставляет полосы-артефакты (лишние «нити» у границы).
        def shift(arr, dy_, dx_):
            out = np.zeros_like(arr)
            h_, w_ = arr.shape[:2]
            ys_ = slice(max(dy_, 0), h_ + min(dy_, 0))
            xs_ = slice(max(dx_, 0), w_ + min(dx_, 0))
            ys2 = slice(max(-dy_, 0), h_ + min(-dy_, 0))
            xs2 = slice(max(-dx_, 0), w_ + min(-dx_, 0))
            out[ys_, xs_] = arr[ys2, xs2]
            return out

        for _ in range(2):
            hole = buf_a < 0.02
            if not hole.any():
                break
            for dy_, dx_ in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                shc = shift(buf_c, dy_, dx_)
                sha = shift(buf_a, dy_, dx_)
                take = hole & (sha > 0.02)
                buf_c[take] = shc[take]
                buf_a[take] = sha[take]
                hole = hole & ~take

        img = np.dstack([np.clip(buf_c, 0, 255),
                         np.clip(buf_a, 0, 1) * 255]).astype(np.uint8)
        return Image.fromarray(img, "RGBA").resize(canvas, Image.LANCZOS)


def rig_for(image: Image.Image) -> Rig:
    """Построить риг по уже вырезанной картинке: рост = высота непрозрачного."""
    a = np.asarray(image)[..., 3]
    ys, xs = np.where(a > 8)
    h = float(ys.max() - ys.min() + 1)
    cx = float((xs.min() + xs.max()) * 0.5)
    return Rig(DAD_BONES, h, (cx, float(ys.min())))


def load_master(path: str) -> CutoutPuppet:
    """Готовый персонаж из мастера: хромакей → обрезка → риг → кукла."""
    rgba = trim(key_green(Image.open(path)))
    return CutoutPuppet(rgba, rig_for(rgba))
