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
    "hip": ((322, 905), None),
    "spine": ((328, 800), None),
    "chest": ((330, 480), "spine"),
    "neck": ((345, 330), "chest"),
    "shoulder": ((296, 392), "chest"),
    "elbow": ((296, 640), "shoulder"),
    "wrist": ((348, 862), "elbow"),
    "knee": ((332, 1120), "hip"),
    "ankle": ((348, 1305), "knee"),
}

SIDE_HEAD = [(0.390, 0.030), (0.545, 0.018), (0.650, 0.043), (0.685, 0.128),
             (0.660, 0.193), (0.610, 0.229), (0.560, 0.253), (0.440, 0.257),
             (0.385, 0.236), (0.352, 0.179), (0.355, 0.093)]
SIDE_TORSO = [(0.312, 0.300), (0.390, 0.240), (0.545, 0.236), (0.677, 0.273),
              (0.712, 0.357), (0.705, 0.500), (0.677, 0.632), (0.470, 0.642),
              (0.335, 0.629), (0.302, 0.500), (0.297, 0.371)]
SIDE_HAND = [(0.430, 0.593), (0.535, 0.589), (0.553, 0.643), (0.523, 0.694),
             (0.449, 0.698), (0.419, 0.647)]
SIDE_FOOT = [(0.386, 0.938), (0.560, 0.930), (0.650, 0.940), (0.662, 0.958),
             (0.646, 0.978), (0.560, 0.988), (0.420, 0.992), (0.386, 0.972)]


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
        # Дальняя нога — копия ближней, затемнённая. Она ниже всех: под торсом.
        "far_thigh": {"from": "thigh", "joint": "hip_far",
                      "z": 1, "dark": 0.24, "dx": -8},
        "far_shin": {"from": "shin", "joint": "knee_far",
                     "z": 2, "dark": 0.24, "dx": -6},
        "far_foot": {"from": "foot", "joint": "ankle_far",
                     "z": 2, "dark": 0.24, "dx": -6},
        # Ноги ПОД торсом: свитер закрывает верх джинсов, как на рисунке.
        "thigh": {"shape": {"band": [0.600, 0.820],
                             "disc_at": list(J["hip"]), "disc_r": 62},
                   "joint": "hip", "z": 3},
        "shin": {"shape": {"band": [0.780, 0.945],
                            "disc_at": list(J["knee"]), "disc_r": 50},
                  "joint": "knee", "z": 4},
        # Стопа — отдельная часть на шарнире стопы: на опоре её можно держать
        # плоской, а не тащить за голенью.
        "foot": {"shape": {"band": [0.936, 1.0],
                            "disc_at": list(J["ankle"]), "disc_r": 40},
                  "joint": "ankle", "z": 4},
        "torso": {"shape": SIDE_TORSO, "joint": "spine", "z": 6},
        "head": {"shape": SIDE_HEAD, "joint": "neck", "z": 7},
        "near_arm_up": {"shape": cap(J["shoulder"], J["elbow"], 60, 54),
                        "joint": "shoulder", "z": 8},
        "near_arm_fo": {"shape": cap(J["elbow"], J["wrist"], 50), "joint": "elbow",
                        "z": 9, "extra": [SIDE_HAND]},
    }
    # Заплатки на шарнирах: при повороте на сгибе открывается щель между
    # капсулами. Кружок, вырезанный вокруг самого сустава, её закрывает.
    # Заплатки больше не нужны: части ног вырезаны по самому силуэту и
    # перекрываются по высоте на ~25 px, поэтому на сгибе не расходится.
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


# --------------------------------------------------------------------------- #
# профиль-«шаг»: ноги разведены, поэтому каждая вырезается отдельно
# --------------------------------------------------------------------------- #
# Замеры по master-side-spread.png (ноги расходятся от паха на y≈1010).
SPREAD_J = {
    "hip": ((392, 975), None),
    "spine": ((360, 880), None),
    "chest": ((352, 500), "spine"),
    "neck": ((352, 330), "chest"),
    "shoulder": ((300, 392), "chest"),
    "elbow": ((300, 640), "shoulder"),
    "wrist": ((350, 862), "elbow"),
    "hip_near": ((430, 985), None),
    "knee_near": ((516, 1150), "hip_near"),
    "ankle_near": ((575, 1270), "knee_near"),
    "hip_far": ((352, 985), None),
    "knee_far": ((228, 1130), "hip_far"),
    "ankle_far": ((160, 1272), "knee_far"),
}

SPREAD_HEAD = [(0.380, 0.030), (0.545, 0.018), (0.650, 0.043), (0.685, 0.128),
               (0.660, 0.193), (0.610, 0.229), (0.560, 0.253), (0.440, 0.257),
               (0.385, 0.236), (0.352, 0.179), (0.355, 0.093)]
