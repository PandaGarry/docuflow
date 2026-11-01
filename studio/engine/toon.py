"""Арт-риг: анимация нарисованных мастер-ассетов (cutout-риг, как в Toon Boom).

Зачем
-----
Процедурная кукла (`puppet.py`) — превиз: логика верная, но рисунок векторный.
Финальный кадр делается из нарисованного мастера стиля B. Плоский рисунок
нельзя «гнуть» одним мешем: при подъёме руки в плече нечем закрыть подмышку, и
картинка рвётся на лохмотья (проверено и на `Image.MESH`, и на LBS-сетке).

Поэтому здесь та же схема, что в настоящей cutout-анимации:

    мастер (RGBA) → скелет по силуэту → разрезание на части (голова, плечи,
    предплечья, бёдра, голени, корпус) → каждая часть двигается ЖЁСТКО
    (поворот вокруг сустава, без деформации) → суставы закрываются заплатками
    → мягкие перекрытия на стыках → кадр

Ключевые решения
----------------
* **Скелет сажается по силуэту**: рост, плечи, бёдра, кисти и стопы берутся из
  мерок мастера, поэтому папа/мама/сын работают без правок кода.
* **Части не деформируются**, а поворачиваются как целое — поэтому рисунок
  (свет, складки, фактура) остаётся ровно таким, каким его нарисовали.
* **Шарниры**: на каждом суставе рисуется круглая заплатка цвета соседней части,
  перекрытия частей расширены — щелей на сгибах не видно.
* **Мимика — локальный варп области головы** в rest-пространстве (гауссовы
  блобы вокруг бровей, глаз, рта). Мастер остаётся тем же рисунком.
* Плечо остаётся в корпусе: рука «растёт» из него, а не отрывается.

Модуль не знает про сцены и таймлайн: на вход поза и параметры лица, на выход
кадр нужного размера.
"""

from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import face as F
import rig as R

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)

WARP_PARAMS: tuple[str, ...] = (
    "brow_raise", "brow_angle", "brow_pinch", "eye_open", "lid", "squint",
    "mouth_open", "mouth_wide", "smile", "mouth_skew", "cheek_raise", "nose_wrinkle",
)

# части тела: имя → (кости, порядок отрисовки, что рисовать заплаткой сверху)
PARTS: dict[str, tuple[str, ...]] = {
    "shin.l": ("shin.l", "foot.l"),
    "thigh.l": ("thigh.l",),
    "shin.r": ("shin.r", "foot.r"),
    "thigh.r": ("thigh.r",),
    "arm.l.up": ("upper_arm.l",),
    "arm.r.up": ("upper_arm.r",),
    "arm.l.lo": ("forearm.l", "hand.l"),
    "arm.r.lo": ("forearm.r", "hand.r"),
    "torso": ("spine", "chest", "neck"),
    "head": ("head",),
}
# плечо рисуется ПОД корпусом (шов в суставе прячется), предплечье — поверх,
# иначе скрещённые руки и телефон у уха уходят за корпус
DRAW_ORDER = ("shin.l", "shin.r", "thigh.l", "thigh.r",
              "arm.l.up", "arm.r.up", "torso",
              "arm.l.lo", "arm.r.lo", "head")

# сустав → (родительская часть, дочерняя часть, кость сустава)
JOINTS = (
    ("thigh.l", "shin.l", "shin.l"),
    ("thigh.r", "shin.r", "shin.r"),
    ("arm.l.up", "arm.l.lo", "forearm.l"),
    ("arm.r.up", "arm.r.lo", "forearm.r"),
)


# --------------------------------------------------------------------------- #
# геометрия и мерки
# --------------------------------------------------------------------------- #


def _silhouette(img: Image.Image, threshold: int = 60) -> np.ndarray:
    return np.asarray(img.convert("RGBA"))[..., 3] > threshold


def _fit_skeleton(sk: R.Skeleton, mask: np.ndarray) -> dict:
    """Посадить скелет по силуэту: масштаб, сдвиг, центр по бёдрам."""
    rows = np.where(mask.any(axis=1))[0]
    if rows.size < 4:
        raise ValueError("пустой силуэт: нечего ригить")
    top, bottom = int(rows.min()), int(rows.max())
    _x0, y0, _x1, y1 = sk.bounds()
    k = (bottom - top) / max(y1 - y0, 1e-6)

    band = mask[int(top + 0.60 * (bottom - top)):int(top + 0.72 * (bottom - top))]
    xs = np.where(band.any(axis=0))[0]
    cx = float((xs.min() + xs.max()) / 2) if xs.size else mask.shape[1] / 2

    return {"k": k, "ox": cx - sk.bones["hips"].world_pos[0] * k,
            "oy": top - y0 * k, "top": top, "bottom": bottom,
            "cx": cx, "height": bottom - top}


def _seg_dist(px: np.ndarray, py: np.ndarray, ax: float, ay: float,
              bx: float, by: float) -> np.ndarray:
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    if l2 < 1e-9:
        return np.hypot(px - ax, py - ay)
    t = np.clip(((px - ax) * vx + (py - ay) * vy) / l2, 0.0, 1.0)
    return np.hypot(px - (ax + t * vx), py - (ay + t * vy))


def _measure(mask: np.ndarray) -> dict:
    """Мерки по силуэту мастера: голова, шея, плечи, бёдра, кисти."""
    rows = np.where(mask.any(axis=1))[0]
    if rows.size < 8:
        raise ValueError("пустой силуэт: нечего ригить")
    top, bottom = int(rows.min()), int(rows.max())
    h = max(bottom - top, 1)
    width = np.zeros(mask.shape[0], np.int32)
    centre = np.zeros(mask.shape[0], np.float64)
    outer = np.zeros(mask.shape[0], np.float64)
    for y in range(top, bottom + 1):
        xs = np.where(mask[y])[0]
        if xs.size:
            width[y] = xs.max() - xs.min() + 1
            centre[y] = (xs.max() + xs.min()) / 2.0
            outer[y] = max(abs(xs.min() - centre[y]), abs(xs.max() - centre[y]))

    band_hi = int(top + 0.45 * h)
    w_max = int(width[top:band_hi].max())

    neck_lo = int(top + 0.06 * h)
    neck_hi = int(top + 0.42 * h)
    neck_y = int(top + 0.2 * h)
    best = 1e9
    for y in range(neck_lo, max(neck_hi, neck_lo + 1)):
        if width[y] and width[y] < 0.55 * w_max and width[y] < best:
            best, neck_y = width[y], y

    head_y = max(range(top, neck_y + 1), key=lambda y: width[y])

    head_r = max(width[head_y] / 2.0, 1.0)
    head_cx = float(centre[head_y])

    hip_y = int(top + 0.62 * h)
    for y in range(int(top + 0.35 * h), bottom):
        xs = np.where(mask[y])[0]
        if xs.size < 2:
            continue
        if np.diff(xs).max(initial=0) > max(0.02 * h, 3):
            hip_y = y
            break

    shoulder_y = int(neck_y + 0.06 * h)
    shoulder_half = float(width[shoulder_y]) / 2.0

    hip_half = float(width[hip_y]) / 2.0 if width[hip_y] else shoulder_half
    hand_y = hip_y
    for y in range(bottom, shoulder_y, -1):
        if outer[y] > hip_half + 0.02 * h:
            hand_y = y
            break

    return {"top": top, "bottom": bottom, "h": h, "width": width, "centre": centre,
            "outer": outer, "head_y": head_y, "head_r": head_r, "head_cx": head_cx,
            "hip_cx": float(centre[hip_y]) if centre[hip_y] else float(centre[top]),
            "neck_y": neck_y, "shoulder_y": shoulder_y, "shoulder_half": shoulder_half,
            "hip_y": hip_y, "hip_half": hip_half, "hand_y": hand_y}


def _fit_rig_to_art(mask: np.ndarray, overrides: dict | None,
                    rig_id: str) -> tuple[R.Skeleton, dict, dict]:
    """Собрать скелет по меркам силуэта: длины костей в единицах арта.

    У нарисованного персонажа своя анатомия (крупная голова, короткий торс).
    Если посадить усреднённый скелет, сустав плеча окажется в голове — руки
    будут вращаться не там. Поэтому плечи, бёдра, кисти и стопы берутся из
    силуэта, а из профиля `rigs.json` наследуются иерархия, rest-углы и толщины.
    """
    m = _measure(mask)
    total = max(m["bottom"] - m["top"], 1)
    k = total / 5.8
    ox, oy = float(m["hip_cx"]), float(m["hip_y"])

    sk = R.build_humanoid(6.0, overrides, rig_id)
    sk.solve()

    def u(py: float) -> float:
        return (py - oy) / k

    def ln(px_len: float) -> float:
        return max(px_len / k, 0.05)

    sh_y = u(m["shoulder_y"])
    chin_y = u(m["neck_y"])
    torso = max(-sh_y, 0.6)
    sk.bones["spine"].length = torso * 0.58
    sk.bones["chest"].length = torso * 0.42
    sk.bones["neck"].length = max(sh_y - chin_y, 0.15)

    head_cy = (m["top"] + m["neck_y"]) / 2.0
    sk.bones["head"].length = max(ln(2.0 * (m["neck_y"] - head_cy)), 0.2)

    shoulder_half = float(m["width"][m["shoulder_y"]]) / 2.0
    hand_x = ox + (m["outer"][m["hand_y"]] or 0.0)
    arm_u = ln(max(math.hypot(hand_x - ox, m["hand_y"] - m["shoulder_y"]), 1.0))
    for side in ("r", "l"):
        sk.bones[f"upper_arm.{side}"].length = arm_u * 0.47
        sk.bones[f"forearm.{side}"].length = arm_u * 0.39
        sk.bones[f"hand.{side}"].length = arm_u * 0.14
    off = ln(shoulder_half * 0.55)
    sk.bones["upper_arm.r"].origin = (0.0, off)
    sk.bones["upper_arm.l"].origin = (0.0, -off)

    leg_u = ln(max(m["bottom"] - m["hip_y"], 1.0))
    for side in ("r", "l"):
        sk.bones[f"thigh.{side}"].length = leg_u * 0.51
        sk.bones[f"shin.{side}"].length = leg_u * 0.49
        sk.bones[f"foot.{side}"].length = leg_u * 0.09
    leg_off = ln(m["hip_half"] * 0.28)
    sk.bones["thigh.r"].origin = (leg_off, 0.0)
    sk.bones["thigh.l"].origin = (-leg_off, 0.0)

    # подгонка по фактическим точкам (rest-углы не строго вертикальны)
    for _ in range(4):
        sk.solve()
        sh_px = oy + sk.bones["upper_arm.r"].world_pos[1] * k
        hand_px = oy + sk.tip("hand.r")[1] * k
        hip_px = oy + sk.bones["hips"].world_pos[1] * k
        foot_px = oy + sk.tip("foot.r")[1] * k
        arm_ratio = (m["hand_y"] - m["shoulder_y"]) / max(hand_px - sh_px, 1e-6)
        leg_ratio = (m["bottom"] - m["hip_y"]) / max(foot_px - hip_px, 1e-6)
        if abs(arm_ratio - 1) < 0.01 and abs(leg_ratio - 1) < 0.01:
            break
        for side in ("r", "l"):
            for bone in ("upper_arm", "forearm", "hand"):
                sk.bones[f"{bone}.{side}"].length *= arm_ratio
            for bone in ("thigh", "shin"):
                sk.bones[f"{bone}.{side}"].length *= leg_ratio
    sk.solve()

    # --- rest-поза рук по рисунку -------------------------------------------------
    # На мастере руки могут быть согнуты (у мамы — в боки). Если оставить rest
    # «руки вниз», кисть при любом движении уедет от нарисованной руки и часть
    # руки оторвётся. Поэтому доворачиваем кости руки так, чтобы цепочка легла
    # ровно по нарисованной руке, и запоминаем это как rest.
    sil_pts = np.argwhere(mask)
    # длина руки по меркам силуэта — в единицах скелета
    arm_len = (sk.bones["upper_arm.r"].length + sk.bones["forearm.r"].length +
               sk.bones["hand.r"].length)
    for side, sign in (("r", 1.0), ("l", -1.0)):
        upper = sk.bones[f"upper_arm.{side}"]
        sh = upper.world_pos
        far_y = max(m["hip_y"], m["hand_y"] - 2.0)
        cand = sil_pts[(sil_pts[:, 0] > m["shoulder_y"]) & (sil_pts[:, 0] < far_y)]
        if cand.size == 0:
            continue
        # самая боковая точка силуэта в полосе руки = кисть или локоть;
        # направление от плеча на неё и есть направление нарисованной руки
        lateral = sign * (cand[:, 1] - ox)
        idx = int(np.argmax(lateral))
        px_x, px_y = float(cand[idx, 1]), float(cand[idx, 0])
        d = ((px_x - ox) / k - sh[0], (px_y - oy) / k - sh[1])
        norm = math.hypot(*d)
        if norm < 1e-3:
            continue
        target = (sh[0] + d[0] / norm * arm_len, sh[1] + d[1] / norm * arm_len)
        R.hand_ik(sk, side, target, pole=(0.6 * sign, 0.8))
        sk.solve()
        for bone in (f"upper_arm.{side}", f"forearm.{side}"):
            sk.bones[bone].rest = sk.bones[bone].angle

    sk.reset_pose()
    sk.solve()

    fit = {"k": k, "ox": ox, "oy": oy, "top": m["top"], "bottom": m["bottom"],
           "cx": ox, "height": total}
    head_unit = ((m["head_cx"] - ox) / k, u(head_cy), m["head_r"] / k)
    info = {"measures": m, "head_unit": head_unit,
            "height_heads": round(total / max(2.0 * m["head_r"], 1e-6), 2)}
    return sk, fit, info


