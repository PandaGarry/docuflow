"""Рисовальные примитивы для карикатурного ролика.

Всё рисуется на PIL/numpy: комикс-текст с обводкой, речевые пузыри,
персонажи со сквош-стретчем и покачиванием, конфетти, спидлайны,
лучи-«бум», виньетка и тряска камеры.
"""

import functools
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import timeline as tl

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.normpath(os.path.join(HERE, "..", "..", "shared", "fonts"))
if not os.path.isdir(FONTS):
    FONTS = os.path.join(HERE, "assets", "fonts")

INK = tl.PALETTE["ink"]
CREAM = tl.PALETTE["cream"]


# ------------------------------------------------------------------ базовое
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_out_back(x, k=1.9):
    x = clamp(x) - 1
    return 1 + (k + 1) * x ** 3 + k * x ** 2


def ease_io(x):
    x = clamp(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def lerp(a, b, k):
    return a + (b - a) * k


@functools.lru_cache(maxsize=32)
def font(weight, size):
    return ImageFont.truetype(os.path.join(FONTS, f"Montserrat-{weight}.ttf"), size)


@functools.lru_cache(maxsize=64)
def load_art(path):
    return Image.open(path).convert("RGBA")


def resize(im, h=None, w=None):
    if h:
        return im.resize((max(1, int(im.width * h / im.height)), int(h)), Image.LANCZOS)
    return im.resize((int(w), max(1, int(im.height * w / im.width))), Image.LANCZOS)


# ------------------------------------------------------------------ текст
def comic_text(text, size, color, rot=0, stroke=INK, stroke_w=None, weight=900,
               shadow=True, tracking=1.0):
    """Крупный «мультяшный» текст: жирная обводка + смещённая тень под буквами."""
    fnt = font(weight, size)
    stroke_w = int(size * 0.10) if stroke_w is None else stroke_w
    tw = int(sum(fnt.getlength(c) for c in text) + tracking * max(len(text) - 1, 0)) + stroke_w * 2 + 12
    th = int(size * 1.42) + stroke_w * 2
    size_px = (max(tw, 8), max(th, 8))

    def draw_run(draw, dx, dy, fill, stroke_fill=None):
        x = stroke_w + 6 + dx
        for c in text:
            draw.text((x, dy), c, font=fnt, fill=fill,
                      stroke_width=stroke_w if stroke_fill else 0,
                      stroke_fill=stroke_fill)
            x += fnt.getlength(c) + tracking

    layer = Image.new("RGBA", size_px, (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", size_px, (0, 0, 0, 0))
        draw_run(ImageDraw.Draw(sh), size * 0.06, size * 0.11, INK + (255,), INK + (255,))
        sh = sh.filter(ImageFilter.GaussianBlur(size * 0.018))
        layer = Image.alpha_composite(layer, sh)

    # рисуем уже на итоговом слое — draw создаём после композитинга
    draw_run(ImageDraw.Draw(layer), 0, 0, color + (255,), stroke + (255,))

    if rot:
        layer = layer.rotate(rot, resample=Image.BICUBIC, expand=True)
    return layer


def text_layer(text, size, color, weight=700, stroke_w=0, stroke_fill=INK, tracking=0.0):
    fnt = font(weight, size)
    tw = int(sum(fnt.getlength(c) for c in text) + tracking * max(len(text) - 1, 0)) + 8
    th = int(size * 1.5) + stroke_w * 2
    layer = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x = 4
    for c in text:
        d.text((x, stroke_w), c, font=fnt, fill=color + (255,),
               stroke_width=stroke_w, stroke_fill=stroke_fill + (255,))
        x += fnt.getlength(c) + tracking
    return layer


def wrap(text, size, weight, max_w, tracking=0.0):
    fnt = font(weight, size)
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = (cur + " " + w).strip()
        width = sum(fnt.getlength(c) for c in probe) + tracking * max(len(probe) - 1, 0)
        if width <= max_w or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def bubble(text, size=46, max_w=620, weight=700, pad=38, tail=(0, 70), tail_w=58):
    """Речевой пузырь: скруглённая плашка + хвост, указывающий на говорящего."""
    tracking = 0.5
    lines = wrap(text, size, weight, max_w - pad * 2, tracking)
    fnt = font(weight, size)
    line_h = int(size * 1.34)
    tw = max(sum(fnt.getlength(c) for c in ln) + tracking * max(len(ln) - 1, 0) for ln in lines)
    tw = int(tw) + pad * 2
    th = line_h * len(lines) + pad * 2

    extra = int(abs(tail[1]) + tail_w + 24)
    W_ = tw + int(abs(tail[0])) + tail_w
    H_ = th + extra + 20
    layer = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    bx0, by0 = int(abs(tail[0]) / 2 + tail_w / 2), 8
    box = [bx0, by0, bx0 + tw, by0 + th]

    # хвост
    tx = bx0 + tw / 2 + tail[0]
    ty = by0 + th - 6
    tip = (tx + tail[0] * 0.5, ty + tail[1])
    poly = [(tx - tail_w / 2, ty - 4), (tx + tail_w / 2, ty - 4), tip]
    d.polygon(poly, fill=CREAM + (255,))
    d.line(poly[::1] + [poly[0]], fill=INK + (255,), width=7, joint="curve")

    # плашка
    radius = int(min(th / 2.2, 52))
    d.rounded_rectangle(box, radius=radius, fill=CREAM + (255,), outline=INK + (255,), width=7)
    # перекрыть стык хвоста с плашкой
    d.rounded_rectangle([box[0] + 4, box[1] + 4, box[2] - 4, box[3] - 4], radius=radius - 4,
                        outline=CREAM + (255,), width=7)
    d.rectangle([tx - tail_w / 2 + 6, ty - 10, tx + tail_w / 2 - 6, ty + 1], fill=CREAM + (255,))

    y = by0 + pad - int(size * 0.12)
    for ln in lines:
        lw = sum(fnt.getlength(c) for c in ln) + tracking * max(len(ln) - 1, 0)
        x = bx0 + (tw - lw) / 2
        for c in ln:
            d.text((x, y), c, font=fnt, fill=INK + (255,))
            x += fnt.getlength(c) + tracking
        y += line_h
    return layer


# ------------------------------------------------------------------ персонажи
def place(img, frame, cx, baseline, height, flip=False):
    im = resize(img, h=int(height))
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    frame.alpha_composite(im, (int(cx - im.width / 2), int(baseline - im.height)))
    return im


def character(name, frame, cx, baseline, height, t, phase=0.0, bob=10.0,
              rot=1.1, squash=0.0, flip=False, pop=None):
    """Персонаж с «дыханием», покачиванием и сквош-стретчем.

    pop: (прогресс 0..1) — анимация появления (подскок с overshoot).
    """
    img = load_art(os.path.join(HERE, "assets", "chars", f"{name}.png"))
    k = math.sin(t * 2.2 + phase)
    dy = k * bob
    ang = math.sin(t * 1.5 + phase * 1.7) * rot
    sy, sx = 1.0 - squash, 1.0 + squash * 0.55
    scale = 1.0
    if pop is not None:
        p = clamp(pop)
        scale = lerp(0.55, 1.0, ease_out_back(p))
        dy -= (1 - ease_io(p)) * 90
        sy *= lerp(1.12, 1.0, p)
    im = resize(img, h=max(1, int(height * scale * sy)))
    im = im.resize((max(1, int(im.width * sx)), im.height), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    if abs(ang) > 0.05:
        im = im.rotate(ang, resample=Image.BICUBIC, expand=True)
    frame.alpha_composite(im, (int(cx - im.width / 2), int(baseline + dy - im.height)))
    return im


def face_crop(name, h, box):
    """Крупный план: обрезаем верхнюю часть картинки с лицом."""
    img = load_art(os.path.join(HERE, "assets", "chars", f"{name}.png"))
    x0, y0, x1, y1 = box
    c = img.crop((int(img.width * x0), int(img.height * y0),
                  int(img.width * x1), int(img.height * y1)))
    return resize(c, h=int(h))


# ------------------------------------------------------------------ эффекты
def burst_layer(size, t, colors, cx=0.5, cy=0.5, rays=22, spin=0.12):
    """Лучи-«бум» для ударных кадров."""
    w, h = size
    layer = Image.new("RGBA", (w, h), colors[0] + (255,))
    d = ImageDraw.Draw(layer)
    R = int(math.hypot(w, h))
    ox, oy = w * cx, h * cy
    rot0 = t * spin
    for i in range(rays):
        a0 = rot0 + i * 2 * math.pi / rays
        a1 = a0 + math.pi / rays
        c = colors[1] if i % 2 == 0 else colors[2]
        d.polygon([(ox, oy),
                   (ox + R * math.cos(a0), oy + R * math.sin(a0)),
                   (ox + R * math.cos(a1), oy + R * math.sin(a1))], fill=c + (255,))
    return layer


def speed_lines(size, t, n=44, color=(255, 255, 255), alpha=120, cx=0.5, cy=0.5,
                seed=5, inner=0.22, rot=0.0):
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = np.random.default_rng(seed)
    R = math.hypot(w, h) / 2
    ox, oy = w * cx, h * cy
    for i in range(n):
        a = rng.uniform(0, 2 * math.pi) + rot
        r0 = R * inner * rng.uniform(0.8, 1.35)
        r1 = r0 + R * rng.uniform(0.16, 0.55)
        wdt = int(rng.uniform(3, 11))
        jitter = math.sin(t * 26 + i) * 5
        d.line([(ox + r0 * math.cos(a), oy + r0 * math.sin(a) + jitter),
                (ox + r1 * math.cos(a), oy + r1 * math.sin(a) + jitter)],
               fill=color + (int(alpha * rng.uniform(0.5, 1.0)),), width=wdt)
    return layer.filter(ImageFilter.GaussianBlur(1.0))


CONFETTI_COLORS = [(255, 96, 84), (240, 187, 76), (144, 220, 196), (96, 128, 255),
                   (255, 255, 255), (255, 150, 190)]


@functools.lru_cache(maxsize=8)
def confetti_field(seed, n):
    rng = np.random.default_rng(seed)
    return {
        "x": rng.uniform(0, 1, n),
        "delay": rng.uniform(0, 2.6, n),
        "speed": rng.uniform(0.35, 1.15, n),
        "size": rng.uniform(8, 26, n),
        "rot": rng.uniform(0, 360, n),
        "spin": rng.uniform(-320, 320, n),
        "sway": rng.uniform(20, 90, n),
        "color": rng.integers(0, len(CONFETTI_COLORS), n),
        "shape": rng.integers(0, 2, n),
    }


def confetti(size, t, n=90, seed=1, progress=1.0, gravity=1.0):
    w, h = size
    f = confetti_field(seed, n)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(n):
        tt = t - f["delay"][i]
        if tt < 0:
            continue
        live = clamp(tt * 0.9) * progress
        if live <= 0.02:
            continue
        y = -60 + tt * f["speed"][i] * 640 * gravity + 0.5 * 900 * tt * tt * 0.35 * gravity
        if y > h + 80:
            continue
        x = f["x"][i] * w + math.sin(tt * 2.4 + i) * f["sway"][i]
        s = f["size"][i]
        a = int(255 * min(1.0, live * 2))
        ang = f["rot"][i] + f["spin"][i] * tt
        c = CONFETTI_COLORS[f["color"][i]]
        if f["shape"][i] == 0:
            sq = Image.new("RGBA", (int(s * 2), int(s * 2)), (0, 0, 0, 0))
            ImageDraw.Draw(sq).rectangle([0, 0, s, s * 0.6], fill=c + (255,))
            sq = sq.rotate(ang, resample=Image.BICUBIC, expand=True)
            if a < 255:
                al = sq.split()[3].point(lambda v: int(v * a / 255))
                sq.putalpha(al)
            layer.alpha_composite(sq, (int(x), int(y)))
        else:
            d.ellipse([x, y, x + s * 0.7, y + s * 0.7], fill=c + (a,))
    return layer


def sparkle(frame, cx, cy, r, alpha=255, arms=4):
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for i in range(arms):
        a = i * math.pi / arms
        d.line([(cx - r * math.cos(a), cy - r * math.sin(a)),
                (cx + r * math.cos(a), cy + r * math.sin(a))],
               fill=(255, 246, 214, alpha), width=6)
    frame.alpha_composite(layer)


def vignette(frame, strength=0.55, power=2.4):
    w, h = frame.size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx / w - 0.5) * 2
    ny = (yy / h - 0.5) * 2
    r = np.sqrt(nx ** 2 + ny ** 2) / math.sqrt(2)
    m = np.clip(1 - strength * (r ** power), 0, 1)[..., None]
    arr = np.asarray(frame.convert("RGB"), np.float32) * m
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")


def grade(img, sat=1.0, brightness=1.0, contrast=1.0, tint=None):
    arr = np.asarray(img.convert("RGB"), np.float32) / 255.0
    arr = (arr - 0.5) * contrast + 0.5
    lum = arr @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    arr = lum[..., None] + (arr - lum[..., None]) * sat
    arr = arr * brightness
    if tint:
        arr = arr * (np.array(tint, np.float32) / 255.0)
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).convert("RGBA")


def dust(frame, t, cx, cy, n=14, seed=3, spread=1.0, alpha=110):
    rng = np.random.default_rng(seed)
    layer = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    tt = clamp(t)
    for i in range(n):
        a = rng.uniform(0, 2 * math.pi)
        dist = (60 + 320 * tt) * rng.uniform(0.5, 1.4) * spread
        r = (26 + 44 * tt) * rng.uniform(0.6, 1.3)
        x = cx + math.cos(a) * dist
        y = cy + math.sin(a) * dist * 0.62
        al = int(alpha * (1 - tt) * rng.uniform(0.5, 1.0))
        if al <= 0:
            continue
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 250, 240, al))
    return layer.filter(ImageFilter.GaussianBlur(6))
