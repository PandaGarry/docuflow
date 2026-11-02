"""Render the 40s narrated family animatic. No video generation service required.

    .venv/bin/python studio/tools/render_pilot.py --check
    .venv/bin/python studio/tools/render_pilot.py --stills
    .venv/bin/python studio/tools/render_pilot.py

Original character art is retained; this is a deliberately limited 2.5D cutout
production, NOT a fully animated 3D episode. See episodes/letter-p.json.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / "studio"
sys.path.insert(0, str(STUDIO / "engine"))
from audio import make_bed, write_wav  # noqa: E402

PLAN = json.loads((STUDIO / "episodes/letter-p.json").read_text())
W, H = PLAN["size"]
FPS, DURATION = PLAN["fps"], PLAN["duration"]
ASSETS = STUDIO / "assets/letter-p"
WORK = STUDIO / "out/letter-p"
OUTPUT = STUDIO / "out/pilot-letter-p.mp4"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
GOLD = (255, 218, 151, 255)
WHITE = (255, 249, 237, 255)
FONT = STUDIO / "fonts/Nunito-800.ttf"
REGULAR = STUDIO / "fonts/Nunito-600.ttf"


def font(size, regular=False):
    return ImageFont.truetype(str(REGULAR if regular else FONT), size)


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def label(im, text, xy, size=30, fill=WHITE, anchor="mm", regular=False):
    ImageDraw.Draw(im).text(xy, text, font=font(size, regular), fill=fill,
                           anchor=anchor, stroke_width=1,
                           stroke_fill=(65, 32, 17, 100))


def cover(im, size):
    w, h = size
    scale = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.Resampling.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


class Pilot:
    def __init__(self):
        self.room = cover(Image.open(ASSETS / "living-room.png").convert("RGB"), (W, H))
        self.actors = {}
        for char, poses in {"dad": ["views/front", "pose/point"],
                            "mom": ["views/front"], "son": ["views/front"]}.items():
            for pose in poses:
                im = Image.open(STUDIO / "characters" / char / f"{pose}.png").convert("RGBA")
                a = np.asarray(im).copy()
                r, g, b = [a[:, :, i].astype(float) for i in range(3)]
                # Tight green-key only: preserve the pale mint cap and clothing.
                green = (g > 1.3 * r) & (g > 1.18 * b) & (g > 75)
                a[:, :, 3][green] = 0
                # Despill just the semi-transparent outline, not the artwork.
                edge = (a[:, :, 3] > 0) & (a[:, :, 3] < 240) & (g > r + 12)
                a[:, :, 1][edge] = np.minimum(g[edge], (r[edge] + b[edge]) / 2 + 8)
                im = Image.fromarray(a)
                box = im.getbbox()
                self.actors[(char, pose)] = im.crop(box)
        self.shadow = Image.new("RGBA", (420, 90))
        ImageDraw.Draw(self.shadow).ellipse((30, 18, 390, 70), fill=(29, 13, 8, 110))
        self.shadow = self.shadow.filter(ImageFilter.GaussianBlur(12))
        # Procedural window dust / firelight, seeded for deterministic renders.
        rng = np.random.default_rng(18)
        self.dust = [(float(rng.uniform(0, W)), float(rng.uniform(90, 600)),
                      float(rng.uniform(0.6, 1.8)), float(rng.uniform(0, 6))) for _ in range(28)]
        yy, xx = np.mgrid[:H, :W]
        v = np.clip((((xx - W / 2) / (W * .72)) ** 2 +
                     ((yy - H / 2) / (H * .88)) ** 2) * 65, 0, 85).astype(np.uint8)
        self.vignette = Image.fromarray(np.dstack((np.zeros_like(v), np.zeros_like(v), np.zeros_like(v), v)))

    def background(self, t, focus=(.5, .48), zoom=1.035):
        cw, ch = W / zoom, H / zoom
        x = np.clip(focus[0] * W - cw / 2, 0, W - cw)
        y = np.clip(focus[1] * H - ch / 2, 0, H - ch)
        im = self.room.transform((W, H), Image.Transform.EXTENT, (x, y, x + cw, y + ch),
                                 resample=Image.Resampling.BICUBIC).convert("RGBA")
        glow = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(glow)
        flicker = 7 + round(3 * math.sin(t * 8) + 2 * math.sin(t * 13))
        d.ellipse((1000, 310, 1280, 680), fill=(255, 153, 48, flicker))
        glow = glow.filter(ImageFilter.GaussianBlur(35))
        im.alpha_composite(glow)
        return im

    def actor(self, im, char, x, floor, height, t, pose="views/front", lean=0):
        source = self.actors[(char, pose)]
        phase = {"dad": 0, "mom": 1.8, "son": 3.1}[char]
        breathe = math.sin(t * 2.15 + phase)
        h = round(height * (1 + .003 * breathe))
        w = round(source.width * h / source.height)
        sprite = source.resize((w, h), Image.Resampling.LANCZOS)
        # Head and body are cutout layers. Tiny rotations keep identity fixed.
        cut = round(h * {"dad": .26, "mom": .255, "son": .355}[char])
        head_mask = Image.new("L", (w, h))
        ImageDraw.Draw(head_mask).rectangle((0, 0, w, cut), fill=255)
        head_mask = head_mask.filter(ImageFilter.GaussianBlur(max(1, h * .003)))
        alpha = sprite.getchannel("A")
        am = np.asarray(alpha).astype(float)
        hm = np.asarray(head_mask).astype(float) / 255
        head, body = sprite.copy(), sprite.copy()
        head.putalpha(Image.fromarray((am * hm).astype(np.uint8)))
        body.putalpha(Image.fromarray((am * (1 - hm)).astype(np.uint8)))
        tilt = lean + .65 * math.sin(t * .9 + phase)
        # Padding prevents the cap/hair being clipped as the head tilts.
        pad = max(12, round(w * .06))
        headpad = Image.new("RGBA", (w + pad * 2, h + pad * 2))
        headpad.alpha_composite(head, (pad, pad))
        headpad = headpad.rotate(tilt, Image.Resampling.BICUBIC,
                                 center=(w / 2 + pad, cut + pad))
        spritepad = Image.new("RGBA", headpad.size)
        spritepad.alpha_composite(body, (pad, pad))
        spritepad.alpha_composite(headpad)
        ground = self.shadow.resize((round(w * 1.12), max(24, round(h * .08))))
        im.alpha_composite(ground, (round(x - ground.width / 2), round(floor - ground.height / 2)))
        im.alpha_composite(spritepad, (round(x - w / 2 - pad), round(floor - h - pad)))

    def family(self, im, t, zoom=1):
        self.actor(im, "dad", 438 - 18 * (zoom - 1), 649, 526 * zoom, t, lean=-1.2)
        self.actor(im, "mom", 837 + 18 * (zoom - 1), 650, 523 * zoom, t, lean=1.4)
        self.actor(im, "son", 641 + 4 * math.sin(t * .65), 660, 324 * zoom, t, lean=math.sin(t) * 1.4)

    def magnifier(self, im, cx, cy, radius, source=None):
        d = ImageDraw.Draw(im)
        if source is not None:
            r = round(radius)
            crop = source.crop((round(cx - r / 1.4), round(cy - r / 1.4),
                                round(cx + r / 1.4), round(cy + r / 1.4)))
            crop = crop.resize((r * 2, r * 2), Image.Resampling.BICUBIC).convert("RGBA")
            mask = Image.new("L", crop.size)
            ImageDraw.Draw(mask).ellipse((0, 0, r * 2 - 1, r * 2 - 1), fill=255)
            crop.putalpha(mask)
            im.alpha_composite(crop, (round(cx - r), round(cy - r)))
        d.line((cx + radius * .70, cy + radius * .70, cx + radius * 1.42, cy + radius * 1.45),
               fill=(42, 24, 20, 255), width=round(radius * .24))
        d.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                  outline=GOLD, width=8)
        d.arc((cx - radius + 15, cy - radius + 15, cx + radius - 15, cy + radius - 15),
              210, 290, fill=(255, 251, 226, 180), width=3)

    def sparkle(self, im, x, y, t, count=10):
        d = ImageDraw.Draw(im)
        for i in range(count):
            theta = i * math.tau / count + t * .6
            r = 65 + 15 * math.sin(t * 4 + i)
            cx, cy = x + r * math.cos(theta), y + r * math.sin(theta)
            s = 3 + 3 * (1 + math.sin(t * 6 + i)) / 2
            d.polygon([(cx, cy - s * 2), (cx + s / 2, cy - s / 2), (cx + s * 2, cy),
                       (cx + s / 2, cy + s / 2), (cx, cy + s * 2),
                       (cx - s / 2, cy + s / 2), (cx - s * 2, cy), (cx - s / 2, cy - s / 2)], fill=GOLD)

    def shot(self, index, t):
        shot = PLAN["shots"][index]
        local = t - shot["start"]
        u = ease(local / (shot["end"] - shot["start"]))
        kind = shot["kind"]
        focus = {"cushion": (.55, .56), "books": (.07, .38), "fireplace": (.92, .60)}
        if kind in focus:
            im = self.background(t, focus[kind], 1.6 + .10 * u)
            source = im.copy()
            target = {"cushion": (710, 410), "books": (190, 315), "fireplace": (1100, 430)}[kind]
            cx = target[0] + 40 * math.sin(local * 1.3)
            cy = target[1] + 30 * math.cos(local * 1.7)
            self.magnifier(im, cx, cy, 110, source)
            # Son watches the search from the foreground; staged as a cutout.
            self.actor(im, "son", 1050 if kind == "books" else 170, 675, 360, t,
                       lean=-3 + 2 * math.sin(local))
            label(im, shot["label"], (W / 2, 135), 45)
        elif kind in ("family", "end"):
            im = self.background(t, zoom=1.035 + .03 * u)
            self.family(im, t, 1 + .025 * u)
            if t < 4.2:
                # Opening title occupies free wall space, not the faces.
                label(im, "Куда пропала буква P?", (W / 2, 87), 49)
            elif kind == "end":
                veil = Image.new("RGBA", im.size, (34, 20, 17, 100))
                im.alpha_composite(veil)
                label(im, "Вместе найдём что угодно.", (W / 2, 270), 51)
                label(im, "Даже то, что не терялось.", (W / 2, 332), 33, GOLD)
                label(im, "КОНЕЦ МАЛЕНЬКОГО ПРИКЛЮЧЕНИЯ", (W / 2, 440), 21, regular=True)
                label(im, "Пробная серия · 2,5D-аниматик", (W / 2, 490), 21, regular=True)
            else:
                self.sparkle(im, 650, 180, t, 6)
        elif kind == "son":
            im = self.background(t, zoom=1.09 + .04 * u)
            self.actor(im, "son", 655, 1005, 855 + u * 30, t, lean=-3 + 2 * math.sin(local))
            label(im, "?", (910, 250 - 10 * math.sin(local * 2)), 110, GOLD)
            label(im, "Маленькая загадка", (280, 190), 29, GOLD)
        elif kind == "dad":
            im = self.background(t, zoom=1.08 + .025 * u)
            self.actor(im, "dad", 510, 990, 850, t, pose="pose/point", lean=-2)
            self.actor(im, "son", 945, 690, 415, t, lean=3)
            self.magnifier(im, 240 + 12 * math.sin(local), 340, 68)
            label(im, "НАЧИНАЕМ ПОИСКИ", (950, 160), 22, GOLD)
        elif kind == "mom":
            im = self.background(t, zoom=1.075 + .025 * u)
            self.actor(im, "mom", 468, 1020, 910, t, lean=3.5)
            self.actor(im, "son", 890, 775, 500, t, lean=-3)
            d = ImageDraw.Draw(im)
            ay = 200 - 10 * math.sin(local * 3)
            d.line((1035, ay + 90, 1035, ay), fill=GOLD, width=6)
            d.line((1017, ay + 20, 1035, ay, 1053, ay + 20), fill=GOLD, width=6)
        elif kind == "reveal":
            im = self.background(t, zoom=1.1 + .025 * u)
            self.actor(im, "son", 640, 1055, 920 + 30 * u, t, lean=math.sin(local * 1.4) * 2)
            if local > 1.1:
                self.sparkle(im, 640, 195 - 30 * u, local)
                label(im, "НАШЛАСЬ!", (1010, 260), 38, GOLD)
        else:
            raise ValueError(kind)
        return im

    def frame(self, t, overlays=True):
        idx = next(i for i, s in enumerate(PLAN["shots"]) if s["start"] <= t < s["end"])
        im = self.shot(idx, t)
        # Short dissolves blend moving shots, never two independently redrawn faces.
        start = PLAN["shots"][idx]["start"]
        if idx and t - start < .22:
            prior = self.shot(idx - 1, start - .001)
            im = Image.blend(prior, im, ease((t - start) / .22))
        dust = Image.new("RGBA", (W, H))
        d = ImageDraw.Draw(dust)
        for x, y, r, phase in self.dust:
            x += math.sin(t * .3 + phase) * 16
            y = 90 + (y - 90 - t * (3 + r)) % 510
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 232, 177, 65))
        im.alpha_composite(dust)
        im.alpha_composite(self.vignette)
        if overlays:
            label(im, "СЕМЕЙНЫЕ ИСТОРИИ", (42, 31), 18, GOLD, anchor="lm")
            label(im, "01  /  ПРОБНАЯ СЕРИЯ", (W - 42, 31), 16, anchor="rm", regular=True)
            current = next((s[2] for s in PLAN["subtitles"] if s[0] <= t < s[1]), None)
            if current:
                lines = self.wrap(current, 1000, font(29))
                box_h = len(lines) * 37 + 22
                panel = Image.new("RGBA", im.size)
                ImageDraw.Draw(panel).rounded_rectangle((W / 2 - 535, H - box_h - 24,
                                                         W / 2 + 535, H - 24), radius=16,
                                                        fill=(29, 20, 17, 221))
                im.alpha_composite(panel)
                for i, line in enumerate(lines):
                    label(im, line, (W / 2, H - box_h - 24 + 12 + i * 37 + 18), 29, regular=True)
            # Fine timeline doubles as an unobtrusive playback guide.
            ImageDraw.Draw(im).rectangle((0, H - 3, round(W * t / DURATION), H), fill=GOLD)
        fade = min(ease(t / .5), ease((DURATION - t) / .6))
        if fade < 1:
            im = Image.blend(Image.new("RGBA", im.size, (23, 15, 13, 255)), im, fade)
        return im.convert("RGB")

    @staticmethod
    def wrap(text, width, f):
        lines, line = [], ""
        for word in text.split():
            proposed = f"{line} {word}".strip()
            if f.getlength(proposed) > width and line:
                lines.append(line)
                line = word
            else:
                line = proposed
        return lines + ([line] if line else [])


def run(args):
    print(" ".join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True)


def audio_mix():
    # Own procedurally synthesized score, not stock/copyrighted soundtrack.
    bed = make_bed(DURATION, bpm=94, fade_out=2.0)
    write_wav(str(WORK / "bed.wav"), bed)
    cmd = [FFMPEG, "-y", "-v", "error", "-i", str(WORK / "bed.wav")]
    for n in PLAN["narration"]:
        cmd += ["-i", str(ASSETS / "audio" / n["file"])]
    filters = ["[0:a]volume=0.13[bed]"]
    for i, n in enumerate(PLAN["narration"], 1):
        ms = round(n["start"] * 1000)
        filters.append(f"[{i}:a]atempo={PLAN['narration_speed']},adelay={ms}:all=1[v{i}]")
    filters.append(f"[v1][v2][v3]amix=inputs=3:normalize=0,apad,atrim=duration={DURATION},"
                   "asplit=2[voice][key]")
    filters.append("[bed][key]sidechaincompress=threshold=0.015:ratio=5:attack=30:release=400[ducked]")
    filters.append("[ducked][voice]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=8,"
                   "apad,atrim=duration=40,afade=t=out:st=38.3:d=1.7[out]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "[out]", "-ar", "48000", str(WORK / "mix.wav")]
    run(cmd)


def validate():
    assert PLAN["shots"][0]["start"] == 0
    assert PLAN["shots"][-1]["end"] == DURATION
    for i, shot in enumerate(PLAN["shots"]):
        assert shot["end"] > shot["start"]
        if i:
            assert shot["start"] == PLAN["shots"][i - 1]["end"]
    last_end = 0
    for start, end, text in PLAN["subtitles"]:
        assert 0 <= start < end <= DURATION and start >= last_end and text.strip()
        last_end = end
    for n in PLAN["narration"]:
        assert (ASSETS / "audio" / n["file"]).is_file()
    print("Timeline, shot boundaries, subtitle ordering, audio sources: OK", flush=True)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--stills", action="store_true")
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    validate()
    pilot = Pilot()
    if args.check:
        for shot in PLAN["shots"]:
            for t in [shot["start"], (shot["start"] + shot["end"]) / 2, shot["end"] - .001]:
                im = pilot.frame(t)
                assert im.size == (W, H) and im.mode == "RGB"
        assert pilot.frame(7).tobytes() == pilot.frame(7).tobytes()
        print("30 boundary/midpoint frames + deterministic render: OK")
        return
    if args.stills:
        times = [2.7, 6, 11, 15, 17.6, 20.1, 23, 28.6, 34, 38.8]
        contact = Image.new("RGB", (1280, 360 * 5))
        for i, t in enumerate(times):
            frame = pilot.frame(t)
            frame.save(WORK / f"frame-{i:02}.jpg", quality=93)
            contact.paste(frame.resize((640, 360)), ((i % 2) * 640, (i // 2) * 360))
        contact.save(WORK / "contact.jpg", quality=93)
        pilot.frame(2.7, overlays=False).save(STUDIO / "out/pilot-letter-p-poster.jpg", quality=94)
        print("Stills ready:", WORK / "contact.jpg")
        return
    audio_mix()
    silent = WORK / "silent.mp4"
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "19",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(silent)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
        try:
            for frame in range(FPS * DURATION):
                proc.stdin.write(pilot.frame(frame / FPS).tobytes())
                if frame % (FPS * 5) == 0:
                    print(f"Rendering {frame / FPS:.0f}/{DURATION}s", flush=True)
        finally:
            proc.stdin.close()
        if proc.wait():
            raise RuntimeError("Video encoder failed")
    run([FFMPEG, "-y", "-v", "error", "-i", silent, "-i", WORK / "mix.wav", "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", str(DURATION), "-movflags", "+faststart", OUTPUT])
    # Independent decode catches broken containers, truncated streams and bad frames.
    run([FFMPEG, "-v", "error", "-xerror", "-i", OUTPUT, "-f", "null", "-"])
    print(f"READY {OUTPUT} ({OUTPUT.stat().st_size / 1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()
