"""Персонаж как объект: скелет + геометрия, собираемая В ПОЗЕ.

Почему геометрия собирается заново, а не деформируется скинами
---------------------------------------------------------------
В песочнице нет Blender, поэтому веса и деформации пришлось решать самим.
Опыт показал: линейное смешивание костей на «наборе капсул» даёт классические
артефакты — сминание в локте, провал в плече, «фантик» на скрутке.

Здесь гибрид, который для стилизованного персонажа надёжнее:

* **Конечности строятся заново каждый кадр** как гладкая труба по ломаной
  «плечо → локоть → запястье» (сплайн Катмулла–Рома). Сгиб локтя получается
  дугой, объём сохраняется, шва нет вообще.
* **Торс** — одна оболочка, деформируется линейным смешиванием по 4 костям
  позвоночника (глубоких сгибов там нет, артефактов не возникает).
* **Голова, кисти, стопы** — жёсткие тела на своей кости. Это и анатомически
  верно: череп не гнётся.

Такая схема даёт непрерывную поверхность без «разрывов на шарнирах» при любой
позе и стоит дешево: пересборка всего персонажа ≈ 60 мс.
"""

from __future__ import annotations

import math

import numpy as np

import body3d as B
import render3d as R3
import rig3d as RIG


# --------------------------------------------------------------------------- #
# вспомогательное
# --------------------------------------------------------------------------- #

