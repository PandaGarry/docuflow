"""2D-риг из одного рисунка: части, шарниры, поворот вместо растяжения.

Зачем
-----
Промежуточные кадры по оптическому потоку тянут картинку: на быстрых фазах
нога вытягивается, руки плывут. Так не бывает у аниматора: он поворачивает
ногу вокруг бедра, а не растягивает её.

Риг делает то же самое. Из ОДНОГО рисунка вырезаются части:
голова, торс, плечо, предплечье, бедро, голень со стопой. У каждой части свой
шарнир. Кадр собирается поворотом частей вокруг шарниров.

Почему один рисунок, а не весь набор поз: части, взятые из одного кадра,
согласованы между собой по размеру и стилю по определению. Это убирает
главную болезнь генератора — «причёска и пропорции гуляют от кадра к кадру».

Дальняя сторона: в профильном рисунке видна только одна рука и одна нога.
Вторая берётся из тех же частей, затемняется и кладётся ПОД торс — так делают
в cutout-анимации. Это даёт полноценный цикл шага с двумя ногами.

Порядок отрисовки (сзади вперёд):
дальняя рука → дальняя нога → торс → голова → ближняя нога → ближняя рука.

Ограничение: это плоская кукольная анимация. При повороте больше ~25° шарнир
даёт видимый излом на сгибе, потому что «мяса» за шарниром нет.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Part:
    """Кусок рисунка с шарниром в собственных координатах."""

    name: str
    img: Image.Image          # вырезанная часть, RGBA
    pivot: tuple[float, float]  # шарнир в координатах части
    z: int                    # порядок отрисовки: меньше — дальше
    dark: float = 0.0         # затемнение (для дальней стороны)


drawing_ref: dict = {}


def _shape_mask(size: tuple[int, int], shape, feather: float = 1.5) -> Image.Image:
    """Маска по фигуре: полигон (доли кадра) или капсула (пиксели).

    Капсула — это отрезок с радиусом: вдоль него ставятся круги. Зачем:
    у квада на конце конечности острые углы, и при повороте вокруг шарнира
    они вылезают наружу — на сгибе колена видна «ступенька». Круглый конец
    вращается вокруг своего центра и стык остаётся закрытым.

        {"capsule": [[x0, y0], [x1, y1], r]}     # пиксели рисунка
    """
    from PIL import ImageDraw
    w, h = size
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    if isinstance(shape, dict) and "capsule" in shape:
        (ax, ay), (bx, by), r = shape["capsule"][:3]
        r2 = shape["capsule"][3] if len(shape["capsule"]) > 3 else r
        # круг через каждые полрадиуса — контур получается гладким
        n = max(2, int(math.hypot(bx - ax, by - ay) / max(1.0, min(r, r2) * 0.25)))
        for i in range(n + 1):
            t = i / n
            cx, cy = ax + (bx - ax) * t, ay + (by - ay) * t
            rr = r + (r2 - r) * t
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=255)
    elif isinstance(shape, dict) and "rect" in shape:
        x0, y0, x1, y1 = shape["rect"]
        d.rectangle((x0 * w, y0 * h, x1 * w, y1 * h), fill=255)
    elif isinstance(shape, dict) and "band" in shape:
        # Полоса по высоте: маска = сам силуэт рисунка в этих строках.
        # Капсула шире или уже реальной ноги, и на сгибе открывалась щель.
        # Силуэт же совпадает с рисунком по определению, поэтому в покое
        # собранный кадр равен мастеру пиксель в пиксель.
        y0, y1 = shape["band"]
        a = np.asarray(drawing_ref.get("alpha")) if drawing_ref else None
        if a is None:
            m.paste(255, (0, int(y0 * h), w, int(y1 * h)))
        else:
            mm = np.zeros((h, w), np.uint8)
            mm[int(y0 * h):int(y1 * h)] = (a[int(y0 * h):int(y1 * h)] > 40) * 255
            m.paste(Image.fromarray(mm))
            # Круг вокруг шарнира: он вращается вместе с частью и поэтому
            # выглядит неподвижным. Прямой срез на сгибе давал видимую
            # «ступеньку» — полосу джинсов поперёк колена.
            if "disc_at" in shape:
                (cx, cy), r = shape["disc_at"], shape.get("disc_r", 46)
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
            # перо по краю обязательно: иначе на сгибе видна жёсткая ступень
            return m.filter(ImageFilter.GaussianBlur(feather)) if feather else m
    elif isinstance(shape, dict) and "poly" in shape:
        d.polygon([(x * w, y * h) for x, y in shape["poly"]], fill=255)
        if "disc_at" in shape:
            (cx, cy), r = shape["disc_at"], shape.get("disc_r", 46)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        return m.filter(ImageFilter.GaussianBlur(feather)) if feather else m
    elif isinstance(shape, dict) and "capsule" in shape and "disc_at" in shape:
        (ax, ay), (bx, by), r = shape["capsule"][:3]
        r2 = shape["capsule"][3] if len(shape["capsule"]) > 3 else r
        n = max(2, int(math.hypot(bx - ax, by - ay) / max(1.0, min(r, r2) * 0.25)))
        for i in range(n + 1):
            t = i / n
            cx, cy = ax + (bx - ax) * t, ay + (by - ay) * t
            rr = r + (r2 - r) * t
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), fill=255)
        (dx, dy), dr = shape["disc_at"], shape.get("disc_r", 46)
        d.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), fill=255)
        return m.filter(ImageFilter.GaussianBlur(feather)) if feather else m
    elif isinstance(shape, dict) and "disc" in shape:
        (cx, cy), r = shape["disc"]
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    else:
        d.polygon([(x * w, y * h) for x, y in shape], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather)) if feather else m


def _poly_mask(size: tuple[int, int], pts: list[tuple[float, float]],
               feather: float = 1.5) -> Image.Image:
    """Маска по полигону в долях кадра."""
    w, h = size
    from PIL import ImageDraw
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).polygon([(x * w, y * h) for x, y in pts], fill=255)
    return m.filter(ImageFilter.GaussianBlur(feather)) if feather else m


def _inpaint(img: Image.Image, holes: list) -> Image.Image:
    """Заполнить дыры, оставшиеся от вырезанных частей.

    Когда рука вырезана из торса, при повороте руки в свитере открывается
    дыра. Закрашиваем её восстановлением по окружению (inpaint): свитер
    однотонный, шов не видно. Без этого риг непригоден — это первое, что
    бросается в глаза.
    """
    import cv2
    if not holes:
        return img
    a = np.asarray(img.convert("RGBA")).copy()
    h, w = a.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for shape in holes:
        mask = np.maximum(mask, np.asarray(_shape_mask((w, h), shape, 0)))
    bgr = cv2.cvtColor(a[..., :3], cv2.COLOR_RGB2BGR)
    # У прозрачных пикселей RGB остаётся зелёным от хромакея — inpaint
    # подтянул бы зелень в свитер. Сначала латаем сам прозрачный фон.
    clear = (a[..., 3] == 0).astype(np.uint8) * 255
    bgr = cv2.inpaint(bgr, clear, 7, cv2.INPAINT_TELEA)
    filled = cv2.inpaint(bgr, mask, 5, cv2.INPAINT_TELEA)
    out = a.copy()
    sel = (mask > 0) & (a[..., 3] > 0)
    out[sel, :3] = cv2.cvtColor(filled, cv2.COLOR_BGR2RGB)[sel]
    out[sel, 3] = 255
    return Image.fromarray(out, "RGBA")


def pad_around_pivot(piece: Image.Image,
                     pivot: tuple[float, float]) -> tuple[Image.Image, tuple[float, float]]:
    """Расширить кусок так, чтобы поворот вокруг шарнира его не обрезал.

    Кусок вырезается по своему bounding box, а `Image.rotate` крутит внутри
    того же холста — при повороте на 60–90° половина руки уходила за край и
    просто исчезала. Поэтому холст куска расширяется до радиуса от шарнира до
    самого дальнего угла, и шарнир встаёт в центр.
    """
    px, py = pivot
    w, h = piece.size
    r = max(math.hypot(px, py), math.hypot(w - px, py),
            math.hypot(px, h - py), math.hypot(w - px, h - py))
    side = int(math.ceil(r)) + 2
    out = Image.new("RGBA", (side * 2, side * 2), (0, 0, 0, 0))
    out.alpha_composite(piece, (int(side - px), int(side - py)))
    return out, (float(side), float(side))


def _crop_alpha(img: Image.Image, mask: Image.Image) -> Image.Image:
    """Вырезать часть: умножить альфу картинки на маску."""
    a = np.asarray(img.convert("RGBA")).astype(np.float32)
    m = np.asarray(mask).astype(np.float32) / 255.0
    a[..., 3] *= m
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def load_rig(char_key: str, view: str = "side") -> dict:
    p = ROOT / "studio" / "2p5d" / char_key / f"rig-{view}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _rot(v: np.ndarray, deg: float) -> np.ndarray:
    """Повернуть вектор на угол в градусах (ось Y вниз, экранная)."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([v[0] * c - v[1] * s, v[0] * s + v[1] * c])


