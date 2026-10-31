"""Риг ходьбы: одна заготовка гнётся по костям, кадр за кадром.

    python studio/tools/walk_rig.py dad        # 6 секунд, 24 к/с

Зачем риг, если были рисованные ключи
-------------------------------------
12 нарисованных ключей держатся по 2 кадра — между ними поза меняется
скачком, глаз видит «переключатель», а не движение. Здесь поза считается
непрерывно: на каждый кадр задаются углы, и рисунок деформируется под них.
Кадры получаются «на единицах», 24 разных позы в секунду.

Анатомия ноги заложена в модель, а не в рисунок:
    a2 = a1 - flex,  flex >= 0
то есть голень всегда отстаёт от бедра — колено сгибается ТОЛЬКО назад,
пятка идёт к ягодице. Выгнуть колено вперёд физически невозможно, поэтому
«сломанная» передняя нога не может появиться.

Что гнётся
----------
Ноги: бедро, голень, стопа (у каждой ноги свои веса).
Руки: плечо с малым махом в противофазе ногам.
Таз: корпус неподвижен, а высота ВСЕГО тела считается из ног — опорная
стопа прибита к полу, поэтому подъём-опускание (bob) получается само и
нога никогда не проваливается под пол.

Деформация непрерывная (linear blend skinning по весам костей), рисунок не
режется на куски, поэтому швов и щелей нет по построению.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
import cv2
from PIL import Image

import cutout

ROOT = HERE.parents[2]
POSES = ROOT / "studio/2p5d/dad/poses"
SOURCE = POSES / "w3-01.png"      # контактная поза: ноги широко, всё видно


# --------------------------------------------------------------------------- #
# скелет (координаты в пикселях исходного рисунка 768x1400)
# --------------------------------------------------------------------------- #
JOINTS = {
    # ближняя к камере нога (в кадре она уходит вправо-вперёд)
    "hip_n": (400, 800), "knee_n": (545, 1030), "ankle_n": (650, 1235),
    "toe_n": (700, 1310),
    # дальняя нога (уходит влево-назад)
    "hip_f": (392, 800), "knee_f": (245, 1075), "ankle_f": (115, 1250),
    "toe_f": (60, 1315),
    # рука
    "shoulder": (330, 520), "elbow": (215, 700), "wrist": (190, 815),
    # корпус
    "pelvis": (390, 800),
}
LEG_N = ("hip_n", "knee_n", "ankle_n")      # цепочка костей ближней ноги
LEG_F = ("hip_f", "knee_f", "ankle_f")
FOOT_N = ("ankle_n", "toe_n")
FOOT_F = ("ankle_f", "toe_f")
ARM = ("shoulder", "elbow", "wrist")

PAD = 60            # поля сверху: тело качается, макушка не должна обрезаться
FLOOR = 1352        # y пола в исходном рисунке
LEG_R = 150.0       # радиус влияния костей ноги, px
ARM_R = 95.0
SIGMA = 10.0        # мягкость перехода на сгибе


def joints_at(size: tuple[int, int]) -> dict:
    """Суставы в пикселях текущего холста (с полями PAD)."""
    w, h = size
    sx, sy = w / 768.0, (h - PAD) / 1400.0
    return {k: (v[0] * sx, v[1] * sy + PAD) for k, v in JOINTS.items()}


def floor_at(size: tuple[int, int]) -> float:
    return FLOOR * (size[1] - PAD) / 1400.0 + PAD


def _ang(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Абсолютный угол сегмента a→b: от «вниз», плюс — вперёд (вправо)."""
    return math.degrees(math.atan2(b[0] - a[0], b[1] - a[1]))


BASE = {
    "thigh_n": _ang(JOINTS["hip_n"], JOINTS["knee_n"]),
    "shin_n": _ang(JOINTS["knee_n"], JOINTS["ankle_n"]),
    "thigh_f": _ang(JOINTS["hip_f"], JOINTS["knee_f"]),
    "shin_f": _ang(JOINTS["knee_f"], JOINTS["ankle_f"]),
    "foot_n": _ang(JOINTS["ankle_n"], JOINTS["toe_n"]),
    "foot_f": _ang(JOINTS["ankle_f"], JOINTS["toe_f"]),
    "arm": _ang(JOINTS["shoulder"], JOINTS["elbow"]),
}
# сгиб, нарисованный в заготовке: a2 = a1 - flex
FLEX_N0 = BASE["thigh_n"] - BASE["shin_n"]
FLEX_F0 = BASE["thigh_f"] - BASE["shin_f"]


