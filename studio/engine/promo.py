"""Промо-конвейер сериала: замок идентичности, промпты, брифы, сборка креатива.

Зачем этот файл существует
--------------------------
Нарисовать промо-картинку моделью — это 20 % работы. Остальные 80 % — удержать
лицо и пропорции героя, попасть в размер площадки, не дать модели нарисовать
текст и не потерять заголовок в интерфейсе соцсети. Здесь эти 80 % закрыты
данными и командами, а не «на глаз».

Что читает
----------
* ``studio/promo/canon/identity.json`` — единственный источник текста о героях
  (identity-блоки, пропорции, запреты, палитра, костюмы);
* ``studio/promo/canon/formats.json`` — размеры площадок, безопасные зоны,
  «мёртвые» области интерфейса, правила кадрирования;
* ``studio/promo/campaign-s1.json`` — календарь кампании и тексты постов;
* мастера ``studio/characters/<id>/master/`` — референсы и замер пропорций.

Команды
-------
    python studio/engine/promo.py refs
    python studio/engine/promo.py prompt --format post-4x5 --cast dad,mom,son \\
        --scene "living room with half-unpacked moving boxes"
    python studio/engine/promo.py briefs
    python studio/engine/promo.py copy --channel telegram
    python studio/engine/promo.py compose art.png --format post-4x5 \\
        --kicker "СЕЗОН 1" --title "Папа всё продумал" --out studio/promo/renders/x.png
    python studio/engine/promo.py verify studio/promo/renders/x.png
    python studio/engine/promo.py check
    python studio/engine/promo.py plan

Только pillow и стандартная библиотека: ничего не нужно доустанавливать.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
PROMO = os.path.join(STUDIO, "promo")
CANON = os.path.join(PROMO, "canon")
REFS = os.path.join(PROMO, "refs")
BRIEFS = os.path.join(PROMO, "briefs")
COPY = os.path.join(PROMO, "copies")
OUT = os.path.join(PROMO, "renders")
CHARACTERS = os.path.join(STUDIO, "characters")
FONTS = os.path.join(STUDIO, "fonts")

IDENTITY = os.path.join(CANON, "identity.json")
FORMATS = os.path.join(CANON, "formats.json")
CAMPAIGN = os.path.join(PROMO, "campaign-s1.json")

PUBLISHED_STATES = ("idea", "brief", "art", "text", "ready", "published")


# ---------------------------------------------------------------- данные


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def identity():
    return load(IDENTITY)


def formats():
    return load(FORMATS)


def campaign():
    return load(CAMPAIGN)


def theme():
    return formats()["theme"]


def font(name, size):
    path = os.path.join(FONTS, name)
    if not os.path.exists(path):
        path = os.path.join(FONTS, "Montserrat-700.ttf")
    return ImageFont.truetype(path, size)


def slug(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-zа-яё0-9]+", "-", text, flags=re.I)
    return text.strip("-")[:40] or "creative"


# ------------------------------------------------- вырезание героя с хромакея


def green_key(img):
    """Маска фигуры: белое — герой, чёрное — хромакей #00B140."""
    r, g, b = img.convert("RGB").split()
    hi = g.point(lambda v: 255 if v > 80 else 0)
    dg_r = ImageChops.subtract(g, r).point(lambda v: 255 if v > 40 else 0)
    dg_b = ImageChops.subtract(g, b).point(lambda v: 255 if v > 40 else 0)
    bg = ImageChops.multiply(hi, ImageChops.multiply(dg_r, dg_b))
    return ImageChops.invert(bg)


def columns_occupied(mask):
    """Список занятых колонок — им режим лист на отдельные фигуры."""
    w, h = mask.size
    strip = mask.resize((w, 1), Image.BOX)
    return [i for i, v in enumerate(strip.tobytes()) if v > 8]


def split_runs(cols, min_len=40):
    runs = []
    if not cols:
        return runs
    start = prev = cols[0]
    for c in cols[1:]:
        if c - prev > 6:
            if prev - start >= min_len:
                runs.append((start, prev))
            start = c
        prev = c
    if prev - start >= min_len:
        runs.append((start, prev))
    return runs


def cutout(img, mask, box, erode=True):
    """RGBA-фигура по маске, обрезанная по box, с эрозией на 1 px (убирает кайму)."""
    alpha = mask.crop(box)
    if erode:
        alpha = alpha.filter(ImageFilter.MinFilter(3))
    figure = img.convert("RGBA").crop(box)
    figure.putalpha(alpha)
    bbox = figure.getbbox()
    return figure.crop(bbox) if bbox else figure


