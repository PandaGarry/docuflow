"""Тестовые ролики движений персонажа: одно место, где всё проверяется глазами.

    python studio/tools/motion_reel.py dad gestures
    python studio/tools/motion_reel.py dad emotions
    python studio/tools/motion_reel.py dad all

Зачем отдельный инструмент
--------------------------
Кадры ещё не движение. Смотреть надо именно ленту: только на ней видно
перескок на стыке ключей, «двойника» от оптического потока и потерянный
контакт с полом.

Как устроены переходы
---------------------
Поза не подменяется следующей картинкой в один кадр: между ключами
вставляются промежуточные кадры (`inbetween.blend` — оптический поток DIS с
проверкой видимости). Переход длится 8–10 кадров, держание — 0,5 с. Именно
это убирает «перескок», который видно при 12 кадрах в секунду на двойках.

Регистрация кадров
------------------
Каждый кадр ставится на холст по голове (её центр — в одну точку), а не по
центру корпуса: центр корпуса в нарисованных отдельно кадрах гуляет на
30–40 px, и персонаж начинает дрожать. Голова при движении на месте стоит.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image, ImageDraw

import characters as ch
import inbetween as ib
import poselib as pl

ROOT = HERE.parents[2]
OUT = ROOT / "studio" / "out"

W, H = 720, 900
GROUND = H - 110
BODY_H = 0.74 * H
FPS = 24
BG = (238, 235, 229)
INK = (60, 56, 52)

# Что смотрим: порядок не случайный — сначала база, потом жесты, потом эмоции.
GESTURES = [
    "idle", "idle-tired", "wave", "point", "think", "cross-arms", "crouch",
    "sit", "salute", "count-one", "fist-up", "clap", "reach-up", "reach-forward",
    "carry", "phone", "read-phone", "eat", "drink", "kneel", "lie-down",
]
EMOTIONS = ["neutral", "happy", "laugh", "smirk", "wink", "annoyed", "angry",
            "sad", "scared", "surprised", "confused", "thinking", "tired",
            "eyes-closed"]


def place(frame: pl.Frame, *, head_reg: bool = False) -> Image.Image:
    """Кадр на общий холст: масштаб по росту, регистрация по голове или корпусу."""
    img = frame.img.convert("RGBA")
    a = frame.anchor
    scale = BODY_H / max(1, a.get("height_px", img.height))
    small = img.resize((max(2, int(img.width * scale)), max(2, int(img.height * scale))),
                       Image.LANCZOS)
    if head_reg:
        hx = a.get("head_cx", img.width / 2) * scale
        hy = a.get("head_cy", img.height * 0.1) * scale
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        canvas.alpha_composite(small, (int(W / 2 - hx), int(0.18 * H - hy)))
        return canvas
    cx = a.get("body_cx", img.width / 2) * scale
    fy = a.get("foot_y", img.height) * scale
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    canvas.alpha_composite(small, (int(W / 2 - cx), int(GROUND - fy)))
    return canvas


def compose(sprite: Image.Image, caption: str, sub: str = "") -> np.ndarray:
    """Положить спрайт на фон, добавить подпись — чтобы на видео было видно,
    какой кадр показывается."""
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, GROUND, W, H], fill=(216, 212, 204))
    d.line([(0, GROUND), (W, GROUND)], fill=(150, 146, 138), width=3)
    canvas.paste(sprite, (0, 0), sprite.getchannel("A"))
    d.text((24, 24), caption, fill=INK)
    if sub:
        d.text((24, 44), sub, fill=(120, 116, 110))
    return np.asarray(canvas)


def transition(a: Image.Image, b: Image.Image, frames: int) -> list[Image.Image]:
    """Промежуточные кадры между двумя позами."""
    return [ib.blend(a, b, (k + 1) / (frames + 1)) for k in range(frames)]


def gestures(char_key: str, keys: list[str] | None = None,
             mode: str = "cut") -> list[np.ndarray]:
    """Позы в ленте: держание → смена позы.

    По умолчанию смена — **склейка**, а не смешивание. Почему: каждая поза
    нарисована отдельно, и у неё своё лицо и своя складка на свитере. Любой
    морфинг между двумя такими рисунками даёт «двойную экспозицию» — два рта,
    две руки. В мультсериалах поза меняется склейкой или рисуется движением,
    а не растворяется. Морфинг оставлен флагом `morph` — он годится только
    для пары кадров, снятых с одного мастера.
    """
    lib = pl.Library(char_key)
    keys = keys or [k for k in GESTURES if lib.pose(k) is not None]
    hold = int(0.7 * FPS)
    trans = int(0.42 * FPS)
    out: list[np.ndarray] = []
    placed = [(k, place(lib.pose(k), head_reg=True)) for k in keys]
    for i, (key, sprite) in enumerate(placed):
        for _ in range(hold):
            out.append(compose(sprite, key, "держание"))
        nxt_key, nxt = placed[(i + 1) % len(placed)]
        if mode == "morph":
            for f in transition(sprite, nxt, trans):
                out.append(compose(f, f"{key} → {nxt_key}", "переход"))
        else:
            out.append(compose(nxt, f"{key} → {nxt_key}", "склейка"))
    return out


def emotions(char_key: str) -> list[np.ndarray]:
    """Все эмоции лица подряд с плавным переходом."""
    char = ch.CHARACTERS[char_key]
    views = ["front", "three-quarter", "side"]
    frames: list[tuple[str, Image.Image]] = []
    for view in views:
        for ek in [k for k in EMOTIONS
                   if (char.dir / "emotions" / view / f"{k}.png").exists()]:
            img = Image.open(char.dir / "emotions" / view / f"{ek}.png").convert("RGBA")
            frames.append((f"{view}/{ek}", img))
    if not frames:
        return []
    # портреты уже одного размера и одной рамки — только масштаб под кадр
    sc = 0.78 * H / frames[0][1].height
    tw = int(frames[0][1].width * sc)
    th = int(frames[0][1].height * sc)
    small = [(n, im.resize((tw, th), Image.LANCZOS)) for n, im in frames]
    hold = int(0.45 * FPS)
    trans = int(0.3 * FPS)
    out: list[np.ndarray] = []
    for i, (name, im) in enumerate(small):
        nxt_name, nxt = small[(i + 1) % len(small)]
        for _ in range(hold):
            out.append(_portrait_frame(im, name))
        for k in range(trans):
            out.append(_portrait_frame(ib.blend(im, nxt, (k + 1) / (trans + 1)),
                                       f"{name} → {nxt_name}"))
    return out


def _portrait_frame(img: Image.Image, caption: str) -> np.ndarray:
    canvas = Image.new("RGB", (W, H), BG)
    canvas.paste(img, ((W - img.width) // 2, 40), img.getchannel("A"))
    ImageDraw.Draw(canvas).text((24, 24), caption, fill=INK)
    return np.asarray(canvas)


def save(frames: list[np.ndarray], path: Path) -> Path:
    import imageio.v2 as imageio
    w = imageio.get_writer(path, fps=FPS, quality=9, macro_block_size=1)
    for f in frames:
        w.append_data(f)
    w.close()
    print(f"{path}  {len(frames)} кадров, {len(frames) / FPS:.1f} с")
    return path


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    what = sys.argv[2] if len(sys.argv) > 2 else "all"
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    if what == "all":
        import imageio.v2 as imageio
        import cycle_preview as cp
        parts: list[np.ndarray] = []
        for cyc in ("walk", "run"):
            path = cp.main(key, cyc)
            parts += [np.asarray(f) for f in imageio.get_reader(path)]
        made.append(save(gestures(key) + emotions(key) + parts,
                         OUT / f"{key}-motion-test.mp4"))
        return 0
    if what in ("gestures", "all"):
        made.append(save(gestures(key), OUT / f"{key}-reel-gestures.mp4"))
    if what == "morph":
        made.append(save(gestures(key, mode="morph"),
                         OUT / f"{key}-reel-gestures-morph.mp4"))
    if what in ("emotions", "all"):
        made.append(save(emotions(key), OUT / f"{key}-reel-emotions.mp4"))
    if what in ("cycles", "all"):
        import cycle_preview as cp
        for cyc in ("walk", "run"):
            try:
                made.append(cp.main(key, cyc))
            except SystemExit as e:  # нет кадров цикла — это ещё не ошибка сборки
                print(f"{cyc}: пропущен ({e})")
    if not made:
        print("нечего собирать: gestures | emotions | cycles | all")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
