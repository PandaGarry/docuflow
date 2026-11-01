#!/usr/bin/env python3
"""Плакаты прогрева: дизайн вокруг вырезки из мастера.

Герои здесь не генерируются (см. docs/34-IDENTITY-LOCK.md). Каждый режим —
это композиция из плоского фона, крупного шрифта и одного-трёх кадров канона:
силуэт, кроп лица, ростовой кадр.

    python studio/engine/promo_poster.py list
    python studio/engine/promo_poster.py all
    python studio/engine/promo_poster.py make announce --out /tmp/x.png
"""
from __future__ import annotations

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from promo_scene import INK, PAPER, SAGE, canon_heads, cutout, cutouts  # noqa: E402

STUDIO = os.path.dirname(HERE)
FONTS = os.path.join(STUDIO, "fonts")
OUT = os.path.join(STUDIO, "promo", "renders")

CORAL = "#FF6054"
MUSTARD = "#F0BB4C"
DEEP = "#1A1210"
KRAFT = "#C9A063"
MUTED = "#8A6A5E"

# метаданные последнего кадра: заголовок и его рамка — для verify
META = {}


def remember(title, x, baseline, width, size, lines=1):
    """Запоминает рамку заголовка, чтобы verify проверил safe-зоны."""
    META["title"] = title
    META["title_box"] = [round(x), round(baseline - size * 0.80),
                         round(x + width), round(baseline + size * (0.12 + 0.98 * (lines - 1)))]


# ------------------------------------------------------------------ шрифты
def fnt(size, weight=800, family="Montserrat"):
    path = os.path.join(FONTS, f"{family}-{weight}.ttf")
    return ImageFont.truetype(path, max(8, int(size)))


def fit(text, max_w, size, weight=800, family="Montserrat", min_size=18):
    """Кегль, при котором строка влезает в max_w."""
    while size > min_size:
        f = fnt(size, weight, family)
        if f.getlength(text) <= max_w:
            return f
        size -= 2
    return fnt(min_size, weight, family)


def tracked(draw, xy, text, font, fill, tracking=0, anchor="ls"):
    """Текст с разрядкой. Возвращает итоговую ширину."""
    x, y = xy
    if tracking == 0:
        draw.text((x, y), text, font=font, fill=fill, anchor=anchor)
        return font.getlength(text)
    total = sum(font.getlength(ch) for ch in text) + tracking * (len(text) - 1)
    if anchor[0] == "m":
        x -= total / 2
    elif anchor[0] == "r":
        x -= total
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="l" + anchor[1])
        x += font.getlength(ch) + tracking
    return total


# ------------------------------------------------------------------ фоны
def ground(W, H, top, bottom, noise=0.035):
    img = Image.new("RGB", (W, H), top)
    mask = Image.new("L", (1, H))
    for y in range(H):
        mask.putpixel((0, y), int(255 * (y / max(1, H - 1)) ** 1.15))
    img = Image.composite(Image.new("RGB", (W, H), bottom), img, mask.resize((W, H)))
    if noise:
        n = Image.effect_noise((W // 3, H // 3), 26).convert("L").resize((W, H))
        img = Image.blend(img, Image.merge("RGB", (n, n, n)), noise)
    return img


def glow(img, cx, cy, radius, color, strength=0.35):
    layer = Image.new("RGB", img.size, color)
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius * 0.55))
    mask = mask.point(lambda v: int(v * strength))
    return Image.composite(layer, img, mask)


# ------------------------------------------------------------------ герои
def _scaled(key, target_h):
    fig = cutout(key)
    k = target_h / fig.height
    return fig.resize((max(1, int(fig.width * k)), max(1, int(target_h))), Image.LANCZOS)


