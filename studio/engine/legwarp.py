"""Деформация рисунка по скелету: нога гнётся, а швов нет.

    python studio/tools/legwarp.py dad walk

Почему не нарезка на куски
--------------------------
Cutout-риг (вырезать бедро, голень, стопу и крутить каждую часть) на плоском
рисунке даёт видимые стыки: за шарниром нет «мяса», и на сгибе появляется
ступень, а при сильном повороте — щель. Именно это и было видно в ролике.

Здесь рисунок НЕ режется. Всё изображение деформируется одним непрерывным
полем смещений: каждая точка сдвигается по взвешенной сумме поворотов костей
(linear blend skinning, как в 3D-риге, только на плоскости). Так как поле
непрерывное и каждая точка смещается ровно один раз, швов и щелей быть не
может по построению — силуэт просто изгибается.

Вес точки по кости берётся из масок частей, которые уже посчитаны для рига
(`rig-stride.json`): точка внутри маски бедра весит 1 для бедра, а на границе
веса сглаживаются. Поэтому колено гнётся плавно, а не «шарниром».

Ограничение честно: на очень сильном сгибе (бег, 70–80°) ткань у колена
сжимается и рисунок слегка «жуётся» — это плата за то, что мы гнём плоскую
картинку, а не модель.
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
import rig2d

ROOT = HERE.parents[2]

# Какие части деформируются какой костью. Ключ — часть в spec["parts"],
# значение — шарнир, вокруг которого она вращается.
BONE_OF = {
    "thigh": "hip_near",
    "shin": "knee_near",
    "foot": "ankle_near",
    "far_thigh": "hip_far",
    "far_shin": "knee_far",
    "far_foot": "ankle_far",
    "torso": "spine",
    "head": "neck",
    "arm_up": "shoulder",
    "arm_fo": "elbow",
    "far_arm_up": "shoulder_far",
    "far_arm_fo": "elbow_far",
}


def _smooth(mask: np.ndarray, sigma: float) -> np.ndarray:
    """Размыть маску — так веса на границе частей переходят плавно."""
    return cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)


def _seg_dist(px: np.ndarray, py: np.ndarray,
              a: tuple[float, float], b: tuple[float, float]) -> np.ndarray:
    """Расстояние от точек (px, py) до отрезка a→b."""
    ax, ay = a
    bx, by = b
    vx, vy = bx - ax, by - ay
    L2 = max(vx * vx + vy * vy, 1e-6)
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / L2, 0.0, 1.0)
    return np.hypot(px - (ax + vx * t), py - (ay + vy * t))


# Кость = отрезок в пикселях рисунка. Стопа идёт вперёд от лодыжки.
def bone_segments(spec: dict, size: tuple[int, int]) -> dict[str, tuple]:
    w, h = size
    J = {k: (v["pos"][0] * w, v["pos"][1] * h) for k, v in spec["joints"].items()}

    def seg(a: str, b: str, dx: float = 0.0) -> tuple:
        return (J[a], (J[b][0] + dx, J[b][1]))

    out = {}
    if "hip_near" in J and "knee_near" in J:
        out["hip_near"] = seg("hip_near", "knee_near")
        out["knee_near"] = seg("knee_near", "ankle_near")
        out["ankle_near"] = seg("ankle_near", "ankle_near", dx=70)
    if "hip_far" in J and "knee_far" in J:
        out["hip_far"] = seg("hip_far", "knee_far")
        out["knee_far"] = seg("knee_far", "ankle_far")
        out["ankle_far"] = seg("ankle_far", "ankle_far", dx=70)
    for j in ("spine", "chest", "neck"):
        if j in J:
            out[j] = (J[j], J[j])
    if "shoulder" in J and "elbow" in J:
        out["shoulder"] = seg("shoulder", "elbow")
        out["elbow"] = seg("elbow", "wrist")
    return out


def weight_maps(spec: dict, size: tuple[int, int],
                sigma: float = 7.0) -> dict[str, np.ndarray]:
    """Вес каждой кости: точка гнётся ТОЙ костью, к которой она ближе.

    Прошлая версия брала веса из масок частей, а маски перекрываются — обе
    ноги тянули друг друга, и силуэт разъезжался «морковкой». Здесь каждый
    пиксель относим к ближайшей кости (как в диаграмме Вороного), а мягкий
    переход на сгибе получается размытием узкой полосы.
    """
    w, h = size
    segs = bone_segments(spec, size)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    names = list(segs)
    dists = np.stack([_seg_dist(xx, yy, *segs[n]) for n in names], axis=0)
    nearest = dists.argmin(0)
    out = {}
    for i, n in enumerate(names):
        m = (nearest == i).astype(np.float32)
        # плавный переход на стыке костей
        m = cv2.GaussianBlur(m, (0, 0), sigma)
        out[n] = m
    total = np.zeros((h, w), np.float32)
    for m in out.values():
        total += m
    for n in out:
        out[n] = out[n] / np.maximum(total, 1e-5)
    return out


def _rot(pts: np.ndarray, deg: float) -> np.ndarray:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.stack([pts[..., 0] * c - pts[..., 1] * s,
                     pts[..., 0] * s + pts[..., 1] * c], axis=-1)


def warp(drawing: Image.Image, spec: dict, angles: dict,
         *, sigma: float = 22.0) -> Image.Image:
    """Изогнуть рисунок по углам шарниров. Швов не бывает по построению."""
    src = np.asarray(drawing.convert("RGBA"))
    h, w = src.shape[:2]
    pup = rig2d.Puppet(drawing, spec)
    totals = pup._totals(angles)
    wmap = weight_maps(spec, (w, h), sigma)

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dx = np.zeros((h, w), np.float32)
    dy = np.zeros((h, w), np.float32)
    for joint, weight in wmap.items():
        if joint not in totals:
            continue
        pos, ang = totals[joint]
        if abs(ang) < 1e-6:
            continue
        px, py = pos[0] * w, pos[1] * h
        # поворот точки вокруг шарнира на суммарный угол кости
        ox, oy = xx - px, yy - py
        nx, ny = _rot(np.stack([ox, oy], -1), ang)[..., 0], _rot(
            np.stack([ox, oy], -1), ang)[..., 1]
        dx += weight * (nx - ox)
        dy += weight * (ny - oy)

    # альфу размывать нельзя, но и рвать нельзя: тянем её тем же полем
    src_f = src.astype(np.float32)
    out = cv2.remap(src_f, xx + dx, yy + dy, interpolation=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def load_side_drawing(name: str = "master-side-spread.png"
                      ) -> tuple[Image.Image, dict]:
    """Заготовка для деформации.

    Берём рисунок, где обе ноги ВИДНЫ и разведены: в ровной стойке профиль
    перекрывает ноги друг другом, и чередование не прочитать. Нарезка такому
    рисунку не годится (ноги нарисованы под углом), а деформация — годится:
    она гнёт силуэт по скелету и не зависит от того, под каким углом нога
    нарисована.
    """
    img = cutout.key_green(
        Image.open(ROOT / "studio/2p5d/dad" / name).convert("RGB"))
    return img, rig2d.load_rig("dad", "stride")


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    what = sys.argv[2] if len(sys.argv) > 2 else "walk"
    import stride_cycle as sc
    frames, fps = sc.build(what)
    out = ROOT / "studio" / "out" / f"{key}-{what}.mp4"
    import imageio.v2 as imageio
    wr = imageio.get_writer(out, fps=fps, quality=9, macro_block_size=1)
    for f in frames:
        wr.append_data(np.asarray(f))
    wr.close()
    print(f"{out}  кадров {len(frames)}, fps {fps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