# --------------------------------------------------------------------------- #
# арт-риг
# --------------------------------------------------------------------------- #


class CutoutRig:
    """Cutout-риг поверх мастер-ассета (жёсткие части + шарниры).

    Даёт идеально чистый рисунок при малых углах (наклон корпуса, шаг, кивок),
    но на подъёме руки выше ~60° в плече видна щель — у плоского фронтального
    рисунка нет нарисованной подмышки. Для больших углов используйте `MeshRig`
    (тянется ткань) или отдельные ракурсы частей (`docs/17-ART-RIG.md`).

    Публичный интерфейс повторяет `puppet.Painter`: `build(pose)` и
    `frame(sk, face, ...)`, поэтому сцены и демо работают с любым рендерером.
    """

    def __init__(self, spec: dict, *, view: str = "front", work_height: int = 900,
                 ss: int = 2, **_ignored):
        self.spec = spec
        self.cid = spec.get("id", "?")
        art_cfg = spec.get("art") or {}
        path = art_cfg.get("view_path") or os.path.join(
            STUDIO, "characters", self.cid, "views", f"{view}.png")
        if not os.path.exists(path):
            raise FileNotFoundError(f"нет мастера для {self.cid}: {path}")

        src = Image.open(path).convert("RGBA")
        scale = max(work_height / src.height, 0.2)
        self.work_size = (max(int(src.width * scale), 8), max(int(src.height * scale), 8))
        self.art = src.resize(self.work_size, Image.LANCZOS)

        mask = _silhouette(self.art)
        manual = art_cfg.get("proportions") or {}
        self.sk_rest, self.fit, self.autofit = _fit_rig_to_art(
            mask, manual, spec.get("rig", "humanoid_v1"))
        self.measure = self.autofit["measures"]

        tune = art_cfg.get("fit") or {}
        self.fit["k"] *= float(tune.get("k", 1.0))
        self.fit["ox"] += float(tune.get("dx", 0.0)) * self.fit["k"]
        self.fit["oy"] += float(tune.get("dy", 0.0)) * self.fit["k"]

        self.ss = ss
        self.limb_split = str(art_cfg.get("limb_split") or "auto")
        # руки нарисованы согнутыми (кисти у бёдер)? тогда любая ротация костей
        # руки рвёт рисунок: такие руки держим жёстко вместе с корпусом
        self.freeze_arms = bool(art_cfg.get("freeze_arms", False)) or \
            self._arms_bent_in_art(_silhouette(self.art))
        self._rest_pts = {n: self.to_px(*b.world_pos) for n, b in self.sk_rest.bones.items()}
        self._cache: dict = {}
        self.face_art = self._face_frame_art()
        self.face_layout = self._detect_face_layout()
        self._filled = self._fill_edges()

    def _fill_edges(self, rings: int = 14) -> np.ndarray:
        """Мастер с залитым фоном: цвет края «растягивается» наружу.

        Нужно для «юбок» на стыках частей: перекрытие должно быть цвета ткани,
        а не прозрачным, иначе щель между частями просто станет дыркой.
        """
        art = np.asarray(self.art, np.float32)
        H, W = art.shape[:2]
        sil = art[..., 3] > 40
        filled = art.copy()
        filled[..., :3] = np.where(sil[..., None], art[..., :3],
                                   np.array([246, 240, 230], np.float32))
        solid = sil.copy()
        for _ in range(rings):
            if solid.all():
                break
            grown = solid.copy()
            grown[1:, :] |= solid[:-1, :]
            grown[:-1, :] |= solid[1:, :]
            grown[:, 1:] |= solid[:, :-1]
            grown[:, :-1] |= solid[:, 1:]
            new = grown & ~solid
            if not new.any():
                break
            idx = np.argwhere(new)
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ys = np.clip(idx[:, 0] + dy, 0, H - 1)
                xs = np.clip(idx[:, 1] + dx, 0, W - 1)
                ok = solid[ys, xs]
                filled[idx[ok, 0], idx[ok, 1], :3] = filled[ys[ok], xs[ok], :3]
            solid = grown
        return filled

    # --- координаты ------------------------------------------------------- #
    def to_px(self, x: float, y: float) -> tuple[float, float]:
        return (self.fit["ox"] + x * self.fit["k"], self.fit["oy"] + y * self.fit["k"])

    def to_unit(self, px: float, py: float) -> tuple[float, float]:
        return ((px - self.fit["ox"]) / self.fit["k"], (py - self.fit["oy"]) / self.fit["k"])

    # --- поза ------------------------------------------------------------- #
    def build(self, pose: str | dict) -> R.Skeleton:
        sk = R.Skeleton.from_dict(self.sk_rest.to_dict())
        sk.rig_id = getattr(self.sk_rest, "rig_id", "humanoid_v1")
        R.apply_pose(sk, pose)
        if self.freeze_arms:
            for side in ("r", "l"):
                for bone in ("upper_arm", "forearm", "hand"):
                    name = f"{bone}.{side}"
                    sk.bones[name].angle = self.sk_rest.bones[name].angle
            sk.solve()
        return sk

    # --- части ------------------------------------------------------------ #
    def _limb_radius(self, bone: str) -> float:
        b = self.sk_rest.bones[bone]
        return max(b.width * 1.35 * self.fit["k"], 6.0)

    def _arms_bent_in_art(self, sil: np.ndarray) -> bool:
        """Согнуты ли руки на самом рисунке (а не только в скелете).

        У мамы в мастере руки в боки: если резать руку по локтю «прямого»
        скелета, кисть окажется в чужой части и оторвётся. Признак — кисть
        скелета далеко от того места, где нарисована рука.
        """
        H, W = sil.shape
        hand = self.to_px(*self.sk_rest.tip("hand.r"))
        r = max(self.measure["head_r"] * 0.5, 6.0)
        y0, y1 = int(max(hand[1] - r, 0)), int(min(hand[1] + r, H))
        x0, x1 = int(max(hand[0] - r, 0)), int(min(hand[0] + r, W))
        if x1 <= x0 or y1 <= y0:
            return True
        return float(sil[y0:y1, x0:x1].mean()) < 0.35

    def parts(self) -> dict:
        """Разрезать мастера на части: голова, плечи, предплечья, ноги, корпус.

        Правила:
        * части ищутся по цилиндрам вокруг костей (руки, ноги), голова — всё
          выше шеи (вместе с волосами и ушами);
        * корпус **достраивается** под рукой узкой полосой у своего края —
          иначе при подъёме руки видна дыра на месте рукава;
        * край каждой части сглаживается, чтобы стык не был ступенькой.
        """
        if self._cache.get("parts") is not None:
            return self._cache["parts"]
        W, H = self.work_size
        art = np.asarray(self.art, np.float32)
        sil = art[..., 3] > 40
        ys, xs = np.mgrid[0:H, 0:W].astype(np.float32)

        # Вороной между структурами: пиксель уходит той части, чья кость ближе.
        # Так граница руки и корпуса идёт по рукаву (а не режет грудь клином),
        # и каждая точка принадлежит ровно одной части.
        def chain_dist(names: tuple[str, ...]) -> np.ndarray:
            return np.min(np.stack([
                _seg_dist(xs, ys, *self.to_px(*self.sk_rest.bones[n].world_pos),
                          *self.to_px(*self.sk_rest.tip(n))).astype(np.float32)
                for n in names]), axis=0)

        arms = ("upper_arm.r", "forearm.r", "hand.r",
                "upper_arm.l", "forearm.l", "hand.l")
        legs = ("thigh.r", "shin.r", "foot.r", "thigh.l", "shin.l", "foot.l")
        torso_bones = ("spine", "chest", "neck")

        d_arm = chain_dist(arms)
        d_leg = chain_dist(legs)
        d_torso = chain_dist(torso_bones)
        d_head = np.hypot(xs - self.measure["head_cx"],
                          ys - (self.measure["neck_y"] - self.measure["head_r"] * 0.75))

        neck_line = int(self.measure["neck_y"] + 0.02 * self.measure["h"])
        head = np.zeros((H, W), bool)
        head[:max(neck_line, 1)] = True
        head |= (d_head < d_torso * 0.92) & (d_head < d_arm) & \
            (ys < self.measure["neck_y"] + self.measure["head_r"] * 0.35)
        head &= sil

        # Разметка «коридором»: у фронтального мастера руки прижаты к телу, и
        # «ближайшая кость» режет грудь клином. Поэтому:
        #   внутри коридора корпуса (шея → бёдра) — торс,
        #   вне коридора до бёдер — руки (сторона по X), делятся по локтю,
        #   ниже бёдер — ноги (сторона по X), делятся по колену.
        m_ = self.measure
        split = self.limb_split
        if split == "auto":
            split = "whole" if self._arms_bent_in_art(sil) else "elbow"
        ys_px = np.arange(H, dtype=np.float32)[:, None]
        cx_row = np.broadcast_to(np.interp(np.arange(H, dtype=np.float32),
                                           np.arange(H), m_["centre"])[:, None],
                                 (H, W))
        sh_half = float(m_["width"][m_["shoulder_y"]]) / 2.0 * 0.78
        hp_half = max(float(m_["hip_half"]), 1.0) * 1.02
        t0, t1 = float(m_["neck_y"]), float(m_["hip_y"])
        frac = np.clip((ys_px[:, 0] - t0) / max(t1 - t0, 1.0), 0.0, 1.0)
        half = (sh_half * (1 - frac) + hp_half * frac)[:, None]
        in_corridor = np.abs(xs - cx_row) <= half
        # если в мастере руки согнуты (кисти у бёдер), коридор их «съедает»:
        # тогда торс ограничиваем капсулой вокруг позвоночника, а всё прочее
        # выше бёдер считаем руками — иначе кисть отрывается от предплечья
        if split == "whole":
            d_trunk = np.min(np.stack([
                _seg_dist(xs, ys, *self.to_px(*self.sk_rest.bones[n].world_pos),
                          *self.to_px(*self.sk_rest.tip(n))).astype(np.float32)
                for n in ("spine", "chest")]), axis=0)
            trunk_r = max(float(m_["width"][m_["shoulder_y"]]) * 0.42, 8.0)
            in_corridor = d_trunk <= trunk_r

        below_hip = ys_px >= t1
        upright = sil & ~head & (ys_px < t1)

        # Вороной с приоритетом оси корпуса: пиксель — рука, только если он
        # ЯВНО ближе к кости руки, чем к оси тела (0.55×). Иначе середина
        # груди уходила бы к руке и грудь резалась клином.
        d_axis = np.abs(xs - cx_row)
        arm_win = d_arm < 0.55 * d_axis
        torso = upright & ~arm_win
        legs_px = sil & ~head & below_hip

        # в остатке — кто ближе: рука или нога (по цепочкам костей)
        def chain_dist(names: tuple[str, ...]) -> np.ndarray:
            return np.min(np.stack([
                _seg_dist(xs, ys, *self.to_px(*self.sk_rest.bones[n].world_pos),
                          *self.to_px(*self.sk_rest.tip(n))).astype(np.float32)
                for n in names]), axis=0)

        arm_bones = ("upper_arm.r", "forearm.r", "hand.r",
                     "upper_arm.l", "forearm.l", "hand.l")
        leg_bones = ("thigh.r", "shin.r", "foot.r", "thigh.l", "shin.l", "foot.l")
        d_arm = chain_dist(arm_bones)
        d_leg = chain_dist(leg_bones)

        elbow_y = {sd: (-1e9 if split == "whole" else
                        self.to_px(*self.sk_rest.tip(f"upper_arm.{sd}"))[1])
                   for sd in ("r", "l")}
        knee_y = {sd: (self.to_px(*self.sk_rest.bones[f"thigh.{sd}"].world_pos)[1]
                       + self.to_px(*self.sk_rest.tip(f"shin.{sd}"))[1]) / 2.0
                  for sd in ("r", "l")}
        hip_cx = m_["hip_cx"]

        limb_zone = sil & ~head & ~torso
        # Руки нарисованы ПОВЕРХ корпуса и ног, поэтому при равной близости
        # пиксель достаётся руке (кисти у бёдер иначе уезжают с ногой и рвутся).
        is_arm = limb_zone & (d_arm <= d_leg * 1.5)
        is_leg = limb_zone & (d_arm > d_leg)

        masks: dict[str, np.ndarray] = {"head": head, "torso": torso}
        for sd in ("r", "l"):
            right = (xs > hip_cx) if sd == "r" else (xs <= hip_cx)
            arm = is_arm & right
            masks[f"arm.{sd}.up"] = arm & (ys_px <= elbow_y[sd])
            masks[f"arm.{sd}.lo"] = arm & (ys_px > elbow_y[sd])
            leg = is_leg & right
            masks[f"thigh.{sd}"] = leg & (ys_px <= knee_y[sd])
            masks[f"shin.{sd}"] = leg & (ys_px > knee_y[sd])
        # Рука нарисована ПОВЕРХ бедра (у мамы кисти лежат на бёдрах). Вороной
        # отдаёт такие пиксели ноге, и при повороте предплечья они остаются на
        # месте — вдоль бедра тянется полоса кожи. Поэтому всё, что попало в
        # «трубу» вокруг кости руки, принадлежит руке, даже если ближе нога.
        for sd in ("r", "l"):
            pipe = np.zeros((H, W), bool)
            for bone in (f"upper_arm.{sd}", f"forearm.{sd}", f"hand.{sd}"):
                rad = self.sk_rest.bones[bone].width * 0.42 * self.fit["k"]
                pipe |= _seg_dist(xs, ys, *self.to_px(*self.sk_rest.bones[bone].world_pos),
                                  *self.to_px(*self.sk_rest.tip(bone))) <= max(rad, 3.0)
            pipe &= sil & ~head
            for part in (f"thigh.{sd}", f"shin.{sd}"):
                if part in masks:
                    masks[part] = masks[part] & ~pipe
            # …и у корпуса тоже: у мамы кисти лежат на жилете, и полоса кожи
            # оставалась на торсе, растягиваясь в «языки» при повороте руки.
            masks["torso"] = masks["torso"] & ~pipe
            # Руку всегда делим по локтю, даже если на мастере она согнута:
            # иначе поворот плеча уносит кисть вместе с предплечьем.
            elbow_y_sd = elbow_y[sd]
            if elbow_y_sd < -1e8:                 # limb_split="whole": без локтя
                masks[f"arm.{sd}.up"] = masks[f"arm.{sd}.up"] | pipe
                masks[f"arm.{sd}.lo"] = masks[f"arm.{sd}.lo"] & ~pipe
            else:
                masks[f"arm.{sd}.up"] = masks[f"arm.{sd}.up"] | (pipe & (ys_px <= elbow_y_sd))
                masks[f"arm.{sd}.lo"] = masks[f"arm.{sd}.lo"] | (pipe & (ys_px > elbow_y_sd))

        covered = np.zeros((H, W), bool)
        for mm in masks.values():
            covered |= mm
        masks["torso"] = torso | (sil & ~head & ~covered)

        # Перекрытие частей: каждая часть расширяется на несколько пикселей, но
        # ТОЛЬКО внутри силуэта и цветом оригинала. Так стык при повороте не
        # расходится, а «двоения» не видно — пиксели те же самые.
        out = {}
        for part, m in masks.items():
            if not m.any():
                continue
            pad = 7 if part in ("torso", "head") else 9
            grown = np.asarray(Image.fromarray((m * 255).astype(np.uint8), "L").filter(
                ImageFilter.MaxFilter(2 * pad + 1)), np.float32) > 20
            grown &= sil
            # альфа: 1 внутри (включая перекрытие), сглаживание только по краю силуэта
            edge = np.asarray(Image.fromarray((sil * 255).astype(np.uint8), "L").filter(
                ImageFilter.GaussianBlur(0.8)), np.float32) / 255.0
            rgba = np.where(m[..., None], art, self._filled).astype(np.float32)
            a = np.where(grown, np.maximum(edge, 0.98), 0.0)
            rgba[..., 3] = a * 255.0
            out[part] = rgba
        self._cache["parts"] = out
        return out

    # --- мимика ----------------------------------------------------------- #
    def _head_frame(self, sk: R.Skeleton) -> tuple[float, float, float, float]:
        """Центр и радиус ЛИЦА в пикселях рабочего арта (+ поворот головы)."""
        L = self.face_layout
        cx, cy, r = float(L["cx"]), float(L["cy"]), float(L["r"])
        rot = sk.bones["head"].world_angle - self.sk_rest.bones["head"].world_angle
        return cx, cy, r, rot

    @staticmethod
    def _blob(u, v, u0, v0, su, sv=None):
        sv = su if sv is None else sv
        return np.exp(-(((u - u0) / su) ** 2 + ((v - v0) / sv) ** 2))

    def _face_frame_art(self) -> dict | None:
        """Где на мастере лицо: центр (между глазами) и радиус — в пикселях арта.

        Источники по порядку:
          1. `art.face` в `character.json` — три точки в долях картинки
             (`eye_l`, `eye_r`, `mouth`). Это данные, а не хардкод: новый
             персонаж размечается в конфиге, код не меняется.
          2. автоопределение по рисунку (пара тёмных пятен глаз);
          3. пропорции по умолчанию от мерок головы.
        """
        cfg = dict((self.spec.get("art") or {}).get("face") or {})
        W, H = self.work_size

        def pt(key: str):
            v = cfg.get(key)
            if not isinstance(v, (list, tuple)) or len(v) != 2:
                return None
            return (float(v[0]) * W, float(v[1]) * H)

        eye_l, eye_r, mouth = pt("eye_l"), pt("eye_r"), pt("mouth")
        if eye_l and eye_r and mouth:
            cx = (eye_l[0] + eye_r[0]) / 2.0
            cy = (eye_l[1] + eye_r[1]) / 2.0
            dy = max(mouth[1] - cy, 1.0)
            return {"cx": cx, "cy": cy, "r": dy / 0.5,
                    "eyes_u": abs(eye_r[0] - eye_l[0]) / 2.0 / max(dy / 0.5, 1e-6),
                    "source": "config"}

        eyes = self._detect_eyes()
        if eyes:
            return eyes

        m = self.measure
        return {"cx": float(m["head_cx"]), "cy": (m["top"] + m["neck_y"]) / 2.0,
                "r": max(float(m["head_r"]), 1.0) * 0.92,
                "eyes_u": 0.42, "source": "default"}

    def _detect_eyes(self) -> dict | None:
        """Пара тёмных пятен (глаза) внутри головы — если конфига нет."""
        art = np.asarray(self.art, np.float32)
        g = art[..., :3].mean(2)
        a = art[..., 3]
        m = self.measure
        r_head = max(float(m["head_r"]), 1.0)
        cx0 = float(m["head_cx"])
        y0 = int(m["top"] + 0.05 * m["h"])
        y1 = int(m["top"] + 0.45 * m["h"])
        zone = (a[y0:y1] > 200)
        zone = zone.copy()
        zone[:, :max(int(cx0 - 0.75 * r_head), 0)] = False
        zone[:, min(int(cx0 + 0.75 * r_head), zone.shape[1]):] = False
        if zone.sum() < 200:
            return None
        gh = g[y0:y1]
        thr = float(np.percentile(gh[zone], 3))
        dark = zone & (gh <= thr)
        ys, xs = np.nonzero(dark)
        if ys.size < 40:
            return None
        X, Y = xs.astype(float), ys.astype(float) + y0
        left, right = X < cx0, X >= cx0
        if left.sum() < 15 or right.sum() < 15:
            return None
        lx, ly = X[left].mean(), Y[left].mean()
        rx, ry = X[right].mean(), Y[right].mean()
        if abs(ly - ry) > 0.25 * r_head:
            return None
        cx, cy = (lx + rx) / 2.0, (ly + ry) / 2.0
        if abs(cx - cx0) > 0.45 * r_head:
            return None
        return {"cx": cx, "cy": cy, "r": max((cy - m["top"]) / 0.55, 0.5 * r_head),
                "eyes_u": abs(rx - lx) / 2.0 / max((cy - m["top"]) / 0.55, 1e-6),
                "source": "auto"}

    def _detect_face_layout(self) -> dict:
        """Разметка мимики в долях радиуса лица (начало — линия глаз)."""
        cfg = dict((self.spec.get("art") or {}).get("face") or {})
        fr = getattr(self, "face_art", None) or {}
        out = {"eyes_v": 0.0, "brow_v": -0.26, "mouth_v": 0.50,
               "eyes_u": float(fr.get("eyes_u", 0.42)), "shift_v": 0.0,
               "cx": float(fr.get("cx", 0.0)), "cy": float(fr.get("cy", 0.0)),
               "r": float(fr.get("r", 1.0)), "source": fr.get("source", "default")}
        out.update({k: float(v) for k, v in cfg.items() if k in out and k not in ("source",)})
        return out

    def _face_disp(self, px, py, sk: R.Skeleton, face: F.Face,
                   scale: float = 1.0, off: tuple[float, float] = (0.0, 0.0)):
        """Смещение мимики в пикселях ТОГО изображения, что передали (px, py).

        `scale`/`off` — как рабочее разрешение рига отображено в это
        изображение (суперсэмплинг и поля). Без них варп на кадре больше
        рабочего размера попадает не туда и «сминает» щёки и нос.
        """
        px = (np.asarray(px, np.float64) - off[0]) / max(scale, 1e-9)
        py = (np.asarray(py, np.float64) - off[1]) / max(scale, 1e-9)
        cx, cy, r, rot = self._head_frame(sk)
        u = (px - cx) / r
        v = (py - cy) / r
        du = np.zeros_like(u, dtype=np.float64)
        dv = np.zeros_like(v, dtype=np.float64)

        g = lambda k: float(face.get(k, 0.0))  # noqa: E731
        L = self.face_layout
        eu = max(float(L["eyes_u"]), 0.15)
        ev, bv, mv = float(L["eyes_v"]), float(L["brow_v"]), float(L["mouth_v"])
        brows = self._blob(u, v, 0.0, bv, eu * 1.45, (mv - bv) * 0.30)
        eyes = self._blob(u, v, 0.0, ev, eu * 1.30, (mv - bv) * 0.28)
        mouth = self._blob(u, v, 0.0, mv, eu * 1.05, (mv - bv) * 0.34)
        chin = self._blob(u, v, 0.0, mv + 0.30, eu * 1.25, (mv - bv) * 0.45)
        cheeks = self._blob(u, v, 0.0, ev + 0.22, eu * 1.85, (mv - bv) * 0.40)
        nose = self._blob(u, v, 0.0, ev + 0.20, eu * 0.60, (mv - bv) * 0.18)

        # амплитуды подобраны так, чтобы нейтраль не менялась вовсе, а эмоция
        # читалась на глаз: при K=1 сдвиги <0.5 px
        if abs(g("brow_raise")) > 1e-6:
            dv -= g("brow_raise") * 0.26 * brows
        if abs(g("brow_angle")) > 1e-6:
            dv += np.abs(u) * g("brow_angle") * 0.42 * brows
        if abs(g("brow_pinch")) > 1e-6:
            du -= np.sign(u) * g("brow_pinch") * 0.22 * brows

        # веки: закрытый глаз «сплющивает» область к линии глаз
        close = max(0.0, 1.0 - g("eye_open")) * 0.85 + g("lid") * 0.75 + \
            max(0.0, g("squint")) * 0.55
        if close > 1e-3:
            k = min(close, 0.95)
            dv -= (v - ev) * k * 0.30 * eyes
            # складка под глазом уходит вверх при прищуре
            dv += k * 0.06 * self._blob(u, v, 0.0, ev + 0.10, eu * 0.9, 0.10)

        # рот: нижняя челюсть едет вниз и чуть вперёд, уголки — по smile
        mo = g("mouth_open")
        if mo > 1e-3:
            # Сам открытый рот РИСУЕТСЯ отдельно (`_open_mouth_art`): растянуть
            # закрытые губы нельзя — получается смазанная «скобка». Варп здесь
            # только чуть опускает подбородок и раздвигает уголки.
            dv += mo * 0.020 * np.clip((v - mv) * 4.0, 0.0, None) * mouth
            dv += mo * 0.26 * chin
            du += np.sign(u) * mo * 0.02 * mouth
        if abs(g("mouth_wide")) > 1e-6:
            du += u * g("mouth_wide") * 0.22 * mouth
        if abs(g("smile")) > 1e-6:
            corner = self._blob(np.abs(u), v, eu * 0.85, mv, eu * 0.60, (mv - bv) * 0.30)
            dv -= g("smile") * 0.30 * corner
            du += np.sign(u) * g("smile") * 0.07 * corner
            dv -= g("smile") * 0.06 * cheeks
        if abs(g("mouth_skew")) > 1e-6:
            du += g("mouth_skew") * 0.34 * v * mouth
            dv -= g("mouth_skew") * 0.14 * mouth
        if abs(g("cheek_raise")) > 1e-6:
            dv -= g("cheek_raise") * 0.22 * cheeks
        if abs(g("nose_wrinkle")) > 1e-6:
            dv -= g("nose_wrinkle") * 0.16 * nose
            du += np.sign(u) * g("nose_wrinkle") * 0.06 * nose

        # ограничитель: на стилизованной голове (у ребёнка r = 125 px) смещение
        # больше 8% радиуса уже читается как «смаз», а не как мимика
        cap = 0.11
        du = np.clip(du, -cap, cap)
        dv = np.clip(dv, -cap, cap)

        c, s_ = math.cos(rot), math.sin(rot)
        k_ = r * max(scale, 1e-9)
        return (du * c - dv * s_) * k_, (du * s_ + dv * c) * k_

    @staticmethod
    def _sample(arr: np.ndarray, x: np.ndarray, y: np.ndarray,
                edge: bool = False) -> np.ndarray:
        """Билинейная выборка массива (H, W, C) в точках (x, y).

        `edge=False` — за границей прозрачность (нужно для скиннинга: там фон);
        `edge=True` — повтор крайнего пикселя (нужно для варпа головы: иначе по
        краю рабочего патча появляется тёмная линия-шов).
        """
        x, y = np.broadcast_arrays(np.asarray(x, np.float32), np.asarray(y, np.float32))
        H, W = arr.shape[:2]
        nch = 1 if arr.ndim == 2 else arr.shape[2]
        if arr.ndim == 2:
            arr = arr[..., None]
        x0 = np.floor(x).astype(np.int32)
        y0 = np.floor(y).astype(np.int32)
        fx = (x - x0)[..., None]
        fy = (y - y0)[..., None]
        out = np.zeros(x.shape + (nch,), np.float32)
        for dy in (0, 1):
            for dx in (0, 1):
                xi = np.clip(x0 + dx, 0, W - 1)
                yi = np.clip(y0 + dy, 0, H - 1)
                w = (fx if dx else 1 - fx) * (fy if dy else 1 - fy)
                inside = ((x0 + dx >= 0) & (x0 + dx < W) &
                          (y0 + dy >= 0) & (y0 + dy < H)) | edge
                out += arr[yi, xi] * w * inside[..., None]
        return out

    def _warp_face(self, img: Image.Image, sk: R.Skeleton, face: F.Face,
                   scale: float = 1.0,
                   off: tuple[float, float] = (0.0, 0.0)) -> Image.Image:
        """Локальный варп головы: двигаем пиксели, не перерисовывая лицо."""
        if not any(abs(float(face.get(k, 0.0))) > 1e-3 for k in WARP_PARAMS):
            return img
        W, H = img.size
        cx, cy, r, _rot = self._head_frame(sk)
        cx, cy, r = cx * scale + off[0], cy * scale + off[1], r * scale
        pad = int(r * 1.1)
        x0, x1 = max(int(cx) - pad, 0), min(int(cx) + pad, W)
        y0, y1 = max(int(cy) - pad, 0), min(int(cy) + pad, H)
        if x1 <= x0 or y1 <= y0:
            return img
        arr = np.asarray(img, np.float32)
        gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float32) + 0.5,
                             np.arange(y0, y1, dtype=np.float32) + 0.5)
        dx, dy = self._face_disp(gx, gy, sk, face, scale, off)
        # Смещение гасим к краю патча: иначе варп утаскивает пиксели в фон и
        # контур головы (кепка, уши) начинает двоиться.
        rr = np.hypot(gx - cx, gy - cy) / max(r, 1e-6)
        fade = np.clip((1.02 - rr) / 0.22, 0.0, 1.0)
        fade = fade * fade * (3 - 2 * fade)
        dx, dy = dx * fade, dy * fade
        patch = self._sample(arr[y0:y1, x0:x1], gx - dx - x0, gy - dy - y0, edge=True)
        arr[y0:y1, x0:x1] = patch
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

    # --- поза частей ------------------------------------------------------ #
    def _part_transform(self, sk: R.Skeleton, part: str) -> tuple[float, float, float]:
        """(угол, rest-пивот, пивот в позе) для части — жёсткий поворот."""
        bones = PARTS[part]
        main = bones[0]
        rest = self.sk_rest.bones[main]
        posed = sk.bones[main]
        delta = posed.world_angle - rest.world_angle
        return delta, self._rest_pts[main], self.to_px(*posed.world_pos)

    def _joint_color(self, part: str, sk: R.Skeleton, point: tuple[float, float]):
        """Цвет заплатки: медиана части рядом с суставом (в rest-координатах)."""
        parts = self.parts()
        arr = parts.get(part)
        if arr is None:
            return None
        x, y = int(point[0]), int(point[1])
        H, W = arr.shape[:2]
        base = max(int(self.measure["head_r"] * 0.12), 4)
        for mul in (1, 2, 4, 8):              # окно расширяем, пока не найдём ткань
            r = base * mul
            x0, x1 = max(x - r, 0), min(x + r, W)
            y0, y1 = max(y - r, 0), min(y + r, H)
            patch = arr[y0:y1, x0:x1]
            sel = patch[..., 3] > 200
            if sel.any():
                cols = patch[..., :3][sel]
                return tuple(int(v) for v in np.median(cols, axis=0))
        return None

    # --- кадр -------------------------------------------------------------- #
    def frame(self, sk: R.Skeleton, face: F.Face | None = None, *,
              face_expr: str = "neutral", size: tuple[int, int] | None = None,
              **_: object) -> Image.Image:
        """API как у `puppet.Painter`: (скелет, лицо, размер) → RGBA-кадр."""
        face = face or F.Face.from_expression(face_expr)
        target = size or (int(self.work_size[0] * 0.9), int(self.work_size[1] * 0.9))
        img = self.render(sk, face, target)
        return self._open_mouth_art(img, sk, face)

    def _mouth_palette(self) -> dict:
        """Цвета рта, взятые из самого мастера (а не придуманные)."""
        key = "mouth_palette"
        if key in self._cache:
            return self._cache[key]
        cfg = (self.spec.get("art") or {}).get("face") or {}
        art = np.asarray(self.art.convert("RGB"), np.float32)
        Hm, Wm = art.shape[:2]
        if not cfg.get("mouth"):
            self._cache[key] = {}
            return {}
        mx = float(cfg["mouth"][0]) * Wm
        my = float(cfg["mouth"][1]) * Hm
        aw = max(int(float(cfg.get("mouth_w", 0.13)) * Wm * 0.5), 2)
        ah = max(int(float(cfg.get("mouth_h", 0.024)) * Hm * 0.5), 2)
        box = art[max(int(my) - ah, 0):int(my) + ah + 1,
                  max(int(mx) - aw, 0):int(mx) + aw + 1].reshape(-1, 3)
        if not len(box):
            self._cache[key] = {}
            return {}
        lum = box.mean(axis=1)
        order = np.argsort(lum)
        dark = box[order[:max(len(box) // 6, 1)]].mean(axis=0)
        lip = box[order[-max(len(box) // 3, 1):]].mean(axis=0)
        # нутро рта — тёмно-красное (линия губ в мастере, приглушённая в
        # красном канале сильнее, чем в зелёном/синем): серое «дупло» выглядит
        # как дырка в бороде, а не как рот
        inner = dark * np.array([0.95, 0.62, 0.62], np.float32)
        out = {"inner": np.clip(inner, 0, 255),
               "rim": np.clip(dark * 0.95, 0, 255),
               "lip": np.clip(lip, 0, 255),
               "tongue": np.clip(0.55 * lip + 0.30 * dark + 40.0, 0, 255)}
        self._cache[key] = out
        return out

    def _open_mouth_art(self, img: Image.Image, sk: R.Skeleton, face: F.Face) -> Image.Image:
        """Открытый рот рисуется, а не «растягивается» из закрытого рисунка.

        В мастере рот закрыт: внутри губ пикселей открытого рта нет, и любая
        попытка растянуть их варпом даёт вместо рта смазанную «скобку».
        Поэтому при `mouth_open` мы рисуем тёмное нутро рта по форме губ
        (контур и цвет берём из мастера), а закрытая линия губ остаётся
        ободком вокруг — как в настоящей 3D-анимации.
        """
        open_ = float(face.get("mouth_open", 0.0))
        if open_ < 0.06:
            return img
        pal = self._mouth_palette()
        cfg = (self.spec.get("art") or {}).get("face") or {}
        if not pal or not cfg.get("mouth"):
            return img
        W, H = img.size
        ww, wh = self.work_size
        k = min(W / ww, H / wh)
        ox, oy = (W - ww * k) / 2.0, (H - wh * k) / 2.0
        # центр рта в рабочем пространстве, повёрнутый вместе с головой
        mx = float(cfg["mouth"][0]) * ww
        my = float(cfg["mouth"][1]) * wh
        delta, rest_p, posed_p = self._part_transform(sk, "head")
        c, s_ = math.cos(delta), math.sin(delta)
        dx, dy = mx - rest_p[0], my - rest_p[1]
        gx = c * dx - s_ * dy + posed_p[0]
        gy = s_ * dx + c * dy + posed_p[1]
        cx, cy = gx * k + ox, gy * k + oy
        a = max(float(cfg.get("mouth_w", 0.13)) * ww * k * 0.5, 2.0)
        b = max(float(cfg.get("mouth_h", 0.024)) * wh * k * 0.5, 1.5)

        wide = float(face.get("mouth_wide", 0.0))
        aa = a * float(np.clip(0.72 + 0.16 * wide, 0.50, 0.94))
        # верх рта обязан перекрыть закрытую линию губ из мастера, иначе она
        # остаётся висеть над открытым ртом тонкой «щёткой»
        bb = b * float(np.clip(1.02 + 1.15 * open_, 1.00, 1.95))
        cy = cy + bb * 0.10                     # челюсть уходит вниз

        pad = int(max(aa, bb) * 2.4) + 3
        x0, x1 = int(cx) - pad, int(cx) + pad + 1
        y0, y1 = int(cy) - pad, int(cy) + pad + 1
        if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
            return img
        x0c, y0c = max(x0, 0), max(y0, 0)
        x1c, y1c = min(x1, W), min(y1, H)
        yy, xx = np.mgrid[y0c:y1c, x0c:x1c].astype(np.float32) + 0.5
        u = (xx - cx) / aa
        v = (yy - cy) / bb
        d = u * u + v * v
        alpha = np.clip((1.0 - d) * 9.0, 0.0, 1.0)        # мягкий край, px-scale
        if not alpha.any():
            return img

        inner = np.asarray(pal["inner"], np.float32)
        lipc = np.asarray(pal["lip"], np.float32)
        # нутро рта: темнее сверху (глубже), светлее снизу
        shade = np.clip(0.72 + 0.55 * v, 0.55, 1.15)[..., None]
        col = np.broadcast_to(inner, d.shape + (3,)) * shade
        # язык — только когда рот открыт по-настоящему
        if open_ > 0.14:
            tu, tv = u / 0.62, (v - 0.52) / 0.46
            tm = np.clip((1.0 - (tu * tu + tv * tv)) * 4.0, 0.0, 1.0) * min(
                (open_ - 0.14) / 0.35, 1.0)
            col = col * (1 - tm[..., None]) + np.asarray(pal["tongue"], np.float32) * tm[..., None]
        # верхние зубы — на широком открытии
        if open_ > 0.45:
            zu, zv = u / 0.72, (v + 0.62) / 0.34
            zm = np.clip((1.0 - (zu * zu + zv * zv)) * 4.0, 0.0, 1.0) * min(
                (open_ - 0.45) / 0.30, 1.0)
            teeth = np.array([252, 248, 240], np.float32) * (0.82 + 0.18 * np.clip(1 - zv, 0, 1))[..., None]
            col = col * (1 - zm[..., None]) + teeth * zm[..., None]
        # ободок губ: чуть темнее кожи у кромки — читается как губы
        rim = np.clip((d - 0.55) * 5.0, 0.0, 1.0)
        col = col * (1 - rim[..., None] * 0.55) + lipc * (rim[..., None] * 0.55)
        # тёмная кромка губ по контуру openings — иначе рот «расплывается»
        edge = np.clip((d - 0.80) * 6.0, 0.0, 1.0) * np.clip((1.06 - d) * 6.0, 0.0, 1.0)
        col = col * (1 - edge[..., None] * 0.75) + np.asarray(pal["rim"], np.float32) * (edge[..., None] * 0.75)

        arr = np.asarray(img, np.float32).copy()
        region = arr[y0c:y1c, x0c:x1c, :3]
        arr[y0c:y1c, x0c:x1c, :3] = region * (1 - alpha[..., None]) + col * alpha[..., None]
        arr[y0c:y1c, x0c:x1c, 3] = np.maximum(
            arr[y0c:y1c, x0c:x1c, 3], alpha * 255.0)
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

    def _scaled_parts(self, RW: int, RH: int) -> tuple[dict, float, float, float]:
        """Части, приведённые к разрешению кадра (кешируются по размеру)."""
        key = ("scaled", RW, RH)
        if self._cache.get("key") == key:
            return self._cache["scaled"]
        parts = self.parts()
        ww, wh = self.work_size
        k = min(RW / ww, RH / wh)
        ox, oy = (RW - ww * k) / 2.0, (RH - wh * k) / 2.0
        tw, th = max(int(round(ww * k)), 1), max(int(round(wh * k)), 1)
        out = {}
        for name, arr in parts.items():
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
            img = img.resize((tw, th), Image.LANCZOS)
            canvas = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
            canvas.paste(img, (int(round(ox)), int(round(oy))))
            out[name] = canvas
        self._cache["key"] = key
        self._cache["scaled"] = (out, k, ox, oy)
        return out, k, ox, oy

    def _rotate_part(self, img: Image.Image, delta: float,
                     pivot_rest: tuple[float, float],
                     pivot_posed: tuple[float, float]) -> Image.Image:
        """Жёсткий поворот слоя вокруг сустава (без деформации рисунка)."""
        if abs(delta) < 1e-4:
            return img
        c, s_ = math.cos(delta), math.sin(delta)
        a, b, d, e = c, s_, -s_, c                   # R(-delta)
        px1, py1 = pivot_posed
        px0, py0 = pivot_rest
        cx_ = px0 - (a * px1 + b * py1)
        cy_ = py0 - (d * px1 + e * py1)
        return img.transform(img.size, Image.AFFINE, (a, b, cx_, d, e, cy_),
                             resample=Image.BICUBIC)

    def _joint_patch(self, canvas: Image.Image, child: str, joint_bone: str,
                     pivot: tuple[float, float], k: float) -> None:
        """Круг-заплатка в суставе: цвет берётся с прилегающей части."""
        parts = self.parts()
        src = parts.get(child)
        if src is None:
            return
        rx, ry = self._rest_pts[joint_bone]
        rad_src = max(int(self.sk_rest.bones[joint_bone].width * 0.7 * self.fit["k"]), 4)
        x, y = int(rx), int(ry)
        H, W = src.shape[:2]
        patch = src[max(y - rad_src, 0):min(y + rad_src, H), max(x - rad_src, 0):min(x + rad_src, W)]
        sel = patch[..., 3] > 200
        if not sel.any():
            return
        color = tuple(int(v) for v in np.median(patch[..., :3][sel], axis=0))
        rad = max(rad_src * k * 0.55, 2.5)
        cx_, cy_ = pivot
        d = ImageDraw.Draw(canvas)
        d.ellipse([cx_ - rad, cy_ - rad, cx_ + rad, cy_ + rad], fill=color + (255,))

    def render(self, sk: R.Skeleton, face: F.Face, size: tuple[int, int]) -> Image.Image:
        """Собрать кадр: жёсткие части + заплатки на сгибах, затем уменьшение."""
        W, H = int(size[0]), int(size[1])
        ss = max(int(self.ss), 1)
        RW, RH = W * ss, H * ss
        scaled, k, ox, oy = self._scaled_parts(RW, RH)

        canvas = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
        for part in DRAW_ORDER:
            layer = scaled.get(part)
            if layer is None:
                continue
            if part == "head" and face is not None:
                layer = self._warp_face(layer, sk, face)
            delta, (px0, py0), (px1, py1) = self._part_transform(sk, part)
            moved = self._rotate_part(
                layer, delta,
                (px0 * k + ox, py0 * k + oy),
                (px1 * k + ox, py1 * k + oy))
            if part == "shin.l":
                pass
            canvas = Image.alpha_composite(canvas, moved)

        for parent, child, joint_bone in JOINTS:
            if joint_bone is None or child not in scaled:
                continue
            _d, _rest, pivot = self._part_transform(sk, child)
            self._joint_patch(canvas, child, joint_bone,
                              (pivot[0] * k + ox, pivot[1] * k + oy), k)

        img = canvas.reduce(ss) if ss > 1 else canvas
        if img.size != (W, H):
            img = img.resize((W, H), Image.LANCZOS)
        return img


# --------------------------------------------------------------------------- #
# утилиты
# --------------------------------------------------------------------------- #


MAX_SHOULDER_DEG = 60.0     # предел подъёма руки на одном плоском мастере
MAX_ELBOW_DEG = 55.0        # предел сгиба локтя (внутренняя сторона не нарисована)


def pose_issues(rig: "CutoutRig", sk: R.Skeleton,
                max_shoulder: float = MAX_SHOULDER_DEG,
                max_elbow: float = MAX_ELBOW_DEG) -> list[str]:
    """Проверить, что поза не выходит за возможности одного фронтального мастера.

    Подъём руки выше ~60° требует нарисованной подмышки. Возвращает список
    предупреждений; пустой список — поза рендерится чисто.
    """
    out: list[str] = []
    for side in ("r", "l"):
        bone = sk.bones.get(f"upper_arm.{side}")
        if bone is None:
            continue
        # сгиб локтя: на плоском рисунке внутренняя сторона локтя не нарисована
        elbow = sk.bones.get(f"forearm.{side}")
        if elbow is not None:
            bend = abs(math.degrees((elbow.world_angle - bone.world_angle + math.pi)
                                    % (2 * math.pi) - math.pi))
            if bend > max_elbow:
                out.append(f"локоть {side}: сгиб {bend:.0f}° > {max_elbow:.0f}° — "
                           f"нужен ракурс руки (docs/17-ART-RIG.md)")
        # отклонение от rest-угла (рука вниз), в градусах
        rest_world = rig.sk_rest.bones[f"upper_arm.{side}"].world_angle
        delta = abs(math.degrees((bone.world_angle - rest_world + math.pi) % (2 * math.pi)
                                 - math.pi))
        if delta > max_shoulder:
            out.append(f"рука {side}: подъём {delta:.0f}° > {max_shoulder:.0f}° — "
                       f"нужен нарисованный ракурс плеча (docs/17-ART-RIG.md)")
    return out


def available(char_id: str) -> bool:
    return os.path.exists(os.path.join(STUDIO, "characters", char_id, "views", "front.png"))


def debug_overlay(spec: dict, pose: str = "idle", out: str | None = None) -> str:
    """Картинка «скелет поверх мастера» — чтобы глазами проверить посадку."""
    rig_ = ArtRig(spec, ss=1)
    sk = rig_.build(pose)
    img = rig_.frame(sk, F.Face.neutral(), size=None).convert("RGBA")
    d = ImageDraw.Draw(img)
    sx = img.width / rig_.work_size[0]
    sy = img.height / rig_.work_size[1]
    for name in sk.bones:
        p = rig_.to_px(*sk.bones[name].world_pos)
        t = rig_.to_px(*sk.tip(name))
        d.line([(p[0] * sx, p[1] * sy), (t[0] * sx, t[1] * sy)],
               fill=(255, 40, 40, 220), width=2)
        d.ellipse([p[0] * sx - 3, p[1] * sy - 3, p[0] * sx + 3, p[1] * sy + 3],
                  fill=(30, 120, 255, 255))
    out = out or os.path.join(STUDIO, "out", f"artfit-{spec.get('id', 'char')}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.convert("RGB").save(out)
    return out


# --------------------------------------------------------------------------- #
# меш-скиннинг: второй способ деформации (для больших углов в плече/бедре)
# --------------------------------------------------------------------------- #


class ArtRig(CutoutRig):
    """LBS-сетка поверх того же мастера и того же скелета.

    Cutout (`ArtRig`) идеален для малых углов: рисунок не меняется вообще.
    Но когда рука поднимается выше 60°, у плеча нужна растяжимая ткань —
    ровно это и делает скиннинг. Здесь сетка, у каждой вершины 1–2 кости с
    весами по расстоянию, и растеризация треугольников с аффинной выборкой.
    """

    blend: float = 6.0      # сглаживание границ частей: мягче стык — ровнее рукав
    alpha_narrow: bool = True    # сжимать мягкую альфу (иначе «дымка» на стыках)
    seal: bool = True            # затягивать мелкие дырки в складках
    # Выше этого угла в плече тянется уже не ткань, а рисунок рукава: нужен
    # отдельный нарисованный ракурс (см. docs/17-ART-RIG.md), это не костыль,
    # а требование любого cutout-пайплайна.

    def __init__(self, spec: dict, *, grid_x: int = 44, grid_y: int = 62, **kw):
        super().__init__(spec, **kw)
        self.grid_x, self.grid_y = grid_x, grid_y
        self._build_grid()
        self._tris = self._build_tris()
        self._weights = self._mesh_weights()
        self._filled, self._cover = self._fill_art()
        self._tri_valid = self._valid_tris()

    def _valid_tris(self) -> np.ndarray:
        """Треугольники, задевающие силуэт (остальные — пустой фон)."""
        tris = self._tris
        ri, ci = tris[..., 0], tris[..., 1]
        vals = np.stack([self._cover[np.clip(self.vy[ri, ci].astype(int), 0, self._cover.shape[0] - 1),
                                      np.clip(self.vx[ri, ci].astype(int), 0, self._cover.shape[1] - 1)]
                         for _ in (0,)], axis=-1)[..., 0] if False else None
        idx_y = np.clip(self.vy[ri, ci].astype(int), 0, self._cover.shape[0] - 1)
        idx_x = np.clip(self.vx[ri, ci].astype(int), 0, self._cover.shape[1] - 1)
        vals = self._cover[idx_y, idx_x]
        return vals.max(axis=1) > 0.05

    def _fill_art(self) -> tuple[np.ndarray, np.ndarray]:
        """Мастер без прозрачного фона + маска покрытия.

        Скиннинг растягивает пиксели. Если растягивать прозрачный фон, в кадре
        появляются дыры (они и были видны как белые клинья у рукава). Поэтому
        фон заранее заливаем цветом края («растяжка» контура, как при
        подготовке ассета в Spine), а прозрачность берём из отдельной маски.
        """
        art = np.asarray(self.art, np.float32)
        H, W = art.shape[:2]
        alpha = art[..., 3]
        # Тело — уверенная альфа (мягкую тень под фигурой телом не считаем, иначе
        # при шаге она растягивается в тёмную дымку)…
        sil = alpha > 140
        # …а вот для распространения ЦВЕТА в фон берём широкую альфу: в узкой
        # щели между ногами альфа бывает 60–140, и если её пропустить, щель
        # заливается цветом бумаги и всплывает в кадре белой полосой.
        wide = alpha > 24
        # Мягкие пиксели силуэта (тень, сглаженный контур) — плохой источник
        # цвета: у кисти это почти чёрная линия стыка с джинсами, и при
        # движении она растягивается в тёмные зубцы. Берём цвет только у
        # непрозрачных пикселей, а мягкие закрашиваем цветом ближайшего
        # плотного — граница остаётся, но перестаёт «рваться».
        solid = alpha > 0.98 * 255.0
        clean = self._spread_far(art[..., :3], solid, max_rings=24)
        art_for_color = np.where(solid[..., None], art[..., :3], clean)
        filled = art.copy()
        filled[..., :3] = self._spread_far(art_for_color, wide)
        solid = sil.copy()
        for _ in range(16):                      # «раздуваем» цвет края наружу
            if solid.all():
                break
            grown = solid.copy()
            grown[1:, :] |= solid[:-1, :]
            grown[:-1, :] |= solid[1:, :]
            grown[:, 1:] |= solid[:, :-1]
            grown[:, :-1] |= solid[:, 1:]
            new = grown & ~solid
            if not new.any():
                break
            idx = np.argwhere(new)
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ys = np.clip(idx[:, 0] + dy, 0, H - 1)
                xs = np.clip(idx[:, 1] + dx, 0, W - 1)
                ok = solid[ys, xs]
                filled[idx[ok, 0], idx[ok, 1], :3] = filled[ys[ok], xs[ok], :3]
            solid = grown

        # Тонкие пряди волос и швы мастера нарисованы полупрозрачными
        # (альфа 80–140) и в силуэт не попадают. В рендере альфа почти
        # бинарная, поэтому такая линия превращалась в СКВОЗНУЮ царапину через
        # всю причёску. Зашиваем просветы шириной 1–2 px, у которых с обеих
        # сторон есть тело: настоящий фон (между ног, вокруг фигуры) шире.
        sil = self._bridge_lines(sil, max_gap=2)
        # Маска покрытия — сам силуэт. Сужать её нельзя: в узкой щели (пах,
        # между ногами) эрозия съедает всю полосу, и в rest-позе появляется
        # светлая щель. Белёсую кайму по контуру убирает не эрозия, а заливка
        # края (`_spread_far`) + кривая альфы в render.
        cover = Image.fromarray((sil * 255).astype(np.uint8), "L").filter(
            ImageFilter.GaussianBlur(0.8))
        return filled[..., :3], np.asarray(cover, np.float32) / 255.0

    @staticmethod
    def _bridge_lines(mask: np.ndarray, max_gap: int = 2) -> np.ndarray:
        """Зашить узкие просветы (≤ `max_gap` px), ограниченные телом с двух сторон.

        Именно такие просветы и бывают артефактом: прядь волос с мягкой альфой,
        шов, сглаженная кромка. Широкий фон (между ног, вокруг рук) не трогаем —
        он шире порога.
        """
        def _axis(m: np.ndarray) -> np.ndarray:
            """Просветы вдоль строк (столбцы обрабатываются транспонированием)."""
            H, W = m.shape
            res = m.copy()
            for x in range(W - 1):
                if m[:, x].all():
                    continue
                for L in range(1, max_gap + 1):
                    x0 = x - L + 1                     # первый пиксель просвета
                    if x0 < 1 or x + 1 >= W:
                        continue
                    ok = (m[:, x0 - 1] & m[:, x + 1] &
                          (~m[:, x0:x + 1]).all(axis=1))
                    if ok.any():
                        res[ok, x0:x + 1] = True
            return res

        return _axis(mask) | _axis(mask.T).T

    @staticmethod
    def _spread_far(rgb: np.ndarray, sil: np.ndarray, max_rings: int = 400) -> np.ndarray:
        """Залить фон цветом БЛИЖАЙШЕГО пикселя силуэта (без усреднения).

        Важно копировать цвет ОДНОГО ближайшего пикселя, а не среднее по
        соседям: на стыке свитера и джинсов усреднение даёт мутный серо-синий,
        и скиннинг вытаскивает его в кадр как «стружку» на краю рукава.
        """
        H, W = sil.shape
        known = sil.copy()
        out = np.where(sil[..., None], rgb, 0.0).astype(np.float32)
        for _ in range(max_rings):
            if known.all():
                break
            new_known = known.copy()
            new_out = out.copy()
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ys0, ys1 = max(dy, 0), H + min(dy, 0)
                xs0, xs1 = max(dx, 0), W + min(dx, 0)
                src_known = np.zeros((H, W), bool)
                src_val = np.zeros_like(out)
                src_known[ys0:ys1, xs0:xs1] = known[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
                src_val[ys0:ys1, xs0:xs1] = out[ys0 - dy:ys1 - dy, xs0 - dx:xs1 - dx]
                take = src_known & ~new_known
                new_out[take] = src_val[take]
                new_known |= take
            if (new_known == known).all():
                break
            known, out = new_known, new_out
        if not known.all():
            # не дошло до краёв: дальше заливаем средним цветом части
            mean = rgb[sil].mean(axis=0) if sil.any() else np.array([246, 240, 230], np.float32)
            out[~known] = mean
        return out

    def _build_grid(self) -> None:
        W, H = self.work_size
        gx, gy = np.meshgrid(np.linspace(0, W, self.grid_x + 1),
                             np.linspace(0, H, self.grid_y + 1))
        self.vx, self.vy = gx.astype(np.float64), gy.astype(np.float64)

    def _build_tris(self) -> np.ndarray:
        gy, gx = np.meshgrid(np.arange(self.vy.shape[0]), np.arange(self.vx.shape[1]),
                             indexing="ij")
        idx = np.stack([gy, gx], axis=-1)
        a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
        return np.concatenate([
            np.stack([a, b, c], axis=-2).reshape(-1, 3, 2),
            np.stack([a, c, d], axis=-2).reshape(-1, 3, 2),
        ])

    # какие кости двигают каждую часть: региональные веса, а не «по расстоянию»
    PART_BONES = {
        "head": ("head",),
        "arm.r.up": ("upper_arm.r",),
        "arm.l.up": ("upper_arm.l",),
        "arm.r.lo": ("forearm.r", "hand.r"),
        "arm.l.lo": ("forearm.l", "hand.l"),
        "torso": ("spine", "chest", "neck"),
        "thigh.r": ("thigh.r",),
        "thigh.l": ("thigh.l",),
        "shin.r": ("shin.r", "foot.r"),
        "shin.l": ("shin.l", "foot.l"),
    }

    def _region_masks(self) -> dict[str, np.ndarray]:
        """Маски частей на сетке (по пикселям скелета), сглаженные для стыков."""
        if getattr(self, "_rmask", None) is not None:
            return self._rmask
        raw = self.parts()
        W, H = self.work_size
        out = {}
        for part, arr in raw.items():
            m = (arr[..., 3] > 40).astype(np.float32)
            out[part] = np.asarray(
                Image.fromarray((m * 255).astype(np.uint8), "L").filter(
                    ImageFilter.GaussianBlur(self.blend)), np.float32) / 255.0
        self._rmask = out
        return out

    def _along(self, bone: str) -> np.ndarray:
        """Параметр t вдоль кости для вершин сетки: 0 у сустава, 1 у конца."""
        b = self.sk_rest.bones[bone]
        ax, ay = self.to_px(*b.world_pos)
        bx, by = self.to_px(*self.sk_rest.tip(bone))
        vx, vy = bx - ax, by - ay
        l2 = max(vx * vx + vy * vy, 1e-6)
        return np.clip(((self.vx - ax) * vx + (self.vy - ay) * vy) / l2, 0.0, 1.4)

    @staticmethod
    def _sstep(k: np.ndarray, lo: float, hi: float) -> np.ndarray:
        t = np.clip((k - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
        return t * t * (3 - 2 * t)

    def _mesh_weights(self) -> np.ndarray:
        """Веса костей в вершинах: маска части × близость к кости.

        Маска части — приор («этот пиксель принадлежит рукаву»), близость к
        кости — то, как вес распределяется внутри части, а размытие маски даёт
        плавное перетекание веса через сустав. Без приора пиксели фона рядом с
        поднятой рукой получают вес руки и тянутся в кадр как белые клинья —
        именно это и рвало картинку.
        """
        masks = self._region_masks()
        # кисть и стопа — короткие кости в конце цепочки: как отдельные веса они
        # только рвут рисунок на мелких пикселях. Пусть их ведут предплечье и
        # голень — на этом стиле этого достаточно.
        skip = ("foot.",)
        bones = [n for n in self.sk_rest.bones
                 if self.sk_rest.bones[n].length > 1e-6 and not n.startswith(skip)]
        index = {n: i for i, n in enumerate(bones)}
        px, py = self.vx, self.vy

        def sample(arr: np.ndarray) -> np.ndarray:
            img = Image.fromarray(arr.astype(np.float32), "F")
            return np.asarray(img.resize((px.shape[1], py.shape[0]), Image.BILINEAR),
                              np.float32)

        # Приор каждой кости — маска ВСЕЙ группы (рука, нога, корпус, голова),
        # а внутри группы вес делит близость к кости. Иначе, например, при
        # limb_split="whole" у предплечья не остаётся своей маски, его кость
        # получает нулевой приор, и рука рвётся по шву.
        def group(parts: tuple[str, ...]) -> np.ndarray:
            acc = np.zeros(self.work_size[::-1], np.float32)
            for p_ in parts:
                m = masks.get(p_)
                if m is not None:
                    acc = np.maximum(acc, m)
            return sample(acc)

        GROUP_PARTS = {
            "arm.r": ("arm.r.up", "arm.r.lo"),
            "arm.l": ("arm.l.up", "arm.l.lo"),
            "leg.r": ("thigh.r", "shin.r"),
            "leg.l": ("thigh.l", "shin.l"),
            "trunk": ("torso",),
            "head": ("head",),
        }
        BONE_GROUP = {
            "upper_arm.r": "arm.r", "forearm.r": "arm.r", "hand.r": "arm.r",
            "upper_arm.l": "arm.l", "forearm.l": "arm.l", "hand.l": "arm.l",
            "thigh.r": "leg.r", "shin.r": "leg.r", "foot.r": "leg.r",
            "thigh.l": "leg.l", "shin.l": "leg.l", "foot.l": "leg.l",
            "spine": "trunk", "chest": "trunk", "neck": "trunk",
            "head": "head",
        }
        gmask = {g: group(parts) for g, parts in GROUP_PARTS.items()}
        prior = {n: gmask.get(BONE_GROUP.get(n, "trunk"),
                              np.zeros(px.shape, np.float32)).copy() for n in bones}

        # Пах: там, где веса обеих ног перекрываются, пиксель не принадлежит ни
        # одной из них — иначе треугольник сетки соединяет левую ногу с правой и
        # при шаге рвёт картинку. Отдаём эту зону тазу (hips): ноги отходят от
        # него, как от центра, а не друг от друга.
        if "thigh.l" in prior and "thigh.r" in prior and "spine" in index:
            shared = np.minimum(prior["thigh.l"], prior["thigh.r"])
            shared = shared * self._sstep(shared, 0.02, 0.30)
            if shared.any():
                prior["thigh.l"] = prior["thigh.l"] - shared
                prior["thigh.r"] = prior["thigh.r"] - shared
                prior["spine"] = prior["spine"] + shared

        dist = {n: _seg_dist(px, py, *self.to_px(*self.sk_rest.bones[n].world_pos),
                             *self.to_px(*self.sk_rest.tip(n))).astype(np.float32)
                for n in bones}
        scale = self.measure["head_r"] * 1.6

        W = np.zeros((len(bones),) + px.shape, np.float64)
        for n in bones:
            falloff = 1.0 / (1.0 + (dist[n] / max(scale, 1.0)) ** 2)
            W[index[n]] = prior[n] * falloff

        # где приор не сработал (заливка фона) — берём ближайшую кость
        empty = W.sum(axis=0) < 1e-4
        if empty.any():
            d_stack = np.stack([dist[n] for n in bones])
            nearest = np.argmin(d_stack, axis=0)
            for i in range(len(bones)):
                W[i][empty & (nearest == i)] = 1e-3

        ssum = np.maximum(W.sum(axis=0), 1e-9)
        W = W / ssum[None]

        # внутри части — жёстко: иначе на большом объекте (крупная голова ребёнка)
        # видно шов вдоль сетки, где вес перетекает между костями
        priors = np.stack([prior[n] for n in bones])
        strongest = np.argmax(priors, axis=0)
        rigid = np.zeros(px.shape, bool)
        if "head" in index:
            rigid = priors[index["head"]] > 0.92
        W[:, rigid] = 0.0
        W[strongest[rigid], np.nonzero(rigid)[0], np.nonzero(rigid)[1]] = 1.0

        self._bone_names = bones
        return W

    # семейства костей: через зазор между ними треугольник тянуть нельзя
    LIMB_FAMILY = {
        "arm.r.up": "arm.r", "arm.r.lo": "arm.r",
        "arm.l.up": "arm.l", "arm.l.lo": "arm.l",
        "thigh.r": "leg.r", "shin.r": "leg.r",
        "thigh.l": "leg.l", "shin.l": "leg.l",
        "torso": "trunk", "head": "head",
    }

    def _cover_soft(self) -> np.ndarray:
        """Покрытие, у которого узкие щели (рука—корпус, пах) считаются телом.

        Ширина такого зазора на мастере — 4–12 px: это не «дырка в рисунке», а
        тёмная линия стыка. При скиннинге треугольник через неё перекидывается,
        и если его выбросить — останется дыра; если оставить без проверки —
        вылезут серые «билеты» на широком фоне (между ногами при шаге). Поэтому
        пустотой считаем только то, что осталось пустым ПОСЛЕ закрытия узких
        зазоров.
        """
        if getattr(self, "_cover_soft_cache", None) is None:
            rad = max(int(round(self.measure["head_r"] * 0.10)), 3)
            a = Image.fromarray((np.clip(self._cover, 0, 1) * 255).astype(np.uint8), "L")
            closed = a.filter(ImageFilter.MaxFilter(2 * rad + 1)).filter(
                ImageFilter.MinFilter(2 * rad + 1))
            self._cover_soft_cache = np.asarray(closed, np.float32) / 255.0
        return self._cover_soft_cache

    def _tri_family(self, tris: np.ndarray) -> np.ndarray:
        """Семейство каждого треугольника (0 корпус, 1 рука-право, 2 рука-лево,
        3 нога-право, 4 нога-лево, 5 голова).

        Считается по маскам частей в rest-пространстве: у треугольника берётся
        середина, и семейство определяется по той части, в чью маску она попала.
        Так «рука поверх бедра» не тянет цвет джинсов на кисть.
        """
        if getattr(self, "_tri_fam_cache", None) is None:
            FAM = [("trunk", ("torso",)), ("arm.r", ("arm.r.up", "arm.r.lo")),
                   ("arm.l", ("arm.l.up", "arm.l.lo")),
                   ("leg.r", ("thigh.r", "shin.r")), ("leg.l", ("thigh.l", "shin.l")),
                   ("head", ("head",))]
            masks = self.parts()
            H, W = self.work_size[1], self.work_size[0]
            score = np.full((len(FAM), H, W), -1.0, np.float32)
            for fi, (_name, parts) in enumerate(FAM):
                for p_ in parts:
                    arr = masks.get(p_)
                    if arr is not None:
                        score[fi] = np.maximum(score[fi], arr[..., 3].astype(np.float32))
            # Считаем покрытие всех трёх вершин для каждого семейства и берём
            # максимум суммы. Мягкие маски частей дают дробное покрытие, поэтому
            # треугольник у границы кисти и бедра честно относят к руке, а не к
            # джинсам (иначе кисть начинала брать тёмный цвет штанов).
            bias = np.array([1.0, 1.35, 1.35, 1.0, 1.0, 1.1], np.float32)[:, None]
            total = np.zeros((len(FAM), len(tris)), np.float32)
            for k in range(3):
                ri_, ci_ = tris[..., k, 0], tris[..., k, 1]
                xi = np.clip(self.vx[ri_, ci_].astype(np.int32), 0, W - 1)
                yi = np.clip(self.vy[ri_, ci_].astype(np.int32), 0, H - 1)
                total += score[:, yi, xi]
            best = np.argmax(total * bias, axis=0).astype(np.int32)
            best[total.max(axis=0) <= 0] = 0            # вне частей — корпус
            self._tri_fam_cache = best
        return self._tri_fam_cache

    def _family_art(self) -> np.ndarray:
        """Цвет мастера отдельно для каждого семейства частей.

        Иначе треугольник кисти, задевающий край, берёт цвет соседних джинсов:
        на кадре это тёмные многоугольники на руке. Для каждой группы
        (руки, ноги, корпус, голова) цвет растягивается только из её
        собственных пикселей, поэтому рука остаётся кожей, а нога — джинсами.
        """
        if getattr(self, "_fam_art_cache", None) is not None:
            return self._fam_art_cache
        art = np.asarray(self.art, np.float32)
        alpha = art[..., 3]
        solid = alpha > 0.98 * 255.0
        masks = self.parts()
        fams = ["trunk", "arm.r", "arm.l", "leg.r", "leg.l", "head"]
        fam_parts = {
            "trunk": ("torso",), "arm.r": ("arm.r.up", "arm.r.lo"),
            "arm.l": ("arm.l.up", "arm.l.lo"), "leg.r": ("thigh.r", "shin.r"),
            "leg.l": ("thigh.l", "shin.l"), "head": ("head",),
        }
        out = []
        for f in fams:
            seed = np.zeros(alpha.shape, bool)
            for p_ in fam_parts[f]:
                m = masks.get(p_)
                if m is not None:
                    seed |= m[..., 3] > 140
            seed &= solid
            if seed.sum() < 30:
                seed = solid
            fill = self._spread_far(art[..., :3], seed, max_rings=60)
            # там, где волна не дошла, остаётся общий фон — это далеко от части
            out.append(fill)
        self._fam_art_cache = np.stack(out)
        return self._fam_art_cache

    def _tri_same_limb(self, tris: np.ndarray) -> np.ndarray:
        """Не рисовать треугольники, соединяющие две РАЗНЫЕ конечности.

        Такой треугольник перекидывается через зазор (между ногами у паха, между
        рукой и корпусом) и при движении тянет пиксели от одной части к другой —
        это и была тёмная «тряпка» между ног и белые клинья у подмышки.
        """
        if getattr(self, "_tri_family_ok", None) is None:
            dom = np.argmax(self._weights, axis=0)          # (gy, gx)
            names = list(self._bone_names)
            fam_id: dict[str, int] = {}
            fam = np.zeros(dom.shape, np.int32)
            for i, name in enumerate(names):
                f = self.LIMB_FAMILY.get(name, "trunk")
                fam_id.setdefault(f, len(fam_id))
                fam[dom == i] = fam_id[f]
            limb_ids = {v for k, v in fam_id.items() if k not in ("trunk", "head")}
            ri, ci = tris[..., 0], tris[..., 1]
            f3 = fam[np.clip(ri, 0, fam.shape[0] - 1), np.clip(ci, 0, fam.shape[1] - 1)]
            l3 = np.where(np.isin(f3, list(limb_ids)), f3, -1) if limb_ids else \
                np.full(f3.shape, -1, np.int32)
            def _pair(i, j):
                return ((l3[:, i] >= 0) & (l3[:, j] >= 0) & (l3[:, i] != l3[:, j]))
            cross = _pair(0, 1) | _pair(0, 2) | _pair(1, 2)
            # ...но только если треугольник реально перекидывается через ПУСТОТУ.
            # Ткань, непрерывная через середину (пах, грудь), принадлежит разным
            # костям, однако фона под ней нет — её рисовать можно и нужно.
            cxs = self.vx[tris[..., 0], tris[..., 1]].mean(axis=1)
            cys = self.vy[tris[..., 0], tris[..., 1]].mean(axis=1)
            cx_i = np.clip(cxs.astype(int), 0, self._cover.shape[1] - 1)
            cy_i = np.clip(cys.astype(int), 0, self._cover.shape[0] - 1)
            # Рука и нога — разные слои глубины (рука нарисована поверх бедра).
            # Треугольник между ними тянет пиксели джинсов на кисть — это те
            # самые тёмные многоугольники. Такие треугольники не рисуем никогда.
            # Ноги-ноги и рука-рука пусть тянутся: это непрерывная ткань.
            self._tri_family_ok = ~cross
            # семейство треугольника = самое частое среди трёх вершин
            fam_order = ["trunk", "arm.r", "arm.l", "leg.r", "leg.l", "head"]
            idx_map = {fid: fam_order.index(name) if name in fam_order else 0
                       for name, fid in fam_id.items()}
            votes = np.stack([np.vectorize(lambda v: idx_map.get(int(v), 0))(f3[:, k])
                              for k in range(3)])
            self._tri_fam_cache = np.array(
                [int(np.bincount(votes[:, i]).argmax()) for i in range(votes.shape[1])],
                np.int32)
        return self._tri_family_ok

    BACKING_BONE = {"upper_arm.r": "chest", "forearm.r": "chest", "hand.r": "chest",
                    "upper_arm.l": "chest", "forearm.l": "chest", "hand.l": "chest"}

    def _posed_verts(self, sk: R.Skeleton,
                     backing: bool = False) -> tuple[np.ndarray, np.ndarray]:
        """Прямое LBS-преобразование вершин сетки (пиксели рамы)."""
        qx = np.zeros_like(self.vx)
        qy = np.zeros_like(self.vy)
        for i, name in enumerate(self._bone_names):
            w = self._weights[i]
            if not w.any():
                continue
            if backing:
                name = self.BACKING_BONE.get(name, name)
            rest = self.sk_rest.bones[name]
            posed = sk.bones[name]
            delta = posed.world_angle - rest.world_angle
            c, s_ = math.cos(delta), math.sin(delta)
            ax, ay = self.to_px(*rest.world_pos)
            bx, by = self.to_px(*posed.world_pos)
            dx, dy = self.vx - ax, self.vy - ay
            qx += w * (c * dx - s_ * dy + bx)
            qy += w * (s_ * dx + c * dy + by)
        return qx, qy

    def render(self, sk: R.Skeleton, face: F.Face, size: tuple[int, int]) -> Image.Image:
        """Кадр = «подкладка» + обычный проход.

        В мастере нет рисунка в подмышке (руки прижаты). Когда рука поворачивается,
        там открывается щель. Поэтому сначала рисуем подкладку — те же пиксели,
        но руки привязаны к корпусу: она закрывает подмышку тканью. Сверху идёт
        обычный проход с повёрнутыми руками. Цвет совпадает, потому что это те же
        пиксели мастера, а не подобранная заливка.
        """
        base = self._render_pass(sk, face, size, backing=True)
        top = self._render_pass(sk, face, size, backing=False)
        # Подкладка закрывает подмышку, но рисует руку, привязанную к корпусу:
        # при повороте руки рядом с настоящей появляется «призрачная» вторая
        # рука. Поэтому берём подкладку ТОЛЬКО в настоящих щелях — там, где
        # верхний проход прозрачен, но зажат телом с двух сторон. Призрачная
        # рука выходит за силуэт и открыта в фон, значит сюда не попадает.
        top_a = np.asarray(top.getchannel("A"))
        max_gap = max(int(round(self.measure["head_r"] * 0.35)), 8)
        gap = self._bridge_lines(top_a > 60, max_gap=max_gap) & (top_a <= 60)
        if gap.any():
            base_a = np.asarray(base.getchannel("A"))
            keep = gap & (base_a > 60)
            if keep.any():
                arr = np.asarray(base).copy()
                arr[..., 3] = np.where(keep, arr[..., 3], 0)
                base = Image.fromarray(arr, "RGBA")
        return Image.alpha_composite(base, top)

    def _render_pass(self, sk: R.Skeleton, face: F.Face, size: tuple[int, int],
                     backing: bool = False) -> Image.Image:
        W, H = int(size[0]), int(size[1])
        ss = max(int(self.ss), 1)
        RW, RH = W * ss, H * ss
        ww, wh = self.work_size
        k = min(RW / ww, RH / wh)
        ox, oy = (RW - ww * k) / 2.0, (RH - wh * k) / 2.0

        # RGB — «залитый» мастер (без прозрачного фона), альфа — из маски покрытия
        rgb_img = Image.new("RGB", (RW, RH), (246, 240, 230))
        cover_img = Image.new("L", (RW, RH), 0)
        tw, th = int(round(ww * k)), int(round(wh * k))
        px0, py0 = int(round(ox)), int(round(oy))
        rgb_img.paste(Image.fromarray(self._filled.astype(np.uint8), "RGB").resize(
            (tw, th), Image.LANCZOS), (px0, py0))
        cover_img.paste(Image.fromarray((self._cover * 255).astype(np.uint8), "L").resize(
            (tw, th), Image.LANCZOS), (px0, py0))
        if face is not None:
            rgb_img = self._warp_face(rgb_img.convert("RGBA"), sk, face,
                                      k, (ox, oy)).convert("RGB")
        art = np.asarray(rgb_img, np.float32)
        cover = np.asarray(cover_img, np.float32) / 255.0

        # цвет по семействам: рука берёт кожу, нога — джинсы (см. _family_art)
        fam = self._tri_family(self._tris)
        fam_art = []
        for layer in self._family_art():
            img_f = Image.new("RGB", (RW, RH), (246, 240, 230))
            img_f.paste(Image.fromarray(layer.astype(np.uint8), "RGB").resize(
                (tw, th), Image.LANCZOS), (px0, py0))
            if face is not None:
                img_f = self._warp_face(img_f.convert("RGBA"), sk, face,
                                        k, (ox, oy)).convert("RGB")
            fam_art.append(np.asarray(img_f, np.float32))
        fam_art = np.stack(fam_art)

        qx, qy = self._posed_verts(sk, backing=backing)
        qx, qy = qx * k + ox, qy * k + oy
        rx, ry = self.vx * k + ox, self.vy * k + oy

        tris = self._tris
        ri, ci = tris[..., 0].astype(np.int32), tris[..., 1].astype(np.int32)
        R = np.stack([rx[ri, ci], ry[ri, ci], np.ones(ri.shape)], axis=-1)
        P = np.stack([qx[ri, ci], qy[ri, ci], np.ones(ri.shape)], axis=-1)
        area = (P[:, 1, 0] - P[:, 0, 0]) * (P[:, 2, 1] - P[:, 0, 1]) - \
               (P[:, 1, 1] - P[:, 0, 1]) * (P[:, 2, 0] - P[:, 0, 0])
        area0 = (R[:, 1, 0] - R[:, 0, 0]) * (R[:, 2, 1] - R[:, 0, 1]) - \
                (R[:, 1, 1] - R[:, 0, 1]) * (R[:, 2, 0] - R[:, 0, 0])
        valid = np.abs(area) > 1e-3
        # Смятые и вывернутые треугольники (складка локтя, подмышка) при выборке
        # «улетают» далеко в фон и приносят в кадр цвет бумаги — белые клинья.
        # Такой треугольник лучше не рисовать: соседние перекроют.
        valid &= np.abs(area0) > 1e-6
        # Треугольник не должен перекидываться через зазор между конечностями:
        # иначе он тянет пиксели от левой ноги к правой (тёмная «тряпка» у паха).
        # (проверка «через зазор» живёт в _tri_same_limb; в render она уже
        # учтена внутри _tri_valid — здесь дублировать не нужно)
        P = P.copy()
        P[~valid] = np.array([[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]])
        M = np.transpose(np.linalg.inv(P) @ R, (0, 2, 1))

        out = np.zeros((RH, RW, 4), np.float32)
        px_, py_ = qx[ri, ci], qy[ri, ci]
        bx0 = np.floor(px_.min(axis=1)).astype(np.int32) - 1
        by0 = np.floor(py_.min(axis=1)).astype(np.int32) - 1
        bx1 = np.ceil(px_.max(axis=1)).astype(np.int32) + 1
        by1 = np.ceil(py_.max(axis=1)).astype(np.int32) + 1
        bw = np.clip(bx1 - bx0 + 1, 1, RW).astype(np.int32)
        bh = np.clip(by1 - by0 + 1, 1, RH).astype(np.int32)
        ok = valid & (bx1 >= 0) & (by1 >= 0) & (bx0 < RW) & (by0 < RH) & self._tri_valid

        # треугольники бьём на «вёдра» по размеру: иначе один крупный треугольник
        # растягивает рабочий буфер на всю пачку и растеризация становится в 20 раз
        # медленнее, чем нужно
        # Порядок слоёв глубины: ноги → корпус → руки → голова. Раньше порядок
        # задавался только размером треугольника, и треугольник джинсов ложился
        # поверх кисти — на руке появлялись тёмные многоугольники.
        msz = np.maximum(bw, bh)
        edges = [6, 10, 16, 24, 36, 56, 90, 10 ** 9]
        ORDER = {3: 0, 4: 0, 0: 1, 1: 2, 2: 2, 5: 3}     # семейство → слой
        depth = np.array([ORDER.get(int(v), 1) for v in fam], np.int32)
        batches = []
        BUDGET = 1_500_000                      # пикселей на пачку (память/скорость)
        for d in range(4):
            lo = 0
            for hi in edges:
                sel = np.where(ok & (msz > lo) & (msz <= hi) & (depth == d))[0]
                lo = hi
                if not sel.size:
                    continue
                sel = sel[np.argsort(-msz[sel])]
                cur: list[int] = []
                tw_m = th_m = 0
                for idx in sel:
                    w_, h_ = int(bw[idx]), int(bh[idx])
                    if cur and (len(cur) + 1) * max(tw_m, w_) * max(th_m, h_) > BUDGET:
                        batches.append(np.array(cur, np.int64))
                        cur, tw_m, th_m = [], 0, 0
                    cur.append(int(idx))
                    tw_m, th_m = max(tw_m, w_), max(th_m, h_)
                if cur:
                    batches.append(np.array(cur, np.int64))
        batches.reverse()          # внутри слоя: крупные раньше, мелкие перекрывают

        for sel in batches:
            if not sel.size:
                continue
            tw, th = int(bw[sel].max()), int(bh[sel].max())
            shape = (sel.size, th, tw)
            px = np.broadcast_to(bx0[sel][:, None, None] +
                                 np.arange(tw, dtype=np.float32)[None, None, :] + 0.5, shape)
            py = np.broadcast_to(by0[sel][:, None, None] +
                                 np.arange(th, dtype=np.float32)[None, :, None] + 0.5, shape)
            a = px_[sel][:, :, None, None]
            b = py_[sel][:, :, None, None]

            def _edge(i, j):
                ex, ey = a[:, j] - a[:, i], b[:, j] - b[:, i]
                cross = ex * (py - b[:, i]) - ey * (px - a[:, i])
                # длина ребра — вектор (n,), а не (n,1,1): иначе допуск
                # раздувается до 5-мерной маски
                return cross, np.sqrt(ex * ex + ey * ey).reshape(-1)

            # Допуск попадания = 0.75 px ПО ГЕОМЕТРИИ, а не «1.2 в единицах
            # векторного произведения». Векторное произведение = |ребро| *
            # расстояние, поэтому при длинном ребре прежний допуск означал
            # 0.005 px: пиксели на шве между треугольниками сетки не попадали ни
            # в один из них, и по всему кадру (волосы, рукав, штанина) шли
            # прозрачные трещины толщиной в 1 px.
            _TOL_PX = 0.75
            (e0, l0), (e1, l1), (e2, l2) = _edge(1, 2), _edge(2, 0), _edge(0, 1)
            sgn = np.where(np.sign(area[sel]) == 0, 1.0, np.sign(area[sel]))[:, None, None]
            t0, t1, t2 = (_TOL_PX * v[:, None, None] for v in (l0, l1, l2))
            inside = ((e0 * sgn >= -t0) & (e1 * sgn >= -t1) & (e2 * sgn >= -t2))
            if not inside.any():
                continue
            m = M[sel]
            sx = m[:, 0, 0][:, None, None] * px + m[:, 0, 1][:, None, None] * py + \
                m[:, 0, 2][:, None, None]
            sy = m[:, 1, 0][:, None, None] * px + m[:, 1, 1][:, None, None] * py + \
                m[:, 1, 2][:, None, None]
            gxi = np.broadcast_to(bx0[sel][:, None, None] +
                                  np.arange(tw, dtype=np.float32)[None, None, :], shape)[inside]
            gyi = np.broadcast_to(by0[sel][:, None, None] +
                                  np.arange(th, dtype=np.float32)[None, :, None], shape)[inside]
            gxi, gyi = gxi.astype(np.int32), gyi.astype(np.int32)
            keep = (gxi >= 0) & (gxi < RW) & (gyi >= 0) & (gyi < RH)
            if not keep.any():
                continue
            # edge=True: за краем мастера цвет «прилипает» к крайнему пикселю.
            # Иначе у самой кромки (кисть, рукав) выборка попадала в чёрный ноль
            # и по контуру шли чёрные зубцы.
            # выборка из карты СВОЕГО семейства
            fi = np.broadcast_to(fam[sel][:, None, None], inside.shape)[inside][keep]
            sxi = np.clip(sx[inside][keep].astype(np.int32), 0, RW - 1)
            syi = np.clip(sy[inside][keep].astype(np.int32), 0, RH - 1)
            rgb = fam_art[fi, syi, sxi]
            # альфа бинарная: при растяжении мягкая альфа размазывается в
            # серую «дымку» вокруг паха и подмышки. Резкая альфа + суперсэмплинг
            # дают чистый край без этой каймы.
            # Пиксельная сетка кадра — центры пикселей (i + 0.5), а массив
            # индексируется с нуля: без сдвига на -0.5 билинейная выборка на
            # самой кромке усредняла «тело» с фоном (0.5 < порога 0.55) и
            # стирала крайний пиксель силуэта — по контуру шли прозрачные
            # царапины. edge=True: за краем кадра альфа не должна рассыпаться.
            cov = self._sample(cover[..., None], sx[inside][keep] - 0.5,
                               sy[inside][keep] - 0.5, edge=True)[..., 0]
            if self.alpha_narrow:
                # Узкая (почти бинарная) альфа. Широкий мягкий край давал
                # полупрозрачные пиксели с «мусорным» цветом (они сэмплируются
                # уже за силуэтом) — именно из них состояли бледно-серые зубцы
                # на стыке руки и корпуса. При ss=2 сглаживание обеспечивает
                # сам суперсэмплинг, а не размазывание альфы.
                cov = np.clip((cov - 0.55) / 0.10, 0.0, 1.0)
            out[gyi[keep], gxi[keep], :3] = rgb
            out[gyi[keep], gxi[keep], 3] = np.clip(cov, 0.0, 1.0) * 255.0

        img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")
        if self.seal:
            img = self._seal_holes(img, rad=max(int(round(2 * ss)), 2))
        img = img.reduce(ss) if ss > 1 else img
        return img.resize((W, H), Image.LANCZOS) if img.size != (W, H) else img

    def _lbs_point(self, p: tuple[float, float], sk: R.Skeleton) -> tuple[float, float]:
        """Куда скиннинг сдвинул точку rest-пространства (по весам сетки)."""
        gy, gx = self._weights.shape[1], self._weights.shape[2]
        fx = p[0] / max(self.work_size[0], 1) * (gx - 1)
        fy = p[1] / max(self.work_size[1], 1) * (gy - 1)
        i0, j0 = int(np.floor(fy)), int(np.floor(fx))
        i0, j0 = min(max(i0, 0), gy - 2), min(max(j0, 0), gx - 2)
        ty, tx = fy - i0, fx - j0
        w = (self._weights[:, i0, j0] * (1 - tx) * (1 - ty) +
             self._weights[:, i0, j0 + 1] * tx * (1 - ty) +
             self._weights[:, i0 + 1, j0] * (1 - tx) * ty +
             self._weights[:, i0 + 1, j0 + 1] * tx * ty)
        qx = qy = 0.0
        for i, name in enumerate(self._bone_names):
            if w[i] < 1e-4:
                continue
            rest = self.sk_rest.bones[name]
            posed = sk.bones[name]
            delta = posed.world_angle - rest.world_angle
            c, s_ = math.cos(delta), math.sin(delta)
            ax, ay = self.to_px(*rest.world_pos)
            bx, by = self.to_px(*posed.world_pos)
            dx, dy = p[0] - ax, p[1] - ay
            qx += w[i] * (c * dx - s_ * dy + bx)
            qy += w[i] * (s_ * dx + c * dy + by)
        return qx, qy

    def _crease_patches(self, img: Image.Image, sk: R.Skeleton, k: float,
                        off: tuple[float, float]) -> Image.Image:
        """Круг-«ткань» во внутренней складке локтя и колена.

        У прямого мастера внутри сгиба нет нарисованных пикселей: при сгибе
        сетка там схлопывается веером и в кадре остаётся решётка с просветами.
        Заплатка цвета ткани (медиана части у сустава) закрывает сгиб так же,
        как это делают cutout-риги в Spine.
        """
        drawn = img.copy()
        d = ImageDraw.Draw(drawn)
        part_of = {"upper_arm.l": "arm.l.up", "upper_arm.r": "arm.r.up",
                   "thigh.l": "thigh.l", "thigh.r": "thigh.r"}
        for parent, child, joint_bone in JOINTS:
            delta, rest_pivot, posed_pivot = self._part_transform(sk, child)
            # заплатку ставим туда, куда сетка РЕАЛЬНО сдвинула сустав: у мягкого
            # скиннинга это не позиция кости, а LBS-образ rest-точки
            posed_pivot = self._lbs_point(rest_pivot, sk)
            if abs(delta) < math.radians(8.0):
                continue
            color = self._joint_color(child, sk, rest_pivot)
            if color is None and part_of.get(parent) in self.parts():
                color = self._joint_color(part_of[parent], sk, rest_pivot)
            if color is None:
                continue
            w = self.sk_rest.bones[joint_bone].width * self.fit["k"]
            rad = max(w * 0.62, 3.0) * k
            cx_ = posed_pivot[0] * k + off[0]
            cy_ = posed_pivot[1] * k + off[1]
            d.ellipse([cx_ - rad, cy_ - rad, cx_ + rad, cy_ + rad],
                      fill=tuple(int(v) for v in color) + (255,))
        return drawn

    def _seal_holes(self, img: Image.Image, rad: int = 4) -> Image.Image:
        """Затянуть узкие просветы между частями (подмышка, пах в rest).

        Просвет «рука — корпус» открыт наружу, поэтому это не «дырка», и
        заливкой изнутри его не взять. Зато он УЗКИЙ и ограничен телом слева и
        справа. Поэтому закрываем его горизонтальным морфологическим
        закрытием: пиксель закрашивается, только если в пределах `rad` слева и
        справа есть тело. Широкий настоящий фон (разведённые ноги в шаге,
        пространство вокруг фигуры) так не закрывается — он шире `rad`.
        """
        a = np.asarray(img.getchannel("A"), np.uint8)
        if not (a > 20).any():
            return img
        H, W = a.shape
        opaque = a > 20
        size = 2 * max(int(rad), 1) + 1
        m = self.measure
        y0 = max(int(m["shoulder_y"] - 0.06 * m["h"]), 0)
        y1 = min(int(m["hip_y"] + 0.20 * m["h"]), H)
        band = np.zeros_like(opaque)
        band[y0:y1] = True
        op = Image.fromarray((opaque * 255).astype(np.uint8), "L")
        closed = op.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))
        gain = (np.asarray(closed, np.uint8) > 20) & ~opaque & band
        if not gain.any():
            return img
        rgb = img.convert("RGB").filter(ImageFilter.GaussianBlur(max(rad * 0.8, 1.0)))
        out = img.copy()
        out.paste(rgb, (0, 0), Image.fromarray((gain * 255).astype(np.uint8), "L"))
        new_alpha = np.where(gain, 255, a)
        out.putalpha(Image.fromarray(new_alpha.astype(np.uint8), "L"))
        return out

    def _lbs_point(self, p: tuple[float, float], sk: R.Skeleton) -> tuple[float, float]:
        """Куда скиннинг сдвинул точку rest-пространства (по весам сетки)."""
        gy, gx = self._weights.shape[1], self._weights.shape[2]
        fx = p[0] / max(self.work_size[0], 1) * (gx - 1)
        fy = p[1] / max(self.work_size[1], 1) * (gy - 1)
        i0, j0 = int(np.floor(fy)), int(np.floor(fx))
        i0, j0 = min(max(i0, 0), gy - 2), min(max(j0, 0), gx - 2)
        ty, tx = fy - i0, fx - j0
        w = (self._weights[:, i0, j0] * (1 - tx) * (1 - ty) +
             self._weights[:, i0, j0 + 1] * tx * (1 - ty) +
             self._weights[:, i0 + 1, j0] * (1 - tx) * ty +
             self._weights[:, i0 + 1, j0 + 1] * tx * ty)
        qx = qy = 0.0
        for i, name in enumerate(self._bone_names):
            if w[i] < 1e-4:
                continue
            rest = self.sk_rest.bones[name]
            posed = sk.bones[name]
            delta = posed.world_angle - rest.world_angle
            c, s_ = math.cos(delta), math.sin(delta)
            ax, ay = self.to_px(*rest.world_pos)
            bx, by = self.to_px(*posed.world_pos)
            dx, dy = p[0] - ax, p[1] - ay
            qx += w[i] * (c * dx - s_ * dy + bx)
            qy += w[i] * (s_ * dx + c * dy + by)
        return qx, qy

    def _crease_patches(self, img: Image.Image, sk: R.Skeleton, k: float,
                        off: tuple[float, float]) -> Image.Image:
        """Круг-«ткань» во внутренней складке локтя и колена.

        У прямого мастера внутри сгиба нет нарисованных пикселей: при сгибе
        сетка там схлопывается веером и в кадре остаётся решётка с просветами.
        Заплатка цвета ткани (медиана части у сустава) закрывает сгиб так же,
        как это делают cutout-риги в Spine.
        """
        drawn = img.copy()
        d = ImageDraw.Draw(drawn)
        part_of = {"upper_arm.l": "arm.l.up", "upper_arm.r": "arm.r.up",
                   "thigh.l": "thigh.l", "thigh.r": "thigh.r"}
        for parent, child, joint_bone in JOINTS:
            delta, rest_pivot, posed_pivot = self._part_transform(sk, child)
            # заплатку ставим туда, куда сетка РЕАЛЬНО сдвинула сустав: у мягкого
            # скиннинга это не позиция кости, а LBS-образ rest-точки
            posed_pivot = self._lbs_point(rest_pivot, sk)
            if abs(delta) < math.radians(8.0):
                continue
            color = self._joint_color(child, sk, rest_pivot)
            if color is None and part_of.get(parent) in self.parts():
                color = self._joint_color(part_of[parent], sk, rest_pivot)
            if color is None:
                continue
            w = self.sk_rest.bones[joint_bone].width * self.fit["k"]
            rad = max(w * 0.62, 3.0) * k
            cx_ = posed_pivot[0] * k + off[0]
            cy_ = posed_pivot[1] * k + off[1]
            d.ellipse([cx_ - rad, cy_ - rad, cx_ + rad, cy_ + rad],
                      fill=tuple(int(v) for v in color) + (255,))
        return drawn

    @staticmethod
    def _seal_holes(img: Image.Image, rad: int = 4) -> Image.Image:
        """Затянуть мелкие дырки, которые оставляет скиннинг в складке.

        Когда локоть или колено сгибается, пиксели у внутренней складки
        сжимаются: часть выходных пикселей «смотрит» уже за силуэт, где альфа
        нулевая, и в кадре остаётся белый клин. Дырка всегда узкая (несколько
        пикселей), а настоящий фон (между ног, вокруг фигуры) — широкий, поэтому
        морфологическое закрытие добивает только складки и не трогает контур.
        """
        a = img.getchannel("A")
        size = 2 * rad + 1
        closed = a.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))
        new = Image.fromarray(np.asarray(closed, np.uint8) - np.asarray(a, np.uint8))
        new = new.point(lambda v: 255 if v > 12 else 0)
        if not new.getbbox():
            return img
        # цвет для залитых пикселей — размытие уже нарисованного кадра
        rgb = img.convert("RGB").filter(ImageFilter.GaussianBlur(rad))
        out = img.copy()
        out.paste(rgb, (0, 0), new)
        alpha = Image.composite(closed, a, new)
        out.putalpha(alpha)
        return out


# `MeshRig` — прежнее имя основного рига (совместимость со скриптами)
MeshRig = ArtRig


if __name__ == "__main__":  # pragma: no cover — ручная проверка
    import sys

    import kit

    cid = sys.argv[1] if len(sys.argv) > 1 else "dad"
    pose = sys.argv[2] if len(sys.argv) > 2 else "idle"
    expr = sys.argv[3] if len(sys.argv) > 3 else "neutral"
    rig_ = ArtRig(kit.load_character(cid))
    sk_ = rig_.build(pose)
    frame = rig_.frame(sk_, F.Face.from_expression(expr), size=(450, 900))
    bg = Image.new("RGB", frame.size, (250, 244, 232))
    bg.paste(frame, (0, 0), frame)
    dst = os.path.join(STUDIO, "out", f"toon-{cid}-{pose}.png")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    bg.save(dst)
    print(dst)

# --------------------------------------------------------------------------- #
# адаптер к пайплайну сцен (тот же интерфейс, что у puppet.Painter)
# --------------------------------------------------------------------------- #


class ToonPainter:
    """Рендерер для `scene.py`: рисует мастера через арт-риг.

    Интерфейс повторяет `puppet.Painter` (`spec`, `build`, `frame`), поэтому
    сцены и тайминг не меняются — меняется только то, чем рисуется персонаж.

    Позиционирование как в сценах: `zoom` — рост в долях кадра, `ground` —
    линия стоп, `offset_x` — сдвиг от центра.
    """

    _cache: dict = {}

    def __init__(self, spec: dict, opts: object | None = None, *, ss: int | None = None):
        self.spec = spec
        self.opts = opts
        w = int(getattr(opts, "width", 720) or 720)
        h = int(getattr(opts, "height", 1280) or 1280)
        self.size = (w, h)
        self.zoom = float(getattr(opts, "zoom", 1.0) or 1.0)
        self.ground = float(getattr(opts, "ground", 0.93) or 0.93)
        self.offset_x = float(getattr(opts, "offset_x", 0.0) or 0.0)
        quality = str(getattr(opts, "quality", "high") or "high")
        self.ss = int(ss if ss is not None else {"preview": 1, "high": 1, "final": 2}
                      .get(quality, 1))

        char_h = max(int(h * self.zoom * 0.92), 64)
        key = (spec.get("id", "?"), char_h)
        rig = self._cache.get(key)
        if rig is None:
            rig = ArtRig(spec, work_height=char_h, ss=self.ss)
            self._cache[key] = rig
        self.rig = rig
        self.char_h = char_h

    def build(self, pose):
        return self.rig.build(pose)

    def frame(self, sk, face=None, *, face_expr: str = "neutral", size=None,
              background: str | None = None, **_ignored):
        from PIL import Image

        W, H = self.size
        rig = self.rig
        art_w = max(int(round(self.char_h * rig.work_size[0] / rig.work_size[1])), 8)
        img = rig.frame(sk, face, face_expr=face_expr, size=(art_w, self.char_h))
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cx = int(round((0.5 + self.offset_x) * W - art_w / 2))
        bottom = int(round(self.ground * H))
        canvas.alpha_composite(img, (cx, max(bottom - self.char_h, 0)))
        return canvas