def head_metrics(figure):
    """Оценка высоты головы по узкому месту (шее) на профиле ширины силуэта.

    Возвращает (head_px, height_px, ratio). Это ИМЕННО оценка: борода папы,
    длинные волосы мамы и кепка сына искажают границу головы, поэтому число
    используется только как ориентир для QA кадра. Канонное число голов
    остаётся за ``character.json`` (height_heads).
    """
    w, h = figure.size
    alpha = figure.getchannel("A")
    rows = alpha.resize((1, h), Image.BOX).tobytes()
    widths = [v / 255.0 * w for v in rows]
    h = len(widths)
    top = next((i for i, v in enumerate(widths) if v > 2), 0)
    bottom = h - 1 - next((i for i, v in enumerate(reversed(widths)) if v > 2), 0)
    height = max(1, bottom - top)

    def smooth(y):
        lo, hi = max(0, y - 3), min(h, y + 4)
        chunk = sorted(widths[lo:hi])
        return sum(chunk) / len(chunk)

    lo_y = top + int(height * 0.10)
    hi_y = top + int(height * 0.42)
    best_y, best_w = None, 1e9
    for y in range(lo_y, hi_y):
        wv = smooth(y)
        if wv < best_w:
            best_y, best_w = y, wv
    if best_y is None:
        return None, height, None
    head_px = best_y - top
    return head_px, height, (head_px / height if height else None)


# --------------------------------------------------------------- команда refs