# --------------------------------------------------------------------------- #
# веса
# --------------------------------------------------------------------------- #
def _seg_dist(xx, yy, a, b):
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    L2 = max(vx * vx + vy * vy, 1e-6)
    t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / L2, 0.0, 1.0)
    return np.hypot(xx - (ax + vx * t), yy - (ay + vy * t))


def _chain_dist(xx, yy, pts):
    """Расстояние до ломаной из точек (в пикселях изображения)."""
    d = None
    for a, b in zip(pts, pts[1:]):
        di = _seg_dist(xx, yy, a, b)
        d = di if d is None else np.minimum(d, di)
    return d


def build_weights(size: tuple[int, int], sigma: float = 26.0) -> dict:
    """Карты весов костей.

    Главное — непрерывность: сумма весов в каждой точке равна 1, поэтому после
    деформации не может появиться дыр, а мягкий переход на сгибе (размытие
    большим ядром) убирает «залом» на колене. Пиксель относится к одной из двух
    ног жёстко (по ближайшей цепочке), внутри ноги веса бедра/голени/стопы
    смешиваются плавно, всё остальное (торс, таз) — «тело», оно не движется и
    служит связкой, чтобы пах не рвался.
    """
    w, h = size
    sx, sy = w / 768.0, (h - PAD) / 1400.0
    J = joints_at(size)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    def chain(names):
        return [J[n] for n in names]

    dn = np.minimum(_chain_dist(xx, yy, chain(LEG_N)),
                    _seg_dist(xx, yy, *chain(FOOT_N)))
    df = np.minimum(_chain_dist(xx, yy, chain(LEG_F)),
                    _seg_dist(xx, yy, *chain(FOOT_F)))
    is_near = dn <= df
    leg_d = np.minimum(dn, df)
    # ноги плавно «растворяются» в теле с высотой: у таза веса ног падают
    hip_y = J["hip_n"][1]
    fade = np.clip((yy - (hip_y - 150 * sy)) / (170 * sy), 0.0, 1.0)
    leg_w = np.clip(1.0 - (leg_d - LEG_R * sx * 0.55) / (LEG_R * sx * 0.75), 0.0, 1.0) * fade

    out = {}
    for side, is_side in (("n", is_near), ("f", ~is_near)):
        bones = {
            f"thigh_{side}": (J[f"hip_{side}"], J[f"knee_{side}"]),
            f"shin_{side}": (J[f"knee_{side}"], J[f"ankle_{side}"]),
            f"foot_{side}": (J[f"ankle_{side}"], J[f"toe_{side}"]),
        }
        raw = {}
        for name, (a2, b2) in bones.items():
            d = _seg_dist(xx, yy, a2, b2)
            raw[name] = 1.0 / (d + 25.0) ** 3
        tot = sum(raw.values())
        for name in raw:
            m = (raw[name] / tot) * leg_w * is_side
            out[name] = cv2.GaussianBlur(m.astype(np.float32), (0, 0), sigma)

    # рука
    in_arm = np.clip(1.0 - (_chain_dist(xx, yy, chain(ARM)) - ARM_R * sx * 0.5)
                     / (ARM_R * sx * 0.8), 0.0, 1.0)
    raw = {
        "arm_up": 1.0 / (_seg_dist(xx, yy, *chain(("shoulder", "elbow"))) + 25.0) ** 3,
        "arm_lo": 1.0 / (_seg_dist(xx, yy, *chain(("elbow", "wrist"))) + 25.0) ** 3,
    }
    tot = sum(raw.values())
    for name in raw:
        out[name] = cv2.GaussianBlur(((raw[name] / tot) * in_arm).astype(np.float32),
                                     (0, 0), sigma)

    tot = np.zeros((h, w), np.float32)
    for m in out.values():
        tot += m
    # остаток (торс, таз, голова) — неподвижная связка
    out["body"] = np.clip(1.0 - tot, 0.0, 1.0)
    tot = tot + out["body"]
    for k in out:
        out[k] = out[k] / np.maximum(tot, 1e-5)
    return out


# --------------------------------------------------------------------------- #
# кинематика
# --------------------------------------------------------------------------- #
def _rot_about(pts: np.ndarray, pivot, deg: float) -> np.ndarray:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    ox = pts[..., 0] - pivot[0]
    oy = pts[..., 1] - pivot[1]
    return np.stack([pivot[0] + ox * c - oy * s,
                     pivot[1] + ox * s + oy * c], axis=-1)


def _len(a, b) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


L1 = {"n": _len(JOINTS["hip_n"], JOINTS["knee_n"]),
      "f": _len(JOINTS["hip_f"], JOINTS["knee_f"])}
