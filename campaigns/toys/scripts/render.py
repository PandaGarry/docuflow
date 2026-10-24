"""Рендер мультика «Уборка»: покадровая cut-out анимация на PIL/numpy -> ffmpeg.

Каждая сцена — своя функция: фон с движением камеры, персонажи с «дыханием»,
сквош-стретчем и подскоками, комикс-надписи, пузыри, конфетти, тряска.

Запуск:
  python scripts/render.py                # полный рендер
  python scripts/render.py --preview 2 8.5  # статичные кадры для проверки
"""

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import art  # noqa: E402
import timeline as tl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BG_DIR = os.path.join(HERE, "assets", "bg")
CHARS = os.path.join(HERE, "assets", "chars")
AUDIO_MIX = os.path.join(HERE, "audio", "mix.wav")
OUT_DIR = os.path.join(HERE, "out")

W, H = tl.W, tl.H
PAD = 90
BASELINE = 0.885 * H
INK, CREAM = tl.PALETTE["ink"], tl.PALETTE["cream"]


# ------------------------------------------------------------------ фон
_bg_cache = {}


def bg_base(name):
    if name not in _bg_cache:
        src = Image.open(os.path.join(BG_DIR, f"room_{name}.png")).convert("RGB")
        h = int(H * 1.55)
        w = int(src.width * h / src.height)
        if w < int(W * 1.35):
            w = int(W * 1.35)
            h = int(src.height * w / src.width)
        _bg_cache[name] = src.resize((w, h), Image.LANCZOS)
    return _bg_cache[name]


def draw_bg(size, name, zoom=1.0, ax=0.5, ay=0.5, sat=1.0, bright=1.0,
            contrast=1.0, tint=None, blur=0.0):
    """Кадрирование фона «по площади» + цветокор."""
    sw, sh = size
    base = bg_base(name)
    cw = int(W * zoom)
    ch = int(H * zoom)
    cw = min(cw, base.width)
    ch = min(ch, base.height)
    x = int((base.width - cw) * art.clamp(ax))
    y = int((base.height - ch) * art.clamp(ay))
    crop = base.crop((x, y, x + cw, y + ch)).resize((sw, sh), Image.BICUBIC)
    out = art.grade(crop, sat=sat, brightness=bright, contrast=contrast, tint=tint)
    if blur > 0:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    return out


