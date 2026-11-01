"""Сборка промо-кадров из мастеров: герой — пиксели эталона, генерация — только фон.

Почему так, а не «сгенерировать картинку по промпту»
----------------------------------------------------
Текстовый промпт не удерживает лицо. Модель каждый раз рисует «похожего, но
другого» героя: меняются глаза, форма бороды, пропорции. Для сериала это брак,
потому что зритель узнаёт героя по лицу, а не по описанию.

Поэтому в промо-кадре герой берётся **вырезанным из мастер-файла** и не
перерисовывается вообще. Масштаб выставляется по канону голов
(`characters/<id>/character.json`), подошвы ставятся на общую линию, под ноги
идёт контактная тень. Фон — либо плоская бумага студии, либо сгенерированная
(или нарисованная) плата без людей: там идентичности нет, и генерация безопасна.

Команды
-------
    python studio/engine/promo_scene.py list
    python studio/engine/promo_scene.py plate --format square --cast mom:stern \\
        --out studio/promo/renders/P03-art.png
    python studio/engine/promo_scene.py scene --format post-4x5 \\
        --cast dad:hips,mom:stern,son:point --bg studio/promo/plates/room.png \\
        --out studio/promo/renders/P01-art.png
    python studio/engine/promo_scene.py cards
    python studio/engine/promo_scene.py proof dad:front
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
FONT = os.path.join(STUDIO, "fonts", "Montserrat-800.ttf")
PROMO = os.path.join(STUDIO, "promo")
CANON = os.path.join(PROMO, "canon")
OUT = os.path.join(PROMO, "renders")
PLATES = os.path.join(PROMO, "plates")
CHARACTERS = os.path.join(STUDIO, "characters")

CUTOUTS = os.path.join(CANON, "cutouts.json")
IDENTITY = os.path.join(CANON, "identity.json")
FORMATS = os.path.join(CANON, "formats.json")

PAPER = "#FFF8EC"
SAGE = "#8AA88A"
INK = "#3B2A26"


# ------------------------------------------------------------------ данные


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def cutouts():
    return load_json(CUTOUTS)["items"]


def identity():
    return load_json(os.path.join(CANON, "identity.json"))


def canon_heads():
    data = load_json(IDENTITY)["characters"]
    return {cid: char["height_heads"] for cid, char in data.items()}


def formats():
    return load_json(FORMATS)["formats"]


def char_json(cid):
    return load_json(os.path.join(CHARACTERS, cid, "character.json"))


# ------------------------------------------------------------- вырезание


def chroma_key(img):
    """Маска фигуры для плоского фона #00B140."""
    r, g, b = img.convert("RGB").split()
    hi = g.point(lambda v: 255 if v > 80 else 0)
    dg_r = ImageChops.subtract(g, r).point(lambda v: 255 if v > 40 else 0)
    dg_b = ImageChops.subtract(g, b).point(lambda v: 255 if v > 40 else 0)
    return ImageChops.invert(ImageChops.multiply(hi, ImageChops.multiply(dg_r, dg_b)))


def despill(rgba):
    """Убирает зелёную кайму по краю: g не больше максимума из r и b."""
    r, g, b, a = rgba.split()
    mask = ImageChops.multiply(
        ImageChops.subtract(g, r).point(lambda v: 255 if v > 18 else 0),
        ImageChops.subtract(g, b).point(lambda v: 255 if v > 18 else 0),
    )
    capped = ImageChops.darker(g, ImageChops.lighter(r, b))
    g = Image.composite(capped, g, mask)
    return Image.merge("RGBA", (r, g, b, a))


def cutout(key):
    """RGBA-фигура по ключу из cutouts.json, обрезанная по содержимому."""
    items = cutouts()
    if key not in items:
        raise SystemExit(f"нет кадра «{key}». Доступно: {', '.join(sorted(items))}")
    path = os.path.join(STUDIO, items[key]["file"])
    if not os.path.exists(path):
        raise SystemExit(f"нет файла {path}")
    img = Image.open(path)
    if items[key]["kind"] == "alpha" and img.mode == "RGBA" and img.getchannel("A").getextrema()[0] < 250:
        bbox = img.getchannel("A").getbbox()
        fig = img.crop(bbox)
    else:
        mask = chroma_key(img)
        bbox = mask.getbbox()
        alpha = mask.crop(bbox).filter(ImageFilter.MinFilter(3))
        fig = img.convert("RGBA").crop(bbox)
        fig.putalpha(alpha)
        fig = despill(fig)
        fig = fig.crop(fig.getbbox())
    return fig


