"""Демо-рендер «живой» анимации на процедурном персонаже.

Цель — доказать, что движок даёт мультяшное движение (IK, anticipation,
follow-through, вторичная анимация, моргание, липсинк), а не «прыгающие
картинки». Персонаж нарисован кодом, чтобы демо не зависело от арт-ассетов.

Запуск:
  python studio/engine/rig_demo.py            # -> studio/out/rig-demo.mp4
  python studio/engine/rig_demo.py --gif      # дополнительно gif
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rig as R  # noqa: E402

W, H = 720, 1280
FPS = 30
DUR = 8.0
INK = (59, 42, 38)
SKIN = (232, 180, 143)
SKIN_D = (210, 150, 111)
SHIRT = (201, 199, 194)
SHIRT_D = (176, 174, 169)
BEARD = (74, 51, 42)
BG_TOP = (255, 248, 236)
BG_BOT = (245, 232, 214)
GROUND = 1120.0
SCALE = 2.35   # пикселей на единицу скелета
BASE_Y = GROUND - (76 + 74) * SCALE - 10   # мировая Y таза: стопы стоят на полу


# --------------------------------------------------------------------------- #
# скелет: простые «рельсы» для демо
# --------------------------------------------------------------------------- #
def build_skeleton(scale: float = 1.0) -> R.Skeleton:
    s = R.Skeleton()
    s.add(R.Bone("root", None, 0.0))
    s.add(R.Bone("hips", "root", 0.0, origin=(0, 0)))
    s.add(R.Bone("spine", "hips", 62 * scale, origin=(0, 0)))
    s.add(R.Bone("chest", "spine", 54 * scale, origin=(0, 0)))
    s.add(R.Bone("neck", "chest", 22 * scale, origin=(0, 0)))
    s.add(R.Bone("head", "neck", 22 * scale, origin=(0, 0)))
    for side, sx in (("l", -1), ("r", 1)):
        s.add(R.Bone(f"upper_arm.{side}", "chest", 74 * scale,
                     origin=(sx * 28 * scale, 0)))
        s.add(R.Bone(f"forearm.{side}", f"upper_arm.{side}", 70 * scale, origin=(0, 0)))
        s.add(R.Bone(f"hand.{side}", f"forearm.{side}", 26 * scale, origin=(0, 0)))
        s.add(R.Bone(f"thigh.{side}", "hips", 76 * scale,
                     origin=(sx * 20 * scale, 0)))
        s.add(R.Bone(f"shin.{side}", f"thigh.{side}", 74 * scale, origin=(0, 0)))
        s.add(R.Bone(f"foot.{side}", f"shin.{side}", 34 * scale, origin=(0, 0)))
    return s


HALF_PI = math.pi / 2


def pose_idle(sk: R.Skeleton, t: float, breath: float = 1.0) -> None:
    """Базовая стойка: таз — начало координат, торс вверх, ноги вниз."""
    k = math.sin(t * 2 * math.pi * 0.25) * breath
    sk.bone("hips").angle = 0.0
    sk.bone("spine").angle = -HALF_PI + math.radians(2.5 * k)
    sk.bone("chest").angle = math.radians(-1.8 * k)
    sk.bone("neck").angle = math.radians(1.2 * k)
    sk.bone("head").angle = math.radians(-2.0 * k + 1.5)
    for side, sx in (("l", -1), ("r", 1)):
        sk.bone(f"thigh.{side}").angle = HALF_PI + sx * math.radians(3.0)
        sk.bone(f"shin.{side}").angle = 0.0
        sk.bone(f"foot.{side}").angle = -HALF_PI


# --------------------------------------------------------------------------- #
# отрисовка человечка по скелету
# --------------------------------------------------------------------------- #
def world_vertices(sk: R.Skeleton) -> dict[str, tuple[tuple[float, float], tuple[float, float]]]:
    """Для каждой кости — (начало, конец) в мировых координатах, центр внизу экрана."""
    out = {}
    for name in sk.order:
        b = sk.bones[name]
        if name == "root":
            continue
        p0 = (W / 2 + b.world_pos[0], BASE_Y + b.world_pos[1])
        tip = sk.tip(name)
        p1 = (W / 2 + tip[0], BASE_Y + tip[1])
        out[name] = (p0, p1)
    return out


def capsule(draw: ImageDraw.ImageDraw, p0, p1, width, fill, outline=INK, ow=4):
    width = int(round(width))
    ow = int(round(ow))
    draw.line([p0, p1], fill=outline, width=width + ow * 2)
    for p in (p0, p1):
        draw.ellipse([p[0] - (width / 2 + ow), p[1] - (width / 2 + ow),
                      p[0] + (width / 2 + ow), p[1] + (width / 2 + ow)], fill=outline)
    draw.line([p0, p1], fill=fill, width=width)
    for p in (p0, p1):
        draw.ellipse([p[0] - width / 2, p[1] - width / 2,
                      p[0] + width / 2, p[1] + width / 2], fill=fill)


def draw_character(frame: Image.Image, sk: R.Skeleton, t: float,
                   eye: float = 1.0, mouth: str = "M", lean: float = 0.0) -> None:
    v = world_vertices(sk)
    S = SCALE
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # ноги (сзади)
    for side in ("l", "r"):
        capsule(d, *v[f"thigh.{side}"], 40 * S, (96, 80, 72))
        capsule(d, *v[f"shin.{side}"], 34 * S, (96, 80, 72))
        capsule(d, *v[f"foot.{side}"], 30 * S, (70, 56, 50))
    # корпус
    hips, chest_top = v["hips"][0], v["chest"][1]
    capsule(d, hips, chest_top, 58 * S, SHIRT)
    # руки
    for side in ("l", "r"):
        capsule(d, *v[f"upper_arm.{side}"], 32 * S, SHIRT)
        capsule(d, *v[f"forearm.{side}"], 28 * S, SKIN)
        capsule(d, *v[f"hand.{side}"], 26 * S, SKIN)
    # шея + голова
    neck_p = v["neck"][0]
    head_bone_top = v["head"][1]
    capsule(d, neck_p, v["head"][0], 24 * S, SKIN_D)
    hx = (v["head"][0][0] + head_bone_top[0]) / 2
    hy = (v["head"][0][1] + head_bone_top[1]) / 2
    r = 44 * S
    d.ellipse([hx - r - 5, hy - r - 5, hx + r + 5, hy + r + 5], fill=INK)
    d.ellipse([hx - r, hy - r, hx + r, hy + r], fill=SKIN)

    # борода
    d.chord([hx - r, hy - r * 0.15, hx + r, hy + r * 1.02], 0, 180, fill=BEARD)
    # волосы
    d.chord([hx - r, hy - r * 1.02, hx + r, hy + r * 0.35], 180, 360, fill=BEARD)
    # глаза
    er = 12 * S
    for sx in (-1, 1):
        ex, ey = hx + sx * 21 * S, hy - 6 * S
        d.ellipse([ex - er, ey - er * eye, ex + er, ey + er * eye], fill=(255, 255, 255),
                  outline=INK, width=3)
        if eye > 0.35:
            pr = 6 * S
            d.ellipse([ex - pr, ey - pr * eye, ex + pr, ey + pr * eye], fill=(64, 44, 34))
            d.ellipse([ex + 1, ey - 3 * eye, ex + 4, ey], fill=(255, 255, 255))
    # брови
    for sx in (-1, 1):
        bx = hx + sx * 21 * S
        d.line([(bx - 12 * S, hy - 28 * S), (bx + 12 * S, hy - 31 * S)], fill=BEARD,
               width=int(6 * S))
    # рот по виземе
    mw = 13 * S
    my = hy + 20 * S
    shapes = {"M": 0.0, "A": 20 * S, "E": 12 * S, "I": 8 * S, "O": 14 * S,
              "U": 10 * S, "F": 0.0, "L": 6 * S, "C": 4 * S}
    h = shapes.get(mouth, 0.0)
    if h > 0:
        d.ellipse([hx - mw, my - h * 0.45, hx + mw, my + h * 0.55],
                  fill=(120, 58, 58), outline=INK, width=3)
    else:
        d.line([(hx - mw, my), (hx + mw, my)], fill=INK, width=int(4 * S * 0.9))

    frame.alpha_composite(layer)


def background(t: float) -> Image.Image:
    arr = np.zeros((H, W, 3), np.float32)
    for y in range(H):
        k = y / H
        arr[y, :, :] = np.array(BG_TOP) * (1 - k) + np.array(BG_BOT) * k
    img = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    d = ImageDraw.Draw(img)
    # «комната»: плинтус и ковёр
    d.rectangle([0, GROUND - 10, W, GROUND + 14], fill=(138, 168, 138))
    d.rounded_rectangle([60, GROUND + 20, W - 60, H - 40], radius=40, fill=(255, 96, 84))
    d.rounded_rectangle([90, GROUND + 46, W - 90, H - 70], radius=30, outline=(255, 216, 200), width=10)
    return img


# --------------------------------------------------------------------------- #
# сценарий демо: idle -> anticipation -> wave -> point -> удивление -> прыжок
# --------------------------------------------------------------------------- #
def mirror(angle: float) -> float:
    """Зеркальный угол для левой руки (симметричная поза)."""
    return math.pi - angle


def shot_script(t: float) -> dict:
    """Возвращает параметры кадра: углы рук, эмоцию, рот.

    Углы — мировые, 0 = вправо, +pi/2 = вниз.
    """
    sk = build_skeleton(SCALE)
    pose_idle(sk, t)

    DOWN_R, DOWN_L = 1.35, mirror(1.35)      # руки опущены
    if t < 2.2:                               # idle + дыхание
        arm_r, arm_l = DOWN_R, DOWN_L
        mouth, eye = "M", 1.0
    elif t < 3.3:                             # anticipation + подъём руки
        k = R.clamp((t - 2.2) / 0.42)
        arm_r = R.lerp(DOWN_R, -0.75, R.ease_out_back(k))
        arm_l = DOWN_L
        mouth, eye = ("A" if k > 0.6 else "M"), 1.0
    elif t < 4.9:                             # машем
        arm_r = -0.75 + math.sin((t - 3.3) * 9.0) * 0.22
        arm_l = DOWN_L
        mouth, eye = "A", 1.0
    elif t < 6.1:                             # палец в камеру (IK)
        k = R.clamp((t - 4.9) / 0.45)
        arm_r = R.lerp(-0.75, -0.12, R.ease_in_out(k))
        arm_l = DOWN_L
        mouth, eye = "E", 1.0
    elif t < 7.0:                             # удивление: руки врозь
        k = R.clamp((t - 6.1) / 0.25)
        arm_r = R.lerp(-0.12, -0.55, R.ease_out_back(k, 2.4))
        arm_l = R.lerp(DOWN_L, mirror(-0.55), R.ease_out_back(k, 2.4))
        mouth, eye = "O", 1.35
    else:                                     # прыжок с руками вверх
        k = R.clamp((t - 7.0) / 0.5)
        arm_r = R.lerp(-0.55, -1.25, R.ease_out_quad(k))
        arm_l = R.lerp(mirror(-0.55), mirror(-1.25), R.ease_out_quad(k))
        mouth, eye = "A", 1.0
    return {"sk": sk, "arm_r": arm_r, "arm_l": arm_l, "mouth": mouth, "eye": eye}


def build_frame(t: float, blink_state: float, spring_x: float,
                jump_y: float, squash_k: float) -> Image.Image:
    p = shot_script(t)
    sk = p["sk"]

    # --- 1. базовая поза и прямой проход (нужны мировые углы родителей)
    sk.solve()

    # --- 2. IK: кисти тянутся к целям, локти считаются сами
    for side, target_angle in (("r", p["arm_r"]), ("l", p["arm_l"])):
        upper = sk.bone(f"upper_arm.{side}")
        parent_world_angle = sk.bone(upper.parent).world_angle
        shoulder_world = upper.world_pos
        l1, l2 = upper.length, sk.bone(f"forearm.{side}").length
        reach = (l1 + l2) * 0.94
        target = (shoulder_world[0] + math.cos(target_angle) * reach,
                  shoulder_world[1] + math.sin(target_angle) * reach)
        a1, a2, _ = R.solve_ik2(shoulder_world, target, l1, l2,
                                pole=(0, 1) if side == "r" else (0, -1))
        upper.angle = a1 - parent_world_angle
        sk.bone(f"forearm.{side}").angle = (a2 - a1) - upper.parent_scale_angle if False else (a2 - a1)
        sk.solve()

    # --- 3. прыжок, сквош-стретч и вторичная анимация головы
    sk.bones["root"].origin = (0.0, jump_y)
    sy, sx = R.squash_stretch(squash_k)
    sk.bones["root"].scale = (sx, sy)
    sk.bone("head").angle += spring_x * 0.12
    sk.solve()

    frame = background(t)
    draw_character(frame, sk, t, eye=p["eye"] * blink_state, mouth=p["mouth"])

    # тень под персонажем (сжимается в прыжке)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sw = 150 * SCALE * (1 - min(0.5, abs(jump_y) / 700))
    sd.ellipse([W / 2 - sw, GROUND - 8, W / 2 + sw, GROUND + 22],
               fill=(60, 40, 30, 60))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    frame = Image.alpha_composite(shadow, frame)

    # лёгкое зерно и виньетка — «студийный» вид
    arr = np.asarray(frame.convert("RGB"), np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx / W - 0.5) * 2) ** 2 + ((yy / H - 0.5) * 2) ** 2) / 1.41
    arr *= np.clip(1 - 0.35 * r ** 2.2, 0, 1)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gif", action="store_true")
    ap.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "rig-demo.mp4"))
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n = int(DUR * FPS)

    # мигание
    blinks = R.blink_times(DUR, 3.0, seed=7)
    blink_curve = [1.0] * n
    for bt in blinks:
        i0 = int(bt * FPS)
        for k in range(4):
            if i0 + k < n:
                blink_curve[i0 + k] = [1.0, 0.25, 0.1, 0.5][k]

    # пружина вторичной анимации: возбуждается поворотом корпуса
    spring = R.Spring(stiffness=90, damping=11, gravity=40, limit=1.2)
    drive = [math.sin(t * 3.2) * (3 if t > 5.0 else 1) for t in (i / FPS for i in range(n))]
    spring_vals = spring.run(n, FPS, drive)

    # прыжок и приземление
    jump_y = []
    squash = []
    for i in range(n):
        t = i / FPS
        if t < 7.0:
            jump_y.append(0.0)
            squash.append(0.0)
        elif t < 7.18:                       # присед
            k = (t - 7.0) / 0.18
            jump_y.append(14 * R.ease_in_out(k))
            squash.append(0.18 * R.ease_in_out(k))
        elif t < 7.75:                       # полёт
            k = (t - 7.18) / 0.57
            jump_y.append(-150 * 4 * k * (1 - k))
            squash.append(-0.10 * math.sin(math.pi * k))
        else:                                # приземление + отскок
            k = (t - 7.75) / 0.25
            jump_y.append(12 * math.exp(-k * 5) * math.cos(k * 12))
            squash.append(0.20 * math.exp(-k * 6) * abs(math.cos(k * 10)))

    from imageio_ffmpeg import get_ffmpeg_exe
    ffmpeg = get_ffmpeg_exe()
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", args.out]
    print(f"• демо рига: {n} кадров -> {args.out}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frames_for_gif = []
    try:
        for i in range(n):
            t = i / FPS
            img = build_frame(t, blink_curve[i], spring_vals[i], jump_y[i], squash[i])
            proc.stdin.write(img.tobytes())
            if args.gif and i % 2 == 0:
                frames_for_gif.append(img.resize((W // 2, H // 2), Image.LANCZOS))
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit("ffmpeg failed")
    if args.gif:
        gif_path = args.out.replace(".mp4", ".gif")
        frames_for_gif[0].save(gif_path, save_all=True, append_images=frames_for_gif[1:],
                               duration=int(1000 / FPS * 2), loop=0, optimize=True)
        print("✓", gif_path)
    print("✓", args.out)


if __name__ == "__main__":
    main()