L2 = {"n": _len(JOINTS["knee_n"], JOINTS["ankle_n"]),
      "f": _len(JOINTS["knee_f"], JOINTS["ankle_f"])}
ANKLE_Y = {"n": JOINTS["ankle_n"][1], "f": JOINTS["ankle_f"][1]}
ANKLE_X = {"n": JOINTS["ankle_n"][0], "f": JOINTS["ankle_f"][0]}


def ankle_track(t: float, side: str, cfg: dict) -> tuple[float, float]:
    """Куда поставить лодыжку в момент t (в пикселях рисунка).

    Ходьба «на месте»: в опоре стопа едет по полу назад с постоянной
    скоростью (иначе она «катается»), в переносе — идёт по дуге вперёд с
    подъёмом. Именно это делает шаг шагом, а не переставлением ног.
    """
    ph = t if side == "n" else (t + 0.5) % 1.0
    half = cfg["stride"] * 0.5
    base_x = ANKLE_X[side]
    y_floor = FLOOR - cfg["sole"]

    if ph < cfg["stance"]:                       # опора: пятка→носок назад
        k = ph / cfg["stance"]
        x = base_x + half - cfg["stride"] * k
        y = y_floor
    else:                                        # перенос: дуга вперёд
        k = (ph - cfg["stance"]) / (1.0 - cfg["stance"])
        # плавный разгон и мягкую постановку
        e = 0.5 - 0.5 * math.cos(math.pi * k)
        x = base_x - half + cfg["stride"] * e
        y = y_floor - cfg["lift"] * math.sin(math.pi * k) ** 0.9
    return x, y


def ik_leg(side: str, ankle: tuple[float, float],
           hip_dy: float = 0.0) -> dict:
    """Обратная кинематика двухзвенной ноги. Колено гнётся ТОЛЬКО назад."""
    H = (JOINTS[f"hip_{side}"][0], JOINTS[f"hip_{side}"][1] + hip_dy)
    l1, l2 = L1[side], L2[side]
    dx, dy = ankle[0] - H[0], ankle[1] - H[1]
    d = min(math.hypot(dx, dy), l1 + l2 - 0.5)
    d = max(d, abs(l1 - l2) + 0.5)
    base = math.degrees(math.atan2(dx, dy))
    cos_a = (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)
    alpha = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    thigh_abs = base + alpha                      # колено вперёд, не назад
    K = (H[0] + l1 * math.sin(math.radians(thigh_abs)),
         H[1] + l1 * math.cos(math.radians(thigh_abs)))
    shin_abs = math.degrees(math.atan2(ankle[0] - K[0], ankle[1] - K[1]))
    rot_thigh = thigh_abs - BASE[f"thigh_{side}"]
    rot_shin = shin_abs - BASE[f"shin_{side}"] - rot_thigh
    return {"thigh": rot_thigh, "shin": rot_shin,
            "thigh_abs": thigh_abs, "shin_abs": shin_abs,
            "flex": thigh_abs - shin_abs}


def angles_at(t: float, cfg: dict) -> dict:
    """Повороты костей (градусы от рисунка) для кадра t."""
    bob = cfg["bob"] * math.cos(4 * math.pi * t)   # 2 подъёма за цикл
    out = {}
    for side in ("n", "f"):
        ph = t if side == "n" else (t + 0.5) % 1.0
        ank = ankle_track(t, side, cfg)
        ik = ik_leg(side, ank, hip_dy=bob)
        out[f"thigh_{side}"] = ik["thigh"]
        out[f"shin_{side}"] = ik["shin"]
        # стопа: в опоре плоская (компенсируем поворот ноги), в переносе
        # подтягиваем носок, чтобы он не цеплял пол
        swing = max(0.0, (ph - cfg["stance"]) / (1.0 - cfg["stance"]))
        if ph < cfg["stance"]:
            foot = -(ik["thigh"] + ik["shin"])
        else:
            foot = -(ik["thigh"] + ik["shin"]) * (1 - swing) \
                   + cfg["toe"] * math.sin(math.pi * swing)
        out[f"foot_{side}"] = foot
        out[f"_ank_{side}"] = ank
        out[f"_flex_{side}"] = ik["flex"]
    out["arm_up"] = -cfg["arm"] * math.cos(2 * math.pi * t)
    out["arm_lo"] = out["arm_up"] * 0.5
    out["_bob"] = bob
    return out


def foot_positions(t: float, cfg: dict, size) -> dict:
    w, h = size
    sx, sy = w / 768.0, (h - PAD) / 1400.0
    a = angles_at(t, cfg)
    return {s: (a[f"_ank_{s}"][0] * sx, a[f"_ank_{s}"][1] * sy + PAD)
            for s in ("n", "f")}


