"""Живость лица: глаза и рот как слои поверх кадра эмоции.

Зачем отдельный модуль. Эмоции — это статичные портреты, но в сериале нужны:
моргание, бегающий взгляд, речь. Генерировать каждый кадр заново нельзя — лицо
«поплывёт» между кадрами. Поэтому лицо собирается из базы и слоёв:

1. **База** — портрет эмоции (`emotions/*.png`).
2. **Глаза** — берутся из той же базы в другом состоянии (`eyes-closed`).
   Моргание = наложение закрытых век на область глаз с мягкой маской, а не
   подмена всего лица: тогда причёска и борода не дёргаются.
3. **Взгляд** — зрачок ищется как тёмное пятно в области глаза и сдвигается
   на 2–6 % ширины глаза. Это дёшево и не требует новых генераций.
4. **Рот** — форма рта под визем берётся из портретов виземов, вырезается
   овалом вокруг рта и накладывается с растушёвкой по краю.

Все слои выравниваются **по центрам зрачков**: масштаб головы в портретах
гуляет (head_w 537…710), а межзрачковое расстояние — самый устойчивый якорь.

Границы применимости: голова должна быть в одном ракурсе (фронт), поворот
больше ~20° ломает и моргание, и рот. Для профиля нужны отдельные базы.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import poselib as pl

ROOT = Path(__file__).resolve().parents[2]


def load_landmarks(char_key: str) -> dict:
    """Размеченные якоря лица (studio/2p5d/<персонаж>/face.json).

    Автопоиск зрачков по тёмным пятнам на этих портретах не работает: в тёмные
    пятна попадают брови и борода (interpupillary «гулял» от 16 до 400 px).
    Поэтому лицо размечается ОДИН раз руками по сетке, а дальше все слои
    выравниваются по этой разметке. Разметка — часть канона персонажа.
    """
    p = ROOT / "studio" / "2p5d" / char_key / "face.json"
    return json.loads(p.read_text()) if p.exists() else {}


def landmarks_px(lm: dict, size: tuple[int, int]) -> dict:
    """Перевести доли в пиксели конкретного кадра."""
    w, h = size
    e = lm.get("eyes", {})
    m = lm.get("mouth", {})
    return {
        "L": (e["L"][0] * w, e["L"][1] * h),
        "R": (e["R"][0] * w, e["R"][1] * h),
        "ipd": e.get("ipd", 0.25) * w,
        "eye_w": e.get("eye_w", 0.09) * w,
        "eye_h": e.get("eye_h", 0.04) * w,
        "mid": ((e["L"][0] + e["R"][0]) / 2 * w, e["L"][1] * h),
        "mouth": (m.get("cx", 0.5) * w, m.get("cy", 0.37) * h),
        "mouth_w": m.get("w", 0.18) * w,
        "mouth_h": m.get("h", 0.055) * w,
    }


# --------------------------------------------------------------------------- #
# якоря лица
# --------------------------------------------------------------------------- #

def _dark_map(rgb: np.ndarray) -> np.ndarray:
    """Маска тёмных пикселей: зрачки и брови темнее всего на лице."""
    lum = rgb.astype(np.float32).mean(axis=2)
    return lum < 90


def find_eyes(img: Image.Image, *, search_top: float = 0.18,
              search_bottom: float = 0.55) -> dict:
    """Найти центры зрачков.

    Ищем тёмные пятна в средней трети головы: брови выше, борода ниже, зрачки
    между ними. Из тёмных пикселей берём кластеры и отбираем пару, у которой
    центры на одной высоте и между ними есть зазор — это и есть глаза.
    """
    a = np.asarray(img.convert("RGBA"))
    rgb, alpha = a[..., :3], a[..., 3] > 40
    ys, xs = np.where(alpha)
    if not len(ys):
        return {}
    top, bot = ys.min(), ys.max()
    h = bot - top + 1
    d = _dark_map(rgb) & alpha
    d[: int(top + search_top * h), :] = False
    d[int(top + search_bottom * h):, :] = False

    # кластеризация по сетке 4 px (без scipy)
    scale = 4
    hh, ww = d.shape
    ch, cw = hh // scale, ww // scale
    small = d[: ch * scale, : cw * scale].reshape(ch, scale, cw, scale).any(axis=(1, 3))
    seen = np.zeros_like(small)
    blobs = []
    from collections import deque
    for sy in range(ch):
        for sx in range(cw):
            if not small[sy, sx] or seen[sy, sx]:
                continue
            q = deque([(sy, sx)])
            seen[sy, sx] = True
            pts = []
            while q:
                y, x = q.popleft()
                pts.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < ch and 0 <= nx < cw and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if len(pts) >= 6:                     # мелкие блики не считаем
                py = [p[0] for p in pts]
                px = [p[1] for p in pts]
                blobs.append({
                    "cx": (min(px) + max(px) + 1) * scale / 2,
                    "cy": (min(py) + max(py) + 1) * scale / 2,
                    "w": (max(px) - min(px) + 1) * scale,
                    "h": (max(py) - min(py) + 1) * scale,
                    "area": len(pts) * scale * scale,
                })
    if len(blobs) < 2:
        return {}
    # пара: похожий размер, одна высота, максимальная площадь суммарно
    best, best_score = None, -1e9
    for i in range(len(blobs)):
        for j in range(i + 1, len(blobs)):
            a1, b1 = blobs[i], blobs[j]
            if a1["cx"] > b1["cx"]:
                a1, b1 = b1, a1
            gap = b1["cx"] - a1["cx"]
            if gap < 0.06 * ww or gap > 0.75 * ww:
                continue
            size_ratio = min(a1["area"], b1["area"]) / max(a1["area"], b1["area"])
            dy = abs(a1["cy"] - b1["cy"])
            score = size_ratio * 2 - dy / (0.2 * h) + (a1["area"] + b1["area"]) / (h * ww)
            if score > best_score:
                best_score = score
                best = (a1, b1)
    if best is None:
        return {}
    left, right = best
    return {
        "L": (left["cx"], left["cy"]),
        "R": (right["cx"], right["cy"]),
        "ipd": right["cx"] - left["cx"],
        "eye_w": (left["w"] + right["w"]) / 2,
        "eye_h": (left["h"] + right["h"]) / 2,
        "mid": ((left["cx"] + right["cx"]) / 2, (left["cy"] + right["cy"]) / 2),
    }


# --------------------------------------------------------------------------- #
# выравнивание
# --------------------------------------------------------------------------- #

def align_to(frame: Image.Image, ref: Image.Image, lm: dict) -> tuple[Image.Image, dict, dict]:
    """Привести портрет к масштабу и положению эталона по разметке лица.

    Оба кадра сняты в одном формате, поэтому разметка одна и та же — масштаб
    фактически 1:1; функция оставлена на случай кадров другого размера.
    """
    e_ref = landmarks_px(lm, ref.size)
    if frame.size == ref.size:
        return frame, e_ref, e_ref
    k = ref.size[0] / frame.size[0]
    w, h = frame.size
    new = frame.resize((max(int(w * k), 1), max(int(h * k), 1)), Image.LANCZOS)
    dx = e_ref["mid"][0] - e_fr["mid"][0] * k
    dy = e_ref["mid"][1] - e_fr["mid"][1] * k
    canvas = Image.new("RGBA", ref.size, (0, 0, 0, 0))
    canvas.alpha_composite(new, (int(dx), int(dy)))
    return canvas, e_ref, e_ref


# --------------------------------------------------------------------------- #
# моргание
# --------------------------------------------------------------------------- #

def _ellipse_mask(size: tuple[int, int], cx: float, cy: float,
                  rx: float, ry: float, feather: float = 3.0) -> Image.Image:
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w]
    d = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    m = np.clip((1.0 - d) * 4.0, 0.0, 1.0) * 255
    img = Image.fromarray(m.astype(np.uint8), "L")
    return img.filter(ImageFilter.GaussianBlur(feather)) if feather else img


def blink(base: Image.Image, closed: Image.Image, *, lm: dict,
          amount: float = 1.0) -> Image.Image:
    """Опустить веко на `amount` (0 — открыто, 1 — закрыто).

    Не смешивать кадры: полупрозрачное наложение двух разных век даёт смаз.
    Правильнее «напускать» закрытое веко сверху вниз с мягкой границей — так
    это и выглядит на видео: сначала кожа века, потом смыкание.
    """
    if amount <= 0.01:
        return base
    px = landmarks_px(lm, base.size)
    aligned, _, _ = align_to(closed, base, lm)
    out = base.copy()
    w, h = base.size
    for side in ("L", "R"):
        cx, cy = px[side]
        rx = max(px["eye_w"] * 0.86, 5)
        ry = max(px["eye_h"] * 1.25, 4)
        # мягкая граница века: при amount=1 покрыт весь овал
        yy, xx = np.mgrid[0:h, 0:w]
        cover_y = cy - ry + 2.0 * ry * (1.0 - float(amount))
        edge = max(ry * 0.28, 1.5)
        vert = np.clip((yy - (cover_y - edge)) / edge, 0.0, 1.0)
        oval = np.clip((1.0 - (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)) * 4.0, 0, 1)
        mask = Image.fromarray((np.clip(vert * oval, 0, 1) * 255).astype(np.uint8), "L")
        mask = mask.filter(ImageFilter.GaussianBlur(1.6))
        patch = Image.new("RGBA", base.size, (0, 0, 0, 0))
        patch.paste(aligned, (0, 0), mask)
        out.alpha_composite(patch)
    return out


# --------------------------------------------------------------------------- #
# взгляд
# --------------------------------------------------------------------------- #

def look(base: Image.Image, lm: dict, dx: float = 0.0,
         dy: float = 0.0) -> Image.Image:
    """Сдвинуть зрачки внутри глаз: `dx`, `dy` — в долях ширины глаза."""
    eyes = landmarks_px(lm, base.size)
    out = base.copy()
    a = np.asarray(base.convert("RGBA"))
    for side in ("L", "R"):
        cx, cy = eyes[side]
        r = max(eyes["eye_h"] * 0.42, 2)
        # зрачок: тёмное пятно вокруг центра
        x0, y0 = int(cx - r), int(cy - r)
        x1, y1 = int(cx + r), int(cy + r)
        if x1 <= x0 or y1 <= y0:
            continue
        patch = a[y0:y1, x0:x1].copy()
        canvas = Image.fromarray(patch, "RGBA")
        dest = (int(x0 + dx * eyes["eye_w"]), int(y0 + dy * eyes["eye_h"]))
        mask = _ellipse_mask((x1 - x0, y1 - y0), r, r, r, r, feather=1.5)
        out.paste(canvas, dest, mask)
    return out


# --------------------------------------------------------------------------- #
# проверка
# --------------------------------------------------------------------------- #

def report(char_key: str) -> str:
    """Якоря лица персонажа — для проверки глазами по сетке."""
    lm = load_landmarks(char_key)
    if not lm:
        return "нет face.json — разметить лицо по сетке"
    lib = pl.Library(char_key)
    fr = lib.emotion("neutral")
    if fr is None:
        return "нет neutral.png"
    px = landmarks_px(lm, fr.img.size)
    return (f"кадр {fr.img.size}: глаза L={tuple(round(v) for v in px['L'])} "
            f"R={tuple(round(v) for v in px['R'])} ipd={px['ipd']:.0f} "
            f"рот={tuple(round(v) for v in px['mouth'])} w={px['mouth_w']:.0f}")


# --------------------------------------------------------------------------- #
# рот под речь
# --------------------------------------------------------------------------- #

def _gray(img: Image.Image) -> np.ndarray:
    a = np.asarray(img.convert("RGBA"), np.float32)
    lum = a[..., :3].mean(axis=2)
    alpha = a[..., 3] / 255.0
    return lum * alpha


def estimate_shift(base: Image.Image, target: Image.Image, lm: dict) -> tuple[float, float]:
    """Сдвиг между кадрами через фазовую корреляцию.

    Виземы сгенерированы как правка портрета, но генератор слегка сдвигает
    лицо (на 3–8 px). Если накладывать рот без учёта сдвига, вокруг рта видно
    кольцо — граница между двумя версиями лица. Здесь считаем сдвиг по области
    щёк и носа и возвращаем его, чтобы наложение было точным.
    """
    px = landmarks_px(lm, base.size)
    (ex, ey) = px["mid"]
    w, h = base.size
    r = int(min(w, h) * 0.16)
    box = (int(ex - r), int(ey - r * 0.4), int(ex + r), int(ey + r * 1.6))
    A = _gray(base.crop(box))
    B = _gray(target.crop(box))
    fa = np.fft.rfft2(A - A.mean())
    fb = np.fft.rfft2(B - B.mean())
    cc = np.fft.irfft2(fa * np.conj(fb), s=A.shape)
    dy, dx = np.unravel_index(int(np.argmax(cc)), cc.shape)
    if dy > A.shape[0] // 2:
        dy -= A.shape[0]
    if dx > A.shape[1] // 2:
        dx -= A.shape[1]
    return float(dx), float(dy)


def align_shift(target: Image.Image, dx: float, dy: float) -> Image.Image:
    """Сдвинуть кадр на (dx, dy), не оставляя чёрных полос по краям."""
    a = np.asarray(target.convert("RGBA"))
    h, w = a.shape[:2]
    out = np.zeros_like(a)
    sx0, sx1 = max(int(dx), 0), w + min(int(dx), 0)
    sy0, sy1 = max(int(dy), 0), h + min(int(dy), 0)
    dx0, dx1 = max(-int(dx), 0), w + min(-int(dx), 0)
    dy0, dy1 = max(-int(dy), 0), h + min(-int(dy), 0)
    out[sy0:sy1, sx0:sx1] = a[dy0:dy1, dx0:dx1]
    return Image.fromarray(out, "RGBA")


def morph_mouth(base: Image.Image, target: Image.Image, lm: dict,
                amount: float = 1.0, *, threshold: float = 12.0) -> Image.Image:
    """Подмешать форму рта из визема, не трогая остальное лицо.

    Просто «наложить овал вокруг рта» не годится: генератор рисует слегка
    ДРУГОЕ лицо, и по границе овала видно кольцо. Поэтому берём из визема
    только те пиксели, которые реально изменились (губы и рот), а остальное
    оставляем из базы. Маска — разность кадров, сглаженная и ограниченная
    овалом вокруг рта по разметке.
    """
    px = landmarks_px(lm, base.size)
    cx, cy = px["mouth"]
    rx = px["mouth_w"] * 0.92
    ry = px["mouth_h"] * 2.0

    b = np.asarray(base.convert("RGBA"), np.float32)
    t = np.asarray(target.convert("RGBA"), np.float32)
    diff = np.abs(b[..., :3] - t[..., :3]).mean(axis=2)
    soft = np.clip((diff - threshold) / max(threshold, 1.0), 0.0, 1.0)

    h, w = diff.shape
    yy, xx = np.mgrid[0:h, 0:w]
    oval = np.clip((1.0 - (((xx - cx) / rx) ** 2 + ((yy - cy - ry * 0.1) / ry) ** 2)) * 3.0,
                   0.0, 1.0)
    mask_arr = np.clip(soft * oval * float(amount), 0.0, 1.0)
    mask = Image.fromarray((mask_arr * 255).astype(np.uint8), "L")
    mask = mask.filter(ImageFilter.GaussianBlur(3.0))

    out = base.copy()
    patch = Image.new("RGBA", base.size, (0, 0, 0, 0))
    patch.paste(target, (0, 0), mask)
    out.alpha_composite(patch)
    return out


# --------------------------------------------------------------------------- #
# микродвижение головы
# --------------------------------------------------------------------------- #

def breathe(base: Image.Image, t: float, *, amp: float = 0.006) -> Image.Image:
    """Дыхание: голова и плечи чуть вверх-вниз, период ~4 с.

    `t` — время в секундах. Возвращает кадр, сдвинутый на доли процента роста:
    на видео это читается как живой человек, а не как наклейка.
    """
    import math
    dy = math.sin(2 * math.pi * t / 4.0) * amp * base.height
    out = Image.new("RGBA", base.size, (0, 0, 0, 0))
    out.alpha_composite(base, (0, int(dy)))
    return out
