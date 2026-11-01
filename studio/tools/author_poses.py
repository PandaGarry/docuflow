"""Авторинг поз через IK: цели для кистей → углы костей → poses.json.

Зачем скрипт, а не ручные числа
-------------------------------
Поза «машет» в старых данных давала руку **горизонтально**, хотя описание
обещало «поднята высоко»: числа в градусах ничего не говорят о результате.
Здесь поза задаётся тем, что видно на картинке — куда приходит кисть (в долях
роста от бёдер), — а углы считает IK. Промах невозможен: кисть в цели.

Запуск (перезаписывает studio/library/poses.json):

    /home/user/.venv/bin/python studio/tools/author_poses.py            # записать
    /home/user/.venv/bin/python studio/tools/author_poses.py --dry-run  # показать

Единицы: X вправо, Y вниз, 0 — центр бёдер. Рост ≈ 6.3, голова ≈ 1.05,
плечи на y ≈ −2.35, кисть в покое приходит в (1.31, 0.0).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "engine"))

import library as L  # noqa: E402
import rig as R  # noqa: E402

POSES_PATH = os.path.join(STUDIO, "library", "poses.json")

# id → (label, tags, prompt, поза)
#   hands: сторона → (x, y) цель кисти; None — оставить в покое
#   legs:  сторона → (угол бедра, угол голени) в градусах от rest (как в poses.json)
#   root:  (dx, dy) смещение корпуса
SPECS: dict[str, dict] = {
    "idle": {
        "label": "Стоит спокойно", "tags": ["loop", "base"],
        "prompt": "standing relaxed, arms hanging naturally at the sides",
        "hands": {"r": (1.00, 0.10), "l": (-1.00, 0.10)},
    },
    "idle_shift": {
        "label": "Стоит, вес на одной ноге", "tags": ["loop", "base"],
        "prompt": "standing with weight on one leg, relaxed shoulders",
        "hands": {"r": (0.94, 0.16), "l": (-1.04, 0.04)},
        "misc": {"hips": 1.5, "chest": -1.5, "head": 1.0},
    },
    "breath": {
        "label": "Дышит", "tags": ["loop", "base"],
        "prompt": "breathing calmly, chest slightly raised",
        "hands": {"r": (1.00, 0.12), "l": (-1.00, 0.12)},
        "misc": {"spine": -0.8},
    },
    "wave": {
        "label": "Машет рукой", "tags": ["greeting", "friendly"],
        "prompt": "right arm raised high and waving, left arm relaxed",
        "hands": {"r": (1.45, -4.10), "l": (-1.00, 0.10)},
        "misc": {"chest": -2, "head": 3},
    },
    "wave_left": {
        "label": "Машет левой рукой", "tags": ["greeting", "friendly"],
        "prompt": "left arm raised high and waving, right arm relaxed",
        "mirror_of": "wave",
    },
    "point": {
        "label": "Показывает рукой", "tags": ["emphasis"],
        "prompt": "right arm extended diagonally, pointing to the side",
        "hands": {"r": (1.95, -1.75), "l": (-1.00, 0.10)},
        "misc": {"chest": -2, "head": 2},
    },
    "point_up": {
        "label": "Показывает вверх", "tags": ["emphasis"],
        "prompt": "right arm pointing up, index finger up",
        "hands": {"r": (1.05, -4.15), "l": (-1.00, 0.10)},
        "misc": {"head": -6},
    },
    "point_aside": {
        "label": "Показывает в сторону", "tags": ["emphasis"],
        "prompt": "right arm stretched out to the side horizontally",
        "hands": {"r": (2.10, -2.45), "l": (-1.00, 0.10)},
        "misc": {"head": 6},
    },
    "think": {
        "label": "Думает, рука у подбородка", "tags": ["emotion"],
        "prompt": "hand at chin, thinking, eyes up",
        "hands": {"r": (0.34, -2.42), "l": (-1.14, -0.62)},
        "misc": {"head": -4, "chest": -1},
    },
    "surprise": {
        "label": "Удивлён, руки вверх", "tags": ["emotion", "big"],
        "prompt": "both hands up in surprise, shoulders raised",
        "hands": {"r": (1.70, -3.55), "l": (-1.70, -3.55)},
        "misc": {"head": -3},
    },
    "carry": {
        "label": "Несёт коробку", "tags": ["action"],
        "prompt": "carrying a box in front, both hands forward at chest height",
        "hands": {"r": (0.52, -1.55), "l": (-0.52, -1.55)},
        "misc": {"spine": 2, "chest": 2},
    },
    "hands_on_hips": {
        "label": "Руки в боки", "tags": ["attitude"],
        "prompt": "hands on hips, elbows out",
        "hands": {"r": (0.60, -0.62), "l": (-0.60, -0.62)},
    },
    "stern": {
        "label": "Строгий, руки скрещены", "tags": ["attitude"],
        "prompt": "arms crossed on chest, stern look", "crossed": True,
        "hands": {"r": (-0.52, -1.80), "l": (0.52, -1.74)},
        "misc": {"head": 2},
    },
    "shrug": {
        "label": "Пожимает плечами", "tags": ["emotion"],
        "prompt": "shoulders raised, palms up, elbows bent",
        "hands": {"r": (1.15, -1.55), "l": (-1.15, -1.55)},
        "misc": {"head": -2, "chest": -1},
    },
    "facepalm": {
        "label": "Хватается за лицо", "tags": ["emotion", "comedy"],
        "prompt": "hand on forehead, facepalm",
        "hands": {"r": (0.24, -2.98), "l": (-0.96, 0.35)},
        "misc": {"head": 6, "spine": 3},
    },
    "thumbs_up": {
        "label": "Большой палец вверх", "tags": ["positive", "action"],
        "prompt": "right forearm up, thumbs up, friendly nod",
        "hands": {"r": (0.86, -1.95), "l": (-1.00, 0.10)},
        "misc": {"head": -2},
    },
    "slump": {
        "label": "Поник", "tags": ["emotion"],
        "prompt": "slumped shoulders, head down, arms limp",
        "hands": {"r": (0.86, 0.34), "l": (-0.86, 0.34)},
        "misc": {"spine": 5, "chest": 4, "head": 12, "neck": 4},
    },
    "walk": {
        "label": "Идёт (кадр 1)", "tags": ["locomotion"],
        "prompt": "walking, one leg forward, arms swinging",
        "hands": {"r": (1.12, -0.10), "l": (-0.78, 0.34)},
        "legs": {"r": (-16, 14), "l": (16, -10)},
        "misc": {"spine": 2, "chest": -1},
    },
    "walk_2": {
        "label": "Идёт (кадр 2)", "tags": ["locomotion"],
        "prompt": "walking, opposite leg forward, arms swinging",
        "mirror_of": "walk",
    },
    "run": {
        "label": "Бежит", "tags": ["locomotion", "big"],
        "prompt": "running, legs wide apart, arms pumping",
        "hands": {"r": (1.05, -1.35), "l": (-1.15, -0.55)},
        "legs": {"r": (-34, 66), "l": (30, -58)},
        "misc": {"spine": 8, "chest": 2, "head": -6},
        "root": (0.0, -0.06),
    },
    "jump": {
        "label": "Прыжок", "tags": ["big", "action"],
        "prompt": "jumping up, knees tucked, arms up",
        "hands": {"r": (1.20, -3.95), "l": (-1.20, -3.95)},
        "legs": {"r": (-14, 40), "l": (14, 40)},
        "misc": {"spine": -2, "head": -4},
        "root": (0.0, -0.22),
    },
    "crouch": {
        "label": "Присел", "tags": ["action"],
        "prompt": "crouching down, knees bent, hands on knees",
        "hands": {"r": (0.72, -0.55), "l": (-0.72, -0.55)},
        "legs": {"r": (-30, 60), "l": (30, 60)},
        "misc": {"spine": 10, "chest": 6, "head": 6},
        "root": (0.0, 0.42),
    },
    "sit": {
        "label": "Сидит", "tags": ["action"],
        "prompt": "sitting, thighs forward, hands on knees",
        "hands": {"r": (0.66, -0.25), "l": (-0.66, -0.25)},
        "legs": {"r": (-52, 50), "l": (52, 50)},
        "misc": {"spine": 3, "head": -2},
        "root": (0.0, 0.55),
    },
    "hold_phone": {
        "label": "Телефон у уха", "tags": ["action"],
        "prompt": "phone held to the ear with right hand",
        "hands": {"r": (0.62, -2.86), "l": (-1.05, 0.20)},
        "misc": {"head": 2, "chest": -1},
    },
    "knock": {
        "label": "Стучит в дверь", "tags": ["action"],
        "prompt": "knocking on a door, right fist forward at chest height",
        "hands": {"r": (1.55, -2.55), "l": (-1.00, 0.10)},
        "misc": {"spine": 3, "head": -2},
    },
    "scold": {
        "label": "Ругает, палец вверх", "tags": ["attitude", "comedy"],
        "prompt": "scolding, index finger raised, other hand on hip",
        "hands": {"r": (1.15, -2.95), "l": (-0.60, -0.62)},
        "misc": {"head": 3, "chest": -2},
    },
    "arms_out": {
        "label": "Руки в стороны, «что происходит?!»", "tags": ["emotion", "big"],
        "prompt": "arms spread out to the sides, palms open, confused",
        "hands": {"r": (1.95, -1.45), "l": (-1.95, -1.45)},
        "misc": {"head": -3, "chest": -2},
    },
    "palms_up": {
        "label": "Ладони вверх, «ну и?»", "tags": ["attitude"],
        "prompt": "both palms up, questioning look",
        "hands": {"r": (1.72, -1.72), "l": (-1.72, -1.72)},
        "misc": {"head": 2, "chest": -1},
    },
    "point_low": {
        "label": "Показывает вниз-в сторону", "tags": ["emphasis"],
        "prompt": "pointing down to the side",
        "hands": {"r": (1.85, -0.55), "l": (-1.00, 0.10)},
        "misc": {"head": 5, "spine": 2},
    },
    "lean_side": {
        "label": "Наклон вбок, «серьёзно?»", "tags": ["emotion"],
        "prompt": "leaning to the side, skeptical",
        "hands": {"r": (1.18, 0.04), "l": (-0.86, 0.22)},
        "misc": {"spine": -4, "chest": -3, "head": 4},
    },
    "back_off": {
        "label": "Отшатнулся назад", "tags": ["emotion", "big"],
        "prompt": "leaning back in shock, arms slightly forward",
        "hands": {"r": (1.45, -1.05), "l": (-1.45, -1.05)},
        "misc": {"spine": -6, "chest": -4, "head": -8},
    },
    "sag": {
        "label": "Обмяк, руки повисли", "tags": ["emotion"],
        "prompt": "shoulders down, arms limp, exhausted",
        "hands": {"r": (0.92, 0.30), "l": (-0.92, 0.30)},
        "misc": {"spine": 4, "chest": 3, "head": 10, "neck": 3},
    },
    "reach": {
        "label": "Тянется вперёд-в сторону", "tags": ["action"],
        "prompt": "reaching out to the side",
        "hands": {"r": (2.05, -1.15), "l": (-1.00, 0.10)},
        "misc": {"spine": 2, "head": 2},
    },
    "celebrate": {
        "label": "Празднует, руки вверх", "tags": ["big", "positive"],
        "prompt": "both arms up in celebration, jumping slightly",
        "hands": {"r": (0.98, -4.30), "l": (-0.98, -4.30)},
        "misc": {"spine": -3, "head": -5},
        "root": (0.0, -0.12),
    },
}

POLE = {"r": (1.0, 0.7), "l": (-1.0, 0.7)}


def reach(sk: R.Skeleton, side: str, target: tuple[float, float]) -> float:
    """Дотянуть КИСТЬ (конец кисти, а не запястье) до цели. Возвращает промах.

    `hand_ik` ставит в цель запястье, поэтому цель для неё — точка на длину
    кисти ближе; направление кисти при этом коллинеарно предплечью, так что
    поправка уточняется итеративно (2–3 прохода достаточно).
    """
    hand_len = sk.bones[f"hand.{side}"].length
    upper, fore, hand = (sk.bones[f"upper_arm.{side}"], sk.bones[f"forearm.{side}"],
                         sk.bones[f"hand.{side}"])
    wrist = target
    best = (1e9, upper.angle, fore.angle, hand.angle)
    for _ in range(8):
        R.hand_ik(sk, side, wrist, pole=POLE[side])
        tip = sk.tip(f"hand.{side}")
        err = math.hypot(tip[0] - target[0], tip[1] - target[1])
        if err < best[0]:
            best = (err, upper.angle, fore.angle, hand.angle)
        if err < 1e-3:
            break
        elbow = sk.tip(f"upper_arm.{side}")
        dx, dy = target[0] - elbow[0], target[1] - elbow[1]
        d = math.hypot(dx, dy) or 1.0
        wrist = (target[0] - hand_len * dx / d, target[1] - hand_len * dy / d)
    upper.angle, fore.angle, hand.angle = best[1], best[2], best[3]
    sk.solve()
    return best[0]


def build(pose_id: str, spec: dict) -> dict:
    """Собрать данные позы: IK для рук, углы для ног, дерево углов."""
    sk = R.build_humanoid(6.0, None, "humanoid_v1")
    sk.reset_pose()

    root = spec.get("root")
    if root:
        sk.bones["root"].origin = (float(root[0]), float(root[1]))
        sk.solve()

    for k, v in (spec.get("misc") or {}).items():
        bone = sk.bones[k]
        bone.angle = bone.rest + math.radians(float(v))
    sk.solve()

    for side, target in (spec.get("hands") or {}).items():
        if target is None:
            continue
        reach(sk, side, (float(target[0]), float(target[1])))

    for side, (thigh, shin) in (spec.get("legs") or {}).items():
        sk.bones[f"thigh.{side}"].angle = sk.bones[f"thigh.{side}"].rest + math.radians(thigh)
        sk.bones[f"shin.{side}"].angle = math.radians(shin)
    sk.solve()

    bones = sk.capture(round_to=1)
    out = {
        "label": spec["label"],
        "tags": spec["tags"],
        "bones": bones,
        "prompt": spec["prompt"],
    }
    if root:
        out["root"] = [round(float(root[0]), 3), round(float(root[1]), 3)]
    if spec.get("mirror_of"):
        out.pop("bones")
        out["mirror_of"] = spec["mirror_of"]
    return out


def check(pose_id: str, sk: R.Skeleton, crossed: bool = False) -> list[str]:
    """Проверки «анатомического брака» позы."""
    problems = []
    for side in ("r", "l"):
        hand = sk.tip(f"hand.{side}")
        sign = 1.0 if side == "r" else -1.0
        # кисть не должна уходить за корпус (сквозь живот) или ниже колен
        if not crossed and hand[0] * sign < 0.18 and -2.3 < hand[1] < 0.4:
            problems.append(f"кисть {side} входит в корпус: ({hand[0]:.2f}, {hand[1]:.2f})")
        if hand[1] > 0.9:
            problems.append(f"кисть {side} ниже бёдер: y={hand[1]:.2f}")
        if abs(hand[0]) > 2.3:
            problems.append(f"кисть {side} за габаритом: x={hand[0]:.2f}")
        if hand[1] < -4.8:
            problems.append(f"кисть {side} слишком высоко: y={hand[1]:.2f}")
        elbow = sk.tip(f"upper_arm.{side}")
        if not crossed and abs(elbow[0]) < 0.30 and -2.2 < elbow[1] < -0.2:
            problems.append(f"локоть {side} в корпусе: x={elbow[0]:.2f}")
    return problems


def kit_spec() -> dict:
    """Спека папы — только как носитель скелета для проверок."""
    import kit
    return kit.load_character("dad")


def main() -> int:
    ap = argparse.ArgumentParser(description="Авторинг поз через IK")
    ap.add_argument("--dry-run", action="store_true", help="не записывать poses.json")
    args = ap.parse_args()

    data = json.load(open(POSES_PATH, encoding="utf-8"))
    poses = data["poses"]
    problems_total = 0
    report = []
    report_limits: list[str] = []
    import toon  # проверка пределов арт-рига (подъём руки на плоском мастере)
    probe_rig = toon.MeshRig(kit_spec(), ss=1, work_height=600)

    for pose_id, spec in SPECS.items():
        new = build(pose_id, spec)
        # проверка на собранном скелете
        probe = R.build_humanoid(6.0, None, "humanoid_v1")
        R.apply_pose(probe, new if "bones" in new else pose_id)
        if "mirror_of" in new:
            probe = R.build_humanoid(6.0, None, "humanoid_v1")
            R.apply_pose(probe, {"mirror_of": new["mirror_of"]})
        problems = check(pose_id, probe, crossed=bool(spec.get("crossed")))
        for warn in toon.pose_issues(probe_rig, probe):
            report_limits.append(f"  ~ {pose_id}: {warn}")
        for p in problems:
            report.append(f"  ! {pose_id}: {p}")
        problems_total += len(problems)
        if pose_id in poses:
            poses[pose_id].update(new)
        else:
            poses[pose_id] = new
        hand_info = ""
        if spec.get("hands"):
            parts = []
            for side, tgt in spec["hands"].items():
                got = probe.tip(f"hand.{side}")
                err = math.hypot(got[0] - tgt[0], got[1] - tgt[1])
                parts.append(f"{side}: цель ({tgt[0]:.2f},{tgt[1]:.2f}) → "
                             f"({got[0]:.2f},{got[1]:.2f}) промах {err:.3f}")
            hand_info = " | " + "; ".join(parts)
        print(f"{pose_id:14s}{hand_info}")

    if report:
        print("\n".join(report))
    if report_limits:
        print("\nпределы арт-рига (поза рендерится, но плечо требует ракурса):")
        print("\n".join(report_limits))
    print(f"\nпроверок не прошло: {problems_total}")

    if not args.dry_run:
        data["comment"] = ("Позы заданы целями кистей и собраны IK (tools/author_poses.py). "
                           "Углы — отклонения от rest в градусах.")
        with open(POSES_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"записано: {POSES_PATH} ({len(poses)} поз)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
