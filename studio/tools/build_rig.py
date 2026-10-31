"""Собрать скелеты персонажа из замеров рисунка: профиль и фронт.

    python studio/tools/build_rig.py dad

Скелеты лежат в `studio/2p5d/<char>/rig-<вид>.json`. Части тела описаны
капсулами (отрезок + радиус): у капсулы круглый конец, поэтому при повороте
вокруг шарнира стык остаётся закрытым, а не даёт «ступеньку».

Почему два скелета разные
------------------------
Профиль: видна одна рука и одна нога, вторая рисуется копией с затемнением.
Фронт: в рисунке есть ОБЕ руки и ОБЕ ноги, поэтому каждая режется отдельно —
это точнее, чем затемнённая копия.

Принцип вырезания: торс остаётся целым, руки рисуются ПОВЕРХ него. Тогда при
подъёме руки из-под неё открывается не дыра, а сам торс — как в cutout-риге
у South Park.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
W, H = 768, 1400


def cap(a, b, r, r2=None):
    return {"capsule": [list(a), list(b), r] + ([r2] if r2 else [])}


def norm(joints: dict) -> dict:
    """Позиции шарниров — в долях кадра, чтобы риг не зависел от размера."""
    out = {}
    for k, v in joints.items():
        out[k] = {"pos": [v["pos"][0] / W, v["pos"][1] / H], "parent": v["parent"]}
    return out


# --------------------------------------------------------------------------- #
# профиль
# --------------------------------------------------------------------------- #
SIDE_J = {
    "hip": ((322, 819), None),
    "spine": ((328, 760), None),
    "chest": ((330, 470), "spine"),
    "neck": ((345, 330), "chest"),
    "shoulder": ((296, 392), "chest"),
    "elbow": ((296, 640), "shoulder"),
    "wrist": ((348, 862), "elbow"),
    "knee": ((322, 1106), "hip"),
    "ankle": ((340, 1300), "knee"),
}

SIDE_HEAD = [(0.390, 0.030), (0.545, 0.018), (0.650, 0.043), (0.685, 0.128),
             (0.660, 0.193), (0.610, 0.229), (0.560, 0.253), (0.440, 0.257),
             (0.385, 0.236), (0.352, 0.179), (0.355, 0.093)]
SIDE_TORSO = [(0.312, 0.300), (0.390, 0.240), (0.545, 0.236), (0.677, 0.273),
              (0.712, 0.357), (0.705, 0.500), (0.677, 0.632), (0.470, 0.642),
              (0.335, 0.629), (0.302, 0.500), (0.297, 0.371)]
SIDE_HAND = [(0.430, 0.593), (0.535, 0.589), (0.553, 0.643), (0.523, 0.694),
             (0.449, 0.698), (0.419, 0.647)]
SIDE_FOOT = [(0.390, 0.950), (0.612, 0.944), (0.671, 0.957), (0.677, 0.973),
             (0.651, 0.987), (0.430, 0.993), (0.388, 0.979)]


def side_spec() -> dict:
    J = {k: v[0] for k, v in SIDE_J.items()}
    joints = {k: {"pos": list(v[0]), "parent": v[1]} for k, v in SIDE_J.items()}
    # дальняя сторона: отдельные ветки, иначе поворот ближней руки тянет дальнюю
    for extra, parent in (("hip_far", None), ("spine_far", "hip_far"),
                          ("chest_far", "spine_far"), ("shoulder_far", "chest_far"),
                          ("elbow_far", "shoulder_far"), ("wrist_far", "elbow_far"),
                          ("knee_far", "hip_far"), ("ankle_far", "knee_far")):
        src = extra.replace("_far", "")
        joints[extra] = {"pos": list(J[src]), "parent": parent}

    parts = {
        "far_arm_up": {"from": "near_arm_up", "joint": "shoulder_far",
                       "z": 0, "dark": 0.26, "dx": -10},
        "far_arm_fo": {"from": "near_arm_fo", "joint": "elbow_far",
                       "z": 1, "dark": 0.26, "dx": -10},
        "far_thigh": {"from": "thigh", "joint": "hip_far",
                      "z": 2, "dark": 0.22, "dx": -8},
        "far_shin": {"from": "shin", "joint": "knee_far",
                     "z": 3, "dark": 0.22, "dx": -6},
        "torso": {"shape": SIDE_TORSO, "joint": "spine", "z": 4},
        "head": {"shape": SIDE_HEAD, "joint": "neck", "z": 5},
        "thigh": {"shape": cap(J["hip"], J["knee"], 96, 70), "joint": "hip", "z": 6},
        "shin": {"shape": cap(J["knee"], J["ankle"], 62, 58), "joint": "knee",
                 "z": 7, "extra": [SIDE_FOOT]},
        "near_arm_up": {"shape": cap(J["shoulder"], J["elbow"], 60, 54),
                        "joint": "shoulder", "z": 8},
        "near_arm_fo": {"shape": cap(J["elbow"], J["wrist"], 50), "joint": "elbow",
                        "z": 9, "extra": [SIDE_HAND]},
    }
    return {"frame": [W, H], "anchor": [J["hip"][0] / W, J["hip"][1] / H],
            "joints": norm(joints), "parts": parts}


# --------------------------------------------------------------------------- #
# фронт
# --------------------------------------------------------------------------- #
FRONT_J = {
    "hip": ((385, 980), None),
    "spine": ((385, 800), None),
    "chest": ((385, 520), "spine"),
    "neck": ((385, 320), "chest"),
    "shoulder_l": ((255, 420), "chest"),
    "elbow_l": ((100, 730), "shoulder_l"),
    "wrist_l": ((48, 878), "elbow_l"),
    "shoulder_r": ((515, 420), "chest"),
    "elbow_r": ((670, 730), "shoulder_r"),
    "wrist_r": ((722, 878), "elbow_r"),
    "hip_l": ((300, 985), "hip"),
    "knee_l": ((288, 1160), "hip_l"),
    "ankle_l": ((292, 1315), "knee_l"),
    "hip_r": ((470, 985), "hip"),
    "knee_r": ((472, 1160), "hip_r"),
    "ankle_r": ((482, 1315), "knee_r"),
}

FRONT_HEAD = [(0.335, 0.030), (0.400, 0.008), (0.560, 0.008), (0.665, 0.040),
              (0.672, 0.150), (0.628, 0.215), (0.560, 0.242), (0.505, 0.248),
              (0.495, 0.265), (0.400, 0.265), (0.390, 0.242), (0.330, 0.212),
              (0.322, 0.130)]
FRONT_TORSO = [(0.318, 0.250), (0.420, 0.230), (0.500, 0.230), (0.610, 0.240),
               (0.700, 0.278), (0.732, 0.360), (0.730, 0.500), (0.720, 0.640),
               (0.700, 0.700), (0.560, 0.712), (0.480, 0.700), (0.390, 0.712),
               (0.290, 0.700), (0.272, 0.640), (0.270, 0.500), (0.272, 0.360)]
FRONT_HAND_L = [(0.010, 0.598), (0.098, 0.596), (0.118, 0.650), (0.095, 0.700),
                (0.030, 0.700), (0.012, 0.660)]
FRONT_HAND_R = [(0.902, 0.598), (0.990, 0.598), (0.988, 0.660), (0.968, 0.700),
                (0.902, 0.700), (0.880, 0.650)]
# Середина груди: её рука не должна утаскивать (см. subtract у рук).
FRONT_CORE = [(0.30, 0.24), (0.70, 0.24), (0.70, 0.73), (0.30, 0.73)]

FRONT_FOOT_L = [(0.292, 0.940), (0.412, 0.940), (0.418, 0.992), (0.295, 0.992)]
FRONT_FOOT_R = [(0.588, 0.940), (0.708, 0.940), (0.705, 0.992), (0.582, 0.992)]


def front_spec() -> dict:
    J = {k: v[0] for k, v in FRONT_J.items()}
    joints = {k: {"pos": list(v[0]), "parent": v[1]} for k, v in FRONT_J.items()}
    parts = {
        # ноги — под торсом, руки — поверх, голова — сверху
        "thigh_l": {"shape": cap(J["hip_l"], J["knee_l"], 74, 60),
                    "joint": "hip_l", "z": 1},
        "shin_l": {"shape": cap(J["knee_l"], J["ankle_l"], 58, 46),
                   "joint": "knee_l", "z": 2, "extra": [FRONT_FOOT_L]},
        "thigh_r": {"shape": cap(J["hip_r"], J["knee_r"], 74, 60),
                    "joint": "hip_r", "z": 1},
        "shin_r": {"shape": cap(J["knee_r"], J["ankle_r"], 58, 46),
                   "joint": "knee_r", "z": 2, "extra": [FRONT_FOOT_R]},
        "torso": {"shape": FRONT_TORSO, "joint": "spine", "z": 3},
        "head": {"shape": FRONT_HEAD, "joint": "neck", "z": 6},
        # Рука = капсула МИНУС торс (иначе при подъёме уезжает кусок груди)
        # ПЛЮС круг на плече: он закрывает стык, когда рука повёрнута.
        "arm_up_l": {"shape": cap(J["shoulder_l"], J["elbow_l"], 92, 58),
                     "joint": "shoulder_l", "z": 4,
                     "subtract": [FRONT_CORE],
                     "extra": [{"disc": [list(J["shoulder_l"]), 72]}]},
        "arm_fo_l": {"shape": cap(J["elbow_l"], J["wrist_l"], 56, 34),
                     "joint": "elbow_l", "z": 5, "extra": [FRONT_HAND_L],
                     "subtract": [FRONT_TORSO]},
        "arm_up_r": {"shape": cap(J["shoulder_r"], J["elbow_r"], 92, 58),
                     "joint": "shoulder_r", "z": 4,
                     "subtract": [FRONT_CORE],
                     "extra": [{"disc": [list(J["shoulder_r"]), 72]}]},
        "arm_fo_r": {"shape": cap(J["elbow_r"], J["wrist_r"], 56, 34),
                     "joint": "elbow_r", "z": 5, "extra": [FRONT_HAND_R],
                     "subtract": [FRONT_TORSO]},
    }
    return {"frame": [W, H], "anchor": [J["hip"][0] / W, J["hip"][1] / H],
            "joints": norm(joints), "parts": parts}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    d = ROOT / "studio" / "2p5d" / key
    for view, fn in (("side", side_spec), ("front", front_spec)):
        out = d / f"rig-{view}.json"
        out.write_text(json.dumps(fn(), ensure_ascii=False, indent=1))
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