def smooth_path(points, radii, per_seg: int = 6):
    """Сгладить ломаную (Катмулл–Ром) и получить плотный набор точек+радиусов.

    Нужно, чтобы сгиб локтя/колена был дугой, а не «шарниром из двух труб».
    """
    pts = np.asarray(points, np.float64)
    rad = np.asarray(radii, np.float64)
    if len(pts) < 3:
        return pts, rad
    ext = np.vstack([pts[0] + (pts[0] - pts[1]), pts, pts[-1] + (pts[-1] - pts[-2])])
    ext_r = np.concatenate([rad[:1], rad, rad[-1:]])
    out_p, out_r = [], []
    for i in range(len(pts) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        r0, r1, r2, r3 = ext_r[i], ext_r[i + 1], ext_r[i + 2], ext_r[i + 3]
        ts = np.linspace(0, 1, per_seg, endpoint=(i == len(pts) - 2))
        for t in ts:
            t2, t3 = t * t, t * t * t
            p = 0.5 * ((2 * p1) + (-p0 + p2) * t +
                       (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
                       (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            r = 0.5 * ((2 * r1) + (-r0 + r2) * t +
                       (2 * r0 - 5 * r1 + 4 * r2 - r3) * t2 +
                       (-r0 + 3 * r1 - 3 * r2 + r3) * t3)
            out_p.append(p)
            out_r.append(max(float(r), 1e-4))
    return np.array(out_p), np.array(out_r)


def rigid(mesh: R3.Mesh, rest_head, posed_head, rot) -> R3.Mesh:
    """Жёстко перенести меш из позы покоя в позу: v' = R·(v − rest) + posed."""
    m = R3.Mesh(mesh.verts, mesh.tris, mesh.normals, mesh.color, mesh.ao,
                mesh.rough, mesh.cull, mesh.name)
    m.verts = (np.asarray(rot, np.float64) @
               (mesh.verts - np.asarray(rest_head, np.float64)).T).T + np.asarray(
        posed_head, np.float64)
    m.normals = mesh.normals @ np.asarray(rot, np.float64).T
    return m


def _seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    denom = float(ab @ ab)
    if denom < 1e-12:
        return np.linalg.norm(p - a, axis=1)
    t = np.clip(((p - a) @ ab) / denom, 0.0, 1.0)
    proj = a + t[:, None] * ab
    return np.linalg.norm(p - proj, axis=1)


def skin_weights(verts: np.ndarray, skel: "RIG.Skeleton", names: list[str],
                 power: float = 2.6, topk: int = 3) -> tuple[np.ndarray, list[str]]:
    """Веса привязки вершины к костям: обратные расстояния, нормированные.

    Ограничение `topk` обязательно: иначе дальние кости «тянут» вершину и на
    сгибах появляется «резина».
    """
    d = np.stack([_seg_dist(verts, skel.bones[n].head, skel.bones[n].tail)
                  for n in names], axis=1)
    w = 1.0 / np.power(d + 1e-3, power)
    if topk < len(names):
        cut = np.partition(w, -topk, axis=1)[:, -topk][:, None]
        w = np.where(w >= cut, w, 0.0)
    w /= np.maximum(w.sum(axis=1, keepdims=True), 1e-12)
    return w, names


def apply_skin(mesh: R3.Mesh, skel: "RIG.Skeleton", fk: dict,
               weights: np.ndarray, names: list[str]) -> R3.Mesh:
    """Линейное смешивание: v' = Σ w_b · (R_b·(v − head_rest_b) + head_pose_b)."""
    v = mesh.verts
    out = np.zeros_like(v)
    nm = np.zeros_like(mesh.normals)
    for j, name in enumerate(names):
        w = weights[:, j]
        nz = w > 1e-5
        if not nz.any():
            continue
        rest = skel.bones[name].head
        posed = fk[name]["head"]
        rot = fk[name]["rot"]
        out[nz] += (w[nz, None] * ((v[nz] - rest) @ rot.T + posed))
        nm[nz] += w[nz, None] * (mesh.normals[nz] @ rot.T)
    m = R3.Mesh(v, mesh.tris, mesh.normals, mesh.color, mesh.ao, mesh.rough,
                mesh.cull, mesh.name)
    ln = np.linalg.norm(nm, axis=1, keepdims=True)
    m.verts = out
    m.normals = nm / np.maximum(ln, 1e-9)
    return m


# --------------------------------------------------------------------------- #
# персонаж
# --------------------------------------------------------------------------- #

DEFAULT_COLORS = dict(
    skin=(0.86, 0.62, 0.50),
    top=(0.72, 0.73, 0.74),
    bottom=(0.22, 0.26, 0.34),
    shoes=(0.18, 0.14, 0.12),
    hair=(0.20, 0.14, 0.10),
)


class Character:
    """Персонаж: пропорции + скелет + сборка геометрии на любую позу."""

    def __init__(self, p: B.Proportions | None = None, colors: dict | None = None,
                 eyes: bool = True):
        self.p = p or B.Proportions()
        self.colors = dict(DEFAULT_COLORS)
        if colors:
            self.colors.update(colors)
        self.colors["top_dark"] = tuple(c * 0.72 for c in self.colors["top"])
        self.eyes = eyes
        self.skel = RIG.Skeleton.from_proportions(self.p)

        # статичные (не зависящие от позы) оболочки строим один раз
        self.head = B.head_parts(self.p, self.colors, eyes=eyes)
        self.torso = B.torso_parts(self.p, self.colors)
        self.torso_w = [skin_weights(m.verts, self.skel,
                                     ["pelvis", "spine", "chest", "neck"],
                                     power=2.2, topk=3) for m in self.torso]
        self.rest_joints = self._joints(RIG.forward_kinematics(self.skel, RIG.Pose()))
        self._limb_cache: dict[tuple, list[R3.Mesh]] = {}

    # ------------------------------------------------------------------ #
    def _joints(self, fk: dict) -> dict:
        j = {}
        for side in ("L", "R"):
            j[f"shoulder.{side}"] = fk[f"upperarm.{side}"]["head"]
            j[f"elbow.{side}"] = fk[f"forearm.{side}"]["head"]
            j[f"wrist.{side}"] = fk[f"hand.{side}"]["head"]
            j[f"hand_end.{side}"] = fk[f"hand.{side}"]["tail"]
            j[f"hip.{side}"] = fk[f"thigh.{side}"]["head"]
            j[f"knee.{side}"] = fk[f"shin.{side}"]["head"]
            j[f"ankle.{side}"] = fk[f"foot.{side}"]["head"]
            j[f"toe.{side}"] = fk[f"toe.{side}"]["head"]
            j[f"toe_end.{side}"] = fk[f"toe.{side}"]["tail"]
        j["neck_a"] = fk["chest"]["tail"]
        j["neck_b"] = fk["head"]["head"]
        return j

    def _rots(self, fk: dict) -> dict:
        return {side: {"hand": fk[f"hand.{side}"]["rot"],
                       "foot": fk[f"foot.{side}"]["rot"]} for side in ("L", "R")}

    # ------------------------------------------------------------------ #
    def build(self, pose: RIG.Pose | None = None) -> list[R3.Mesh]:
        """Собрать все меши персонажа в заданной позе."""
        pose = pose or RIG.Pose()
        fk = RIG.forward_kinematics(self.skel, pose)
        joints = self._joints(fk)
        rots = self._rots(fk)
        out: list[R3.Mesh] = []

        # торс — скиннинг
        for m, w in zip(self.torso, self.torso_w):
            out.append(apply_skin(m, self.skel, fk, *w))

        # конечности — пересборка по позе
        out += B.limb_parts(self.p, self.colors, joints, rots)

        # голова — жёстко на кости головы
        rest_head = self.skel.bones["head"].head
        posed_head = fk["head"]["head"]
        rot = fk["head"]["rot"]
        for m in self.head:
            out.append(rigid(m, rest_head, posed_head, rot))

        # шея — труба между торсом и затылком (живая, без разрыва)
        out.append(self._neck(joints))

        for m in out:
            if m.name == "":
                m.name = "part"
        return out

    # ------------------------------------------------------------------ #
    def _neck(self, joints: dict) -> R3.Mesh:
        p = self.p
        H = p.height
        a = np.asarray(joints["neck_a"], np.float64)
        b = np.asarray(joints["neck_b"], np.float64)
        mid = (a + b) * 0.5
        m = R3.tube([a - (b - a) * 0.10, mid, b + (b - a) * 0.35],
                    [0.056 * H * p.bulk, 0.048 * H * p.bulk, 0.044 * H * p.bulk],
                    seg=24)
        m.color = np.asarray(self.colors["skin"], np.float64)
        m.name = "neck"
        return m
