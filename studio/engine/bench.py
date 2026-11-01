"""Бенчмарк ядра: сколько стоит кадр, промпт, IK — и не деградировало ли что-то.

Запуск:
    python studio/engine/bench.py             # таблица
    python studio/engine/bench.py --assert    # + проверка бюджетов (для CI)

Бюджеты подобраны на слабом CPU с запасом: если они пробиты, значит кто-то
добавил тяжёлую работу в покадровый путь (например, пересчёт фона или градиента
освещения на каждый кадр).
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import face as F  # noqa: E402
import kit  # noqa: E402
import puppet  # noqa: E402
import rig as R  # noqa: E402

# бюджеты (миллисекунды), с запасом ×2-3 от реального времени
BUDGET_MS = {
    "skeleton+pose": 2.5,
    "frame 360x640 preview": 60.0,
    "frame 540x960 high": 200.0,
    "prompt": 1.0,
    "face_at": 0.3,
    "ik": 0.25,
}


def timed(fn, n: int = 20) -> float:
    """Среднее время вызова в миллисекундах."""
    fn()                                   # прогрев
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    return statistics.mean(samples)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--assert", dest="do_assert", action="store_true")
    ap.add_argument("--frames", type=int, default=20)
    args = ap.parse_args()

    spec = kit.load_character("dad")
    results: dict[str, float] = {}

    results["skeleton+pose"] = timed(lambda: R.apply_pose(R.build_humanoid(6.1), "wave"),
                                     args.frames)

    for label, (w, h), quality in (("frame 360x640 preview", (360, 640), "preview"),
                                   ("frame 540x960 high", (540, 960), "high")):
        painter = puppet.Painter(spec, puppet.RenderOpts(width=w, height=h,
                                                         quality=quality))
        sk = painter.build("wave")
        face = F.face_at(1.0, timeline=F.FaceTimeline.from_expressions([(0, "joy")]),
                         spans=F.LipSync.from_text("Привет, это тест", duration=1.0))
        results[label] = timed(lambda: painter.frame(sk, face), max(5, args.frames // 3))

    results["prompt"] = timed(lambda: kit.build_prompt(spec, pose="wave", expression="joy",
                                                       set_name="home"), args.frames)
    timeline = F.FaceTimeline.from_expressions([(0, "joy"), (2, "anger")])
    spans = F.LipSync.from_text("Проверка реплики для бенчмарка", duration=2.0)
    results["face_at"] = timed(lambda: F.face_at(1.2, timeline=timeline, spans=spans),
                               args.frames)

    sk = R.build_humanoid(6.0)
    results["ik"] = timed(lambda: R.hand_ik(sk, "r", (1.6, -1.4)), args.frames)

    # --- точность IK -------------------------------------------------------- #
    # Достижимые цели берём от плеча, чтобы не путать промах с недостижимостью.
    import math

    reach = None
    worst = 0.0
    checked = 0
    for side, base_sign in (("r", 1.0), ("l", -1.0)):
        sk = R.build_humanoid(6.0)
        sk.solve()
        upper, fore = sk.bones[f"upper_arm.{side}"], sk.bones[f"forearm.{side}"]
        reach = upper.length + fore.length
        sh = upper.world_pos
        for frac, ang_deg in ((0.35, -150), (0.55, -100), (0.70, -60), (0.55, 40),
                              (0.85, 15), (0.98, -170), (0.45, 120)):
            ang = math.radians(ang_deg) * base_sign
            target = (sh[0] + math.cos(ang) * reach * frac,
                      sh[1] + math.sin(ang) * reach * frac)
            sk = R.build_humanoid(6.0)
            R.hand_ik(sk, side, target)
            wx, wy = sk.tip(f"forearm.{side}")
            miss = math.hypot(wx - target[0], wy - target[1]) / reach
            worst = max(worst, miss)
            checked += 1

    # Недостижимая цель: рука должна лежать ровно на линии «плечо → цель».
    angle_err = 0.0
    for far in ((3.0, 1.5), (-2.5, 2.0), (0.2, 4.0), (3.0, -3.0)):
        sk = R.build_humanoid(6.0)
        R.hand_ik(sk, "r", far)
        sh = sk.bones["upper_arm.r"].world_pos
        wx, wy = sk.tip("forearm.r")
        a_hand = math.atan2(wy - sh[1], wx - sh[0])
        a_far = math.atan2(far[1] - sh[1], far[0] - sh[0])
        angle_err = max(angle_err, abs(math.atan2(math.sin(a_hand - a_far),
                                                  math.cos(a_hand - a_far))))

    broken_extra = None
    if math.degrees(angle_err) > 0.01:
        broken_extra = f"направление при недостижимой цели: {math.degrees(angle_err):.3f}°"

    print(f"{'операция':22s} {'мс':>8s}   бюджет")
    broken = []
    for name, ms in results.items():
        budget = BUDGET_MS.get(name)
        ok = budget is None or ms <= budget
        mark = "✓" if ok else "✗"
        print(f"{mark} {name:21s} {ms:8.2f}   {budget if budget is not None else '—'}")
        if not ok:
            broken.append(f"{name}: {ms:.1f} мс > {budget} мс")

    print(f"\nточность IK: {checked} достижимых целей, худший промах "
          f"{worst * 100:.4f} % длины руки")
    print(f"недостижимая цель: отклонение направления {math.degrees(angle_err):.4f}°")
    if worst > 0.001:
        broken.append(f"IK промах {worst * 100:.3f} % (порог 0.1 %)")
    if broken_extra:
        broken.append(broken_extra)

    if args.do_assert and broken:
        print("\nПРОВАЛЕНО:")
        for b in broken:
            print("  ✗", b)
        return 1
    if args.do_assert:
        print("\n✓ все бюджеты соблюдены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