def heroes_row(plate, keys, dad_frac, base_frac, gap_frac=0.035, max_w=0.97):
    """Ростовые фигуры в ряд, высоты по канону голов, подошвы на одной линии."""
    H, W = plate.height, plate.width
    heads, book = canon_heads(), cutouts()
    figs = [_scaled(k, H * dad_frac * heads[book[k]["char"]] / heads["dad"]) for k in keys]
    gap = W * gap_frac
    total = sum(f.width for f in figs) + gap * (len(figs) - 1)
    if total > W * max_w:
        k = W * max_w / total
        figs = [f.resize((max(1, int(f.width * k)), max(1, int(f.height * k))), Image.LANCZOS)
                for f in figs]
        gap *= k
        total = sum(f.width for f in figs) + gap * (len(figs) - 1)
    x = (W - total) / 2
    boxes = []
    for f in figs:
        y = int(H * base_frac - f.height)
        plate.paste(f, (int(x), y), f)
        boxes.append((int(x), y, f.width, f.height))
        x += f.width + gap
    return boxes


def hero(plate, key, h_frac, base_frac, x_frac=0.5, align="center"):
    H, W = plate.height, plate.width
    f = _scaled(key, H * h_frac)
    y = int(H * base_frac - f.height)
    x = {"center": (W * x_frac - f.width / 2),
         "left": (W * x_frac),
         "right": (W * x_frac - f.width)}[align]
    plate.paste(f, (int(x), y), f)
    return int(x), y, f.width, f.height


def silhouette(key, color=DEEP):
    fig = cutout(key)
    out = Image.new("RGBA", fig.size, color)
    out.putalpha(fig.getchannel("A"))
    return out


def silhouettes(plate, keys, dad_frac, base_frac, gap_frac=0.03, color=DEEP):
    H, W = plate.height, plate.width
    heads, book = canon_heads(), cutouts()
    figs = [silhouette(k, color) for k in keys]
    figs = [f.resize((max(1, int(f.width * H * dad_frac * heads[book[k]["char"]] / heads["dad"] / f.height)),
                      max(1, int(H * dad_frac * heads[book[k]["char"]] / heads["dad"]))), Image.LANCZOS)
            for f, k in zip(figs, keys)]
    gap = W * gap_frac
    total = sum(f.width for f in figs) + gap * (len(figs) - 1)
    if total > W * 0.99:
        k = W * 0.99 / total
        figs = [f.resize((max(1, int(f.width * k)), max(1, int(f.height * k))), Image.LANCZOS)
                for f in figs]
        gap *= k
        total = sum(f.width for f in figs) + gap * (len(figs) - 1)
    x = (W - total) / 2
    for f in figs:
        plate.paste(f, (int(x), int(H * base_frac - f.height)), f)
        x += f.width + gap


def face_crop(key, side=None, zoom=1.45):
    """Квадратный кроп головы по альфе: высота головы из канона."""
    fig = cutout(key)
    bbox = fig.getbbox()
    heads = canon_heads()[cutouts()[key]["char"]]
    head_h = (bbox[3] - bbox[1]) / heads
    side = side or int(head_h * zoom)
    cx = (bbox[0] + bbox[2]) / 2
    cy = bbox[1] + head_h * 0.58
    box = [cx - side / 2, cy - side / 2, cx + side / 2, cy + side / 2]
    crop = Image.new("RGBA", (int(side), int(side)), (0, 0, 0, 0))
    src = fig.crop([int(box[0]), int(box[1]), int(box[2]), int(box[3])])
    crop.paste(src, (0, 0), src)
    return crop


def disc(img, size, fill=None):
    """Круглая маска поверх кропа."""
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if fill:
        ImageDraw.Draw(out).ellipse([0, 0, size - 1, size - 1], fill=fill)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    if img:
        out.paste(img.resize((size, size), Image.LANCZOS), (0, 0), mask)
    return out, mask


