"""Рендер ролика iPad Air: кадры на PIL/numpy -> ffmpeg.

Пайплайн:
  1. каждая сцена: цветокор, unsharp, скримы для читаемости титров;
  2. движение камеры (Ken Burns) по кривой ease-in-out;
  3. титры с трекингом, свечением и кинетическим появлением;
  4. переходы: кроссфейд + световой «клин» + лёгкая хроматика;
  5. финальная плашка с хромированным логотипом и блик-свипом;
  6. ffmpeg: зерно, виньетка, финальная цветокоррекция, звук.

Запуск: python scripts/render.py [--preview 3.2 8.5 ...]
"""

import argparse
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as tl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENES_DIR = os.path.join(HERE, "assets", "scenes")
FONTS_DIR = os.path.join(HERE, "assets", "fonts")
OUT_DIR = os.path.join(HERE, "out")
AUDIO_MIX = os.path.join(HERE, "audio", "mix.wav")

W, H = tl.W, tl.H
MARGIN = 76
FADE = tl.FADE

_font_cache = {}


def font(weight, size):
    key = (weight, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(
            os.path.join(FONTS_DIR, f"Montserrat-{weight}.ttf"), size)
    return _font_cache[key]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease_io(x):
    x = clamp(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def lerp(a, b, k):
    return a + (b - a) * k


# ------------------------------------------------------------------ цветокор
GRADES = {
    "cool":    {"sat": 1.10, "contrast": 1.10, "tint": (232, 240, 255), "shadows": (12, 18, 34)},
    "warm":    {"sat": 1.12, "contrast": 1.14, "tint": (255, 244, 232), "shadows": (26, 16, 10)},
    "neutral": {"sat": 1.06, "contrast": 1.06, "tint": (250, 248, 245), "shadows": (16, 16, 18)},
    "vivid":   {"sat": 1.22, "contrast": 1.16, "tint": (255, 240, 255), "shadows": (20, 10, 30)},
}


def grade_image(img, kind):
    g = GRADES[kind]
    arr = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0

    # контраст вокруг середины
    arr = (arr - 0.5) * g["contrast"] + 0.5
    lum = arr @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    # насыщенность
    arr = lum[..., None] + (arr - lum[..., None]) * g["sat"]
    lum = np.clip(lum, 0, 1)
    # тон в светах
    w = (np.clip(lum - 0.55, 0, 1) / 0.45)[..., None]
    arr = arr + (np.array(g["tint"], np.float32) / 255.0 - 0.5) * w * 0.10
    # цвет в тенях
    s = (np.clip(0.5 - lum, 0, 1) / 0.5)[..., None]
    arr = arr + np.array(g["shadows"], np.float32) / 255.0 * s * 0.30
    # плотный чёрный
    arr = np.clip(arr, 0, 1) ** 1.06
    out = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    return out.filter(ImageFilter.UnsharpMask(radius=2.4, percent=88, threshold=3))


# ------------------------------------------------------------------ тексты
def tracked_len(text, fnt, tracking):
    return sum(fnt.getlength(c) for c in text) + tracking * max(len(text) - 1, 0)


def draw_tracked(draw, xy, text, fnt, fill, tracking=0.0, anchor_left=True):
    x, y = xy
    if not anchor_left:
        x -= tracked_len(text, fnt, tracking) / 2
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += fnt.getlength(ch) + tracking


def text_layer(lines, fnts, fill, tracking, line_gap, align="left", width=None):
    """Рендер многострочного текста в RGBA-слой с обрезкой по содержимому."""
    widths = [tracked_len(line, fnt, tracking) for line, fnt in zip(lines, fnts)]
    total_w = max(widths) + 8
    line_h = [f.getbbox("HQd")[3] - f.getbbox("HQd")[1] for f in fnts]
    total_h = sum(line_h) + line_gap * (len(lines) - 1) + 16
    layer = Image.new("RGBA", (int(total_w), int(total_h)), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    y = 4
    for i, (line, fnt) in enumerate(zip(lines, fnts)):
        lw = tracked_len(line, fnt, tracking)
        x = 4 if align == "left" else (total_w - lw) / 2
        draw_tracked(d, (x, y), line, fnt, fill, tracking)
        y += line_h[i] + line_gap
    return layer


def composite_soft(base, layer, pos, alpha=1.0, shadow=True):
    if alpha <= 0.002:
        return base
    lay = layer
    if alpha < 1:
        a = lay.split()[3].point(lambda v: int(v * alpha))
        lay = lay.copy()
        lay.putalpha(a)
    if shadow:
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        dark = Image.new("RGBA", lay.size, (0, 0, 0, 200))
        dark.putalpha(lay.split()[3].point(lambda v: int(v * 0.55)))
        dark = dark.filter(ImageFilter.GaussianBlur(14))
        sh.paste(dark, (pos[0] + 2, pos[1] + 6), dark)
        base = Image.alpha_composite(base, sh)
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    out.paste(lay, pos, lay)
    return Image.alpha_composite(base, out)


def text_with_glow(frame, layer, pos, color, alpha, radius=28, strength=0.3):
    """Аддитивное свечение вокруг текста + сам текст с мягкой тенью."""
    if alpha <= 0.002:
        return frame
    gc = Image.new("L", (W, H), 0)
    gc.paste(layer.split()[3], pos)
    gc = gc.filter(ImageFilter.GaussianBlur(radius))
    g = (np.asarray(gc, np.float32) / 255.0 * alpha * strength)[..., None]
    arr = np.asarray(frame.convert("RGB"), np.float32) / 255.0
    arr = arr + g * (np.array(color, np.float32) / 255.0)
    frame = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).convert("RGBA")
    return composite_soft(frame, layer, pos, alpha)


# ------------------------------------------------------------------ сцена
class Scene:
    def __init__(self, spec):
        self.s = spec
        self.start = spec["start"]
        self.end = spec["end"]
        self.dur = self.end - self.start
        self.zoom0, self.zoom1, self.pan0, self.pan1 = spec["motion"]

        src = Image.open(os.path.join(SCENES_DIR, spec["image"])).convert("RGB")
        # рабочее разрешение: с запасом под максимальный зум
        big_h = int(H * max(self.zoom0, self.zoom1) * 1.06)
        big_w = int(big_h * src.width / src.height)
        if big_w < W * max(self.zoom0, self.zoom1) * 1.06:
            big_w = int(W * max(self.zoom0, self.zoom1) * 1.06)
            big_h = int(big_w * src.height / src.width)
        big = src.resize((big_w, big_h), Image.LANCZOS)
        self.base = grade_image(big, spec.get("grade", "neutral"))

        # скримы для читаемости титров
        self.scrim = self._make_scrim()
        self.texts = [self._prep_text(t) for t in spec["texts"]]
        band = []
        for it in self.texts:
            if it["kind"] in ("brand_center", "sub_center", "legal"):
                continue
            top = it["spec"]["y"] * H
            band.append((top, top + it["layer"].height))
        self.text_band = (min(b[0] for b in band), max(b[1] for b in band)) if band else None

    def _make_scrim(self):
        top = 0.55
        bottom = 0.85
        y = np.arange(H, dtype=np.float32)[:, None] / H
        a = np.zeros((H, 1), np.float32)
        a += np.clip((0.30 - y) / 0.30, 0, 1) ** 2 * top
        a += np.clip((y - 0.46) / 0.54, 0, 1) ** 1.7 * bottom
        a = np.clip(a, 0, 0.94)
        grad = np.repeat(a[:, :, None], 3, axis=2)
        return Image.fromarray((grad * 255).astype(np.uint8)).convert("RGB"), a

    def _prep_text(self, spec):
        kind = spec["kind"]
        lines = spec["text"].split("\n")
        if kind in ("brand", "brand_center"):
            weight, size, track, gap = 800, spec.get("size", 118), 2, 10
        elif kind == "headline":
            weight, size, track, gap = 700, spec.get("size", 74), -1.5, 18
        elif kind == "eyebrow":
            weight, size, track, gap = 600, spec.get("size", 33), 6.5, 8
        elif kind == "sub":
            weight, size, track, gap = 400, spec.get("size", 36), 1.5, 10
        elif kind == "sub_center":
            weight, size, track, gap = 400, spec.get("size", 40), 3, 12
        elif kind == "legal":
            weight, size, track, gap = 300, spec.get("size", 22), 1.2, 6
        else:
            weight, size, track, gap = 500, 40, 2, 10
        fill = {"eyebrow": (222, 212, 255), "legal": (192, 192, 208)}.get(kind, (255, 255, 255))
        max_w = W - 2 * MARGIN
        # автоподгонка: длинные строки не должны вылезать за поля кадра
        while True:
            fnt = font(weight, size)
            layer = text_layer(lines, [fnt] * len(lines), fill + (255,), track, gap,
                               align="center" if "center" in kind else "left")
            if layer.width <= max_w or size <= 16:
                break
            size -= 2
            if kind == "eyebrow":
                track = max(2.0, track - 0.5)
        return {"spec": spec, "layer": layer, "kind": kind, "color": fill,
                "t_in": spec["t_in"], "dur": spec.get("dur", 0.75)}

    # --- движение камеры
    def camera(self, t_local):
        k = ease_io(t_local / max(self.dur, 1e-6))
        z = lerp(self.zoom0, self.zoom1, k)
        cw = int(W * z)
        ch = int(H * z)
        cw = min(cw, self.base.width)
        ch = min(ch, self.base.height)
        pan = lerp(self.pan0, self.pan1, k)
        max_x = self.base.width - cw
        max_y = self.base.height - ch
        x = int(max_x * 0.5)
        y = int(max_y * pan)
        frame = self.base.crop((x, y, x + cw, y + ch))
        if (cw, ch) != (W, H):
            frame = frame.resize((W, H), Image.BICUBIC)
        return frame

    def render(self, t_local, t_global):
        frame = self.camera(t_local).convert("RGBA")

        # усиление контраста света в начале сцены (reveal)
        reveal = 1.0 - 0.20 * (1 - smooth(t_local / 0.55))
        if reveal < 0.999:
            arr = np.asarray(frame.convert("RGB"), np.float32) / 255.0
            frame = Image.fromarray((np.clip(arr * reveal, 0, 1) * 255).astype(np.uint8)).convert("RGBA")

        # скрим
        _, scrim_a = self.scrim
        alpha = np.clip(scrim_a * 0.80, 0, 1)
        # мягкая панель под блоком титров: гарантирует контраст на любом кадре
        if self.text_band:
            y0, y1 = self.text_band
            yy = np.arange(H, dtype=np.float32)
            band = (np.clip((yy - (y0 - 150)) / 170, 0, 1)
                    * np.clip(((y1 + 130) - yy) / 170, 0, 1))[:, None]
            alpha = np.clip(alpha + band * 0.52, 0, 0.96)
        arr = np.asarray(frame.convert("RGB"), np.float32) / 255.0
        arr = arr * (1 - alpha[..., None])
        frame = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8)).convert("RGBA")

        frame = self.draw_texts(frame, t_global)
        frame = self.draw_chrome(frame, t_global)
        return frame

    # --- титры
    def draw_texts(self, frame, t_global):
        for item in self.texts:
            if t_global < item["t_in"] - 0.02:
                continue
            if item["kind"] == "brand_center":
                frame = self.draw_brand_center(frame, item, t_global)
                continue
            prog = clamp((t_global - item["t_in"]) / item["dur"])
            a = smooth(prog)
            slide = (1 - ease_io(prog)) * 26
            layer = item["layer"]
            pos = (int(W / 2 - layer.width / 2),
                   int(item["spec"]["y"] * H + slide))
            strength = 0.22 if item["kind"] == "headline" else 0.34
            frame = text_with_glow(frame, layer, pos, item["color"], a,
                                   radius=30, strength=strength)

            if item["kind"] == "eyebrow":
                lw = int(64 * smooth(clamp(prog * 1.6)))
                if lw > 0:
                    d = ImageDraw.Draw(frame)
                    ly = pos[1] - 34
                    d.line([(int(W / 2 - lw / 2), ly), (int(W / 2 + lw / 2), ly)],
                           fill=tl.ACCENT + (int(235 * a),), width=3)
                    d.ellipse([W / 2 - 4, ly - 4, W / 2 + 4, ly + 4],
                              fill=tl.ACCENT_2 + (int(255 * a),))
        return frame

    def draw_brand_center(self, frame, item, t_global):
        prog = clamp((t_global - item["t_in"]) / item["dur"])
        a = smooth(prog)
        layer = item["layer"]
        pos = (int(W / 2 - layer.width / 2), int(item["spec"]["y"] * H - layer.height / 2 + (1 - ease_io(prog)) * 18))

        # хром-градиент внутри букв
        mask = layer.split()[3]
        grad = Image.new("RGB", layer.size)
        gd = ImageDraw.Draw(grad)
        for yy in range(layer.height):
            k = yy / max(layer.height - 1, 1)
            c = (int(lerp(235, 255, 1 - k * 0.6)), int(lerp(240, 255, 1 - k * 0.5)),
                 int(lerp(255, 255, 1 - k * 0.2)))
            gd.line([(0, yy), (layer.width, yy)], fill=c)
        chrome = Image.new("RGBA", layer.size, (0, 0, 0, 0))
        chrome.paste(grad, (0, 0), mask)

        frame = text_with_glow(frame, chrome, pos, (150, 130, 255), a,
                               radius=40, strength=0.55)

        # блик-свип по логотипу
        sweep = clamp((t_global - (item["t_in"] + 0.45)) / 0.75)
        if 0 < sweep < 1:
            sw = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            sd = ImageDraw.Draw(sw)
            x = int(lerp(-160, layer.width + 160, smooth(sweep)))
            sd.polygon([(x, layer.height), (x + 70, 0), (x + 130, 0), (x + 60, layer.height)],
                       fill=(255, 255, 255, 150))
            sw.putalpha(Image.composite(sw.split()[3], Image.new("L", layer.size, 0), mask))
            tmp = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            tmp.paste(sw, pos, sw)
            frame = Image.alpha_composite(frame, tmp)
        return frame

    # --- интерфейсная графика
    def draw_chrome(self, frame, t_global):
        d = ImageDraw.Draw(frame)
        # верхний вордмарк
        if t_global > 1.0 and t_global < 37.9:
            a = smooth(clamp((t_global - 1.0) / 0.7)) * (1 - smooth(clamp((t_global - 37.2) / 0.7)))
            fnt = font(600, 26)
            x = MARGIN
            y = 104
            d.line([(x, y + 8), (x, y + 40)], fill=(255, 255, 255, int(120 * a)), width=2)
            draw_tracked(d, (x + 18, y), "iPad Air", fnt, (255, 255, 255, int(225 * a)), 3.2)
            fnt2 = font(400, 20)
            draw_tracked(d, (x + 18, y + 34), "КОНЦЕПТ-РОЛИК", fnt2,
                         (200, 190, 255, int(150 * a)), 3.6)
        return frame