# ------------------------------------------------------------------ вспомогательное
def pill(text, size=34, weight=700, fg=INK, bg=CREAM, pad=(28, 14), border=5, tracking=1.2):
    fnt = art.font(weight, size)
    tw = int(sum(fnt.getlength(c) for c in text) + tracking * max(len(text) - 1, 0))
    th = int(size * 1.32)
    layer = Image.new("RGBA", (tw + pad[0] * 2 + border * 2, th + pad[1] * 2 + border * 2),
                      (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([border // 2, border // 2, layer.width - border // 2,
                         layer.height - border // 2],
                        radius=layer.height // 2, fill=bg + (255,), outline=fg + (255,),
                        width=border)
    x = border + pad[0]
    for c in text:
        d.text((x, border + pad[1] - size * 0.06), c, font=fnt, fill=fg + (255,))
        x += fnt.getlength(c) + tracking
    return layer


def put(stage, layer, cx=None, top=None, alpha=1.0, scale=1.0, rot=0.0, left=None):
    if alpha <= 0.01:
        return
    im = layer
    if scale != 1.0:
        im = art.resize(im, h=max(1, int(im.height * scale)))
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        im = im.copy()
        im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
    x = left if left is not None else cx - im.width / 2
    stage.alpha_composite(im, (int(x), int(top)))


def pop_in(t, t0, dur=0.38):
    return art.clamp((t - t0) / dur)


# --- игрушки (нарезка из листа спрайтов)
TOY_BOXES = {
    "bear": (0.03, 0.04, 0.21, 0.42),
    "car": (0.22, 0.05, 0.47, 0.35),
    "ball": (0.48, 0.05, 0.63, 0.35),
    "dino": (0.63, 0.04, 0.81, 0.42),
    "blocks": (0.81, 0.02, 0.99, 0.42),
    "doll": (0.02, 0.45, 0.22, 0.86),
    "train": (0.42, 0.40, 0.79, 0.62),
    "bucket": (0.26, 0.62, 0.42, 0.93),
    "lolli": (0.46, 0.63, 0.58, 0.93),
    "duck": (0.58, 0.64, 0.71, 0.90),
    "box": (0.77, 0.62, 0.97, 0.93),
}


def toy(name, height):
    key = (name, int(height))
    if key not in _bg_cache:
        sheet = art.load_art(os.path.join(HERE, "assets", "raw", "toys_cut.png"))
        x0, y0, x1, y1 = TOY_BOXES[name]
        c = sheet.crop((int(sheet.width * x0), int(sheet.height * y0),
                        int(sheet.width * x1), int(sheet.height * y1)))
        bbox = c.split()[3].getbbox()
        if bbox:
            c = c.crop(bbox)
        _bg_cache[key] = art.resize(c, h=int(height))
    return _bg_cache[key]


def flying_toy(stage, name, cx, cy, height, rot=0.0, alpha=1.0):
    im = toy(name, height)
    if rot:
        im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        im = im.copy()
        im.putalpha(im.split()[3].point(lambda v: int(v * alpha)))
    stage.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))


# ------------------------------------------------------------------ контекст кадра
class Shot:
    """Один кадр: фон-оверскан + «сцена» с персонажами и графикой."""

    def __init__(self, canvas_size, stage_size, bg):
        self.canvas = bg.convert("RGBA")
        self.stage = Image.new("RGBA", stage_size, (0, 0, 0, 0))


def compose(bg, stage, shake=(0, 0), rot=0.0):
    canvas = bg.copy()
    canvas.alpha_composite(stage, (PAD + int(shake[0]), PAD + int(shake[1])))
    if abs(rot) > 0.01:
        canvas = canvas.rotate(rot, resample=Image.BICUBIC, center=(canvas.width / 2,
                                                                   canvas.height / 2))
    box = (PAD, PAD, PAD + W, PAD + H)
    out = canvas.crop(box)
    if out.size != (W, H):
        out = out.resize((W, H), Image.BICUBIC)
    return out


def shake_amp(t, amp, freq=23.0, seed=0.0):
    if amp <= 0:
        return (0, 0)
    x = math.sin(t * freq + seed) * amp + math.sin(t * freq * 2.7 + seed * 2) * amp * 0.4
    y = math.cos(t * freq * 1.13 + seed) * amp * 0.8
    return (x, y)


def flash(stage_or_frame, alpha, color=(255, 255, 255)):
    if alpha <= 0.01:
        return stage_or_frame
    ov = Image.new("RGBA", stage_or_frame.size, color + (int(255 * alpha),))
    return Image.alpha_composite(stage_or_frame, ov)


def comic_overlay(stage, t, items=None):
    """Комикс-надписи с «пружинным» появлением и лёгким дрожанием."""
    items = tl.COMIC_TEXT if items is None else items
    for it in items:
        dt = t - it["t"]
        if dt < 0 or dt > it.get("dur", 1.2):
            continue
        p = art.clamp(dt / 0.26)
        scale = art.lerp(0.4, 1.0, art.ease_out_back(p, 2.6)) * (1 + 0.06 * math.sin(dt * 14))
        wob = math.sin(dt * 9) * 1.6
        layer = art.comic_text(it["text"], it["size"], it["color"], rot=it["rot"] + wob)
        put(stage, layer, cx=W / 2, top=int(it.get("y", 0.20) * H), scale=scale,
            alpha=art.smooth(art.clamp(dt / 0.14)))


# ------------------------------------------------------------------ сцены
def scene_ask(stage, t, sub):
    """Ребёнок просит позвать друзей."""
    art.character("kid_ask", stage, cx=0.46 * W, baseline=BASELINE,
                  height=0.54 * H, t=t, bob=11, rot=1.3, pop=min(1, sub / 0.4))
    b = art.bubble("Мам! А можно\nко мне друзья?", size=52, max_w=700)
    put(stage, b, cx=0.52 * W, top=int(0.235 * H),
        scale=art.lerp(0.6, 1.0, art.ease_out_back(pop_in(sub, 0.35))),
        alpha=art.smooth(pop_in(sub, 0.35, 0.2)))
    # сердечко-«пожалуйста»
    if sub > 1.4:
        k = math.sin((sub - 1.4) * 5) * 8
        art.sparkle(stage, 0.80 * W, 0.50 * H + k, 18, alpha=200)


def scene_ok(stage, t, sub):
    """Мама разрешает — с условием."""
    art.character("kid_ask", stage, cx=0.26 * W, baseline=BASELINE + 20,
                  height=0.40 * H, t=t, phase=1.2, bob=8, rot=1.0, flip=False)
    art.character("mom_ok", stage, cx=0.70 * W, baseline=BASELINE,
                  height=0.60 * H, t=t, phase=0.3, bob=9, rot=0.9,
                  pop=min(1, sub / 0.45))
    b = art.bubble("Можно. Только\nпотом уберитесь.", size=48, max_w=640)
    put(stage, b, cx=0.44 * W, top=int(0.20 * H),
        scale=art.lerp(0.7, 1.0, art.ease_out_back(pop_in(sub, 0.55))),
        alpha=art.smooth(pop_in(sub, 0.55, 0.2)))


def scene_aga(stage, t, sub):
    """«АГА!» — ударный кадр с конфетти."""
    art.character("kid_yay", stage, cx=0.5 * W, baseline=BASELINE + 40,
                  height=0.72 * H, t=t, bob=16, rot=2.2, squash=0.03 * math.sin(t * 18))
    stage.alpha_composite(art.confetti(stage.size, sub + 0.15, n=110, seed=4), (0, 0))


def scene_party(stage, t, sub):
    """Вечеринка: быстрые монтажные вставки, летающие игрушки."""
    cut = int(sub / 0.8)
    local = sub - cut * 0.8
    layouts = [(0.50, 0.60, 1.0), (0.34, 0.54, -1.0), (0.62, 0.62, 1.0), (0.44, 0.56, -1.0)]
    cx_f, h_f, flip = layouts[cut % len(layouts)]

    def flight(items, alpha):
        for i, (nm, fx, fy, fh, spin) in enumerate(items):
            bx = fx * W + math.sin(sub * 2.2 + i) * 38
            by = fy * H + math.cos(sub * 2.6 + i * 1.7) * 52 - 20
            flying_toy(stage, nm, bx, by, fh * H, rot=spin * sub * 0.55, alpha=alpha)

    # дальний план — за героем
    flight([("bear", 0.11, 0.30, 0.10, 200), ("duck", 0.20, 0.17, 0.075, 140),
            ("ball", 0.90, 0.26, 0.085, 120), ("car", 0.88, 0.44, 0.075, -160)],
           alpha=0.95)

    squish = 0.05 * math.sin(local * 26)
    art.character("kid_yay", stage, cx=cx_f * W, baseline=BASELINE + 40,
                  height=h_f * H, t=t, bob=22, rot=3.0, squash=squish, flip=flip > 0)

    # ближний план — по краям кадра
    flight([("lolli", 0.93, 0.62, 0.075, 90), ("dino", 0.09, 0.56, 0.085, -110),
            ("bucket", 0.88, 0.78, 0.08, 60)], alpha=0.9)

    stage.alpha_composite(art.speed_lines(stage.size, t, n=22, alpha=80, inner=0.34,
                                          seed=11 + cut), (0, 0))
    stage.alpha_composite(art.confetti(stage.size, sub + 0.4, n=60, seed=9 + cut), (0, 0))

    # карточка времени
    if sub > 1.55:
        p = pop_in(sub, 1.55, 0.3)
        pill_layer = pill("ЧЕРЕЗ 3 ЧАСА", size=40, weight=800, bg=CREAM, fg=INK)
        put(stage, pill_layer, cx=W / 2, top=int(0.105 * H),
            scale=art.lerp(0.7, 1.0, art.ease_out_back(p)), alpha=art.smooth(p))


def scene_mess(stage, t, sub):
    """Ревел бардака."""
    art.character("kid_shock", stage, cx=0.50 * W, baseline=BASELINE + 30,
                  height=0.44 * H, t=t, bob=6, rot=1.0, pop=min(1, sub / 0.5))
    if sub > 0.55:
        stage.alpha_composite(art.dust(stage, art.clamp((sub - 0.55) / 0.9), 0.5 * W,
                                       0.8 * H, n=16, seed=6, spread=1.4, alpha=120), (0, 0))


def scene_slam(stage, t, sub):
    """Дверь хлопнула: пыль, тишина, сверчки."""
    if sub > 0.75:
        # после хлопка: пустая комната, только сверчок
        p = art.clamp(sub - 0.75)
        small = art.text_layer("цвырк…", 34, (200, 190, 180), weight=600, tracking=1.5)
        put(stage, small, cx=0.76 * W, top=int(0.62 * H),
            alpha=art.clamp(math.sin(p * 6) * 0.5 + 0.5) * 0.9)
    else:
        stage.alpha_composite(art.dust(stage, art.clamp(sub / 0.6), 0.5 * W, 0.62 * H,
                                       n=20, seed=8, spread=1.8, alpha=140), (0, 0))
        # ударная волна
        r = 90 + 900 * art.ease_io(art.clamp(sub / 0.6))
        ring = Image.new("RGBA", stage.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ring)
        a = int(180 * (1 - art.clamp(sub / 0.6)))
        d.ellipse([0.5 * W - r, 0.62 * H - r * 0.7, 0.5 * W + r, 0.62 * H + r * 0.7],
                  outline=(255, 255, 255, a), width=14)
        stage.alpha_composite(ring, (0, 0))


def scene_stern(stage, t, sub):
    """Мама требует уборку, ребёнок с ухмылкой слушает."""
    art.character("mom_stern", stage, cx=0.70 * W, baseline=BASELINE,
                  height=0.62 * H, t=t, phase=0.5, bob=8, rot=0.9,
                  pop=min(1, sub / 0.5))
    art.character("kid_smug", stage, cx=0.24 * W, baseline=BASELINE + 26,
                  height=0.40 * H, t=t, phase=2.1, bob=9, rot=1.2)
    b = art.bubble("А теперь —\nсобираем игрушки.", size=44, max_w=580)
    put(stage, b, cx=0.40 * W, top=int(0.185 * H),
        scale=art.lerp(0.72, 1.0, art.ease_out_back(pop_in(sub, 0.5))),
        alpha=art.smooth(pop_in(sub, 0.5, 0.2)))


def scene_smirk(stage, t, sub):
    """Крупный план: ухмылка и пауза перед ответом."""
    face = art.load_art(os.path.join(CHARS, "kid_face.png"))
    zoom = 1.02 + 0.05 * art.ease_io(sub / 3.1)
    im = art.resize(face, h=int(H * 1.06 * zoom))
    drift = math.sin(sub * 0.9) * 10
    stage.alpha_composite(im, (int(W / 2 - im.width / 2 + drift),
                               int(0.50 * H - im.height / 2)))
    # вопросики с «пружинкой»
    for i, (tt, q) in enumerate([(0.55, "?"), (1.15, "?")]):
        p = pop_in(sub, tt, 0.32)
        if p <= 0:
            continue
        col = (255, 205, 92) if i == 0 else (255, 138, 178)
        # светлая плашка-кружок, чтобы знак читался на любом фоне
        r = int(74 * art.lerp(0.5, 1.0, art.ease_out_back(p)))
        badge = Image.new("RGBA", (r * 2 + 16, r * 2 + 16), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge)
        bd.ellipse([8, 8, r * 2 + 8, r * 2 + 8], fill=CREAM + (255,), outline=INK + (255,),
                   width=8)
        ql = art.comic_text(q, int(r * 1.5), col, rot=-10 + i * 16, stroke_w=7)
        badge.alpha_composite(ql, (int(badge.width / 2 - ql.width / 2),
                                   int(badge.height / 2 - ql.height / 2)))
        put(stage, badge, cx=(0.84 - i * 0.13) * W, top=int((0.14 + i * 0.09) * H),
            alpha=p)
    # реплика «...» намёком
    if sub > 1.9:
        p = pop_in(sub, 1.9, 0.3)
        art.sparkle(stage, 0.14 * W, 0.30 * H + math.sin(t * 5) * 6, 22, alpha=int(190 * p))


def scene_point(stage, t, sub):
    """Палец в камеру и панчлайн."""
    pulse = 1 + 0.015 * math.sin(sub * 9)
    art.character("kid_point", stage, cx=0.5 * W, baseline=BASELINE + 70,
                  height=0.74 * H * pulse, t=t, bob=12, rot=1.4,
                  pop=min(1, sub / 0.35))
    stage.alpha_composite(art.speed_lines(stage.size, t, n=34, alpha=110, inner=0.26,
                                          seed=17, color=(255, 240, 200)), (0, 0))
    b = art.bubble("Нет. Мы же все знаем,\nчто это будешь\nделать ты.", size=50, max_w=760)
    put(stage, b, cx=0.5 * W, top=int(0.13 * H),
        scale=art.lerp(0.65, 1.0, art.ease_out_back(pop_in(sub, 0.45))),
        alpha=art.smooth(pop_in(sub, 0.45, 0.2)))


def scene_momwow(stage, t, sub):
    """Реакция мамы: «ТЁМА!»"""
    art.character("mom_shock", stage, cx=0.43 * W, baseline=BASELINE,
                  height=0.68 * H, t=t, bob=14, rot=2.4,
                  squash=0.02 * math.sin(sub * 22), pop=min(1, sub / 0.3))
    art.character("kid_point", stage, cx=0.84 * W, baseline=BASELINE + 20,
                  height=0.36 * H, t=t, phase=1.0, bob=10, rot=2.0)
    stage.alpha_composite(art.confetti(stage.size, sub * 0.3, n=18, seed=21,
                                       gravity=0.4), (0, 0))


def scene_end(stage, t, sub):
    """Финальная карточка."""
    art.character("kid_smug", stage, cx=0.52 * W, baseline=BASELINE + 120,
                  height=0.50 * H, t=t, bob=10, rot=1.2,
                  pop=min(1, sub / 0.45))
    t1 = art.comic_text("ПОДПИШИСЬ,", 108, tl.PALETTE["coral"], rot=-3)
    put(stage, t1, cx=0.5 * W, top=int(0.135 * H),
        scale=art.lerp(0.5, 1.0, art.ease_out_back(pop_in(sub, 0.15, 0.5))),
        alpha=art.smooth(pop_in(sub, 0.15, 0.25)))
    t2 = art.comic_text("ПОКА МАМА", 74, CREAM, rot=2)
    t3 = art.comic_text("УБИРАЕТ", 74, CREAM, rot=-2)
    put(stage, t2, cx=0.5 * W, top=int(0.245 * H),
        scale=art.lerp(0.5, 1.0, art.ease_out_back(pop_in(sub, 0.4, 0.45))),
        alpha=art.smooth(pop_in(sub, 0.4, 0.25)))
    put(stage, t3, cx=0.5 * W, top=int(0.305 * H),
        scale=art.lerp(0.5, 1.0, art.ease_out_back(pop_in(sub, 0.55, 0.45))),
        alpha=art.smooth(pop_in(sub, 0.55, 0.25)))
    p = pop_in(sub, 1.0, 0.35)
    put(stage, pill("СЕРИЯ 2 СКОРО", size=34, weight=800),
        cx=0.5 * W, top=int(0.915 * H),
        scale=art.lerp(0.7, 1.0, art.ease_out_back(p)), alpha=art.smooth(p))
    if sub > 0.9:
        for i, (x, y, r) in enumerate([(0.18, 0.24, 26), (0.84, 0.20, 20), (0.78, 0.66, 22)]):
            art.sparkle(stage, x * W, y * H + math.sin(t * 4 + i) * 8, r,
                        alpha=int(160 + 80 * math.sin(t * 6 + i)))


SCENE_FUNCS = {
    "ask": scene_ask, "ok": scene_ok, "aga": scene_aga, "party": scene_party,
    "mess": scene_mess, "slam": scene_slam, "stern": scene_stern,
    "smirk": scene_smirk, "point": scene_point, "momwow": scene_momwow, "end": scene_end,
}

# Настройки камеры и цвета по сценам: (zoom0, zoom1, ax, ay, sat, bright, shake)
CAMERA = {
    "ask":    (1.06, 1.14, 0.50, 0.62, 1.05, 1.02, 0),
    "ok":     (1.10, 1.04, 0.52, 0.58, 1.05, 1.02, 0),
    "aga":    (1.16, 1.02, 0.50, 0.58, 1.18, 1.06, 16),
    "party":  (1.14, 1.20, 0.50, 0.55, 1.24, 1.06, 10),
    "mess":   (1.34, 1.02, 0.50, 0.60, 1.10, 1.00, 22),
    "slam":   (1.16, 1.06, 0.50, 0.62, 1.02, 0.86, 26),
    "stern":  (1.10, 1.18, 0.52, 0.58, 1.04, 0.97, 0),
    "smirk":  (1.04, 1.16, 0.50, 0.34, 1.08, 0.94, 0),
    "point":  (1.16, 1.06, 0.50, 0.58, 1.14, 1.03, 4),
    "momwow": (1.12, 1.22, 0.46, 0.56, 1.16, 1.02, 18),
    "end":    (1.12, 1.05, 0.50, 0.60, 1.06, 1.03, 0),
}


def build_frame(t_global):
    # какая сцена активна
    scene = tl.SCENES[0]
    for sc in tl.SCENES:
        if sc["start"] <= t_global < sc["end"]:
            scene = sc
            break
    sub = t_global - scene["start"]
    span = scene["end"] - scene["start"]
    k = art.clamp(sub / max(span, 1e-6))

    cam = CAMERA[scene["id"]]
    z0, z1, ax, ay, sat, bright, sh = cam
    zoom = art.lerp(z0, z1, art.ease_io(k))

    # атмосфера по сцене
    name = scene["bg"]
    tint = None
    blur = 0.0
    if scene["id"] == "slam" and sub > 0.75:
        bright *= 0.72
    if scene["id"] == "smirk":
        blur = 16.0 * (1 - 0.3 * k)
        sat *= 0.9
    if scene["id"] == "momwow":
        tint = (255, 236, 232)
    if scene["id"] == "end":
        blur = 7.0

    # «АГА!» — лучи вместо комнаты
    if scene["id"] == "aga":
        bg = art.burst_layer((W + 2 * PAD, H + 2 * PAD), t_global,
                             (tl.PALETTE["coral"], tl.PALETTE["mustard"], (255, 214, 150)),
                             spin=0.35)
        bg = bg.convert("RGBA")
    else:
        bg = draw_bg((W + 2 * PAD, H + 2 * PAD), name, zoom=zoom, ax=ax, ay=ay,
                     sat=sat, bright=bright, tint=tint, blur=blur)

    stage = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    SCENE_FUNCS[scene["id"]](stage, t_global, sub)

    comic_overlay(stage, t_global)

    # тряска
    amp = sh * (1 - 0.55 * k) if sh else 0
    if scene["id"] == "slam":
        amp = 26 * (1 - art.clamp(sub / 0.8)) + 3
    if scene["id"] == "party":
        amp = 10 + 6 * math.sin(sub * 9)
    sx, sy = shake_amp(t_global, amp, seed=scene["start"])
    rot = 0.0
    if amp > 4:
        rot = math.sin(t_global * 19) * amp * 0.015

    out = compose(bg, stage, (sx, sy), rot).convert("RGBA")

    # вспышки на ударных склейках
    for ft, fw in [(7.95, 0.26), (12.80, 0.30), (15.45, 0.36), (28.85, 0.26), (21.20, 0.10)]:
        dt = t_global - ft
        if 0 <= dt < fw:
            out = flash(out, (1 - dt / fw) ** 2.2 * 0.8)
    if scene["id"] == "momwow":
        out = flash(out, 0.10 * max(0, math.sin(sub * 8)), (255, 120, 110))

    out = art.vignette(out, strength=0.34, power=2.6)
    return out.convert("RGB")


# ------------------------------------------------------------------ рендер
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", nargs="*", type=float, default=None)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "toys-cleanup.mp4"))
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.preview:
        for t in args.preview:
            img = build_frame(t)
            p = os.path.join(OUT_DIR, f"preview_{t:05.2f}.jpg")
            img.save(p, quality=93)
            print("  →", p)
        return

    from imageio_ffmpeg import get_ffmpeg_exe
    ffmpeg = get_ffmpeg_exe()
    n_frames = int(tl.TOTAL * tl.FPS)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(tl.FPS), "-i", "-",
        "-i", AUDIO_MIX,
        "-filter_complex",
        "[0:v]eq=saturation=1.02:contrast=1.01,format=yuv420p[v];"
        "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "20",
        "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
        "-g", str(tl.FPS * 2), "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{tl.TOTAL:.2f}", args.out,
    ]
    print(f"• рендер {n_frames} кадров -> {args.out}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n_frames):
            t = i / tl.FPS
            proc.stdin.write(build_frame(t).tobytes())
            if i % 90 == 0:
                print(f"  {i}/{n_frames}  ({t:5.1f} с)", flush=True)
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg exited with {code}")
    print("✓ готово:", args.out)


if __name__ == "__main__":
    main()