def head_disc(plate, key, diameter, cx, cy, ring=None, ring_w=None, bg=PAPER, zoom=None):
    """Круг с лицом героя: кроп мастера, обрезанный по кругу.

    Прозрачные поля кропа заливаются цветом подложки: иначе `paste` с маской
    берёт RGB прозрачных пикселей (чёрный) и внутри круга получается чернота.
    """
    d = int(diameter)
    crop = face_crop(key, zoom=zoom).resize((d, d), Image.LANCZOS)
    base = Image.new("RGBA", (d, d), bg)
    base.alpha_composite(crop)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    x, y = int(cx - d / 2), int(cy - d / 2)
    plate.paste(base.convert("RGB"), (x, y), mask)
    if ring:
        ImageDraw.Draw(plate).ellipse([x, y, x + d, y + d], outline=ring,
                                      width=ring_w or max(3, d // 40))


def wordmark(plate, x, y, color=INK, size=None, tracking=None):
    H = plate.height
    size = size or H * 0.017
    f = fnt(size)
    tracked(ImageDraw.Draw(plate), (x, y), "«ПЕРЕЕЗД» · С1", f, color,
            tracking if tracking is not None else size * 0.28)


# ------------------------------------------------------------------ режимы
def m_announce(W=1080, H=1350):
    """Анонс: горчичный плакат, крупное имя, трио по нижнему краю."""
    plate = ground(W, H, MUSTARD, "#E0A63C")
    d = ImageDraw.Draw(plate)
    k = fnt(H * 0.023)
    tracked(d, (W * 0.09, H * 0.095), "МУЛЬТСЕРИАЛ", k, INK, H * 0.006)
    f = fit("ПЕРЕЕЗД", W * 0.82, H * 0.155)
    tw = tracked(d, (W * 0.088, H * 0.245), "ПЕРЕЕЗД", f, INK, H * 0.004)
    remember("ПЕРЕЕЗД", W * 0.088, H * 0.245, tw, f.size)
    d.rectangle([W * 0.09, H * 0.268, W * 0.09 + W * 0.20, H * 0.268 + H * 0.010], fill=CORAL)
    sub = fnt(H * 0.026)
    d.text((W * 0.09, H * 0.322), "12 серий по 40 секунд", font=sub, fill=INK)
    d.text((W * 0.09, H * 0.362), "премьера — скоро", font=sub, fill="#6B4A3B")
    heroes_row(plate, ["dad:hips", "mom:stern", "son:point"], dad_frac=0.60, base_frac=1.005)
    return plate


def m_quote(W=1080, H=1350, key="dad:front", line1="Я всё", line2="продумал.",
            who="папа", tail="сезон 1 · скоро"):
    """Цитата: крупный текст сверху слева, герой стоит справа."""
    plate = ground(W, H, PAPER, "#F2E6D2", noise=0.02)
    d = ImageDraw.Draw(plate)
    d.rectangle([0, 0, W * 0.038, H], fill=CORAL)
    box = hero(plate, key, h_frac=0.72, base_frac=0.975, x_frac=0.99, align="right")
    tx = W * 0.115
    maxw = max(W * 0.42, box[0] - tx - W * 0.02)   # текст не заезжает на героя
    tracked(d, (tx, H * 0.115), "СЕЗОН 1 · СКОРО", fnt(H * 0.022), CORAL, H * 0.005)
    q = fnt(H * 0.15)
    d.text((tx, H * 0.20), "«", font=q, fill=MUSTARD, anchor="ls")
    f1 = fit(line1, maxw, H * 0.115)
    f2 = fit(line2, maxw, H * 0.115)
    d.text((tx, H * 0.335), line1, font=f1, fill=INK, anchor="ls")
    d.text((tx, H * 0.335 + f1.size * 1.04), line2, font=f2, fill=INK, anchor="ls")
    remember(f"{line1} {line2}", tx, H * 0.335, max(f1.getlength(line1), f2.getlength(line2)), f1.size, 2)
    y = H * 0.335 + f1.size * 1.04 + f2.size * 1.55
    d.text((tx, y), "— " + who.upper(), font=fnt(H * 0.024), fill=CORAL, anchor="ls")
    d.text((tx, H * 0.905), tail, font=fnt(H * 0.022), fill=MUTED, anchor="ls")
    wordmark(plate, tx, H * 0.957, MUTED)
    return plate


def m_silhouette(W=1080, H=1350):
    """Тизер: коралловый плакат, семья силуэтом, вопрос крупно."""
    plate = ground(W, H, CORAL, "#D8402F")
    plate = glow(plate, W * 0.5, H * 0.05, W * 0.9, "#FF8A6E", 0.45)
    silhouettes(plate, ["dad:front", "mom:front", "son:front"], dad_frac=0.72, base_frac=1.02)
    d = ImageDraw.Draw(plate)
    k = fnt(H * 0.023)
    tracked(d, (W * 0.075, H * 0.115), "ТЕПЕРЬ МЫ ЖИВЁМ ЗДЕСЬ", k, INK, H * 0.005)
    f = fit("кто", W * 0.70, H * 0.115)
    d.text((W * 0.072, H * 0.735), "кто", font=f, fill=PAPER, anchor="ls")
    f2 = fit("переезжает?", W * 0.828, H * 0.115)
    d.text((W * 0.072, H * 0.735 + f.size * 1.02), "переезжает?", font=f2, fill=PAPER, anchor="ls")
    remember("кто переезжает?", W * 0.072, H * 0.735, max(f.getlength("кто"), f2.getlength("переезжает?")), f.size, 2)

    return plate


def m_portrait(W=1080, H=1080, key="dad:front", name="ПАПА", tag="он всё продумал", ring=MUSTARD):
    """Карточка героя: круг с лицом мастера, имя, подпись."""
    plate = ground(W, H, PAPER, "#F4E8D4", noise=0.02)
    d = ImageDraw.Draw(plate)
    disc_d = W * 0.66
    color = {"ПАПА": MUSTARD, "МАМА": CORAL, "СЫН": SAGE}.get(name, MUSTARD)
    d.ellipse([(W - disc_d) / 2 - W * 0.02, H * 0.06, (W + disc_d) / 2 + W * 0.02,
               H * 0.06 + disc_d + W * 0.04], fill=color)
    zoom = {"СЫН": 1.95, "МАМА": 1.65}.get(name, 1.55)
    head_disc(plate, key, disc_d, W / 2, H * 0.06 + disc_d / 2 + W * 0.02, ring=PAPER,
              ring_w=int(W * 0.012), bg=color, zoom=zoom)
    f = fit(name, W * 0.80, H * 0.14)
    tw = tracked(d, (W / 2, H * 0.845), name, f, INK, H * 0.012, anchor="ms")
    remember(name, W / 2 - tw / 2, H * 0.845, tw, f.size)
    tracked(d, (W / 2, H * 0.895), tag.upper(), fnt(H * 0.026), MUTED, H * 0.004, anchor="ms")
    tracked(d, (W / 2, H * 0.955), "«ПЕРЕЕЗД» · С1", fnt(H * 0.019), "#B08D7C", H * 0.005,
            anchor="ms")
    return plate


def m_faces(W=1080, H=1350):
    """Знакомство: три круга с лицами, одна семья, три характера."""
    plate = ground(W, H, PAPER, "#F0E3CD", noise=0.02)
    d = ImageDraw.Draw(plate)
    tracked(d, (W / 2, H * 0.115), "ЗНАКОМЬТЕСЬ", fnt(H * 0.024), CORAL, H * 0.007, anchor="ms")
    trio = [("dad:front", "ПАПА", MUSTARD), ("mom:front", "МАМА", CORAL), ("son:front", "СЫН", SAGE)]
    dia = W * 0.265
    for i, (key, name, color) in enumerate(trio):
        cx = W * (0.205 + i * 0.295)
        cy = H * 0.33
        d.ellipse([cx - dia / 2 - W * 0.012, cy - dia / 2 - W * 0.012,
                   cx + dia / 2 + W * 0.012, cy + dia / 2 + W * 0.012], fill=color)
        head_disc(plate, key, dia, cx, cy, ring=PAPER, ring_w=int(W * 0.008), bg=color,
                  zoom={"dad:front": 1.75, "mom:front": 1.75, "son:front": 2.05}[key])
        tracked(d, (cx, cy + dia / 2 + H * 0.045), name, fnt(H * 0.024), INK, H * 0.006,
                anchor="ms")
    f = fit("одна семья", W * 0.86, H * 0.115)
    tw = tracked(d, (W / 2, H * 0.665), "одна семья", f, INK, H * 0.002, anchor="ms")
    f2 = fit("три характера", W * 0.86, H * 0.115)
    tw2 = tracked(d, (W / 2, H * 0.665 + f.size * 1.15), "три характера", f2, CORAL, H * 0.002,
                  anchor="ms")
    remember("одна семья · три характера", W / 2 - max(tw, tw2) / 2, H * 0.665,
             max(tw, tw2), f.size, 2)
    d.rectangle([W * 0.5 - W * 0.06, H * 0.905, W * 0.5 + W * 0.06, H * 0.905 + H * 0.008],
                fill=MUSTARD)
    tracked(d, (W / 2, H * 0.965), "мультсериал · скоро", fnt(H * 0.022), MUTED, H * 0.004,
            anchor="ms")
    return plate


def m_meme(W=1080, H=1080, key="dad:shrug", line="«ТУТ ВСЁ ВЛЕЗЕТ»", sub="папа · пять минут назад"):
    """Мем: плоский фон, крупная реплика сверху, герой снизу."""
    plate = ground(W, H, MUSTARD, "#E3A63B")
    hero(plate, key, h_frac=0.74, base_frac=1.0, x_frac=0.66, align="center")
    d = ImageDraw.Draw(plate)
    tracked(d, (W * 0.075, H * 0.10), "ПЕРЕЕЗД · МЕМ", fnt(H * 0.02), "#7A4E2D", H * 0.005)
    f = fit(line, W * 0.85, H * 0.115)
    d.text((W * 0.072, H * 0.235), line, font=f, fill=INK, anchor="ls")
    remember(line, W * 0.072, H * 0.235, f.getlength(line), f.size)
    d.rectangle([W * 0.075, H * 0.265, W * 0.075 + W * 0.18, H * 0.265 + H * 0.009], fill=CORAL)
    d.text((W * 0.075, H * 0.325), sub, font=fnt(H * 0.026), fill="#6B4A3B", anchor="ls")
    d.text((W * 0.075, H * 0.905), "12 коробок", font=fit("12 коробок", W * 0.4, H * 0.05),
           fill=INK, anchor="ls")
    d.text((W * 0.075, H * 0.955), "один папа", font=fnt(H * 0.024), fill="#6B4A3B", anchor="ls")
    return plate


MODES = {
    "announce": (m_announce, 1080, 1350, "Анонс: имя сериала и трио"),
    "quote": (m_quote, 1080, 1350, "Цитата: крупный текст + герой"),
    "silhouette": (m_silhouette, 1080, 1350, "Тизер: силуэты семьи"),
    "portrait": (m_portrait, 1080, 1080, "Карточка: круг с лицом"),
    "faces": (m_faces, 1080, 1350, "Знакомство: три лица"),
    "meme": (m_meme, 1080, 1080, "Мем: реплика + герой"),
}


def cmd_list(args):
    for name, (_, w, h, desc) in MODES.items():
        print(f"{name:12s} {w}×{h}  {desc}")


def sidecar(path, img, mode):
    """Паспорт кадра: формат, safe-зоны и рамка заголовка для verify."""
    import json
    from promo_scene import formats
    fmts = formats()
    key = next((k for k, v in fmts.items() if (v["w"], v["h"]) == img.size), None)
    if not key:
        return
    spec = fmts[key]
    safe = spec["safe"]
    data = {
        "format": key, "w": img.width, "h": img.height, "safe": safe,
        "anchor": "poster",
        "limits": [safe, safe, img.width - safe, img.height - safe],
        "title_box": META.get("title_box"),
        "ui_zones": [],
        "source": "studio/engine/promo_poster.py",
        "poster": mode,
        "title": META.get("title", ""),
    }
    if not data["title_box"]:
        return
    with open(os.path.splitext(path)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def cmd_make(args):
    fn, w, h, _ = MODES[args.mode]
    META.clear()
    kw = {k: v for k, v in vars(args).items()
          if k in ("key", "line", "line1", "line2", "sub", "who", "name", "tag") and v is not None}
    img = fn(**kw)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.convert("RGB").save(args.out)
    sidecar(args.out, img, args.mode)
    print(f"{args.out}  ({img.width}×{img.height})  {args.mode}")


BATCH = [
    ("warmup-01-announce", "announce", {}),
    ("warmup-02-quote", "quote", {}),
    ("warmup-03-silhouette", "silhouette", {}),
    ("warmup-04-portrait", "portrait", {}),
    ("warmup-05-faces", "faces", {}),
    ("warmup-06-meme", "meme", {}),
    # вариации на том же движке: другой герой, другая реплика
    ("warmup-07-quote-mom", "quote", {"key": "mom:stern", "line1": "Ты", "line2": "серьёзно?",
                                      "who": "мама"}),
    ("warmup-08-portrait-son", "portrait", {"key": "son:front", "name": "СЫН",
                                            "tag": "он всё понял"}),
    ("warmup-09-meme-facepalm", "meme", {"key": "dad:facepalm",
                                         "line": "«СЕЙЧАС НАЙДУ»",
                                         "sub": "папа · коробка №7"}),
]


def cmd_all(args):
    os.makedirs(OUT, exist_ok=True)
    for name, mode, kw in BATCH:
        fn, _, _, _ = MODES[mode]
        META.clear()
        img = fn(**kw)
        path = os.path.join(OUT, name + ".png")
        img.convert("RGB").save(path)
        sidecar(path, img, mode)
        print(f"{path}  ({img.width}×{img.height})")


def cmd_sheet(args):
    """Контакт-лист пачки прогрева."""
    from PIL import ImageDraw as _D
    f1, f2 = fnt(34), fnt(22)
    tiles, H = [], 660
    for name, mode, _kw in BATCH:
        im = Image.open(os.path.join(OUT, name + ".png")).convert("RGB")
        w = int(im.width * H / im.height)
        im = im.resize((w, H), Image.LANCZOS)
        t = Image.new("RGB", (w, H + 92), PAPER)
        t.paste(im, (0, 0))
        d = _D.Draw(t)
        fs, text = 32, MODES[mode][3]
        while fs > 16 and d.textlength(text, font=fnt(fs)) > w - 24:
            fs -= 2
        d.text((12, H + 12), text, font=fnt(fs), fill=INK)
        d.text((12, H + 54), name.replace("warmup-", "").upper(), font=f2, fill=(150, 120, 110))
        tiles.append(t)
    gap, pad, cols = 24, 30, 3
    rows = [tiles[i:i + cols] for i in range(0, len(tiles), cols)]
    W = max(sum(t.width for t in r) + gap * (len(r) + 1) for r in rows) + pad * 2
    Hh = sum(r[0].height for r in rows) + gap * (len(rows) - 1) + pad * 3
    sheet = Image.new("RGB", (W, Hh), INK)
    y = pad
    for r in rows:
        x = pad
        for t in r:
            sheet.paste(t, (x, y))
            x += t.width + gap
        y += r[0].height + pad
    out = args.out or os.path.join(OUT, "warmup-sheet.png")
    sheet.save(out)
    print(f"{out}  ({sheet.width}×{sheet.height})")


def main(argv=None):
    ap = argparse.ArgumentParser(description="плакаты прогрева сообщества")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="какие режимы есть")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("make", help="один плакат")
    p.add_argument("mode", choices=list(MODES))
    p.add_argument("--out", required=True)
    p.add_argument("--key", default=None, help="кадр из cutouts.json: dad:shrug, mom:stern …")
    p.add_argument("--line", default=None, help="реплика (quote/meme)")
    p.add_argument("--line1", default=None)
    p.add_argument("--line2", default=None)
    p.add_argument("--sub", default=None)
    p.add_argument("--who", default=None)
    p.add_argument("--name", default=None, help="подпись на карточке: ПАПА, МАМА, СЫН")
    p.add_argument("--tag", default=None, help="подпись под именем")
    p.set_defaults(func=cmd_make)

    p = sub.add_parser("all", help="вся пачка прогрева")
    p.set_defaults(func=cmd_all)

    p = sub.add_parser("sheet", help="контакт-лист пачки")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_sheet)

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