# ------------------------------------------------------------------ переходы
def apply_flash(frame, t_global, cuts):
    """Короткая световая вспышка + хроматическая аберрация на склейке."""
    best = None
    for c in cuts:
        dt = abs(t_global - c)
        if dt < 0.30:
            best = (c, dt)
            break
    if not best:
        return frame
    c, dt = best
    k = (1 - dt / 0.30) ** 2
    arr = np.asarray(frame.convert("RGB"), np.float32)

    # хроматика: раздвигаем каналы по горизонтали
    shift = int(round(7 * k))
    if shift:
        r = np.roll(arr[..., 0], shift, axis=1)
        b = np.roll(arr[..., 2], -shift, axis=1)
        arr = np.stack([r, arr[..., 1], b], axis=-1)

    # вспышка + световой клин
    arr = np.clip(arr * (1 + 0.30 * k) + 40 * k, 0, 255)
    img = Image.fromarray(arr.astype(np.uint8))
    if k > 0.05:
        streak = Image.new("RGB", frame.size, (0, 0, 0))
        d = ImageDraw.Draw(streak)
        cy = int(H * 0.5)
        h = int(2 + 3 * k)
        d.rectangle([0, cy - h, W, cy + h], fill=(255, 255, 255))
        streak = streak.filter(ImageFilter.GaussianBlur(26 + 30 * (1 - k)))
        img = Image.blend(img, Image.blend(img, streak, 0.55), 0.55 * k)
    return img.convert("RGBA")