# --------------------------------------------------------------- построение


def cover(img, W, H, focus=None):
    k = max(W / img.width, H / img.height)
    img = img.resize((max(W, int(img.width * k + 0.5)), max(H, int(img.height * k + 0.5))), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    if focus:
        fx, fy = focus
        left = int(max(0, min(img.width - W, fx * img.width - W / 2)))
        top = int(max(0, min(img.height - H, fy * img.height - H / 2)))
    return img.crop((left, top, left + W, top + H))


def studio_background(W, H, band="right", floor=True, band_h=0.86, floor_line=True):
    """Фон студии: бумага + шалфейная панель, как на мастер-листах."""
    bg = Image.new("RGB", (W, H), PAPER)
    grad = Image.new("L", (1, H), 0)
    for y in range(H):
        grad.putpixel((0, y), int(26 * (y / max(1, H - 1)) ** 1.5))
    bg = Image.composite(Image.new("RGB", (W, H), "#EADFCB"), bg, grad.resize((W, H)))
    d = ImageDraw.Draw(bg)
    band_w = int(W * 0.34)
    x0 = W - band_w if band == "right" else (0 if band == "left" else -1)
    if x0 >= 0:
        d.rectangle([x0, 0, x0 + band_w, int(H * band_h)], fill=SAGE)
    if floor:
        floor_y = int(H * 0.86)
        grad = Image.new("L", (1, H), 0)
        for y in range(H):
            if y >= floor_y:
                t = (y - floor_y) / max(1, H - floor_y)
                grad.putpixel((0, y), int(52 * t))
        grad = grad.resize((W, H))
        warm = Image.new("RGB", (W, H), "#E7DCC8")
        bg = Image.composite(warm, bg, grad)
        if floor_line:
            d = ImageDraw.Draw(bg)
            d.line([0, floor_y, W, floor_y], fill="#DCCFB6", width=2)
    return bg


def _shadow_ellipse(plate, cx, base_y, w, h, blur, opacity, color="#3A2A20"):
    """Один слой тени. Поле вокруг эллипса обязательно: иначе blur обрезается."""
    w, h = max(8, int(w)), max(6, int(h))
    pad = max(6, int(blur * 2.2))
    mask = Image.new("L", (w + pad * 2, h + pad * 2), 0)
    ImageDraw.Draw(mask).ellipse([pad, pad, pad + w - 1, pad + h - 1], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    mask = mask.point(lambda v: int(v * opacity))
    plate.paste(Image.new("RGB", mask.size, color),
                (int(cx - mask.width / 2), int(base_y - h / 2 - pad)), mask)


def contact_shadow(plate, cx, base_y, width, strength=1.0):
    """Тень контакта, два слоя.

    Одна широкая размытая тень не держит фигуру: герой «висит» над полом.
    Нужны две — узкое плотное пятно прямо под стопами (контакт) и мягкое
    окружение вокруг (ambient occlusion). Тогда фигура стоит, а не наклеена.
    """
    # 1. контакт: узко, плотно, почти без размытия
    _shadow_ellipse(plate, cx, base_y + width * 0.012,
                    width * 0.46, width * 0.085, max(3, width * 0.012),
                    0.55 * strength)
    # 2. окружение: шире, светлее, сильно размыто
    _shadow_ellipse(plate, cx, base_y + width * 0.03,
                    width * 0.86, width * 0.16, max(10, width * 0.05),
                    0.22 * strength)


def place(plate, figs, heads, base_y, dad_h, gap_frac=0.055, min_scale=0.35):
    """Ставит героев на общую линию подошв.

    В группе высоты считаются по канону голов (папа 5.9 · мама 5.7 · сын 4.4).
    Соло-кадр масштабируется «по кадру»: иначе сын занимает треть кадра, и
    карточка выглядит пустой.
    """
    W = plate.width
    dad_heads = heads["dad"]
    solo = len(figs) == 1
    scaled, total = [], 0
    for fig, cid in figs:
        target = dad_h if solo else dad_h * heads[cid] / dad_heads
        k = target / fig.height
        new = fig.resize((max(1, int(fig.width * k)), max(1, int(target))), Image.LANCZOS)
        scaled.append(new)
        total += new.width
    gap = int(W * gap_frac)
    total += gap * (len(scaled) - 1)
    if total > W * 0.94:
        k = W * 0.94 / total
        scaled = [f.resize((max(1, int(f.width * k)), max(1, int(f.height * k))), Image.LANCZOS) for f in scaled]
        total = int(total * k)
        gap = int(gap * k)
    x = (W - total) // 2
    boxes = []
    for fig in scaled:
        y = int(base_y - fig.height)
        contact_shadow(plate, x + fig.width / 2, base_y, fig.width)
        plate.paste(fig, (x, y), fig)
        boxes.append((x, y, fig.width, fig.height))
        x += fig.width + gap
    return boxes


def build(fmt, cast, bg_path=None, band="right", focus=None, dad_frac=0.80,
          baseline=0.90, floor=True, floor_line=True):
    spec = formats()[fmt]
    W, H = spec["w"], spec["h"]
    if bg_path:
        plate = cover(Image.open(bg_path).convert("RGB"), W, H, focus)
    else:
        plate = studio_background(W, H, band=band, floor=floor, floor_line=floor_line)
    figs = [(cutout(key), cutouts()[key]["char"]) for key in cast]
    heads = canon_heads()
    dad_h = H * dad_frac
    place(plate, figs, heads, base_y=H * baseline, dad_h=dad_h)
    return plate


# ------------------------------------------------------------------ команды


def cmd_list(args):
    items = cutouts()
    by_char = {}
    for key, item in items.items():
        by_char.setdefault(item["char"], []).append((key, item.get("label", ""), item["kind"]))
    for cid in ("dad", "mom", "son"):
        print(f"{cid}:")
        for key, label, kind in sorted(by_char.get(cid, [])):
            mark = "альфа" if kind == "alpha" else "хромакей"
            print(f"  {key:20s} {label:34s} {mark}")


def cmd_plate(args):
    cast = [c.strip() for c in args.cast.split(",") if c.strip()]
    plate = build(args.format, cast, args.bg, args.band, args.focus, args.dad, args.baseline)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    plate.save(args.out)
    print(f"{args.out}  ({plate.width}×{plate.height})  {', '.join(cast)}")


def cmd_scene(args):
    cmd_plate(args)


def cmd_lineup(args):
    """Линейка семьи: фигуры на одной линии, подписи под ногами, без крупного текста."""
    spec = formats()[args.format]
    W, H = spec["w"], spec["h"]
    plate = studio_background(W, H, band="right", floor=False, band_h=1.0)
    cast = [c.strip() for c in args.cast.split(",") if c.strip()]
    book, heads = cutouts(), canon_heads()
    labels = {cid: ch["label"].upper() for cid, ch in identity()["characters"].items()}
    figs = [(cutout(k), book[k]["char"]) for k in cast]
    base_y = H * args.baseline
    boxes = place(plate, figs, heads, base_y=base_y, dad_h=H * args.dad)
    draw = ImageDraw.Draw(plate, "RGBA")
    ink = (59, 42, 38), (140, 110, 100), (240, 187, 76)
    left = max(0, boxes[0][0] - int(W * 0.03))
    right = min(W, boxes[-1][0] + boxes[-1][2] + int(W * 0.03))
    draw.line([(left, int(base_y)), (right, int(base_y))], fill=ink[0] + (70,), width=3)
    f_name = ImageFont.truetype(FONT, int(H * 0.036))
    f_sub = ImageFont.truetype(FONT, int(H * 0.022))
    for (x, y, w, h), (fig, cid) in zip(boxes, figs):
        cx = x + w / 2
        draw.line([(int(cx), int(base_y)), (int(cx), int(base_y) + int(H * 0.012))],
                  fill=ink[2] + (255,), width=5)
        name = labels.get(cid, cid.upper())
        ty = base_y + H * 0.028
        tw = draw.textlength(name, font=f_name)
        draw.text((cx - tw / 2, ty), name, font=f_name, fill=ink[0])
        sub = f"{heads[cid]:.1f} головы".replace(".", ",")
        sw = draw.textlength(sub, font=f_sub)
        draw.text((cx - sw / 2, ty + H * 0.05), sub, font=f_sub, fill=ink[0])
    f_kick = ImageFont.truetype(FONT, int(H * 0.024))
    draw.text((int(W * 0.07), int(H * 0.06)), args.kicker.upper(), font=f_kick, fill=(255, 96, 84))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    plate.save(args.out)
    print(f"{args.out}  ({plate.width}×{plate.height})  {', '.join(cast)}")


def cmd_cards(args):
    """Карточки героев: фигура стоит на полу студии, подпись внизу.

    Пол обязателен: без линии горизонта и градиента фигура «летит» над бумагой,
    даже если тень есть.
    """
    labels = {cid: ch["label"] for cid, ch in identity()["characters"].items()}
    jobs = [("dad", "dad:front"), ("mom", "mom:front"), ("son", "son:front")]
    os.makedirs(OUT, exist_ok=True)
    for cid, key in jobs:
        plate = build("post-4x5", [key], band="none", dad_frac=0.76, baseline=0.88,
                      floor=True, floor_line=False)
        d = ImageDraw.Draw(plate)
        name = labels[cid].upper()
        f = ImageFont.truetype(FONT, int(plate.height * 0.052))
        d.text((plate.width * 0.085, plate.height * 0.945), name, font=f,
               fill=INK, anchor="ls")
        d.rectangle([plate.width * 0.085, plate.height * 0.962,
                     plate.width * 0.085 + plate.width * 0.13,
                     plate.height * 0.962 + plate.height * 0.006], fill="#FF6054")
        out = os.path.join(OUT, f"card-{cid}.png")
        plate.save(out)
        print(f"{out}  ({plate.width}×{plate.height})  {key}")


def cmd_sheet(args):
    """Контакт-лист партии: кадры в два ряда с подписями."""
    rows = [
        [("P01", "Мультсериал про свою семью", "4:5 · Telegram + VK", "P01-post-4x5.png", 700),
         ("P05", "Линейка семьи", "4:5 · знакомство с героями", "P05-lineup.png", 700),
         ("P08", "Дата премьеры", "4:5 · афиша", "P08-post-4x5.png", 700)],
        [("P02", "Папа", "1:1 · карточка", "P02-square.png", 520),
         ("P03", "Мама", "1:1 · карточка", "P03-square.png", 520),
         ("P04", "Сын", "1:1 · карточка", "P04-square.png", 520),
         ("P10", "Открывашка Shorts", "9:16 · YouTube", "P10-shorts-cover.png", 520)],
    ]
    f1, f2 = ImageFont.truetype(FONT, 34), ImageFont.truetype(FONT, 22)
    gap, lbl, pad = 26, 96, 34
    built = []
    for row in rows:
        tiles = []
        for pid, title, fmt, name, h in row:
            path = os.path.join(OUT, name)
            if not os.path.exists(path):
                raise SystemExit(f"нет кадра: {path}")
            im = Image.open(path).convert("RGB")
            w = int(im.width * h / im.height)
            im = im.resize((w, h), Image.LANCZOS)
            t = Image.new("RGB", (w, h + lbl), PAPER)
            t.paste(im, (0, 0))
            d = ImageDraw.Draw(t)
            fs, text = 34, f"{pid} · {title}"
            while fs > 18 and d.textlength(text, font=ImageFont.truetype(FONT, fs)) > w - 26:
                fs -= 2
            d.text((14, h + 14 + (34 - fs) // 2), text, font=ImageFont.truetype(FONT, fs), fill=INK)
            d.text((14, h + 58), fmt, font=f2, fill=(150, 120, 110))
            tiles.append(t)
        W = sum(t.width for t in tiles) + gap * (len(tiles) + 1)
        band = Image.new("RGB", (W, tiles[0].height + gap), PAPER)
        x = gap
        for t in tiles:
            band.paste(t, (x, gap))
            x += t.width + gap
        built.append(band)
    W = max(b.width for b in built) + pad * 2
    H = sum(b.height for b in built) + pad * (len(built) + 1)
    sheet = Image.new("RGB", (W, H), INK)
    y = pad
    for b in built:
        sheet.paste(b, (pad, y))
        y += b.height + pad
    out = args.out or os.path.join(OUT, "_batch-proof.png")
    sheet.save(out)
    print(f"{out}  ({sheet.width}×{sheet.height})")


def cmd_proof(args):
    """Доказательство: в кадре тот же рисунок, что в мастере (сравнение «глаза в глаза»)."""
    items = cutouts()
    key = args.key
    item = items[key]
    fig = cutout(key)
    k = args.scale
    card_fig = fig.resize((max(1, int(fig.width * k)), max(1, int(fig.height * k))), Image.LANCZOS)

    # силуэт: альфа карточки — это альфа мастера, масштабированная (не перерисованная)
    a = fig.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    b = card_fig.getchannel("A").point(lambda v: 255 if v > 128 else 0)
    b = b.resize(a.size, Image.LANCZOS).point(lambda v: 255 if v > 128 else 0)
    inter = ImageChops.multiply(a, b)
    union = ImageChops.lighter(a, b)
    iou = sum(inter.histogram()[255:]) / max(1, sum(union.histogram()[255:]))

    face_h = int(fig.height * 0.30)
    face = fig.crop((0, 0, fig.width, face_h))
    card_face = card_fig.crop((0, 0, card_fig.width, int(face_h * k)))
    ZOOM_H = 460

    def fit(im, h):
        kk = h / im.height
        return im.resize((max(1, int(im.width * kk)), h), Image.LANCZOS)

    lf, rf = fit(face, ZOOM_H), fit(card_face, ZOOM_H)
    GAP, PAD, HEAD = 60, 40, 64
    W = PAD * 2 + lf.width + GAP + rf.width
    H = PAD + HEAD + ZOOM_H + 40
    proof = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(proof)
    proof.paste(lf, (PAD, PAD + HEAD), lf)
    proof.paste(rf, (PAD + lf.width + GAP, PAD + HEAD), rf)
    try:
        from PIL import ImageFont
        f = ImageFont.truetype(os.path.join(STUDIO, "fonts", "Montserrat-800.ttf"), 26)
    except Exception:
        f = None
    d.text((PAD, 24), f"МАСТЕР · {item['file']}", fill=INK, font=f)
    d.text((PAD + lf.width + GAP, 24), f"ТО ЖЕ В КАДРЕ · масштаб {k:.2f}", fill=INK, font=f)
    d.line([PAD + lf.width + GAP // 2, PAD + HEAD, PAD + lf.width + GAP // 2, H - 20], fill="#D8CBB4", width=2)
    out = os.path.join(OUT, f"_proof-{key.replace(':', '-')}.png")
    proof.save(out)
    print(out)
    print(f"  источник: {item['file']}  ({fig.width}×{fig.height})")
    print(f"  масштаб в кадре: {k:.2f} · поворот и отражение не применялись")
    print(f"  совпадение силуэта с мастером: {iou * 100:.2f} %")
    print("  глаза, брови, борода, чёлка, кепка — пиксели мастера, не генерация")


def main(argv=None):
    ap = argparse.ArgumentParser(description="сборка промо-кадров из мастеров")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="какие кадры героев доступны")
    p.set_defaults(func=cmd_list)

    for name, func, help_text in (("plate", cmd_plate, "собрать кадр из мастеров"),
                                  ("scene", cmd_scene, "то же, с фоном из файла")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--format", required=True)
        p.add_argument("--cast", required=True, help="dad:hips,mom:stern,son:point")
        p.add_argument("--bg", default=None, help="фон без людей (jpg/png)")
        p.add_argument("--band", default="right", choices=["right", "left", "none"])
        p.add_argument("--focus", nargs=2, type=float, default=None, metavar=("X", "Y"))
        p.add_argument("--dad", type=float, default=0.80, help="высота папы в долях кадра")
        p.add_argument("--baseline", type=float, default=0.90, help="линия подошв в долях кадра")
        p.add_argument("--out", required=True)
        p.set_defaults(func=func)

    p = sub.add_parser("lineup", help="линейка семьи: фигуры + подписи под ногами")
    p.add_argument("--format", default="post-4x5")
    p.add_argument("--cast", required=True)
    p.add_argument("--kicker", default="Линейка сезона")
    p.add_argument("--dad", type=float, default=0.62)
    p.add_argument("--baseline", type=float, default=0.72)
    p.add_argument("--names", default="")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_lineup, bg=None, band="right", focus=None)

    p = sub.add_parser("cards", help="три карточки героев (P02, P03, P04)")
    p.set_defaults(func=cmd_cards)

    p = sub.add_parser("sheet", help="контакт-лист партии")
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_sheet)

    p = sub.add_parser("proof", help="сравнить кадр с мастером")
    p.add_argument("key")
    p.add_argument("--scale", type=float, default=0.8)
    p.set_defaults(func=cmd_proof)

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
