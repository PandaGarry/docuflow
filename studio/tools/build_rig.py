"""Собрать скелет профиля из долей и замеров рисунка.

    python studio/tools/build_rig.py dad

Скелет хранится в `studio/2p5d/<char>/rig-side.json`. Части тела описаны
не полигонами «на глаз», а капсулами (отрезок + радиус): у капсулы круглый
конец, поэтому при повороте вокруг шарнира стык остаётся закрытым.

Дальние рука и нога не рисуются отдельно: в профильном рисунке второй пары
просто нет. Они берутся копией ближних частей, затемняются и кладутся под
торс — так делает любая cutout-анимация.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
W, H = 768, 1400

# Шарниры: пиксели рисунка. Значения пришли из замеров силуэта.
J = {
    "hip": (322, 819),
    "spine": (328, 760),
    "chest": (330, 470),
    "neck": (345, 330),
    "shoulder": (296, 392),
    "elbow": (296, 640),
    "wrist": (348, 862),
    "knee": (322, 1106),
    "ankle": (340, 1300),
}

# Полигоны по долям кадра — только там, где форма сложная (голова, торс).
HEAD = [(0.390, 0.030), (0.545, 0.018), (0.650, 0.043), (0.685, 0.128),
        (0.660, 0.193), (0.610, 0.229), (0.560, 0.253), (0.440, 0.257),
        (0.385, 0.236), (0.352, 0.179), (0.355, 0.093)]
TORSO = [(0.312, 0.300), (0.390, 0.240), (0.545, 0.236), (0.677, 0.273),
         (0.712, 0.357), (0.705, 0.500), (0.677, 0.632), (0.470, 0.642),
         (0.335, 0.629), (0.302, 0.500), (0.297, 0.371)]
HAND = [(0.430, 0.593), (0.535, 0.589), (0.553, 0.643), (0.523, 0.694),
        (0.449, 0.698), (0.419, 0.647)]
FOOT = [(0.390, 0.950), (0.612, 0.944), (0.671, 0.957), (0.677, 0.973),
        (0.651, 0.987), (0.430, 0.993), (0.388, 0.979)]


def cap(a, b, r, r2=None):
    return {"capsule": [list(a), list(b), r] + ([r2] if r2 else [])}


def spec() -> dict:
    joints = {
        "hip": {"pos": list(J["hip"]), "parent": None},
        "spine": {"pos": list(J["spine"]), "parent": None},
        "chest": {"pos": list(J["chest"]), "parent": "spine"},
        "neck": {"pos": list(J["neck"]), "parent": "chest"},
        "shoulder": {"pos": list(J["shoulder"]), "parent": "chest"},
        "elbow": {"pos": list(J["elbow"]), "parent": "shoulder"},
        "wrist": {"pos": list(J["wrist"]), "parent": "elbow"},
        "knee": {"pos": list(J["knee"]), "parent": "hip"},
        "ankle": {"pos": list(J["ankle"]), "parent": "knee"},
    }
    # Дальняя сторона: отдельные ветки, иначе поворот ближней руки тянет дальнюю.
    joints["hip_far"] = {"pos": list(J["hip"]), "parent": None}
    joints["spine_far"] = {"pos": list(J["spine"]), "parent": "hip_far"}
    joints["chest_far"] = {"pos": list(J["chest"]), "parent": "spine_far"}
    joints["shoulder_far"] = {"pos": list(J["shoulder"]), "parent": "chest_far"}
    joints["elbow_far"] = {"pos": list(J["elbow"]), "parent": "shoulder_far"}
    joints["wrist_far"] = {"pos": list(J["wrist"]), "parent": "elbow_far"}
    joints["knee_far"] = {"pos": list(J["knee"]), "parent": "hip_far"}
    joints["ankle_far"] = {"pos": list(J["ankle"]), "parent": "knee_far"}
    # В файле позиции хранятся в долях кадра — так риг не зависит от размера.
    for j in joints.values():
        j["pos"] = [j["pos"][0] / W, j["pos"][1] / H]

    arm_up = cap(J["shoulder"], J["elbow"], 60, 54)
    arm_fo = cap(J["elbow"], J["wrist"], 50)
    thigh = cap(J["hip"], J["knee"], 96, 70)
    shin = cap(J["knee"], J["ankle"], 62, 58)

    parts = {
        # дальняя сторона — копии ближних, затемнённые, под торсом
        "far_arm_up": {"from": "near_arm_up", "joint": "shoulder_far",
                       "z": 0, "dark": 0.26, "dx": -10},
        "far_arm_fo": {"from": "near_arm_fo", "joint": "elbow_far",
                       "z": 1, "dark": 0.26, "dx": -10},
        "far_thigh": {"from": "thigh", "joint": "hip_far",
                      "z": 2, "dark": 0.22, "dx": -8},
        "far_shin": {"from": "shin", "joint": "knee_far",
                     "z": 3, "dark": 0.22, "dx": -6},
        # Торс БЕЗ выреза под руку: если вырезать и заделать дыру инпейнтом,
        # при взмахе на месте руки видно светлое пятно. Пусть торс остаётся
        # целым, а рука рисуется поверх — это обычная практика cutout-рига.
        "torso": {"shape": TORSO, "joint": "spine", "z": 4},
        "head": {"shape": HEAD, "joint": "neck", "z": 5},
        "thigh": {"shape": thigh, "joint": "hip", "z": 6},
        "shin": {"shape": shin, "joint": "knee", "z": 7, "extra": [FOOT]},
        "near_arm_up": {"shape": arm_up, "joint": "shoulder", "z": 8},
        "near_arm_fo": {"shape": arm_fo, "joint": "elbow", "z": 9,
                        "extra": [HAND]},
    }
    return {"frame": [W, H], "anchor": [J["hip"][0] / W, J["hip"][1] / H],
            "joints": joints, "parts": parts}


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    out = ROOT / "studio/2p5d" / key / "rig-side.json"
    out.write_text(json.dumps(spec(), ensure_ascii=False, indent=1))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
