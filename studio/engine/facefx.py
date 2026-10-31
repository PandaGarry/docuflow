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


def load_landmarks(char_key: str, view: str = "front") -> dict:
    """Размеченные якоря лица (studio/2p5d/<персонаж>/face.json).

    Автопоиск зрачков по тёмным пятнам на этих портретах не работает: в тёмные
    пятна попадают брови и борода (interpupillary «гулял» от 16 до 400 px).
    Поэтому лицо размечается ОДИН раз руками по сетке, отдельно для каждого
    ракурса, а дальше все слои выравниваются по этой разметке.
    """
    p = ROOT / "studio" / "2p5d" / char_key / "face.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    views = data.get("views", {})
    if view in views:
        return views[view]
    return data if "eyes" in data else {}


_BBOX_CACHE: dict = {}


def portrait_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    """Рамка содержимого портрета.

    Кадры эмоций приходят разного размера (768x1400, 768x1390, 681x1385),
    поэтому доли от размера картинки НЕ работают: одна и та же разметка
    попадала на щёку вместо глаза. Разметка задана в долях от рамки
    содержимого — она у всех кадров одна.
    """
    key = id(img)
    if key in _BBOX_CACHE:
        return _BBOX_CACHE[key]
    a = np.asarray(img.convert("RGBA"))[..., 3] > 40
    ys, xs = np.where(a)
    box = (int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1),
           int(ys.max() - ys.min() + 1)) if len(xs) else (0, 0, img.width, img.height)
    _BBOX_CACHE[key] = box
    return box


def to_canvas(img: Image.Image, canvas: tuple[int, int]) -> Image.Image:
    """Привести портрет к общему холсту по рамке содержимого.

    Кадры эмоций отличаются размером на 5–15 px, и простое наложение падает с
    несовпадением форм. Масштабируем по высоте содержимого и ставим по центру:
    так все портреты одного персонажа совпадают пиксель в пиксель.
    """
    bx, by, bw, bh = portrait_bbox(img)
    cw, ch = canvas
    k = ch / bh
    crop = img.crop((bx, by, bx + bw, by + bh))
    new = crop.resize((max(int(bw * k), 1), ch), Image.LANCZOS)
    out = Image.new("RGBA", canvas, (0, 0, 0, 0))
    out.alpha_composite(new, (int(cw / 2 - new.width / 2), 0))
    return out


def landmarks_px(lm: dict, img: tuple[int, int] | Image.Image) -> dict:
    """Перевести доли от рамки содержимого в пиксели конкретного кадра."""
    if isinstance(img, Image.Image):
        size = img.size
        bx, by, bw, bh = portrait_bbox(img)
    else:
        size = img
        bx, by, bw, bh = 0, 0, size[0], size[1]
    w, h = size

    def pt(pair):
        return (bx + pair[0] * bw, by + pair[1] * bh)

    eyes = [pt(e) for e in lm.get("eyes", [])]
    brows = [pt(e) for e in lm.get("brows", [])]
    mouth = pt(lm.get("mouth", [0.5, 0.37]))
    e_w = lm.get("eye_w", 0.09) * w
    e_h = lm.get("eye_h", 0.04) * w
    return {
        "eyes": eyes,
        "eye_w": e_w,
        "eye_h": e_h,
        "brows": brows,
        "ipd": (abs(eyes[1][0] - eyes[0][0]) if len(eyes) > 1 else 0.0),
        "mid": (sum(p[0] for p in eyes) / max(len(eyes), 1),
                sum(p[1] for p in eyes) / max(len(eyes), 1)),
        "mouth": mouth,
        "mouth_w": lm.get("mouth_w", 0.18) * w,
        "mouth_h": lm.get("mouth_h", 0.055) * w,
    }


# --------------------------------------------------------------------------- #
# выравнивание
# --------------------------------------------------------------------------- #

