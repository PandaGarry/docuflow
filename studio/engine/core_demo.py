"""Демо ядра: кукла говорит, меняет позу и выражение лица — без единой генерации.

Это проверка «на глаз» того, что новый слой работает вместе:
скелет из данных → позы из библиотеки → эмоции из параметров → липсинк →
микромимика и мигание → кадры → mp4.

Запуск:
    python studio/engine/core_demo.py                 # -> studio/out/core-demo.mp4
    python studio/engine/core_demo.py --char mom --fps 30 --width 720
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import face as F  # noqa: E402
import kit  # noqa: E402
import puppet  # noqa: E402
import rig as R  # noqa: E402

# сценарий: (время, поза, эмоция)
SHOTS = [
    (0.0, "idle", "calm"),
    (0.9, "idle_shift", "calm"),
    (1.6, "think", "think"),
    (2.9, "scold", "annoyed"),
    (3.7, "surprise", "panic"),
    (4.6, "hands_on_hips", "deadpan"),
]

LINE = "Так. Коробки в машине, паспорт в кармане. Всё под контролем!"


def pose_weight(t: float) -> tuple[str, str, float, float]:
    """Возвращает (поза A, поза B, доля перехода, время начала перехода)."""
    for (t0, p0, _e0), (t1, p1, _e1) in zip(SHOTS, SHOTS[1:]):
        if t0 <= t < t1:
            span = max(min(0.35, (t1 - t0) * 0.6), 1e-3)
            k = R.clamp((t - (t1 - span)) / span)
            return p0, p1, R.ease_in_out(k), t0
    return SHOTS[-1][1], SHOTS[-1][1], 0.0, SHOTS[-1][0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--char", default="dad")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--width", type=int, default=540)
    ap.add_argument("--seconds", type=float, default=5.4)
    ap.add_argument("--out", default=os.path.join(STUDIO, "out", "core-demo.mp4"))
    args = ap.parse_args()

    spec = kit.load_character(args.char)
    height = int(args.width * 16 / 9)
    opts = puppet.RenderOpts(width=args.width, height=height, ss=2, ground=0.93)
    painter = puppet.Painter(spec, opts)

    timeline = F.FaceTimeline.from_expressions([(t, e) for t, _p, e in SHOTS], ease="ease")
    spans = F.lip_sync(LINE, start=0.5, duration=args.seconds - 1.4, chars_per_sec=12.5)
    blinks = R.blink_times(args.seconds, avg_interval=2.4, seed=3)

    n = int(args.seconds * args.fps)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    from imageio_ffmpeg import get_ffmpeg_exe
    cmd = [get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{args.width}x{height}",
           "-r", str(args.fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out]
    print(f"• {args.char}: {n} кадров, {args.width}x{height}, {args.fps} fps -> {args.out}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n):
            t = i / args.fps

            # 1. поза: переход между двумя соседними позами сценария
            pa, pb, k, _ = pose_weight(t)
            sk = painter.build(pa)
            if k > 0 and pb != pa:
                pose_a = kit.L.pose(pa)["bones"]
                pose_b = kit.L.pose(pb)["bones"]
                for name in sk.bones:
                    a = float(pose_a.get(name, 0.0))
                    b = float(pose_b.get(name, 0.0))
                    sk.bones[name].angle = sk.bones[name].rest + math.radians(
                        a + (b - a) * k)
                sk.solve()
            # дыхание поверх позы
            R.apply_pose(sk, "breath", weight=0.6 + 0.4 * math.sin(t * 2.1),
                         additive=True)

            # 2. лицо: эмоция + липсинк + мигание + микромимика
            blink = 1.0
            for bt in blinks:
                dt = t - bt
                if -0.06 <= dt <= 0.10:
                    blink = min(blink, max(0.0, abs(dt) / 0.09))
            face = F.face_at(t, timeline=timeline, spans=spans, blink=blink,
                             micro=1.0, seed=7)

            # 3. кадр
            img = painter.frame(sk, face, background="studio")
            proc.stdin.write(img.tobytes())
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit("ffmpeg failed")
    print("✓", args.out)


if __name__ == "__main__":
    main()