def cmd_refs(args):
    os.makedirs(REFS, exist_ok=True)
    canon = identity()
    lock = {"schema": 1, "comment": "Замер пропорций и контрольные точки. Собрано promo.py refs.", "characters": {}}
    fronts = {}

    for cid, char in canon["characters"].items():
        master_dir = os.path.join(STUDIO, char["refs"]["turnaround"])
        if not os.path.exists(master_dir):
            print(f"  ! {cid}: нет мастера {master_dir}")
            continue
        sheet = Image.open(master_dir)
        mask = green_key(sheet)
        runs = split_runs(columns_occupied(mask))
        if not runs:
            print(f"  ! {cid}: на листе не найдено фигур")
            continue
        picks = []
        for (x0, x1) in runs[:3]:
            band = mask.crop((max(0, x0 - 4), 0, min(sheet.width, x1 + 5), sheet.height))
            bbox = band.getbbox()
            if not bbox:
                continue
            box = (bbox[0] + max(0, x0 - 4), bbox[1], bbox[2] + max(0, x0 - 4), bbox[3])
            picks.append(cutout(sheet, mask, box))
        if not picks:
            continue
        front = picks[0]
        fronts[cid] = front

        # карточка тела: на кремовом фоне, а не на хромакее — иначе модель
        # приносит зелёный фон в промо-кадры
        paper = tuple(int(theme()["paper"][i:i + 2], 16) for i in (1, 3, 5))
        pad = int(front.height * 0.05)
        card = Image.new("RGB", (front.width + pad * 2, front.height + pad * 2), paper)
        card.paste(front, (pad, pad), front)
        card.save(os.path.join(REFS, f"{cid}-front.png"))

        face_path = os.path.join(STUDIO, char["refs"]["face"])
        if os.path.exists(face_path):
            face = Image.open(face_path)
            if face.mode != "RGBA":
                face = face.convert("RGBA")
            bbox = face.getbbox() or (0, 0, face.width, face.height)
            face = face.crop(bbox)
            side = max(face.size)
            # 8 % поля: генератору нужен воздух вокруг головы, иначе он «дорисовывает»
            # обрезанную макушку и меняет форму головы
            inner = int(side * 0.88)
            k = min(inner / face.width, inner / face.height)
            face = face.resize((max(1, int(face.width * k)), max(1, int(face.height * k))), Image.LANCZOS)
            sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(face, ((side - face.width) // 2, (side - face.height) // 2), face)
            sq = sq.resize((1024, 1024), Image.LANCZOS)
            plate = Image.new("RGB", (1024, 1024), paper)
            plate.paste(sq, (0, 0), sq)
            plate.save(os.path.join(REFS, f"{cid}-face.png"))

        head_px, height_px, ratio = head_metrics(front)
        lock["characters"][cid] = {
            "label": char["label"],
            "height_px": height_px,
            "silhouette_head_px": head_px,
            "silhouette_heads": round(height_px / head_px, 2) if head_px else None,
            "canon_heads": char["height_heads"],
            "silhouette_head_ratio": round(ratio, 4) if ratio else None,
            "note": "silhouette_* — оценка по силуэту (борода/волосы/кепка её искажают). Канон — canon_heads.",
            "front_card": f"promo/refs/{cid}-front.png",
            "face_card": f"promo/refs/{cid}-face.png",
            "locked": char["locked"],
        }
        print(f"  {cid:4s} {char['label']:5s} силуэт {height_px:4d} px · "
              f"голова ~{head_px:3d} px ({height_px / head_px:.2f} по силуэту, "
              f"канон {char['height_heads']})")

    # линейка семьи: головы одного размера, высоты — по канону
    if fronts:
        order = [c for c in canon["cast_rules"]["left_to_right"] if c in fronts]
        base_h = 900
        max_heads = max(canon["characters"][c]["height_heads"] for c in order)
        scaled = []
        for c in order:
            fig = fronts[c]
            target = int(base_h * canon["characters"][c]["height_heads"] / max_heads)
            k = target / fig.height
            scaled.append(fig.resize((max(1, int(fig.width * k)), target), Image.LANCZOS))
        gap = 70
        margin = 60
        total_w = sum(f.width for f in scaled) + gap * (len(scaled) - 1) + margin * 2
        total_h = max(f.height for f in scaled) + margin * 2
        paper = tuple(int(theme()["paper"][i:i + 2], 16) for i in (1, 3, 5))
        lineup = Image.new("RGB", (total_w, total_h), paper)
        x = margin
        for fig in scaled:
            lineup.paste(fig, (x, total_h - margin - fig.height), fig)
            x += fig.width + gap
        lineup.save(os.path.join(REFS, "family-lineup.png"))

        # подписанная версия — для документов и людей, не для модели
        labeled = lineup.copy()
        d = ImageDraw.Draw(labeled)
        f = font("Nunito-700.ttf", 34)
        x = margin
        for cid, fig in zip(order, scaled):
            cap = canon["characters"][cid]["label"]
            d.text((x, total_h - margin - fig.height - 44), cap, font=f, fill="#3B2A26")
            x += fig.width + gap
        labeled.save(os.path.join(REFS, "family-lineup-labeled.png"))

        # единый лист идентичности: трио + три лица — подаётся модели одним файлом
        faces = []
        for c in order:
            p = os.path.join(REFS, f"{c}-face.png")
            if os.path.exists(p):
                faces.append(Image.open(p).convert("RGB").resize((420, 420), Image.LANCZOS))
        rows = 1 + (1 if faces else 0)
        sheet_w = max(lineup.width, 420 * len(faces) + 40 * max(1, len(faces) - 1) if faces else lineup.width)
        sheet_h = lineup.height + (460 if faces else 0)
        sheet = Image.new("RGB", (sheet_w, sheet_h), paper)
        sheet.paste(lineup, ((sheet_w - lineup.width) // 2, 0))
        if faces:
            fx = (sheet_w - (len(faces) * 420 + (len(faces) - 1) * 40)) // 2
            for fimg in faces:
                sheet.paste(fimg, (fx, lineup.height + 20))
                fx += 460
        sheet.save(os.path.join(REFS, "identity-sheet.png"))
        lock["lineup"] = {
            "order": order,
            "file": "promo/refs/family-lineup.png",
            "sheet": "promo/refs/identity-sheet.png",
            "scale": "канонные height_heads: папа 5.9 · мама 5.7 · сын 4.4",
            "note": ("мастера нарисованы в разном масштабе (свой лист — свой кадр), "
                     "поэтому линейка нормируется по канону, а не по пикселям листа"),
        }
        print(f"  линейка семьи: promo/refs/family-lineup.png · лист идентичности: promo/refs/identity-sheet.png")

    with open(os.path.join(REFS, "lock.json"), "w", encoding="utf-8") as fh:
        json.dump(lock, fh, ensure_ascii=False, indent=2)
    print(f"  замер записан: promo/refs/lock.json")


# -------------------------------------------------------------- промпт-сборка


def wrap_plain(text, width):
    """Перенос по словам с сохранением явных переводов строки."""
    out = []
    for para in str(text).split("\n"):
        words, cur = para.split(), ""
        for w in words:
            if len(cur) + len(w) + 1 > width:
                out.append(cur)
                cur = w
            else:
                cur = f"{cur} {w}".strip()
        out.append(cur)
    return "\n".join(out)


def build_bg_prompt(fmt_key, scene, extra=""):
    """Промпт ТОЛЬКО для фона. Герои не генерируются — они берутся из мастеров.

    Это главное правило пайплайна: текстовый промпт не удерживает лицо, поэтому
    генерация остаётся только там, где идентичности нет — фон, свет, реквизит.
    """
    canon = identity()
    fmts = formats()["formats"]
    if fmt_key not in fmts:
        raise SystemExit(f"неизвестный формат: {fmt_key}. Есть: {', '.join(fmts)}")
    spec = fmts[fmt_key]
    parts = [
        ("STYLE", "Stylized volumetric 3D cartoon environment art, painterly textures, soft forms, "
                  "no harsh outlines, warm homely palette: cream walls (#FFF8EC), sage-green accents "
                  "(#8AA88A), mustard props (#F0BB4C), coral detail (#FF6054)."),
        ("SHOT", "Empty room plate for a promo poster. " + (scene.strip() or
                  "plain warm cream studio backdrop (#FFF8EC) with a soft floor shadow.")),
        ("LIGHT", canon["light_block"]),
        ("FRAMING", spec["framing"] + ". " + spec["prompt_note"] + "."),
        ("EMPTY", "The frame must be EMPTY: no people, no characters, no silhouettes of people, "
                  "no animals, no text, no letters, no signs, no logos, no watermark, "
                  "no handwriting or labels on props."),
    ]
    if extra:
        parts.insert(4, ("NOTES", extra.strip()))
    parts.append(("NEGATIVE", "no people, no hands, no face, no figures, no text, no letters, "
                             "no captions, no logo, no watermark, no neon colours, no photographic "
                             "realism, no busy clutter, no vignette, no lens flare"))
    out = []
    for tag, text in parts:
        out.append(f"[{tag}]")
        out.append(wrap_plain(text, 96))
        out.append("")
    return "\n".join(out).strip() + "\n"


def cutout_book():
    path = os.path.join(CANON, "cutouts.json")
    return load(path)["items"] if os.path.exists(path) else {}


def final_name(post):
    if post.get("art_mode") == "lineup":
        return f"studio/promo/renders/{post['id']}-lineup.png"
    return f"studio/promo/renders/{post['id']}-{post['format']}.png"


def scene_command(post, fmt_key):
    cast = post.get("art_cast") or []
    if post.get("art_mode") == "lineup":
        return (f".venv/bin/python studio/engine/promo_scene.py lineup --format {fmt_key} "
                f"--cast {','.join(cast)} --kicker \"{post.get('copy', {}).get('kicker', 'Линейка сезона')}\" "
                f"--dad {post.get('art_dad', 0.665):.2f} --baseline {post.get('art_baseline', 0.775):.2f} "
                f"--out {final_name(post)}")
    bg = post.get("art_bg")
    cmd = [".venv/bin/python studio/engine/promo_scene.py", "scene" if bg else "plate",
           "--format", fmt_key, "--cast", ",".join(cast)]
    if bg:
        cmd += ["--bg", "studio/" + bg.lstrip("studio/")]
    cmd += ["--dad", f"{post.get('art_dad', 0.80):.2f}",
            "--baseline", f"{post.get('art_baseline', 0.90):.2f}"]
    cmd += ["--out", f"studio/promo/renders/{post['id']}-art.png"]
    return " ".join(cmd)


def cmd_prompt(args):
    """Фон-промпт под формат. Героев не описываем — их берём из мастеров."""
    text = build_bg_prompt(args.format, args.scene or "", args.extra or "")
    if args.cast:
        book = cutout_book()
        lines = ["", "[ГЕРОИ — НЕ ГЕНЕРИРУЮТСЯ, БЕРУТСЯ ИЗ МАСТЕРОВ]"]
        for key in [c.strip() for c in args.cast.split(",") if c.strip()]:
            item = book.get(key)
            if item:
                lines.append(f"  {key:20s} {item.get('label', ''):34s} studio/{item['file']}")
            else:
                lines.append(f"  {key:20s} ! нет в cutouts.json — сначала рисуем кадр в библиотеку")
        text += "\n".join(lines) + "\n"
    if args.write:
        os.makedirs(os.path.dirname(os.path.abspath(args.write)), exist_ok=True)
        with open(args.write, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(args.write)
    else:
        print(text)


# ------------------------------------------------------------------- брифы


def cmd_briefs(args):
    os.makedirs(BRIEFS, exist_ok=True)
    canon = identity()
    fmts = formats()["formats"]
    camp = campaign()
    book = cutout_book()
    made = 0
    for post in camp["posts"]:
        spec = fmts[post["format"]]
        cast = post.get("cast") or []
        copy = post.get("copy", {})
        bg = post.get("art_bg")
        lines = [
            f"# {post['id']} · {copy.get('headline', post['kind'])}",
            "",
            f"- **Неделя:** {post['week']:+d} ({post.get('date_hint', '—')})",
            f"- **Канал:** {post.get('channel_label', post['channel'])}",
            f"- **Формат:** {spec['label']} · {spec['w']}×{spec['h']}",
            f"- **Герои:** {', '.join(canon['characters'][c]['label'] for c in cast)}",
            f"- **Цель поста:** {post.get('goal', '—')}",
            f"- **Статус:** {post.get('status', 'idea')}",
            "",
            "## Как собирается кадр",
            "",
            "Герои **не генерируются**: кадр собирается из мастер-файлов, поэтому лицо и",
            "пропорции совпадают с эталоном пиксель в пиксель.",
            "",
            "| кадр | что | файл |",
            "|------|-----|------|",
        ]
        for key in post.get("art_cast", []):
            item = book.get(key, {})
            lines.append(f"| `{key}` | {item.get('label', '—')} | `studio/{item.get('file', '—')}` |")
        lines += [
            "",
            "```bash",
            scene_command(post, post["format"]),
            "```",
            "",
            f"Компоновка: {post.get('art_layout', '—')}",
            "",
            f"Доказательство для приёмки: `.venv/bin/python studio/engine/promo_scene.py proof "
            f"{(post.get('art_cast') or ['dad:front'])[0]}`",
            "",
        ]
        if not bg:
            lines += ["## Фон", "",
                      "Плоская студия (бумага + шалфейная панель) — генерировать не нужно.", ""]
        else:
            lines += ["## Фон", "",
                      f"Плата: `studio/{bg}`. Если нужен другой — генерируем **только фон**:",
                      "", "```", build_bg_prompt(post["format"], post.get("scene", "")).rstrip(), "```", ""]
        if post.get("art_mode") == "lineup":
            lines += [
                "## Типографика",
                "",
                "Крупного заголовка нет: подписи и рост в головах рисует `lineup` под",
                "ногами фигур, кернинг — Montserrat. Кадр сдаётся сразу после `scene`.",
                "",
            ]
        else:
            lines += [
                "## Типографика",
                "",
                "```bash",
            f".venv/bin/python studio/engine/promo.py compose studio/promo/renders/{post['id']}-art.png \\",
            f"    --format {post['format']} --kicker \"…\" --title \"{copy.get('headline', '')[:40]}\" \\",
            f"    --plate --out studio/promo/renders/{post['id']}-{post['format']}.png",
            "```",
            "",
            "## Текст",
            "",
            f"**{copy.get('headline', '—')}**",
            "",
            copy.get("body", "—"),
            "",
            ("**Призыв:** " + copy["cta"]) if copy.get("cta") else "",
            "",
            ("**Хештеги:** " + " ".join(copy.get("hashtags", []))) if copy.get("hashtags") else "",
            "",
            "## Правила кадра",
            "",
            f"- Безопасная зона: {spec['safe']} px; «мёртвые» области: {spec['ui_comment']}",
            f"- Заголовок: до {spec['title_max_words']} слов, до {spec['title_max_lines']} строк.",
            f"- {spec['title_rules']}",
            "- Текст — только нашим слоем, модель кириллицу не рисует.",
            "",
        ]
        path = os.path.join(BRIEFS, f"{post['id']}-{slug(copy.get('headline', post['kind']))}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        made += 1
    print(f"брифов собрано: {made} → studio/promo/briefs/")


# --------------------------------------------------------------- тексты


def cmd_copy(args):
    os.makedirs(COPY, exist_ok=True)
    camp = campaign()
    limits = camp.get("channel_limits", {})
    groups = {}
    for post in camp["posts"]:
        if args.channel != "all" and post["channel"] != args.channel:
            continue
        groups.setdefault(post["week"], []).append(post)
    lines = [f"# Тексты кампании · {camp['meta']['title']}", "",
             "_Собрано `studio/engine/promo.py copy`. Источник — `studio/promo/campaign-s1.json`, "
             "правки вносить туда, иначе файл перезапишется._", ""]
    for week in sorted(groups):
        lines += [f"## Неделя {week:+d}", ""]
        for post in groups[week]:
            copy = post.get("copy", {})
            body = copy.get("body", "")
            lim = limits.get(post["channel"], 0)
            warn = f"  \n> ⚠️ длина {len(body)} символов, лимит площадки {lim}" if lim and len(body) > lim else ""
            lines += [
                f"### {post['id']} · {post.get('channel_label', post['channel'])} · {post.get('date_hint', '')}",
                "",
                f"**{copy.get('headline', '—')}**",
                "",
                body,
                "",
                (f"**{copy['cta']}**" if copy.get("cta") else ""),
                "",
                (" ".join(copy.get("hashtags", [])) if copy.get("hashtags") else ""),
                warn,
                "",
                "---",
                "",
            ]
    name = f"{args.channel}.md" if args.channel != "all" else "all.md"
    path = os.path.join(COPY, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(path)


# --------------------------------------------------------------- сборка


def hexrgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def track_text(draw, xy, text, fnt, fill, track=0):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + track
    return x


def text_width(fnt, text, track=0):
    return sum(fnt.getlength(ch) for ch in text) + track * max(0, len(text) - 1)


def wrap_px(text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = f"{cur} {w}".strip()
        if text_width(fnt, probe) <= max_w or not cur:
            cur = probe
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_title(text, font_name, max_w, max_h, max_lines, top=110):
    size = top
    while size > 24:
        fnt = font(font_name, size)
        lines = wrap_px(text, fnt, max_w)
        needed = len(lines) * size * 1.12
        if len(lines) <= max_lines and needed <= max_h:
            return fnt, lines, size
        size -= 4
    fnt = font(font_name, 24)
    return fnt, wrap_px(text, fnt, max_w)[:max_lines], 24


def ui_inset(spec, edge):
    """Сколько пикселей от края занимает интерфейс площадки (кнопки, плашки)."""
    W, H = spec["w"], spec["h"]
    inset = 0
    for (x0, y0, x1, y1) in spec["ui"]:
        # учитываем только «полосы» у самого края, а не прямоугольники,
        # которые просто касаются края углом
        if edge == "bottom" and y1 >= H - 1 and (x1 - x0) >= W * 0.5:
            inset = max(inset, H - y0)
        if edge == "top" and y0 <= 0 and (x1 - x0) >= W * 0.5:
            inset = max(inset, y1)
        if edge == "left" and x0 <= 0 and (y1 - y0) >= H * 0.5:
            inset = max(inset, x1)
        if edge == "right" and x1 >= W - 1 and (y1 - y0) >= H * 0.5:
            inset = max(inset, W - x0)
    return inset


def cmd_compose(args):
    fmts = formats()
    if args.format not in fmts["formats"]:
        raise SystemExit(f"неизвестный формат: {args.format}")
    spec = fmts["formats"][args.format]
    th = fmts["theme"]
    W, H = spec["w"], spec["h"]
    safe = args.safe if args.safe is not None else spec["safe"]
    paper, accent, accent2 = hexrgb(th["paper"]), hexrgb(th["accent"]), hexrgb(th["accent2"])

    # ── 1. арт: cover-кроп под формат
    art = Image.open(args.art).convert("RGB")
    k = max(W / art.width, H / art.height)
    art = art.resize((max(W, int(art.width * k + 0.5)), max(H, int(art.height * k + 0.5))), Image.LANCZOS)
    left = (art.width - W) // 2
    top = (art.height - H) // 2
    if args.focus:
        fx, fy = args.focus
        left = int(max(0, min(art.width - W, fx * art.width - W / 2)))
        top = int(max(0, min(art.height - H, fy * art.height - H / 2)))
    base = art.crop((left, top, left + W, top + H))

    # ── 2. границы контента: safe-зона И интерфейс площадки
    m = int(H * 0.02)
    top_lim = max(safe, ui_inset(spec, "top")) + m
    bottom_lim = H - max(safe, ui_inset(spec, "bottom")) - m
    left_lim = max(safe, ui_inset(spec, "left"))
    right_lim = W - max(safe, ui_inset(spec, "right"))
    text_w = right_lim - left_lim - 24

    brand_h = 0 if args.no_brand else 46
    brand_top = bottom_lim - brand_h
    stack_bottom = brand_top - (18 if brand_h else 0)

    kicker_h = 84 if args.kicker else 0
    sub_h = (48 * 2) if args.sub else 0
    fixed = kicker_h + sub_h + (40 if (args.kicker or args.title) else 0)
    title_h = max(120, min(int(H * 0.30), stack_bottom - top_lim - fixed))

    title_font, title_lines, size = fit_title(args.title or "", th["fonts"]["title"],
                                              text_w, title_h, spec["title_max_lines"],
                                              top=min(132, int(H * 0.115)))
    title_block = int(len(title_lines) * size * 1.12)
    stack_h = fixed + title_block

    y0 = top_lim if args.anchor == "top" else stack_bottom - stack_h

    has_text = bool(args.kicker or args.title or args.sub)
    # ── 3. scrim: без него контраст на светлом кадре не гарантирован
    scrim = Image.new("L", (1, H), 0)
    band = max(stack_h + 140, int(H * 0.40))
    for y in range(H):
        d = (y / band) if args.anchor == "top" else ((H - y) / band)
        d = 1.0 - max(0.0, min(1.0, d))
        scrim.putpixel((0, y), int(212 * (d ** 1.35)))
    if has_text:
        scrim = scrim.resize((W, H))
        layer = Image.new("RGB", (W, H), hexrgb(th["scrim"]))
        base = Image.composite(layer, base, scrim)

    # ── 4. текст (при --plate сначала считаем ширину, потом рисуем подложку)
    fk = font(th["fonts"]["kicker"], 34) if args.kicker else None
    fs = font(th["fonts"]["body"], 36) if args.sub else None
    kicker_txt = args.kicker.upper() if args.kicker else ""
    kicker_w = (min(text_w, text_width(fk, kicker_txt, track=3) + 44) if fk else 0)
    probe = ImageDraw.Draw(base)
    title_w = max((probe.textlength(line, font=title_font) for line in title_lines), default=0)
    sub_lines = wrap_px(args.sub, fs, text_w)[:2] if fs else []
    sub_w = max((probe.textlength(line, font=fs) for line in sub_lines), default=0)
    block_w = max(kicker_w, title_w, sub_w)

    if args.plate:
        pad_p = 30
        px0 = left_lim - pad_p
        py0 = y0 - pad_p
        px1 = min(right_lim + pad_p, left_lim + block_w + pad_p * 2)
        py1 = min(bottom_lim + pad_p, y0 + stack_h + pad_p)
        if brand_h:
            py1 = max(py1, brand_top + 46 + 10)
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([px0 + 6, py0 + 8, px1 + 6, py1 + 8],
                                                 radius=34, fill=(0, 0, 0, 70))
        shadow = shadow.filter(ImageFilter.GaussianBlur(10))
        base = Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")
        plate = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(plate).rounded_rectangle([px0, py0, px1, py1], radius=32,
                                               fill=hexrgb(th["scrim"]) + (168,))
        base = Image.alpha_composite(base.convert("RGBA"), plate).convert("RGB")

    draw = ImageDraw.Draw(base)
    y = y0
    y_start = y0

    if args.kicker:
        draw.rounded_rectangle([left_lim, y, left_lim + kicker_w, y + 58], radius=29, fill=accent)
        track_text(draw, (left_lim + 22, y + 12), kicker_txt, fk, paper, track=3)
        y += 58 + 26

    for line in title_lines:
        draw.text((left_lim + 3, y + 5), line, font=title_font, fill=(0, 0, 0))
        draw.text((left_lim, y), line, font=title_font, fill=paper)
        y += int(size * 1.12)

    if args.kicker or args.title:
        draw.rounded_rectangle([left_lim, y + 6, left_lim + 96, y + 16], radius=5, fill=accent2)
        y += 40

    if args.sub:
        for line in sub_lines:
            draw.text((left_lim + 2, y + 3), line, font=fs, fill=(0, 0, 0))
            draw.text((left_lim, y), line, font=fs,
                      fill=tuple(int(c * 0.9 + 255 * 0.1) for c in paper))
            y += 48

    if brand_h:
        fb = font(th["fonts"]["brand"], 28)
        bw = text_width(fb, args.brand.upper(), track=2) + 34
        draw.rounded_rectangle([left_lim, brand_top, left_lim + bw, brand_top + 46], radius=23,
                               fill=(0, 0, 0))
        track_text(draw, (left_lim + 17, brand_top + 8), args.brand.upper(), fb, paper, track=2)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    base.save(args.out)
    side = {
        "format": args.format, "w": W, "h": H, "safe": safe,
        "anchor": args.anchor,
        "limits": [left_lim, top_lim, right_lim, bottom_lim],
        "title_box": [left_lim, int(y_start), right_lim, int(y)],
        "ui_zones": spec["ui"],
        "source": os.path.abspath(args.art),
        "title": args.title, "kicker": args.kicker, "plate": bool(args.plate),
    }
    with open(os.path.splitext(args.out)[0] + ".json", "w", encoding="utf-8") as fh:
        json.dump(side, fh, ensure_ascii=False, indent=2)
    print(f"{args.out}  ({W}×{H})")


# --------------------------------------------------------------- проверка


def cmd_verify(args):
    fmts = formats()["formats"]
    ok = True
    for path in args.files:
        print(f"— {path}")
        if not os.path.exists(path):
            print("  FAIL файла нет")
            ok = False
            continue
        if os.path.basename(path).endswith("-art.png"):
            print("  skip промежуточный арт без типографики (проверяется только финал)")
            continue
        img = Image.open(path)
        side_path = os.path.splitext(path)[0] + ".json"
        side = load(side_path) if os.path.exists(side_path) else None
        key = side["format"] if side else None
        if not key:
            match = [k for k, v in fmts.items() if (v["w"], v["h"]) == img.size]
            key = match[0] if match else None
        if not key:
            print(f"  FAIL размер {img.width}×{img.height} не совпадает ни с одним форматом")
            ok = False
            continue
        spec = fmts[key]
        if (img.width, img.height) != (spec["w"], spec["h"]):
            print(f"  FAIL {key}: ждали {spec['w']}×{spec['h']}, получили {img.width}×{img.height}")
            ok = False
        else:
            print(f"  ok   формат {key} · {spec['w']}×{spec['h']}")
        size_mb = os.path.getsize(path) / 1048576
        print(f"  {'ok  ' if size_mb <= 8 else 'WARN'} вес {size_mb:.2f} МБ (лимит площадок ~8 МБ)")
        if side:
            lx0, ty0, lx1, by1 = side.get("limits", [0, 0, spec["w"], spec["h"]])
            x0, y0, x1, y1 = side["title_box"]
            if x0 < lx0 - 1 or x1 > lx1 + 1 or y0 < ty0 - 1 or y1 > by1 + 1:
                print(f"  WARN заголовок выходит за границы контента {[lx0, ty0, lx1, by1]}")
                ok = False
            hits = []
            for (ux0, uy0, ux1, uy1) in spec["ui"]:
                if x0 < ux1 and x1 > ux0 and y0 < uy1 and y1 > uy0:
                    hits.append((ux0, uy0, ux1, uy1))
            if hits:
                print(f"  FAIL заголовок попадает в интерфейсную область: {hits}")
                ok = False
            else:
                print("  ok   заголовок вне интерфейсных областей")
        else:
            print("  WARN нет sidecar .json — проверены только размер и вес")
    print("ИТОГ:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


# --------------------------------------------------------- консистентность


def cmd_check(args):
    canon = identity()
    fmts = formats()["formats"]
    camp = campaign()
    limits = camp.get("channel_limits", {})
    problems = 0

    def bad(msg):
        nonlocal problems
        problems += 1
        print(f"  FAIL {msg}")

    ids = set()
    for post in camp["posts"]:
        pid = post.get("id", "?")
        if pid in ids:
            bad(f"{pid}: повтор id")
        ids.add(pid)
        if not re.match(r"^P\d{2}$", pid):
            bad(f"{pid}: id должен быть вида P01")
        for cid in post.get("cast", []):
            if cid not in canon["characters"]:
                bad(f"{pid}: неизвестный герой {cid}")
        if len(post.get("cast", [])) > canon["cast_rules"]["max_in_frame"]:
            bad(f"{pid}: больше {canon['cast_rules']['max_in_frame']} героев в кадре")
        if post.get("format") not in fmts:
            bad(f"{pid}: неизвестный формат {post.get('format')}")
        if post.get("status") not in PUBLISHED_STATES:
            bad(f"{pid}: статус {post.get('status')} не из {PUBLISHED_STATES}")
        copy = post.get("copy") or {}
        if not copy.get("headline"):
            bad(f"{pid}: нет заголовка")
        body = copy.get("body", "")
        if not body:
            bad(f"{pid}: нет текста")
        lim = limits.get(post.get("channel"))
        if lim and len(body) > lim:
            bad(f"{pid}: текст {len(body)} символов > лимита {post.get('channel')} ({lim})")
        for word in ("уникальн", "инновацион", "синерг", "контент-маркет"):
            if word in (copy.get("headline", "") + body).lower():
                bad(f"{pid}: канцелярит/штамп «{word}» — см. docs/32-TONE-AND-COPY.md")

    weeks = sorted({p["week"] for p in camp["posts"]})
    print(f"  ok   постов {len(camp['posts'])}, недели {weeks[0]:+d}…{weeks[-1]:+d}")
    print(f"  ok   героев в замке {len(canon['characters'])}, форматов {len(fmts)}")
    for path in ("promo/refs/identity-sheet.png", "promo/refs/family-lineup.png"):
        if not os.path.exists(os.path.join(STUDIO, path)):
            print(f"  WARN нет {path} — запустите `promo.py refs`")
    print("ИТОГ:", "PASS" if problems == 0 else f"FAIL ({problems})")
    return 0 if problems == 0 else 1


def cmd_plan(args):
    camp = campaign()
    print(f"# {camp['meta']['title']}\n")
    print("| id | нед. | день | канал | формат | герои | заголовок | статус |")
    print("|----|------|------|-------|--------|-------|-----------|--------|")
    for post in sorted(camp["posts"], key=lambda p: p["id"]):
        cast = "+".join(c[0].upper() for c in post["cast"])
        print(f"| {post['id']} | {post['week']:+d} | {post.get('day', '—')} | "
              f"{post.get('channel_label', post['channel'])} | {post['format']} | {cast} | "
              f"{post.get('copy', {}).get('headline', '')} | {post.get('status', '')} |")


# ------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(description="промо-конвейер: референсы, промпты, брифы, креативы")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("refs", help="карточки идентичности и линейка семьи")
    p.set_defaults(func=cmd_refs)

    p = sub.add_parser("prompt", help="промпт для ФОНА (герои не генерируются)")
    p.add_argument("--format", required=True)
    p.add_argument("--scene", default="")
    p.add_argument("--cast", default="", help="необязательно: показать, какие кадры взять из мастеров")
    p.add_argument("--extra", default="")
    p.add_argument("--write", default="")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("briefs", help="брифы по всем постам кампании")
    p.set_defaults(func=cmd_briefs)

    p = sub.add_parser("copy", help="человекочитаемая подборка текстов")
    p.add_argument("--channel", default="all", choices=["all", "telegram", "vk", "youtube"])
    p.set_defaults(func=cmd_copy)

    p = sub.add_parser("compose", help="наложить типографику на готовый арт")
    p.add_argument("art")
    p.add_argument("--format", required=True)
    p.add_argument("--kicker", default="")
    p.add_argument("--title", default="")
    p.add_argument("--sub", default="")
    p.add_argument("--brand", default="«ПЕРЕЕЗД» · С1")
    p.add_argument("--no-brand", action="store_true")
    p.add_argument("--anchor", default="bottom", choices=["bottom", "top"])
    p.add_argument("--safe", type=int, default=None)
    p.add_argument("--focus", nargs=2, type=float, default=None, metavar=("X", "Y"))
    p.add_argument("--plate", action="store_true", help="подложка под текст (для пёстрых кадров)")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser("verify", help="проверить размеры, вес и безопасные зоны")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("check", help="проверить данные кампании и канона")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("plan", help="календарь таблицей")
    p.set_defaults(func=cmd_plan)

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