def align_to(frame: Image.Image, ref: Image.Image, lm: dict) -> tuple[Image.Image, dict, dict]:
    """Привести портрет к масштабу и положению эталона по разметке лица.

    Оба кадра сняты в одном формате, поэтому разметка одна и та же — масштаб
    фактически 1:1; функция оставлена на случай кадров другого размера.
    """
    e_ref = landmarks_px(lm, ref)
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

    Берём при этом не весь овал глаза, а только РАЗНИЦУ между открытым и
    закрытым кадром: у генератора тон кожи вокруг глаза немного другой, и
    сплошной овал оставлял светлое пятно вокруг глаза.
    """
    if amount <= 0.01:
        return base
    px = landmarks_px(lm, base)
    if closed.size != base.size:
        closed = to_canvas(closed, base.size)
    aligned, _, _ = align_to(closed, base, lm)

    b = np.asarray(base.convert("RGBA"), np.float32)
    c = np.asarray(aligned.convert("RGBA"), np.float32)
    diff = np.abs(b[..., :3] - c[..., :3]).mean(axis=2)
    changed = np.clip((diff - 10.0) / 12.0, 0.0, 1.0)

    out = base.copy()
    w, h = base.size
    yy, xx = np.mgrid[0:h, 0:w]
    for (cx, cy) in px["eyes"]:
        rx = max(px["eye_w"] * 0.95, 5)
        ry = max(px["eye_h"] * 1.45, 4)
        cover_y = cy - ry + 2.0 * ry * (1.0 - float(amount))
        edge = max(ry * 0.3, 1.5)
        vert = np.clip((yy - (cover_y - edge)) / edge, 0.0, 1.0)
        oval = np.clip((1.0 - (((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)) * 3.0, 0, 1)
        mask_arr = np.clip(changed * vert * oval, 0.0, 1.0)
        mask = Image.fromarray((mask_arr * 255).astype(np.uint8), "L")
        mask = mask.filter(ImageFilter.GaussianBlur(1.4))
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
    px = landmarks_px(lm, base)
    out = base.copy()
    a = np.asarray(base.convert("RGBA"))
    for (cx, cy) in px["eyes"]:
        r = max(px["eye_h"] * 0.42, 2)
        x0, y0 = int(cx - r), int(cy - r)
        x1, y1 = int(cx + r), int(cy + r)
        if x1 <= x0 or y1 <= y0:
            continue
        canvas = Image.fromarray(a[y0:y1, x0:x1].copy(), "RGBA")
        dest = (int(x0 + dx * px["eye_w"]), int(y0 + dy * px["eye_h"]))
        mask = _ellipse_mask((x1 - x0, y1 - y0), r, r, r, r, feather=1.5)
        out.paste(canvas, dest, mask)
    return out


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
    px = landmarks_px(lm, base)
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
    px = landmarks_px(lm, base)
    cx, cy = px["mouth"]
    rx = px["mouth_w"] * (1.15 if len(px["eyes"]) == 1 else 0.92)
    ry = px["mouth_h"] * 2.0

    if target.size != base.size:
        target = to_canvas(target, base.size)
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


# --------------------------------------------------------------------------- #
# неизменность причёски
# --------------------------------------------------------------------------- #

def _hair_mask(img: Image.Image, cut_y: float) -> np.ndarray:
    """Тёмные волосы выше линии глаз."""
    a = np.asarray(img.convert("RGBA"))
    lum = a[..., :3].astype(np.float32).mean(axis=2)
    m = (lum < 118) & (a[..., 3] > 40)
    m[int(cut_y):, :] = False
    return m


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx > r * r:
                continue
            out |= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    return out


def keep_hair(emotion: Image.Image, canon: Image.Image, lm: dict,
              *, grow: int = 4, feather: float = 3.0) -> Image.Image:
    """Вернуть причёску канона на кадр эмоции.

    Генератор при каждой правке перерисовывает волосы: силуэт причёски
    расходится с эталоном на 10–40 % (замер по IoU маски волос). Для сериала
    это недопустимо — причёска должна быть одинаковой в каждом кадре.

    ВНИМАНИЕ: способ рабочий только частично. Причёски канона и кадра не
    совпадают пиксель в пиксель (разная линия роста волос), и на границе
    остаётся тонкая серая линия. В конвейере НЕ используется; вместо этого
    расхождение причёски измеряется в `qa_mimic` (IoU), а кадры с сильным
    расхождением перегенерируются.

    Ключевой момент: НЕЛЬЗЯ резать по горизонтали. Прямая линия проходит по
    коже лба, и шов видно (тон кожи у кадров чуть разный). Поэтому маска —
    объединение волос канона и волос кадра, слегка раздутое и размытое: шов
    идёт по естественному контуру волос, где тёмное переходит в светлое.
    """
    if emotion.size != canon.size:
        canon = to_canvas(canon, emotion.size)
    px = landmarks_px(lm, emotion)
    if not px["eyes"]:
        return emotion
    # строго выше бровей: брови — тоже тёмные. Если пустить маску ниже,
    # перенос стирает выражение и оставляет бледное эхо бровей канона
    if px["brows"]:
        cut = min(y for (_, y) in px["brows"]) - 1.2 * px["eye_h"]
    else:
        cut = min(y for (_, y) in px["eyes"]) - 3.6 * px["eye_h"]
    union = _hair_mask(canon, cut) | _hair_mask(emotion, cut)
    union = _dilate(union, grow)
    union[int(cut):, :] = False
    mask = Image.fromarray((union * 255).astype(np.uint8), "L")
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))
    out = emotion.copy()
    patch = Image.new("RGBA", emotion.size, (0, 0, 0, 0))
    patch.paste(canon, (0, 0), mask)
    out.alpha_composite(patch)
    return out