# --------------------------------------------------------------------------- #
# рендер
# --------------------------------------------------------------------------- #
def render(drawing: np.ndarray, weights: dict, angles: dict,
           shift_y: float = 0.0) -> np.ndarray:
    h, w = drawing.shape[:2]
    J = joints_at((w, h))
    piv = {
        "thigh_n": J["hip_n"], "shin_n": J["knee_n"], "foot_n": J["ankle_n"],
        "thigh_f": J["hip_f"], "shin_f": J["knee_f"], "foot_f": J["ankle_f"],
        "arm_up": J["shoulder"], "arm_lo": J["elbow"],
    }
    # цепочка зависимостей: поворот голени включает поворот бедра и т.д.
    parent = {"shin_n": "thigh_n", "foot_n": "shin_n",
              "shin_f": "thigh_f", "foot_f": "shin_f",
              "arm_lo": "arm_up"}

    def total(bone):
        a = angles.get(bone, 0.0)
        p = parent.get(bone)
        while p:
            a += angles.get(p, 0.0)
            p = parent.get(p)
        return a

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = np.zeros((h, w), np.float32)
    dy = np.zeros((h, w), np.float32)
    for bone, wmap in weights.items():
        ang = total(bone)
        if abs(ang) < 1e-4:
            continue
        pts = _rot_about(np.stack([xx, yy], -1), piv[bone], ang)
        dx += wmap * (pts[..., 0] - xx)
        dy += wmap * (pts[..., 1] - yy)

    src = drawing.astype(np.float32)
    out = cv2.remap(src, xx + dx, yy + dy, cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    if shift_y:
        M = np.float32([[1, 0, 0], [0, 1, shift_y]])
        out = cv2.warpAffine(out, M, (w, h), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0, 0))
    return np.clip(out, 0, 255).astype(np.uint8)


def load_source() -> tuple[np.ndarray, tuple[int, int]]:
    img = Image.open(SOURCE).convert("RGB")
    rgba = cutout.key_green(img)
    rgba = cutout.kill_blue_rim(rgba)
    rgba = cutout.flatten_bad_patch(rgba)
    rgba = cutout.tighten(rgba)
    a = np.asarray(rgba)
    pad = np.zeros((a.shape[0] + PAD, a.shape[1], 4), np.uint8)
    pad[PAD:] = a
    return pad, (pad.shape[1], pad.shape[0])


def cycle_frames(cfg: dict, n: int = 24) -> list[np.ndarray]:
    """Кадры цикла. Тело качается на bob, ноги решаются под этот же сдвиг,
    поэтому стопа остаётся на полу, а не «едет» за корпусом."""
    draw, size = load_source()
    weights = build_weights(size)
    frames = []
    for i in range(n):
        t = i / n
        a = angles_at(t, cfg)
        img = render(draw, weights, a, shift_y=float(a["_bob"]))
        # Пол: подошва опорной стопы должна стоять ровно на одной линии. После
        # деформации низ силуэта гуляет на пару пикселей — доводим кадр до пола.
        ys = np.where((img[..., 3] > 40).any(axis=1))[0]
        img = render(draw, weights, a,
                     shift_y=float(a["_bob"]) + (floor_at(size) - float(ys.max())))
        frames.append(img)
    return frames


WALK = {
    "stride": 250.0,     # px: полный ход стопы за цикл
    "stance": 0.52,      # доля цикла, когда стопа стоит на полу
    "lift": 95.0,        # px: подъём стопы в переносе
    "sole": 18.0,        # px: насколько подошва ниже лодыжки
    "toe": 18.0,         # градусы: подтяжка носка в переносе
    "bob": 9.0,          # px: покачивание тела (на 2 шага — 2 подъёма)
    "arm": 24.0,         # градусы: мах плеча в противофазе ногам
}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    loops = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    fps = 24
    frames = cycle_frames(WALK)
    h, w = frames[0].shape[:2]
    out = ROOT / "studio" / "out" / f"{key}-walk.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = []
    for _ in range(loops):
        for f in frames:
            im = Image.fromarray(f, "RGBA")
            bg = Image.new("RGBA", im.size, (238, 235, 229, 255))
            buf.append(np.asarray(Image.alpha_composite(bg, im).convert("RGB")))
    import imageio.v2 as imageio
    wr = imageio.get_writer(out, fps=fps, quality=9, macro_block_size=1)
    for b in buf:
        wr.append_data(b)
    wr.close()
    print(f"{out}  цикл {len(frames)} кадров, всего {len(buf)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
