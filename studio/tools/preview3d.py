"""Превью 3D-анимации в MP4: персонаж + цикл движения, без сцены.

Нужен, чтобы смотреть ДВИЖЕНИЕ, а не отдельные кадры: плавность, посадка стопы,
противофаза рук и покачивание корпуса видно только в движении.

    python studio/tools/preview3d.py walk --seconds 2.8 --out studio/out/preview-walk.mp4

Рендер идёт покадрово (numpy-растеризатор), затем ffmpeg собирает H.264.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "engine"))

import animation as AN          # noqa: E402
import body3d as B              # noqa: E402
import character as CH          # noqa: E402
import render3d as R3           # noqa: E402


def ffmpeg_bin() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def make_anim(kind: str, skel, args):
    if kind == "walk":
        base = AN.Walk(skel, cycle=args.cycle, stride=0.46, step_height=0.13,
                       bob=0.028, sway=0.024, arm_swing=0.46)
    elif kind == "idle":
        base = AN.Idle(skel, cycle=4.2)
    elif kind == "wave":
        base = AN.Wave(skel, cycle=3.0)
    elif kind == "hips":
        base = AN.HandsOnHips(skel, cycle=4.0)
    elif kind == "point":
        base = AN.PointArm(skel, cycle=3.4)
    else:
        raise SystemExit(f"неизвестная анимация: {kind}")
    # вторичка: голова запаздывает от корпуса
    return AN.Secondary(base, lag=0.07, gain=0.55) if not args.no_secondary else base


def camera_for(kind: str, H: float, view: str) -> R3.Camera:
    cy = H * 0.50
    dist = (H * 1.25) / (2 * np.tan(np.radians(15)))
    if view == "side":
        return R3.Camera(eye=(dist * 0.99, cy, dist * 0.12), target=(0, cy, 0), fov=30)
    if view == "front":
        return R3.Camera(eye=(0.0, cy, dist), target=(0, cy, 0), fov=30)
    return R3.Camera(eye=(dist * 0.55, cy, dist * 0.85), target=(0, cy, 0), fov=30)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("kind", choices=["walk", "idle", "wave", "hips", "point"])
    ap.add_argument("--no-secondary", action="store_true")
    ap.add_argument("--seconds", type=float, default=2.8)
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--size", type=int, nargs=2, default=[480, 820])
    ap.add_argument("--ss", type=int, default=2)
    ap.add_argument("--view", choices=["three_quarter", "side", "front"],
                    default="three_quarter")
    ap.add_argument("--cycle", type=float, default=0.92)
    ap.add_argument("--out", default="studio/out/preview.mp4")
    args = ap.parse_args()

    p = B.Proportions()
    ch = CH.Character(p)
    anim = make_anim(args.kind, ch.skel, args)
    cam = camera_for(args.kind, p.height, args.view)
    n = int(round(args.seconds * args.fps))
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg_bin(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{args.size[0]}x{args.size[1]}", "-r", str(args.fps), "-i", "-",
           "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    t0 = time.time()
    try:
        for i in range(n):
            t = i / args.fps
            pose = anim.pose_at(t)
            img = R3.render(ch.build(pose), tuple(args.size), cam, ss=args.ss,
                            background=(0.97, 0.95, 0.92))
            proc.stdin.write(img[..., :3].astype(np.uint8).tobytes())
            if i % 12 == 0:
                fps_now = (i + 1) / max(time.time() - t0, 1e-6)
                print(f"кадр {i + 1}/{n}  ({fps_now:.2f} кадр/с)", flush=True)
    finally:
        proc.stdin.close()
        proc.wait()
    dt = time.time() - t0
    print(f"готово: {out}  {n} кадров, {n / dt:.2f} кадр/с, {dt:.1f} с")


if __name__ == "__main__":
    main()
