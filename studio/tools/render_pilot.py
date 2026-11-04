"""Render the current family pilot: native 1080p, articulated 2.5D limited animation.

    .venv/bin/python studio/tools/render_pilot.py --check
    .venv/bin/python studio/tools/render_pilot.py --stills
    .venv/bin/python studio/tools/render_pilot.py

Character artwork changes on twos (12 fps); camera and effects on ones (24 fps).
This is NOT a full 3D production or phoneme-synchronized character dialogue.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import sys

import cv2
import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / 'studio'
sys.path.insert(0, str(STUDIO / 'engine'))
from audio import make_bed, write_wav, pluck, SR  # noqa: E402
from limited import Actor, smooth  # noqa: E402

PLAN = json.loads((STUDIO / 'episodes/letter-p.json').read_text())
W, H = PLAN['size']
S = W / 1280
FPS, DURATION = PLAN['fps'], PLAN['duration']
ASSETS = STUDIO / 'assets/letter-p'
WORK = STUDIO / 'out/letter-p'
OUTPUT = STUDIO / 'out/pilot-letter-p.mp4'
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
GOLD = (255, 218, 151, 255)
WHITE = (255, 249, 237, 255)


def px(v):
    return round(v * S)


@lru_cache(maxsize=32)
def font(size, regular=False):
    return ImageFont.truetype(str(STUDIO / 'fonts' / ('Nunito-600.ttf' if regular else 'Nunito-800.ttf')), px(size))


def cover(image):
    factor = max(W / image.width, H / image.height)
    image = image.resize((round(image.width * factor), round(image.height * factor)), Image.Resampling.LANCZOS)
    x, y = (image.width - W) // 2, (image.height - H) // 2
    return image.crop((x, y, x + W, y + H))


class Stage:
    def __init__(self, image):
        self.im = image

    def text(self, text, x, y, size=30, fill=WHITE, anchor='mm', regular=False):
        ImageDraw.Draw(self.im).text((px(x), px(y)), text, font=font(size, regular),
                                    fill=fill, anchor=anchor, stroke_width=px(.6),
                                    stroke_fill=(45, 26, 17, 95))

    def line(self, points, fill=GOLD, width=3):
        ImageDraw.Draw(self.im).line([(px(x), px(y)) for x, y in points], fill=fill,
                                    width=max(1, px(width)), joint='curve')

    def roundrect(self, box, radius=12, fill=(40, 27, 20, 220), outline=None, width=1):
        ImageDraw.Draw(self.im).rounded_rectangle(tuple(px(v) for v in box), radius=px(radius),
                                                 fill=fill, outline=outline, width=px(width))

    def ellipse(self, box, fill=None, outline=None, width=1):
        ImageDraw.Draw(self.im).ellipse(tuple(px(v) for v in box), fill=fill, outline=outline, width=px(width))

    def sprite(self, image, x, y, width=None, height=None, angle=0):
        if height is not None:
            factor = px(height) / image.height
        else:
            factor = px(width) / image.width
        sp = image.resize((max(1, round(image.width * factor)), max(1, round(image.height * factor))), Image.Resampling.LANCZOS)
        if angle:
            sp = sp.rotate(angle, Image.Resampling.BICUBIC, expand=True)
        self.im.alpha_composite(sp, (round(px(x) - sp.width / 2), round(px(y) - sp.height / 2)))


class Pilot:
    def __init__(self):
        self.room = cover(Image.open(ASSETS / 'living-room.png').convert('RGB'))
        rigs = json.loads((ASSETS / 'acting/rigs.json').read_text())
        self.actors = {name: Actor(ROOT, data) for name, data in rigs.items()}
        shadow = Image.new('RGBA', (640, 130))
        ImageDraw.Draw(shadow).ellipse((40, 35, 600, 100), fill=(28, 14, 9, 115))
        self.shadow = shadow.filter(ImageFilter.GaussianBlur(16))
        rng = np.random.default_rng(18)
        self.dust = [(float(rng.uniform(40, 1240)), float(rng.uniform(90, 600)),
                      float(rng.uniform(.6, 1.5)), float(rng.uniform(0, 6))) for _ in range(24)]
        yy, xx = np.mgrid[:H, :W]
        v = np.clip((((xx - W / 2) / (W * .76)) ** 2 +
                     ((yy - H / 2) / (H * .92)) ** 2) * 55, 0, 75).astype(np.uint8)
        self.vignette = Image.fromarray(np.dstack((np.zeros_like(v), np.zeros_like(v), np.zeros_like(v), v)))

    @lru_cache(maxsize=18)
    def drawing(self, key, qt, head, arm, gesture):
        return self.actors[key].render(qt, head=head, arm=arm, gesture=gesture)

    def actor(self, stage, key, x, floor, height, t, *, head=0, arm=0, gesture=1, squash=1, lift=0):
        actor = self.actors[key]
        # Quantized parameters avoid sub-pixel jitter and retain bounded caching.
        qt = math.floor(t * PLAN['acting_fps'] + 1e-6) / PLAN['acting_fps']
        drawing = self.drawing(key, qt, round(head * 2) / 2, round(arm * 2) / 2, round(gesture, 2))
        factor = px(height) / actor.height
        width = max(1, round(drawing.width * factor / math.sqrt(squash)))
        h = max(1, round(drawing.height * factor * squash))
        drawing = drawing.resize((width, h), Image.Resampling.LANCZOS)
        sx, sy = width / (actor.w + 2 * actor.pad), h / (actor.h + 2 * actor.pad)
        # Scale the source around its measured sole, not the image bounding-box center.
        left = round(px(x) - (actor.anchor_x + actor.pad) * sx)
        top = round(px(floor - lift) - (actor.foot + actor.pad) * sy)
        shadow_width = actor.w * height / actor.height * .9
        stage.sprite(self.shadow, x, floor + 3, width=shadow_width * (1 - lift * .004))
        stage.im.alpha_composite(drawing, (left, top))

    def background(self, t, focus=(.5, .5), zoom=1.035):
        cw, ch = W / zoom, H / zoom
        x = float(np.clip(focus[0] * W - cw / 2, 0, W - cw))
        y = float(np.clip(focus[1] * H - ch / 2, 0, H - ch))
        im = self.room.transform((W, H), Image.Transform.EXTENT, (x, y, x + cw, y + ch),
                                 resample=Image.Resampling.BICUBIC).convert('RGBA')
        glow = Image.new('RGBA', (W, H))
        flicker = 6 + round(2 * math.sin(t * 8) + math.sin(t * 13))
        ImageDraw.Draw(glow).ellipse((px(1010), px(300), px(1280), px(690)), fill=(255, 157, 62, flicker))
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(px(24))))
        return Stage(im)

    def family(self, stage, t, *, happy=False, zoom=1):
        self.actor(stage, 'dad-rest', 426 - (zoom - 1) * 200, 637, 518 * zoom, t, head=-2)
        self.actor(stage, 'mom-rest', 854 + (zoom - 1) * 200, 637, 516 * zoom, t, head=2)
        key = 'son-laugh' if happy else 'son-rest'
        squash = 1 + (.012 * math.sin(t * 8) if happy else 0)
        self.actor(stage, key, 641, 651, 328 * zoom, t, head=-1, squash=squash)

    def sparkle(self, stage, x, y, t, count=8, strength=1):
        draw = ImageDraw.Draw(stage.im)
        for i in range(count):
            theta = i * math.tau / count + t * .35
            r = 65 + 10 * math.sin(t * 3 + i)
            cx, cy = x + r * math.cos(theta), y + r * math.sin(theta)
            s = strength * (2.5 + 2 * (1 + math.sin(t * 5 + i)) / 2)
            points = [(cx, cy - 2 * s), (cx + .5 * s, cy - .5 * s), (cx + 2 * s, cy),
                      (cx + .5 * s, cy + .5 * s), (cx, cy + 2 * s), (cx - .5 * s, cy + .5 * s),
                      (cx - 2 * s, cy), (cx - .5 * s, cy - .5 * s)]
            draw.polygon([(px(a), px(b)) for a, b in points], fill=GOLD)

    def magnifier(self, stage, x, y, r):
        # Actual magnified patch, not an empty circle sliding over a plate.
        p = px(r)
        source = stage.im.copy()
        patch = source.crop((px(x) - round(p / 1.45), px(y) - round(p / 1.45),
                             px(x) + round(p / 1.45), px(y) + round(p / 1.45)))
        patch = patch.resize((p * 2, p * 2), Image.Resampling.LANCZOS)
        mask = Image.new('L', patch.size)
        ImageDraw.Draw(mask).ellipse((0, 0, p * 2 - 1, p * 2 - 1), fill=255)
        patch.putalpha(mask)
        stage.im.alpha_composite(patch, (px(x) - p, px(y) - p))
        stage.line([(x + r * .68, y + r * .68), (x + r * 1.4, y + r * 1.4)], fill=(51, 30, 21, 255), width=r * .20)
        stage.ellipse((x - r, y - r, x + r, y + r), outline=(91, 53, 31, 255), width=10)
        stage.ellipse((x - r + 4, y - r + 4, x + r - 4, y + r - 4), outline=GOLD, width=3)
        ImageDraw.Draw(stage.im).arc(tuple(px(v) for v in (x - r + 15, y - r + 15, x + r - 15, y + r - 15)),
                                     210, 290, fill=WHITE, width=px(2))

    def shot(self, shot, t):
        local = t - shot['start']
        u = smooth(local / (shot['end'] - shot['start']))
        kind = shot['kind']
        stage = self.background(t, zoom=1.035 + .025 * u)
        if kind in ('family', 'together', 'end'):
            self.family(stage, t, happy=kind == 'together' and t < 35.4, zoom=1 + .02 * u)
            if kind == 'family':
                stage.text('Куда пропала буква P?', 640, 75, 46)
                stage.text('Маленькое семейное расследование', 640, 116, 19, GOLD, regular=True)
            elif kind == 'end':
                stage.im.alpha_composite(Image.new('RGBA', (W, H), (28, 18, 15, 145)))
                stage.text('Дело раскрыто.', 640, 267, 58)
                stage.text('Вместе найдём что угодно.', 640, 335, 33, GOLD)
                stage.text('Даже то, что не терялось.', 640, 379, 25)
                stage.text('КОНЕЦ МАЛЕНЬКОГО ПРИКЛЮЧЕНИЯ', 640, 477, 17, regular=True)
            else:
                # Reaction beats settle instead of bouncing throughout the whole shot.
                if local < 1.6:
                    self.sparkle(stage, 640, 212, t, 5, .7)
        elif kind == 'question':
            stage = self.background(t, focus=(.47, .5), zoom=1.10 + .04 * u)
            scan = -3 + 6 * smooth((local - .5) / 1.1) - 4 * smooth((local - 2.4) / .8)
            self.actor(stage, 'son-search', 655, 1110, 1015 + u * 20, t, head=scan, gesture=.85)
            if local > .7:
                stage.text('?', 966, 253 - 8 * math.sin(local * 2), 92, GOLD)
        elif kind == 'think':
            stage = self.background(t, focus=(.43, .5), zoom=1.12 + .03 * u)
            self.actor(stage, 'dad-think', 585, 1088, 1000, t, head=-1.5, gesture=1)
            self.actor(stage, 'son-search', 1000, 800, 505, t, head=-3, gesture=.35)
        elif kind == 'detective':
            stage = self.background(t, zoom=1.075 + .03 * u)
            self.actor(stage, 'dad-point', 490, 1000, 890, t, head=-2)
            self.actor(stage, 'son-search', 973, 760, 468, t, head=2, gesture=.3)
            stage.roundrect((848, 141, 1152, 187), 23, fill=(44, 29, 21, 211), outline=(222, 180, 116, 150))
            stage.text('ДЕЛО № 01', 1000, 164, 22, GOLD)
        elif kind in ('cushion', 'books', 'fireplace'):
            focus = {'cushion': (.55, .58), 'books': (.05, .40), 'fireplace': (.95, .62)}[kind]
            stage = self.background(t, focus=focus, zoom=1.75 + .09 * u)
            target = {'cushion': (660, 400), 'books': (220, 332), 'fireplace': (1070, 422)}[kind]
            x = target[0] + 36 * math.sin(local * 1.4)
            y = target[1] + 20 * math.cos(local * 1.7)
            self.magnifier(stage, x, y, 118)
            side = 1020 if kind == 'books' else 180
            self.actor(stage, 'son-search', side, 684, 405, t, head=3 * math.sin(local), gesture=.6)
            stage.text(shot['label'], 640, 122, 40)
        elif kind == 'hint':
            stage = self.background(t, focus=(.54, .5), zoom=1.09 + .03 * u)
            forearm = 16 * (1 - smooth((local - .15) / .65)) + 2 * math.sin(local * 3)
            self.actor(stage, 'mom-hint', 478, 1098, 1030, t, head=1.8, arm=forearm)
            self.actor(stage, 'son-search', 944, 855, 570, t, head=-4 * smooth(local / 1.3), gesture=.2)
        elif kind == 'cap':
            stage = self.background(t, zoom=1.10 + .05 * u)
            # A drawn cap-touch key plus a small continuous wrist deformation.
            # The large arm raise is a key change, not a solved shoulder/elbow rig.
            arm = 15 * (1 - smooth((local - .18) / .88))
            self.actor(stage, 'son-cap', 642, 1147, 1060 + 20 * u, t, head=0, arm=arm)
            if local > 1.45:
                self.sparkle(stage, 647, 175 - 20 * u, local, 7, smooth((local - 1.45) / .3))
                stage.text('Вот же она!', 1015, 262, 34, GOLD)
        elif kind == 'laugh':
            stage = self.background(t, zoom=1.15 + .02 * u)
            anticipation = math.sin(min(local / .18, 1) * math.pi) * .025
            lift = max(0, math.sin((local - .18) * math.pi / .65)) * 17 if .18 < local < .83 else 0
            squash = 1 - anticipation + .009 * math.sin(local * 9)
            self.actor(stage, 'son-laugh', 642, 1147, 1060, t, head=-2 + math.sin(local * 5), squash=squash, lift=lift)
        else:
            raise ValueError(f'Unknown shot: {kind}')
        return stage

    @staticmethod
    def wrap(text, f, width):
        lines, line = [], ''
        for word in text.split():
            candidate = f'{line} {word}'.strip()
            if f.getlength(candidate) > width and line:
                lines.append(line)
                line = word
            else:
                line = candidate
        return lines + ([line] if line else [])

    def frame(self, t, overlays=True):
        shot = next(s for s in PLAN['shots'] if s['start'] <= t < s['end'])
        stage = self.shot(shot, t)
        # Straight motivated cuts; never dissolve two faces/arms into double images.
        dust = Image.new('RGBA', (W, H))
        dd = ImageDraw.Draw(dust)
        for x, y, r, phase in self.dust:
            x += math.sin(t * .3 + phase) * 14
            y = 80 + (y - 80 - t * (2 + r)) % 520
            dd.ellipse((px(x - r), px(y - r), px(x + r), px(y + r)), fill=(255, 232, 177, 48))
        stage.im.alpha_composite(dust)
        stage.im.alpha_composite(self.vignette)
        if overlays:
            stage.text('СЕМЕЙНЫЕ ИСТОРИИ', 37, 29, 16, GOLD, anchor='lm')
            if shot['kind'] == 'end':
                stage.text('Пилот · 2,5D-анимация', 640, 531, 18, regular=True)
            text = next((s[2] for s in PLAN['subtitles'] if s[0] <= t < s[1]), None)
            if text:
                lines = self.wrap(text, font(27, True), px(1060))
                box_h = len(lines) * 34 + 20
                # Composite translucent panel rather than replacing scene alpha.
                panel = Stage(Image.new('RGBA', (W, H)))
                panel.roundrect((80, 720 - box_h - 24, 1200, 696), 13, fill=(25, 20, 17, 224))
                stage.im.alpha_composite(panel.im)
                for i, line in enumerate(lines):
                    stage.text(line, 640, 720 - box_h - 24 + 12 + i * 34 + 16, 27, regular=True)
        fade = min(smooth(t / .45), smooth((DURATION - t) / .6))
        if fade < 1:
            stage.im = Image.blend(Image.new('RGBA', (W, H), (23, 15, 13, 255)), stage.im, fade)
        return stage.im.convert('RGB')


def run(args):
    subprocess.run([str(a) for a in args], check=True)


def foley():
    """Small original search sweeps and reveal chime; no downloaded sound effects."""
    out = np.zeros(round(DURATION * SR), np.float32)
    rng = np.random.default_rng(33)
    def add(at, sound):
        start = round(at * SR)
        end = min(len(out), start + len(sound))
        out[start:end] += sound[:end - start]
    for at in (10.5, 13.7, 16.4, 18.8):
        n = round(.23 * SR)
        tt = np.arange(n) / SR
        noise = rng.normal(0, 1, n)
        noise = np.convolve(noise, np.ones(25) / 25, mode='same')
        add(at, noise * np.sin(np.pi * tt / .23) ** 2 * .13)
    for at, freq in ((26.7, 659.25), (26.84, 830.61), (27., 987.77)):
        add(at, pluck(freq, 1.1, .08))
    write_wav(str(WORK / 'foley.wav'), out)


def audio_mix():
    write_wav(str(WORK / 'bed.wav'), make_bed(DURATION, bpm=94, fade_out=2.))
    foley()
    cmd = [FFMPEG, '-y', '-v', 'error', '-i', str(WORK / 'bed.wav')]
    for n in PLAN['narration']:
        cmd += ['-i', str(ASSETS / 'audio' / n['file'])]
    cmd += ['-i', str(WORK / 'foley.wav')]
    filters = ['[0:a]volume=0.13[bed]']
    for i, n in enumerate(PLAN['narration'], 1):
        ms = round(n['start'] * 1000)
        filters.append(f"[{i}:a]atempo={PLAN['narration_speed']},adelay={ms}:all=1[v{i}]")
    filters += [f'[v1][v2][v3]amix=inputs=3:normalize=0,apad,atrim=duration={DURATION},asplit=2[voice][key]',
                '[bed][key]sidechaincompress=threshold=0.015:ratio=5:attack=30:release=400[ducked]',
                f'[ducked][voice][4:a]amix=inputs=3:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=8,'
                f'apad,atrim=duration={DURATION},afade=t=out:st=38.3:d=1.7[out]']
    cmd += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-ar', '48000', str(WORK / 'mix.wav')]
    run(cmd)


def validate():
    assert W / H == 16 / 9 and W % 2 == H % 2 == 0
    assert PLAN['shots'][0]['start'] == 0 and PLAN['shots'][-1]['end'] == DURATION
    for i, shot in enumerate(PLAN['shots']):
        assert shot['end'] > shot['start']
        if i:
            assert shot['start'] == PLAN['shots'][i - 1]['end']
    last_end = 0
    for start, end, text in PLAN['subtitles']:
        assert 0 <= start < end <= DURATION and start >= last_end and text.strip()
        last_end = end
    for n in PLAN['narration']:
        assert (ASSETS / 'audio' / n['file']).is_file()
    print('Timeline, shot boundaries, subtitle ordering, audio sources: OK', flush=True)


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--stills', action='store_true')
    p.add_argument('--check', action='store_true')
    p.add_argument('--audio-only', action='store_true', help='Remix and remux cached silent render')
    args = p.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    validate()
    if not args.audio_only:
        pilot = Pilot()
        if args.check:
            for shot in PLAN['shots']:
                for t in (shot['start'], (shot['start'] + shot['end']) / 2, shot['end'] - .001):
                    im = pilot.frame(t)
                    assert im.size == (W, H) and im.mode == 'RGB'
            assert pilot.frame(7).tobytes() == pilot.frame(7).tobytes()
            print(f"{len(PLAN['shots']) * 3} boundary/midpoint frames + deterministic render: OK")
            return
        if args.stills:
            times = [2.7, 6, 9.3, 11.8, 15, 17.6, 20., 23., 25.5, 27.8, 30., 34.]
            contact = Image.new('RGB', (1920, 360 * 4))
            for i, t in enumerate(times):
                im = pilot.frame(t)
                im.save(WORK / f'frame-{i:02}.jpg', quality=94)
                contact.paste(im.resize((640, 360)), ((i % 3) * 640, (i // 3) * 360))
            contact.save(WORK / 'contact.jpg', quality=94)
            pilot.frame(2.7, overlays=False).save(STUDIO / 'out/pilot-letter-p-poster.jpg', quality=94)
            print('Stills:', WORK / 'contact.jpg')
            return
    audio_mix()
    silent = WORK / 'silent.mp4'
    if not args.audio_only:
        cmd = [FFMPEG, '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(FPS), '-i', '-', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
               '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(silent)]
        with subprocess.Popen(cmd, stdin=subprocess.PIPE) as proc:
            try:
                for frame in range(FPS * DURATION):
                    proc.stdin.write(pilot.frame(frame / FPS).tobytes())
                    if frame % (FPS * 5) == 0:
                        print(f'Rendering {frame / FPS:.0f}/{DURATION}s', flush=True)
            finally:
                proc.stdin.close()
            if proc.wait():
                raise RuntimeError('Video encoder failed')
    run([FFMPEG, '-y', '-v', 'error', '-i', silent, '-i', WORK / 'mix.wav', '-map', '0:v:0', '-map', '1:a:0',
         '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(DURATION), '-movflags', '+faststart', OUTPUT])
    run([FFMPEG, '-v', 'error', '-xerror', '-i', OUTPUT, '-f', 'null', '-'])
    print(f'READY {OUTPUT} ({OUTPUT.stat().st_size / 1e6:.1f} MB)', flush=True)


if __name__ == '__main__':
    main()