def compose_frame(t_global, scenes):
    # находим активные сцены (обычно одна, на переходе — две)
    active = []
    for sc in scenes:
        if sc.start - FADE / 2 <= t_global < sc.end + FADE / 2:
            active.append(sc)
    if not active:
        active = [scenes[min(range(len(scenes)),
                             key=lambda i: abs(scenes[i].start - t_global))]]

    if len(active) == 1:
        sc = active[0]
        return sc.render(t_global - sc.start, t_global)

    a, b = active[0], active[1]
    cut = b.start
    k = smooth(clamp((t_global - (cut - FADE / 2)) / FADE))
    fa = np.asarray(a.render(t_global - a.start, t_global).convert("RGB"), np.float32)
    fb = np.asarray(b.render(t_global - b.start, t_global).convert("RGB"), np.float32)
    out = fa * (1 - k) + fb * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).convert("RGBA")


def frame_at(t_global, scenes, cuts):
    img = compose_frame(t_global, scenes)
    img = apply_flash(img, t_global, cuts)
    d = ImageDraw.Draw(img)
    # прогресс-бар
    p = clamp(t_global / tl.TOTAL)
    d.rectangle([0, H - 3, int(W * p), H], fill=tl.ACCENT + (110,))
    return img.convert("RGB")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", nargs="*", type=float, default=None)
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "ipad-air-promo.mp4"))
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    print("• подготовка сцен…")
    scenes = [Scene(s) for s in tl.SCENES]
    cuts = [s["start"] for s in tl.SCENES[1:]]

    if args.preview:
        for t in args.preview:
            img = frame_at(t, scenes, cuts)
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
        "[0:v]vignette=angle=PI/4.6:eval=init,"
        "eq=gamma=0.99:saturation=1.03:contrast=1.02,"
        "noise=alls=4:allf=t,"
        "format=yuv420p[v];"
        "[1:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "slow", "-crf", "21",
        "-profile:v", "high", "-level", "4.2", "-pix_fmt", "yuv420p",
        "-g", str(tl.FPS * 2), "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-t", f"{tl.TOTAL:.2f}",
        args.out,
    ]
    print(f"• рендер {n_frames} кадров -> {args.out}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for i in range(n_frames):
            t = i / tl.FPS
            frame = frame_at(t, scenes, cuts)
            proc.stdin.write(frame.tobytes())
            if i % 60 == 0:
                print(f"  {i}/{n_frames}  ({t:5.1f} с)", flush=True)
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg exited with {code}")
    print("✓ готово:", args.out)


if __name__ == "__main__":
    main()