class Puppet:
    """Собранный персонаж: части + шарниры + отрисовка в позе.

    Вращение иерархическое: поворот бедра тянет за собой колено и стопу.
    Это прямой кинематический расчёт (FK), как в любом 2D-риге.
    """

    def __init__(self, drawing: Image.Image, spec: dict):
        self.size = drawing.size
        self.spec = spec
        self.parts: dict[str, Part] = {}
        self.patches: list[Part] = []
        for q in spec.get("patches", []):
            cx, cy = q["sample"]
            r = q["r"]
            x0, y0 = int(cx * drawing.width - r), int(cy * drawing.height - r)
            box = (x0, y0, x0 + 2 * r, y0 + 2 * r)
            piece = drawing.crop(box)
            m = Image.new("L", piece.size, 0)
            from PIL import ImageDraw
            ImageDraw.Draw(m).ellipse((6, 6, piece.width - 6, piece.height - 6), fill=255)
            m = m.filter(ImageFilter.GaussianBlur(6))
            piece = _crop_alpha(piece, m)
            self.patches.append(Part(
                name=f"patch:{q['joint']}", img=piece, pivot=(r, r),
                z=q.get("z", 0), dark=q.get("dark", 0.0)))
            self.part_joint = getattr(self, "part_joint", {})
            self.part_joint[f"patch:{q['joint']}"] = q["joint"]
        order = sorted(spec["parts"].items(),
                       key=lambda kv: 0 if "from" not in kv[1] else 1)
        for name, p in order:
            if "from" in p:
                src_part = self.parts[p["from"]]
                piece = src_part.img
                if p.get("dark"):
                    arr = np.asarray(piece).astype(np.float32)
                    arr[..., :3] *= 1.0 - p["dark"]
                    piece = Image.fromarray(arr.astype(np.uint8), "RGBA")
                self.parts[name] = Part(
                    name=name, img=piece,
                    pivot=(src_part.pivot[0] + p.get("dx", 0),
                           src_part.pivot[1]),
                    z=p.get("z", 0), dark=0.0)
                continue
            src = _inpaint(drawing, p.get("holes", []))
            drawing_ref["alpha"] = np.asarray(drawing.convert("RGBA"))[..., 3]
            mask = _shape_mask(drawing.size, p.get("shape", p.get("poly")),
                               p.get("feather", 1.5))
            # Порядок важен: сначала вычитаем, потом добавляем.
            # Капсула плеча захватывает часть груди; если её не вычесть, при
            # подъёме руки вместе с рукавом поворачивался кусок торса —
            # получалась «плита» свитера. Вырезаем середину груди, а круг на
            # плече добавляем ПОСЛЕ — он нужен целым, он закрывает стык.
            for sub in p.get("subtract", []):
                m = np.asarray(mask).copy()
                s_mask = np.asarray(_shape_mask(drawing.size, sub, 0))
                m[s_mask > 127] = 0
                mask = Image.fromarray(m)
            for extra in p.get("extra", []):
                mask = Image.fromarray(np.maximum(
                    np.asarray(mask), np.asarray(_shape_mask(
                        drawing.size, extra, p.get("feather", 1.5)))).astype(np.uint8))
            piece = _crop_alpha(src, mask)
            bbox = piece.getbbox()
            if not bbox:
                continue
            piece = piece.crop(bbox)
            jx, jy = spec["joints"][p["joint"]]["pos"]
            pivot = (jx * drawing.width - bbox[0], jy * drawing.height - bbox[1])
            piece, pivot = pad_around_pivot(piece, pivot)
            self.parts[name] = Part(
                name=name,
                img=piece,
                pivot=pivot,
                z=p.get("z", 0),
                dark=p.get("dark", 0.0),
            )

    # ---- иерархия -----------------------------------------------------
    def _totals(self, angles: dict[str, float]) -> dict[str, tuple[np.ndarray, float]]:
        """Положение и суммарный угол каждого шарнира (в долях кадра)."""
        joints = self.spec["joints"]
        cache: dict[str, tuple[np.ndarray, float]] = {}

        def solve(name: str) -> tuple[np.ndarray, float]:
            if name in cache:
                return cache[name]
            node = joints[name]
            parent = node.get("parent")
            own = float(angles.get(name, 0.0))
            if parent is None:
                cache[name] = (np.array(node["pos"], float), own)
            else:
                ppos, pang = solve(parent)
                off = np.array(node["pos"], float) - np.array(joints[parent]["pos"], float)
                cache[name] = (ppos + _rot(off, pang), pang + own)
            return cache[name]

        for j in joints:
            solve(j)
        return cache

    # ---- отрисовка ----------------------------------------------------
    def render(self, angles: dict[str, float], *,
               canvas: tuple[int, int] | None = None,
               anchor: tuple[float, float] | None = None,
               shift: tuple[float, float] = (0.0, 0.0)) -> Image.Image:
        """Собрать кадр. `angles` — углы поворота шарниров в градусах."""
        w, h = canvas or self.size
        # якорь — это положение ТАЗА на холсте, а не ступней: части
        # позиционируются относительно таза, ноги уходят вниз сами
        hips = np.array(self.spec["joints"]["hip"]["pos"], float)
        ax, ay = anchor or self.spec.get("anchor", [hips[0], hips[1]])
        totals = self._totals(angles)

        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        items = list(self.parts.values()) + self.patches
        for part in sorted(items, key=lambda p: p.z):
            joint = (self.spec["parts"][part.name]["joint"]
                     if part.name in self.spec["parts"]
                     else self.part_joint[part.name])
            pos_frac, total_ang = totals[joint]
            # сдвиг шарнира относительно таза, в пикселях холста
            delta = (pos_frac - hips) * np.array([w, h])
            target = np.array([ax * w, ay * h]) + delta + np.asarray(shift, float)
            img = part.img
            px, py = part.pivot
            rot = img.rotate(-total_ang, resample=Image.BICUBIC, center=(px, py),
                             fillcolor=(0, 0, 0, 0))
            if part.dark:
                a = np.asarray(rot).astype(np.float32)
                a[..., :3] *= (1.0 - part.dark)
                rot = Image.fromarray(a.astype(np.uint8), "RGBA")
            out.alpha_composite(rot, (int(round(target[0] - px)),
                                      int(round(target[1] - py))))
        return out


def debug_overlay(drawing: Image.Image, spec: dict) -> Image.Image:
    """Показать полигоны частей и шарниры — для проверки глазами."""
    from PIL import ImageDraw
    im = drawing.convert("RGBA").copy()
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    colors = [(255, 80, 80), (80, 160, 255), (120, 230, 120), (255, 210, 80),
              (220, 120, 255), (90, 230, 230), (255, 150, 60), (200, 200, 200)]
    for i, (name, p) in enumerate(spec["parts"].items()):
        c = colors[i % len(colors)]
        pts = [(x * im.width, y * im.height) for x, y in p["poly"]]
        d.line(pts + [pts[0]], fill=c + (255,), width=3)
        d.text((pts[0][0] + 4, pts[0][1] + 4), name, fill=c + (255,))
        jx, jy = spec["joints"][p["joint"]]["pos"]
        X, Y = jx * im.width, jy * im.height
        d.ellipse([X - 7, Y - 7, X + 7, Y + 7], outline=(255, 255, 255, 255), width=3)
    return Image.alpha_composite(im, layer)