SPREAD_TORSO = [(0.320, 0.300), (0.400, 0.240), (0.545, 0.236), (0.677, 0.273),
                (0.712, 0.357), (0.705, 0.500), (0.680, 0.632), (0.500, 0.700),
                (0.360, 0.700), (0.310, 0.560), (0.300, 0.400)]
SPREAD_HAND = [(0.440, 0.596), (0.545, 0.592), (0.562, 0.646), (0.532, 0.697),
               (0.458, 0.700), (0.428, 0.650)]


def _leg(hip, knee, ankle, foot_box, z):
    """Нога: бедро, голень и стопа отдельными частями с кругами на сгибах."""
    return {
        "thigh": {"shape": {"capsule": [list(hip), list(knee),
                                        foot_box[0] // 2 + 40,
                                        foot_box[0] // 2 + 30],
                            "disc_at": list(hip), "disc_r": 62},
                  "joint": "hip", "z": z},
        "shin": {"shape": {"capsule": [list(knee), list(ankle), 52, 44],
                           "disc_at": list(knee), "disc_r": 48},
                 "joint": "knee", "z": z + 1},
        "foot": {"shape": {"poly": foot_box[1], "disc_at": list(ankle),
                           "disc_r": 38},
                 "joint": "ankle", "z": z + 2},
    }


# Край свитера: он не должен поворачиваться вместе с бедром, иначе между
# ног уезжает тёмный клин.
CROTCH = [(0.440, 0.690), (0.600, 0.690), (0.596, 0.726),
          (0.520, 0.716), (0.470, 0.724)]


def spread_spec() -> dict:
    J = {k: v[0] for k, v in SPREAD_J.items()}
    joints = {k: {"pos": list(v[0]), "parent": v[1]} for k, v in SPREAD_J.items()}
    foot_near = [(0.672, 0.908), (0.965, 0.918), (0.975, 0.952),
                 (0.800, 0.972), (0.680, 0.972)]
    foot_far = [(0.075, 0.918), (0.300, 0.912), (0.318, 0.948),
                (0.230, 0.968), (0.080, 0.962)]
    parts = {
        # дальняя нога — своя геометрия, а не затемнённая копия
        "far_thigh": {"shape": {"capsule": [list(J["hip_far"]), list(J["knee_far"]), 78, 66],
                                "disc_at": list(J["hip_far"]), "disc_r": 62},
                      "joint": "hip_far", "z": 1, "dark": 0.20},
        "far_shin": {"shape": {"capsule": [list(J["knee_far"]), list(J["ankle_far"]), 52, 44],
                               "disc_at": list(J["knee_far"]), "disc_r": 48},
                     "joint": "knee_far", "z": 2, "dark": 0.20},
        "far_foot": {"shape": {"poly": foot_far, "disc_at": list(J["ankle_far"]),
                               "disc_r": 38},
                     "joint": "ankle_far", "z": 3, "dark": 0.20},
        "near_thigh": {"shape": {"capsule": [list(J["hip_near"]), list(J["knee_near"]), 78, 66],
                                 "disc_at": list(J["hip_near"]), "disc_r": 62},
                       "joint": "hip_near", "z": 4},
        "near_shin": {"shape": {"capsule": [list(J["knee_near"]), list(J["ankle_near"]), 52, 44],
                                "disc_at": list(J["knee_near"]), "disc_r": 48},
                      "joint": "knee_near", "z": 5},
        "near_foot": {"shape": {"poly": foot_near, "disc_at": list(J["ankle_near"]),
                                "disc_r": 38},
                      "joint": "ankle_near", "z": 6},
        "torso": {"shape": SPREAD_TORSO, "joint": "spine", "z": 8},
        "head": {"shape": SPREAD_HEAD, "joint": "neck", "z": 9},
        "arm_up": {"shape": {"capsule": [list(J["shoulder"]), list(J["elbow"]), 62, 54],
                             "disc_at": list(J["shoulder"]), "disc_r": 56},
                   "joint": "shoulder", "z": 10},
        "arm_fo": {"shape": {"capsule": [list(J["elbow"]), list(J["wrist"]), 50, 46],
                             "extra": [SPREAD_HAND]},
                   "joint": "elbow", "z": 11},
    }
    return {"frame": [W, H], "anchor": [J["hip"][0] / W, J["hip"][1] / H],
            "joints": norm(joints), "parts": parts}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    d = ROOT / "studio" / "2p5d" / key
    for view, fn in (("side", side_spec), ("front", front_spec),
                     ("stride", spread_spec)):
        out = d / f"rig-{view}.json"
        out.write_text(json.dumps(fn(), ensure_ascii=False, indent=1))
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
