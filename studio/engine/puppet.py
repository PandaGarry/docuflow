"""Кукла: процедурный персонаж из character.json + поза + эмоция + одежда.

Зачем это нужно
---------------
Генерация арта даёт качество, но не даёт мгновенных вариантов. Кукла даёт
обратное: любую позу, любое выражение и любую одежду можно увидеть за секунды,
без обращения к модели и без риска «другое лицо». Это рабочий инструмент
превизуализации и одновременно fallback-рендер, если арт-ассет ещё не готов.

Кукла читает те же данные, что и весь пайплайн: `character.json` (пропорции,
палитра, причёска), `library/poses.json`, `library/expressions.json`,
`library/wardrobe.json`. Ничего не зашито в код — новый персонаж появляется
одним JSON-файлом.

Запуск:
  python studio/engine/puppet.py preview --char dad --pose wave --expr joy
  python studio/engine/puppet.py sheet --char dad          # сетка поз/эмоций
  python studio/engine/puppet.py outfit --char dad --top shirt_blue --out out.png
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import face as F  # noqa: E402
import library as L  # noqa: E402
import rig as R  # noqa: E402

FONT_DIR = os.path.join(STUDIO, "fonts")
BG_TOP = (255, 248, 236)
BG_BOT = (243, 230, 212)


# --------------------------------------------------------------------------- #
# утилиты цвета
# --------------------------------------------------------------------------- #


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def shade(rgb, k: float) -> tuple[int, int, int]:
    """k<0 — темнее, k>0 — светлее (в сторону тёплого света)."""
    if k >= 0:
        return tuple(int(c + (255 - c) * k) for c in rgb)  # type: ignore[return-value]
    return tuple(int(c * (1 + k)) for c in rgb)  # type: ignore[return-value]


def mix(a, b, k: float):
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))


# --------------------------------------------------------------------------- #
# параметры рендера
# --------------------------------------------------------------------------- #


QUALITY = {
    "preview": {"ss": 1},           # быстрый превью: ~25-35 мс на кадр
    "high": {"ss": 2},              # рабочий: суперсэмплинг ×2
    "final": {"ss": 3},             # финальный: ×3, дорого
}


@dataclass
class RenderOpts:
    width: int = 720
    height: int = 1280
    ss: int | None = None           # суперсэмплинг; None — взять из пресета quality
    ground: float = 0.90            # где стоят ноги (доля высоты)
    margin: float = 0.06            # поля
    background: str = "studio"      # studio | chroma | none
    shadow: bool = True
    grain: float = 0.7
    # смещение и зум для сцен: доли кадра (0.5 = центр, 1.0 = целая ширина/высота)
    offset_x: float = 0.0
    offset_y: float = 0.0
    zoom: float = 1.0
    alpha: bool = False             # вернуть RGBA-слой (для сцен с несколькими персонажами)
    quality: str = "high"           # preview | high | final (задаёт ss, если ss не задан вручную)

    def __post_init__(self) -> None:
        if self.ss is None:
            self.ss = int(QUALITY.get(self.quality, QUALITY["high"])["ss"])
        self.ss = max(1, int(self.ss))


_LIGHT_CACHE: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}


def _light_fields(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Поля «тень/блик» для bbox: свет сверху-справа, тень снизу-слева.

    Зависит только от размера прямоугольника, поэтому кешируется. Поля
    возвращаются как read-only: их нельзя портить на месте.
    """
    key = (h, w)
    if key not in _LIGHT_CACHE:
        yy, xx = np.mgrid[0:h, 0:w]
        nx = (xx - (w - 1) / 2) / max(w / 2, 1)
        ny = (yy - (h - 1) / 2) / max(h / 2, 1)
        light_dir = -(0.85 * nx + 0.55 * ny)      # >0 — сторона света
        dark = np.clip(-light_dir, 0, 1) ** 1.2
        light = np.clip(light_dir, 0, 1) ** 2.0
        dark.flags.writeable = False
        light.flags.writeable = False
        if len(_LIGHT_CACHE) > 64:
            _LIGHT_CACHE.clear()
        _LIGHT_CACHE[key] = (dark, light)
    return _LIGHT_CACHE[key]


def _erode(m: np.ndarray, steps: int = 2) -> np.ndarray:
    """Эрозия маски на steps пикселей (для мягкого контура) — без PIL-фильтров."""
    out = m
    for _ in range(steps):
        out = np.minimum.reduce([
            out,
            np.roll(out, 1, axis=0), np.roll(out, -1, axis=0),
            np.roll(out, 1, axis=1), np.roll(out, -1, axis=1),
        ])
    return out


_BG_CACHE: dict[tuple[int, int, int], Image.Image] = {}


def _background_cache(W: int, H: int, ground: float) -> Image.Image:
    """Фон: вертикальный градиент + мягкий свет сверху-слева + линия пола.

    Считается один раз на размер и дальше копируется. Раньше на каждый кадр шёл
    цикл по 2000+ строкам и полноразмерный blur — самая дорогая операция в
    покадровом рендере.
    """
    key = (W, H, int(ground * 1000))
    if key in _BG_CACHE:
        return _BG_CACHE[key]

    k = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None, None]
    top = np.array(BG_TOP, np.float32)[None, None, :]
    bot = np.array(BG_BOT, np.float32)[None, None, :]
    arr = np.broadcast_to(top * (1 - k) + bot * k, (H, W, 3)).copy()
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert("RGBA")

    # мягкий свет сверху-слева — на уменьшенной маске, потом растягиваем
    small_size = (max(W // 8, 8), max(H // 8, 8))
    glow = Image.new("L", small_size, 0)
    ImageDraw.Draw(glow).ellipse([small_size[0] * 0.05, -small_size[1] * 0.25,
                                  small_size[0] * 0.95, small_size[1] * 0.55], fill=60)
    glow = glow.filter(ImageFilter.GaussianBlur(small_size[1] * 0.12)).resize(
        (W, H), Image.BILINEAR)
    img = Image.composite(Image.new("RGBA", (W, H), (255, 250, 240, 255)), img, glow)

    ImageDraw.Draw(img).rectangle([0, H * ground, W, H], fill=(236, 222, 202))
    _BG_CACHE[key] = img
    return img


# --------------------------------------------------------------------------- #
# художник
# --------------------------------------------------------------------------- #


class Painter:
    """Рисует одного персонажа. Состояние — только конфиг, кадры независимы."""

    def __init__(self, spec: dict, opts: RenderOpts | None = None):
        self.spec = spec
        self.opts = opts or RenderOpts()
        self.pal = self._palette()
        self.k = 1.0
        self.ox = 0.0
        self.oy = 0.0
        # кеши: одинаковые данные на каждом кадре не пересобираются
        self._outfit_cache: dict[tuple, dict] = {}
        self._hints: tuple[dict, dict] | None = None
        self._metrics_cache: dict[float, dict] = {}

    def _background(self, mode: str | None) -> Image.Image:
        o = self.opts
        W, H = o.width * o.ss, o.height * o.ss
        mode = mode or o.background
        if mode == "chroma":
            return Image.new("RGBA", (W, H), (0, 177, 64, 255))
        return _background_cache(W, H, o.ground).copy()

    # --- данные ---------------------------------------------------------- #
    def _palette(self) -> dict:
        ident = self.spec.get("identity", {})
        pal = {
            "skin": "#E8B48F",
            "skin_shade": "#D19A76",
            "hair": "#4A332A",
            "eye": "#5B3A29",
            "mouth": "#B4564F",
            "line": "#3B2A26",
        }
        pal.update(self.spec.get("palette", {}) or {})
        if ident.get("skin"):
            pal["skin"] = ident["skin"]
        pal["skin"] = hex_rgb(pal["skin"])
        pal["skin_shade"] = mix(pal["skin"], hex_rgb("#8A4B32"), 0.35)
        pal["skin_light"] = mix(pal["skin"], (255, 250, 240), 0.35)
        pal["hair"] = hex_rgb(pal["hair"])
        pal["hair_shade"] = shade(pal["hair"], -0.32)
        pal["hair_light"] = shade(pal["hair"], 0.18)
        pal["eye"] = hex_rgb(pal.get("eye", "#5B3A29"))
        pal["mouth"] = hex_rgb(pal.get("mouth", "#B4564F"))
        pal["mouth_dark"] = shade(pal["mouth"], -0.35)
        pal["line"] = hex_rgb(pal.get("line", "#3B2A26"))
        return pal

    def outfit(self, set_name: str | None = None) -> dict[str, str]:
        """Слот → id вещи для текущего комплекта (или для переопределений)."""
        wardrobe = self.spec.get("wardrobe") or {}
        sets = wardrobe.get("sets") or {}
        set_name = set_name or wardrobe.get("default")
        return dict(sets.get(set_name, {})) if set_name else {}

    def item(self, item_id: str | None) -> dict:
        if not item_id:
            return {}
        try:
            return L.item(item_id)
        except KeyError:
            return {}

    def resolve_outfit(self, overrides: dict[str, str] | None = None,
                       set_name: str | None = None) -> dict[str, dict]:
        """Собрать комплект: слот → {id, item}. Учитывает переопределения (кеш)."""
        key = (set_name, tuple(sorted((overrides or {}).items())))
        if key in self._outfit_cache:
            return self._outfit_cache[key]
        base = self.outfit(set_name)
        base.update(overrides or {})
        out = {}
        for slot, item_id in base.items():
            it = self.item(item_id)
            if it:
                out[slot] = {"id": item_id, **it}
        self._outfit_cache[key] = out
        return out

    # --- кадр ------------------------------------------------------------ #
    def build(self, pose: str | dict = "idle", *, pose_weight: float = 1.0,
              root: tuple[float, float] | None = None) -> R.Skeleton:
        ident = self.spec.get("identity", {})
        sk = R.build_humanoid(
            height_heads=float(self.spec.get("height_heads", ident.get("height_heads", 6.5))),
            proportions=self.spec.get("proportions") or {},
            rig_id=self.spec.get("rig", "humanoid_v1"),
        )
        R.apply_pose(sk, pose, weight=pose_weight)
        if root:
            sk.bones["root"].origin = (root[0], root[1])
            sk.solve()
        return sk

    def frame(self, sk: R.Skeleton, face: F.Face | None = None,
              *, face_expr: str = "neutral",
              outfit: dict[str, str] | None = None,
              set_name: str | None = None,
              background: str | None = None, t: float = 0.0,
              caption: str | None = None) -> Image.Image:
        """Отрисовать кадр. Всё остальное — из spec."""
        o = self.opts
        W, H = o.width * o.ss, o.height * o.ss
        face = face or F.Face.from_expression(face_expr)

        x0, y0, x1, y1 = sk.bounds()
        units_h = max(y1 - y0, 1e-6)
        units_w = max(x1 - x0, 1e-6)
        avail_h = H * (o.ground - o.margin - 0.02)
        avail_w = W * (1 - 2 * o.margin)
        self.k = min(avail_h / units_h, avail_w / units_w) * o.zoom
        self.ox = W / 2 - (x0 + x1) / 2 * self.k + o.offset_x * W
        self.oy = H * o.ground - y1 * self.k + o.offset_y * H

        img = self._background(background) if background != "none" else Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if o.shadow:
            self._shadow(img, sk)
        self._draw_body(img, sk, face, self.resolve_outfit(outfit, set_name))
        if caption:
            self._caption(img, caption)
        # суперсэмплинг кратен 2 → reduce (box-фильтр) точнее и в разы быстрее LANCZOS
        if o.ss >= 2 and img.width == o.width * o.ss and img.height == o.height * o.ss:
            img = img.reduce(o.ss)
        else:
            img = img.resize((o.width, o.height), Image.LANCZOS)
        return img if o.alpha else img.convert("RGB")

    # --- фон и тень ------------------------------------------------------ #
    def _shadow(self, img: Image.Image, sk: R.Skeleton) -> None:
        """Контактная тень: размывается только маленькая область под ногами."""
        W, H = img.size
        feet_y = max(sk.tip(f"foot.{s}")[1] for s in "lr") * self.k + self.oy
        feet_x = sum(sk.tip(f"foot.{s}")[0] for s in "lr") / 2 * self.k + self.ox
        spread = 0.55 * (sk.tip("hand.r")[0] - sk.tip("hand.l")[0]) * self.k
        w = min(max(spread, 0.9 * self.k), 1.6 * self.head_radius(sk) * 2)
        blur = max(w * 0.10, 2.0)
        pad = blur * 3
        x0, x1 = int(max(feet_x - w - pad, 0)), int(min(feet_x + w + pad, W))
        y0, y1 = int(max(feet_y - w * 0.3 - pad, 0)), int(min(feet_y + w * 0.4 + pad, H))
        if x1 - x0 < 2 or y1 - y0 < 2:
            return
        layer = Image.new("L", (x1 - x0, y1 - y0), 0)
        d = ImageDraw.Draw(layer)
        cx, cy = feet_x - x0, feet_y - y0
        d.ellipse([cx - w, cy - w * 0.10, cx + w, cy + w * 0.14], fill=90)
        layer = layer.filter(ImageFilter.GaussianBlur(blur))
        img.paste((70, 48, 36, 255), (x0, y0), layer)

    def _caption(self, img: Image.Image, text: str) -> None:
        path = os.path.join(FONT_DIR, "Nunito-700.ttf")
        size = int(img.height * 0.024)
        font = ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default()
        d = ImageDraw.Draw(img)
        d.text((img.width * 0.03, img.height * 0.03), text, font=font, fill=(120, 104, 92))

    # --- геометрия ------------------------------------------------------- #
    def px(self, p: tuple[float, float]) -> tuple[float, float]:
        return (self.ox + p[0] * self.k, self.oy + p[1] * self.k)

    def tip(self, sk: R.Skeleton, bone: str) -> tuple[float, float]:
        return self.px(sk.tip(bone))

    def head_pos(self, sk: R.Skeleton) -> tuple[float, float]:
        """Центр головы: середина кости head, чуть вверх."""
        b = sk.bones["head"]
        hx, hy = b.world_pos
        tx, ty = sk.tip("head")
        cx, cy = (hx + tx) / 2, (hy + ty) / 2 - b.length * 0.08
        return self.px((cx, cy))

    def head_radius(self, sk: R.Skeleton) -> float:
        return sk.bones["head"].length * 1.05 * self.k

    # --- объём ----------------------------------------------------------- #
    @staticmethod
    def _mask(size, fn) -> Image.Image:
        m = Image.new("L", size, 0)
        fn(ImageDraw.Draw(m))
        return m

    def sculpt(self, layer: Image.Image, mask: Image.Image, base,
               shade_k: float = 0.20, light_k: float = 0.14,
               rim_k: float = 0.16) -> None:
        """Залить маску цветом с объёмом: тень снизу-слева, блик сверху-справа.

        Это единственный источник «скульптурности» стиля B: и тело, и голова,
        и одежда освещены одинаково, поэтому сцена выглядит цельно.

        Световые поля кешируются по размеру bbox, контур считается numpy-эрозией:
        на кадр тратится на порядок меньше времени, результат тот же (бит в бит).
        """
        bbox = mask.getbbox()
        if not bbox:
            return
        x0, y0, x1, y1 = bbox
        m = np.asarray(mask.crop(bbox), np.float32) * (1.0 / 255.0)
        h, w = m.shape
        if h < 2 or w < 2:
            layer.alpha_composite(
                Image.new("RGBA", (max(w, 1), max(h, 1)),
                          tuple(int(c) for c in base) + (255,)), (x0, y0))
            return
        dark, light = _light_fields(h, w)

        out = np.empty((h, w, 4), np.float32)
        out[..., :3] = np.array(base, np.float32)
        out[..., 3] = m * 255.0
        rgb = out[..., :3]

        sh = np.array(shade(base, -shade_k), np.float32)
        a = np.clip(dark * (shade_k * 2.0 * m), 0, 1)[..., None]
        rgb *= 1 - a
        rgb += sh * a

        li = np.array(mix(base, (255, 252, 246), 0.60), np.float32)
        a2 = np.clip(light * (light_k * 1.7 * m), 0, 1)[..., None]
        rgb *= 1 - a2
        rgb += li * a2

        # контур: 1 пиксель эрозии, и только на некрупных деталях (на торсе это
        # незаметно, а стоит дорого)
        if rim_k > 0 and h * w <= 260_000:
            rim = np.clip(m - _erode(m, 1), 0, 1) * rim_k
            rgb *= (1 - rim)[..., None]

        layer.alpha_composite(
            Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA"), (x0, y0))

    @staticmethod
    def _band(d: ImageDraw.ImageDraw, pts_a, pts_b, radius: float, fill) -> None:
        d.polygon(list(pts_a) + list(reversed(pts_b)), fill=fill)
        for p in list(pts_a) + list(pts_b):
            d.ellipse([p[0] - radius, p[1] - radius, p[0] + radius, p[1] + radius], fill=fill)

    @staticmethod
    def chord_half(d: ImageDraw.ImageDraw, x0, x1, top, bottom, upper: bool = True,
                   fill=255) -> None:
        """Половина эллипса по заданным границам (PIL chord режет по центру бокса).

        upper=True — от top до bottom, куполом вверх (волосы, кепка, шапка);
        upper=False — от top до bottom, чашей вниз (борода, подбородок).
        """
        if bottom - top < 1:
            return
        if upper:
            d.chord([x0, top, x1, 2 * bottom - top], 180, 360, fill=fill)
        else:
            d.chord([x0, 2 * top - bottom, x1, bottom], 0, 180, fill=fill)

    @staticmethod
    def limb(d: ImageDraw.ImageDraw, p0, p1, r0: float, r1: float, fill=255) -> None:
        """Конечность: сужающийся отрезок с круглыми торцами."""
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        n = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / n, dx / n
        d.polygon([(p0[0] + nx * r0, p0[1] + ny * r0), (p1[0] + nx * r1, p1[1] + ny * r1),
                   (p1[0] - nx * r1, p1[1] - ny * r1), (p0[0] - nx * r0, p0[1] - ny * r0)], fill=fill)
        d.ellipse([p0[0] - r0, p0[1] - r0, p0[0] + r0, p0[1] + r0], fill=fill)
        d.ellipse([p1[0] - r1, p1[1] - r1, p1[0] + r1, p1[1] + r1], fill=fill)

    # --- тело ------------------------------------------------------------ #
    def _metrics(self, sk: R.Skeleton) -> dict:
        radius = self.head_radius(sk)
        cached = self._metrics_cache.get(radius)
        if cached is not None:
            return cached
        """Все ширины — в долях диаметра головы: пропорции не «плывут»."""
        hd = self.head_radius(sk) * 2
        props = self.spec.get("proportions") or {}
        belly = float(props.get("belly", 1.0))
        bulk = float((self.spec.get("body") or {}).get("bulk", 1.0))
        data = {
            "hd": hd,
            "shoulder": 0.56 * hd * bulk,
            "chest": 0.53 * hd * bulk,
            "waist": 0.46 * hd * belly,
            "hip": 0.44 * hd * belly,
            "arm_up": 0.155 * hd * bulk,
            "arm_fore": 0.125 * hd,
            "hand": 0.140 * hd,
            "thigh": 0.255 * hd,
            "calf": 0.205 * hd,
            "ankle": 0.120 * hd,
            "neck": 0.165 * hd,
        }
        self._metrics_cache[radius] = data
        return data

    def _torso_poly(self, hips, chest_top, m: dict, fill_scale: float = 1.0):
        """Силуэт торса: плечи → талия → бёдра, с мягкой талией."""
        left, right = [], []
        n = 16
        for i in range(n + 1):
            u = i / n
            x = hips[0] + (chest_top[0] - hips[0]) * u
            y = hips[1] + (chest_top[1] - hips[1]) * u
            # плечи набирают ширину быстро (u^0.6), поэтому силуэт не «труба»
            w = (m["hip"] * (1 - u) + m["shoulder"] * (u ** 0.6)) * fill_scale
            w *= 1.0 - 0.13 * math.sin(math.pi * u)
            # плечи чуть выше верхней точки — «трапеция» силы
            left.append((x - w, y))
            right.append((x + w, y))
        return left, right

    def _draw_body(self, img: Image.Image, sk: R.Skeleton, face: F.Face,
                   outfit: dict[str, dict]) -> None:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        pal = self.pal
        m = self._metrics(sk)
        hd = m["hd"]

        top = outfit.get("top", {})
        bottom = outfit.get("bottom", {})
        shoes = outfit.get("shoes", {})
        outer = outfit.get("outer", {})
        headwear = outfit.get("headwear", {})
        accessory = outfit.get("accessory", {})

        pants = hex_rgb(bottom.get("draw", {}).get("color", "#2F3540"))
        shirt = hex_rgb(top.get("draw", {}).get("color", "#C9C7C2"))
        coat = hex_rgb(outer.get("draw", {}).get("color", "#7C5A44")) if outer else None

        hips = self.px(sk.bones["hips"].world_pos)
        chest_top = self.tip(sk, "chest")
        neck_top = self.tip(sk, "neck")

        # ---- волосы сзади
        self._draw_hair_back(layer, sk)

        # ---- ноги (штанины) + таз
        for side in "lr":
            p0 = self.px(sk.bones[f"thigh.{side}"].world_pos)
            knee = self.tip(sk, f"thigh.{side}")
            ankle = self.tip(sk, f"shin.{side}")

            def leg(d, p0=p0, knee=knee, ankle=ankle):
                self.limb(d, p0, knee, m["thigh"], m["calf"])
                self.limb(d, knee, ankle, m["calf"] * 0.97, m["ankle"])
            self.sculpt(layer, self._mask(layer.size, leg), pants, shade_k=0.26, light_k=0.12)

        def pelvis(d):
            d.ellipse([hips[0] - m["hip"] * 1.05, hips[1] - m["hip"] * 0.45,
                       hips[0] + m["hip"] * 1.05, hips[1] + m["hip"] * 0.50], fill=255)
        self.sculpt(layer, self._mask(layer.size, pelvis), pants, shade_k=0.24)

        # пояс и молния: читается как одежда, а не как «труба»
        d0 = ImageDraw.Draw(layer)
        d0.line([(hips[0] - m["hip"] * 0.86, hips[1] - m["hip"] * 0.10),
                 (hips[0] + m["hip"] * 0.86, hips[1] - m["hip"] * 0.10)],
                fill=shade(pants, -0.35), width=max(2, int(0.016 * hd)))
        d0.line([(hips[0], hips[1] - m["hip"] * 0.08), (hips[0], hips[1] + m["hip"] * 0.42)],
                fill=shade(pants, -0.28), width=max(1, int(0.010 * hd)))

        # ---- обувь
        shoe_col = hex_rgb(shoes.get("draw", {}).get("color", "#4A3A32"))
        sole = hex_rgb(shoes.get("draw", {}).get("sole", "#E8E2D6"))

        def shoes_mask(d):
            for side in "lr":
                ax, ay = self.tip(sk, f"shin.{side}")
                sx = -1 if side == "r" else 1
                w, h = 0.155 * hd, 0.105 * hd
                d.ellipse([ax - w + sx * 0.03 * hd, ay - h * 0.45,
                           ax + w + sx * 0.03 * hd, ay + h], fill=255)
        self.sculpt(layer, self._mask(layer.size, shoes_mask), shoe_col, shade_k=0.25)

        def sole_mask(d):
            for side in "lr":
                ax, ay = self.tip(sk, f"shin.{side}")
                sx = -1 if side == "r" else 1
                w, h = 0.158 * hd, 0.026 * hd
                d.ellipse([ax - w + sx * 0.03 * hd, ay + h * 1.2,
                           ax + w + sx * 0.03 * hd, ay + h * 4.2], fill=255)
        self.sculpt(layer, self._mask(layer.size, sole_mask), sole, shade_k=0.10, rim_k=0.0)

        # ---- торс (нижняя одежда = верх)
        left, right = self._torso_poly(hips, chest_top, m)
        def torso_mask(d):
            d.polygon(left + list(reversed(right)), fill=255)
            for pts, r in ((left, m["waist"]), (right, m["waist"])):
                pass
            d.ellipse([chest_top[0] - m["shoulder"] * 0.94, chest_top[1] - m["shoulder"] * 0.30,
                       chest_top[0] + m["shoulder"] * 0.94, chest_top[1] + m["shoulder"] * 0.55], fill=255)
            d.ellipse([hips[0] - m["hip"], hips[1] - m["hip"] * 0.7,
                       hips[0] + m["hip"], hips[1] + m["hip"] * 0.7], fill=255)
        self.sculpt(layer, self._mask(layer.size, torso_mask), shirt, shade_k=0.20)

        # ---- куртка/жилет поверх
        if coat is not None:
            outer_kind = outer.get("draw", {})
            ov = 1.12 if outer_kind.get("sleeve") != "none" else 1.06
            ol, orr = self._torso_poly(hips, chest_top, m, fill_scale=ov)
            def outer_mask(d):
                d.polygon(ol + list(reversed(orr)), fill=255)
                d.ellipse([chest_top[0] - m["shoulder"] * ov, chest_top[1] - m["shoulder"] * 0.34,
                           chest_top[0] + m["shoulder"] * ov, chest_top[1] + m["shoulder"] * 0.6], fill=255)
                d.ellipse([hips[0] - m["hip"] * ov, hips[1] - m["hip"] * 0.72,
                           hips[0] + m["hip"] * ov, hips[1] + m["hip"] * 0.72], fill=255)
            self.sculpt(layer, self._mask(layer.size, outer_mask), coat, shade_k=0.24)
            if outer_kind.get("quilt"):
                quilt = Image.new("RGBA", layer.size, (0, 0, 0, 0))
                qd = ImageDraw.Draw(quilt)
                for i in range(4):
                    yy = chest_top[1] + (hips[1] - chest_top[1]) * (0.18 + i * 0.20)
                    qd.line([(chest_top[0] - m["shoulder"] * 1.1, yy),
                             (chest_top[0] + m["shoulder"] * 1.1, yy)],
                            fill=shade(coat, -0.22) + (255,), width=max(1, int(0.012 * hd)))
                quilt.putalpha(Image.composite(quilt.split()[3], Image.new("L", layer.size, 0),
                                               self._mask(layer.size, outer_mask)))
                layer.alpha_composite(quilt)
            # открытая куртка: полы не смыкаются
            if outer_kind.get("sleeve") == "long":
                pass

        # ---- руки
        sleeve = top.get("draw", {}).get("sleeve", "long")
        if coat is not None and outer.get("draw", {}).get("sleeve") == "long":
            sleeve = "long"
            sleeve_col = coat
        else:
            sleeve_col = shirt
        skin = pal["skin"]
        for side in "lr":
            shoulder = self.px(sk.bones[f"upper_arm.{side}"].world_pos)
            elbow = self.tip(sk, f"upper_arm.{side}")
            wrist = self.tip(sk, f"forearm.{side}")
            hand_tip = self.tip(sk, f"hand.{side}")

            def arm(d, shoulder=shoulder, elbow=elbow, wrist=wrist, sleeve=sleeve):
                self.limb(d, shoulder, elbow, m["arm_up"] * 1.18, m["arm_fore"] * 1.15)
                if sleeve == "long":
                    self.limb(d, elbow, wrist, m["arm_fore"] * 1.15, m["arm_fore"] * 1.0)
                elif sleeve == "short":
                    midp = ((shoulder[0] + elbow[0]) / 2, (shoulder[1] + elbow[1]) / 2)
                    self.limb(d, midp, elbow, m["arm_fore"] * 1.2, m["arm_fore"] * 1.1)
            self.sculpt(layer, self._mask(layer.size, arm), sleeve_col, shade_k=0.22)

            if sleeve != "long":
                def bare(d, elbow=elbow, wrist=wrist, shoulder=shoulder):
                    if sleeve == "short":
                        midp = ((shoulder[0] + elbow[0]) / 2, (shoulder[1] + elbow[1]) / 2)
                        self.limb(d, midp, elbow, m["arm_fore"] * 1.1, m["arm_fore"])
                    self.limb(d, elbow, wrist, m["arm_fore"], m["arm_fore"] * 0.85)
                self.sculpt(layer, self._mask(layer.size, bare), skin, shade_k=0.18)

            def hand(d, wrist=wrist, hand_tip=hand_tip):
                hx, hy = (wrist[0] + hand_tip[0]) / 2, (wrist[1] + hand_tip[1]) / 2
                r = m["hand"]
                d.ellipse([hx - r, hy - r * 1.1, hx + r, hy + r * 1.1], fill=255)
            self.sculpt(layer, self._mask(layer.size, hand), skin, shade_k=0.16)

        # ---- шея
        def neck(d):
            w0, w1 = m["neck"] * 0.92, m["neck"] * 1.15
            d.polygon([(chest_top[0] - w0, chest_top[1]), (neck_top[0] - w1, neck_top[1]),
                       (neck_top[0] + w1, neck_top[1]), (chest_top[0] + w0, chest_top[1])], fill=255)
        self.sculpt(layer, self._mask(layer.size, neck), mix(pal["skin"], pal["skin_shade"], 0.45),
                    shade_k=0.26, light_k=0.06)

        # ---- воротник (до головы: капюшон уходит за подбородок)
        d_collar = ImageDraw.Draw(layer)
        collar_item = outer or top
        collar_col = hex_rgb(outer["draw"].get("color")) if (
            outer and outer.get("draw", {}).get("collar") == "stand") else shirt
        self._collar(d_collar, chest_top, neck_top, m["shoulder"] * 0.58,
                     collar_col, collar_item.get("draw", {}).get("collar", "crew"))

        # ---- голова
        self._draw_head(layer, sk, face)
        self._draw_hair_front(layer, sk)
        self._draw_face(layer, sk, face)

        # ---- манжеты: рукав читается как рукав, а не как палка
        d = ImageDraw.Draw(layer)
        if sleeve == "long":
            for side in "lr":
                wx_, wy_ = self.tip(sk, f"forearm.{side}")
                r_c = m["arm_fore"] * 1.02
                d.ellipse([wx_ - r_c, wy_ - r_c * 0.55, wx_ + r_c, wy_ + r_c * 0.55],
                          fill=shade(sleeve_col, -0.14))

        # (воротник уже нарисован до головы — второй раз его рисовать нельзя:
        #  он ложился поверх подбородка тёмной полосой)

        # ---- головной убор и аксессуары
        if headwear:
            self._draw_headwear(layer, sk, headwear)
        if accessory:
            self._draw_accessory(layer, sk, accessory)

        img.alpha_composite(layer)

    # --- детали ---------------------------------------------------------- #
    def _collar(self, d, chest_top, neck_top, w, color, kind: str) -> None:
        if kind in ("none",):
            return
        cx = neck_top[0]
        # воротник сидит на линии плеч, ниже подбородка
        cy = neck_top[1] + (chest_top[1] - neck_top[1]) * 0.62
        if kind == "hood":
            hy = cy - w * 0.10
            d.ellipse([cx - w * 0.90, hy - w * 0.04, cx + w * 0.90, hy + w * 0.40],
                      fill=shade(color, -0.18))
            d.arc([cx - w * 0.90, hy - w * 0.04, cx + w * 0.90, hy + w * 0.40],
                  200, 340, fill=shade(color, -0.34), width=max(2, int(w * 0.09)))
        elif kind == "stand":
            d.rounded_rectangle([cx - w * 0.46, cy - w * 0.02, cx + w * 0.46, cy + w * 0.24],
                                radius=int(w * 0.12), fill=shade(color, -0.10))
        elif kind == "shirt":
            d.polygon([(cx - w * 0.62, cy - w * 0.02), (cx, cy + w * 0.55),
                       (cx + w * 0.62, cy - w * 0.02)], fill=shade(color, 0.12))
            d.line([(cx, cy + w * 0.02), (cx, cy + w * 0.5)], fill=shade(color, -0.3),
                   width=max(1, int(w * 0.05)))
        else:
            d.arc([cx - w * 0.75, cy - w * 0.55, cx + w * 0.75, cy + w * 0.62], 195, 345,
                  fill=shade(color, -0.26), width=max(2, int(w * 0.13)))

    def _draw_head(self, layer: Image.Image, sk: R.Skeleton, face: F.Face) -> None:
        cx, cy = self.head_pos(sk)
        r = self.head_radius(sk)
        pal = self.pal
        ident = self.spec.get("identity", {})
        jaw = float(ident.get("jaw", 1.0))

        def head_mask(d):
            d.ellipse([cx - r * 0.99, cy - r * 1.04, cx + r * 0.99, cy + r * 0.72], fill=255)
            d.ellipse([cx - r * 0.90 * jaw, cy + r * 0.20, cx + r * 0.90 * jaw, cy + r * 0.98], fill=255)
        self.sculpt(layer, self._mask(layer.size, head_mask), pal["skin"],
                    shade_k=0.24, light_k=0.20)

        d = ImageDraw.Draw(layer)
        # уши
        for sx in (-1, 1):
            ex = cx + sx * r * 0.95
            d.ellipse([ex - r * 0.145, cy - r * 0.06, ex + r * 0.145, cy + r * 0.30],
                      fill=pal["skin_shade"])
            d.ellipse([ex - r * 0.075, cy + r * 0.02, ex + r * 0.075, cy + r * 0.20],
                      fill=shade(pal["skin_shade"], -0.14))

    def _hair_draw_hints(self) -> tuple[dict, dict]:
        if self._hints is not None:
            return self._hints
        hair = self.spec.get("hair") or {}
        try:
            style = L.hair_style(hair.get("style", "buzz"))
        except KeyError:
            style = {"draw": {"shape": "round", "volume": 1.0}, "prompt": ""}
        try:
            fh = L.facial_hair(hair.get("facial_hair", "none"))
        except KeyError:
            fh = {"draw": {"kind": "none"}}
        self._hints = (style, fh)
        return self._hints

    def _draw_hair_back(self, layer: Image.Image, sk: R.Skeleton) -> None:
        style, _ = self._hair_draw_hints()
        shape = style.get("draw", {}).get("shape", "round")
        if shape not in ("long", "long_wavy", "ponytail", "bun", "curly", "bob"):
            return
        cx, cy = self.head_pos(sk)
        r = self.head_radius(sk)
        col = self.pal["hair"]

        def mask(d):
            if shape in ("long", "long_wavy", "bob"):
                drop = r * (2.3 if shape != "bob" else 1.35)
                w = r * (1.02 if shape == "long_wavy" else 0.90)
                d.rounded_rectangle([cx - w, cy - r * 0.85, cx + w, cy + drop],
                                    radius=int(r * 0.5), fill=255)
                if shape == "long_wavy":
                    for sx in (-1, 1):
                        for i in range(4):
                            wob = r * (0.24 - 0.03 * i)
                            yy = cy + r * 0.35 + i * drop * 0.22
                            d.ellipse([cx + sx * w * 0.82 - wob, yy - wob * 1.3,
                                       cx + sx * w * 0.82 + wob, yy + wob * 1.3], fill=255)
            elif shape == "ponytail":
                d.ellipse([cx + r * 0.55, cy - r * 0.55, cx + r * 2.0, cy + r * 1.6], fill=255)
            elif shape == "bun":
                d.ellipse([cx - r * 0.48, cy - r * 1.85, cx + r * 0.48, cy - r * 0.95], fill=255)
            elif shape == "curly":
                for dx, dy, rr in [(-0.8, -0.3, 0.42), (0.8, -0.3, 0.42), (0, -0.75, 0.5)]:
                    d.ellipse([cx + (dx - rr) * r, cy + (dy - rr) * r,
                               cx + (dx + rr) * r, cy + (dy + rr) * r], fill=255)
        self.sculpt(layer, self._mask(layer.size, mask), shade(col, -0.12), shade_k=0.26, light_k=0.10)

    def _draw_hair_front(self, layer: Image.Image, sk: R.Skeleton) -> None:
        style, fh = self._hair_draw_hints()
        draw = style.get("draw", {})
        shape = draw.get("shape", "round")
        vol = float(draw.get("volume", 1.0))
        cx, cy = self.head_pos(sk)
        r = self.head_radius(sk)
        col = self.pal["hair"]

        if shape not in ("bald",):
            def mask(d):
                top = cy - r * (1.06 + 0.05 * vol)
                if shape == "spiky":
                    self.chord_half(d, cx - r, cx + r, top + r * 0.14, cy - r * 0.58)
                    for i in range(-4, 5):
                        bx = cx + i * r * 0.215
                        h = r * (0.18 + 0.05 * vol) * (1 - abs(i) * 0.08)
                        d.polygon([(bx - r * 0.10, cy - r * 0.62),
                                   (bx + i * r * 0.012, cy - r * 1.00 - h),
                                   (bx + r * 0.10, cy - r * 0.62)], fill=255)
                elif shape == "curly":
                    for dx, dy, rr in [(-0.72, -0.52, 0.40), (-0.30, -0.82, 0.44),
                                       (0.18, -0.86, 0.40), (0.62, -0.58, 0.36)]:
                        d.ellipse([cx + (dx - rr) * r, cy + (dy - rr) * r,
                                   cx + (dx + rr) * r, cy + (dy + rr) * r], fill=255)
                elif shape in ("long", "long_wavy", "bob"):
                    self.chord_half(d, cx - r, cx + r, top, cy - r * 0.56)
                    if draw.get("bangs") == "side":
                        d.ellipse([cx - r * 0.98, cy - r * 0.98, cx + r * 0.22, cy - r * 0.40], fill=255)
                    else:
                        self.chord_half(d, cx - r * 0.98, cx + r * 0.98, top + r * 0.10, cy - r * 0.52)
                elif shape == "bun":
                    self.chord_half(d, cx - r, cx + r, top, cy - r * 0.52)
                elif shape in ("hidden", "under_cap"):
                    self.chord_half(d, cx - r * 0.96, cx + r * 0.96, cy - r * 0.72, cy - r * 0.34)
                else:
                    self.chord_half(d, cx - r, cx + r, top, cy - r * 0.56)
            self.sculpt(layer, self._mask(layer.size, mask), col, shade_k=0.24, light_k=0.16)

        # выбритые виски
        if draw.get("sides") == "faded":
            d = ImageDraw.Draw(layer)
            for sx in (-1, 1):
                d.ellipse([cx + sx * r * 0.97 - r * 0.12, cy - r * 0.28,
                           cx + sx * r * 0.97 + r * 0.12, cy + r * 0.34],
                          fill=shade(self.pal["skin"], -0.20))

        # борода/усы
        kind = (fh.get("draw") or {}).get("kind", "none")
        if kind != "none":
            density = float((fh.get("draw") or {}).get("density", 1.0))
            beard_col = shade(col, -0.04)

            def beard(d):
                # борода повторяет челюсть, а не свисает «фартуком» за подбородок
                if kind == "full":
                    self.chord_half(d, cx - r * 0.80, cx + r * 0.80, cy + r * 0.30, cy + r * 0.86,
                                    upper=False)
                    # бакенбарды к вискам — чтобы борода соединялась с причёской
                    for sx in (-1, 1):
                        d.ellipse([cx + sx * r * 0.80 - r * 0.16, cy - r * 0.18,
                                   cx + sx * r * 0.80 + r * 0.16, cy + r * 0.42], fill=255)
                elif kind == "stubble":
                    self.chord_half(d, cx - r * 0.82, cx + r * 0.82, cy + r * 0.30, cy + r * 0.88,
                                    upper=False)
                elif kind == "mustache":
                    for sx in (-1, 1):
                        d.ellipse([cx + sx * r * 0.24 - r * 0.20, cy + r * 0.33,
                                   cx + sx * r * 0.24 + r * 0.20, cy + r * 0.46], fill=255)
                elif kind == "goatee":
                    self.chord_half(d, cx - r * 0.30, cx + r * 0.30, cy + r * 0.44, cy + r * 0.90,
                                    upper=False)
            mask = self._mask(layer.size, beard)
            if kind in ("full", "goatee"):
                # вырезаем область губ: борода обрамляет рот, а не съедает его
                hole = self._mask(layer.size, lambda dd: dd.ellipse(
                    [cx - r * 0.42, cy + r * 0.32, cx + r * 0.42, cy + r * 0.80], fill=255))
                mask = Image.composite(Image.new("L", layer.size, 0), mask, hole)
            if kind == "stubble":
                mask = mask.point(lambda v: int(v * 110 * density))
            self.sculpt(layer, mask, beard_col, shade_k=0.20, light_k=0.10)

    def _draw_face(self, layer: Image.Image, sk: R.Skeleton, face: F.Face) -> None:
        d = ImageDraw.Draw(layer)
        cx, cy = self.head_pos(sk)
        r = self.head_radius(sk)
        pal = self.pal
        ident = self.spec.get("identity", {})
        eye_spread = float(ident.get("eye_spread", 1.0))
        line = pal["line"]

        # --- брови
        brow_y = cy - r * 0.34 - face["brow_raise"] * r * 0.10
        for sx in (-1, 1):
            bx = cx + sx * r * 0.34 * eye_spread + sx * face["brow_pinch"] * r * 0.06
            tilt = (face["brow_angle"] * (-sx) * 0.9 + face["brow_raise"] * 0.25) * r * 0.11
            w = r * 0.30
            pts = [(bx - w * 0.55, brow_y + tilt * 0.55 + r * 0.035),
                   (bx, brow_y - tilt * 0.15 - r * 0.02),
                   (bx + w * 0.55, brow_y - tilt * 0.55 - r * 0.015)]
            d.line(pts, fill=pal["hair_shade"], width=max(2, int(r * 0.10)), joint="curve")

        # --- глаза
        open_k = max(face["eye_open"], 0.0)
        lid = face["lid"]
        squint = face["squint"]
        eye_h = open_k * (1 - 0.55 * squint) * (1 - 0.5 * lid)
        for sx in (-1, 1):
            ex = cx + sx * r * 0.34 * eye_spread
            ey = cy - r * 0.03
            ew = r * 0.245
            eh = r * 0.215 * max(eye_h, 0.0)
            if eye_h < 0.10:
                d.arc([ex - ew, ey - r * 0.06, ex + ew, ey + r * 0.10],
                      200, 340, fill=line, width=max(2, int(r * 0.045)))
                continue
            eye_mask = self._mask(layer.size, lambda dd, ex=ex, ey=ey, ew=ew, eh=eh: dd.ellipse(
                [ex - ew, ey - eh, ex + ew, ey + eh], fill=255))
            self.sculpt(layer, eye_mask, (253, 250, 246), shade_k=0.10, light_k=0.0, rim_k=0.0)
            ir = min(ew, eh) * 0.92
            ix = ex + face["look_x"] * ew * 0.30
            iy = ey + face["look_y"] * eh * 0.30
            d.ellipse([ix - ir, iy - ir, ix + ir, iy + ir], fill=pal["eye"])
            d.ellipse([ix - ir * 0.72, iy - ir * 0.72, ix + ir * 0.72, iy + ir * 0.72],
                      fill=shade(pal["eye"], -0.25))
            pr = ir * 0.50 * face["pupil"]
            d.ellipse([ix - pr, iy - pr, ix + pr, iy + pr], fill=(26, 18, 14))
            d.ellipse([ix - ir * 0.55, iy - ir * 0.62, ix - ir * 0.12, iy - ir * 0.18],
                      fill=(255, 255, 255))
            d.ellipse([ix + ir * 0.20, iy + ir * 0.24, ix + ir * 0.44, iy + ir * 0.46],
                      fill=(255, 255, 255, 180))
            # верхнее веко
            if lid > 0.05:
                lid_m = self._mask(layer.size, lambda dd, ex=ex, ey=ey, ew=ew, eh=eh, lid=lid: dd.rectangle(
                    [ex - ew * 1.1, ey - eh * 1.5, ex + ew * 1.1, ey - eh + eh * 2 * lid], fill=255))
                self.sculpt(layer, lid_m, pal["skin"], shade_k=0.16, light_k=0.10, rim_k=0.0)
            d.arc([ex - ew, ey - eh, ex + ew, ey + eh], 190, 350, fill=line,
                  width=max(1, int(r * 0.028)))
            d.arc([ex - ew, ey - eh * 0.9, ex + ew, ey + eh], 20, 160,
                  fill=shade(pal["skin_shade"], -0.15), width=max(1, int(r * 0.02)))

        # --- нос
        nose_mask = self._mask(layer.size, lambda dd: dd.ellipse(
            [cx - r * 0.085, cy + r * 0.16, cx + r * 0.085, cy + r * 0.31], fill=255))
        self.sculpt(layer, nose_mask, mix(pal["skin"], pal["skin_shade"], 0.55),
                    shade_k=0.20, light_k=0.22, rim_k=0.0)
        if face["nose_wrinkle"] > 0.2:
            d.line([(cx - r * 0.10, cy + r * 0.13), (cx + r * 0.03, cy + r * 0.10)],
                   fill=shade(pal["skin_shade"], -0.30), width=max(1, int(r * 0.028)))

        # --- рот ------------------------------------------------------------- #
        # Рот рисуется после бороды (борода приходит раньше, из _draw_hair_front),
        # поэтому он всегда читается. Губы — не «линия улыбки», а объём:
        # верхняя губа, нижняя губа, тёмная полость, зубы и язык по параметрам.
        my = cy + r * 0.55
        mw = r * (0.20 + 0.13 * face["mouth_wide"]) * (1 + 0.22 * max(face["smile"], 0))
        sm = face["smile"]
        skew = face["mouth_skew"] * r * 0.05
        open_k = face["mouth_open"]
        lip = pal["mouth"]
        lip_light = mix(lip, (255, 230, 225), 0.35)

        if open_k > 0.06:
            mh = r * 0.06 + r * 0.30 * open_k
            # полость рта
            d.ellipse([cx - mw + skew, my - mh * 0.55, cx + mw + skew, my + mh],
                      fill=pal["mouth_dark"])
            # нижняя губа
            d.arc([cx - mw + skew, my - mh * 0.10, cx + mw + skew, my + mh * 1.25],
                  15, 165, fill=lip, width=max(2, int(r * 0.035)))
            # верхняя губа
            d.arc([cx - mw + skew, my - mh * 0.95, cx + mw + skew, my + mh * 0.45],
                  195, 345, fill=lip, width=max(2, int(r * 0.035)))
            if face["teeth"] > 0.1:
                tw = mw * (0.55 + 0.30 * face["teeth"])
                d.rounded_rectangle([cx - tw + skew, my - mh * 0.52,
                                     cx + tw + skew, my - mh * 0.52 + mh * 0.34],
                                    radius=int(max(1, mh * 0.12)), fill=(252, 248, 241))
            if face["tongue"] > 0.1:
                d.ellipse([cx - mw * 0.45 + skew, my + mh * 0.28,
                           cx + mw * 0.45 + skew, my + mh * (0.62 + 0.25 * face["tongue"])],
                          fill=(198, 112, 118))
        else:
            # губы сомкнуты: две дуги + уголки вверх/вниз по smile
            curve = sm * r * 0.14
            pts = [(cx - mw + skew, my - curve * 0.75),
                   (cx + skew, my + curve * 0.28),
                   (cx + mw + skew, my - curve * 0.75)]
            d.line(pts, fill=lip, width=max(2, int(r * 0.045)), joint="curve")
            # нижняя губа — светлый объём под линией
            d.line([(x, y + r * 0.030) for x, y in pts], fill=lip_light,
                   width=max(1, int(r * 0.022)), joint="curve")
            if sm > 0.25:
                # уголки уходят вверх — улыбка читается даже в мелком кадре
                for sx in (-1, 1):
                    ex = cx + sx * (mw + r * 0.02) + skew
                    ey = my - curve * 0.75
                    d.arc([ex - r * 0.06, ey - r * 0.09, ex + r * 0.06, ey + r * 0.03],
                          200 if sx > 0 else 0, 340 if sx > 0 else 140,
                          fill=lip, width=max(1, int(r * 0.026)))
        # носогубная тень — связывает нос и рот, лицо не «плоское»
        d.arc([cx - mw * 0.9, my - r * 0.30, cx + mw * 0.9, my + r * 0.10],
              200, 340, fill=shade(pal["skin_shade"], -0.10),
              width=max(1, int(r * 0.018)))

        # --- румянец, слёзы, пот
        if face["blush"] > 0.05:
            for sx in (-1, 1):
                bx = cx + sx * r * 0.58
                blush = self._mask(layer.size, lambda dd, bx=bx: dd.ellipse(
                    [bx - r * 0.17, cy + r * 0.14, bx + r * 0.17, cy + r * 0.34], fill=255))
                layer.paste((236, 150, 140, 255), (0, 0),
                            blush.point(lambda v, k=face["blush"]: int(v * 0.55 * k)))
        if face["tears"] > 0.05:
            for sx in (-1, 1):
                tx = cx + sx * r * 0.34
                d.ellipse([tx - r * 0.035, cy + r * 0.10, tx + r * 0.035,
                           cy + r * (0.18 + 0.35 * face["tears"])], fill=(150, 205, 240))
        if face["sweat"] > 0.05:
            sx0, sy0 = cx + r * 0.92, cy - r * 0.50
            s = r * 0.10 * face["sweat"]
            d.ellipse([sx0 - s, sy0 - s * 0.4, sx0 + s, sy0 + s * 1.4], fill=(150, 205, 240))

    def _draw_headwear(self, layer: Image.Image, sk: R.Skeleton, item: dict) -> None:
        cx, cy = self.head_pos(sk)
        r = self.head_radius(sk)
        draw = item.get("draw", {})
        col = hex_rgb(draw.get("color", "#9FD3C0"))

        bottom = cy - r * 0.46
        def mask(d):
            self.chord_half(d, cx - r * 1.04, cx + r * 1.04, cy - r * 1.12, bottom)
            d.rounded_rectangle([cx - r * 1.04, bottom - r * 0.10, cx + r * 1.04, bottom + r * 0.06],
                                radius=int(r * 0.08), fill=255)
            if draw.get("brim"):
                d.rounded_rectangle([cx + r * 0.05, bottom - r * 0.10, cx + r * 1.30, bottom + r * 0.14],
                                    radius=int(r * 0.10), fill=255)
        self.sculpt(layer, self._mask(layer.size, mask), col, shade_k=0.24, light_k=0.14)
        d = ImageDraw.Draw(layer)
        if draw.get("text"):
            path = os.path.join(FONT_DIR, "Montserrat-800.ttf")
            size = max(8, int(r * 0.30))
            font = ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default()
            text = draw["text"]
            bbox = d.textbbox((0, 0), text, font=font)
            d.text((cx - (bbox[2] - bbox[0]) / 2, cy - r * 0.95), text, font=font,
                   fill=(38, 38, 42))

    def _draw_accessory(self, layer: Image.Image, sk: R.Skeleton, item: dict) -> None:
        d = ImageDraw.Draw(layer)
        draw = item.get("draw", {})
        cx, cy = self.head_pos(sk)
        r = self.head_radius(sk)
        col = hex_rgb(draw.get("color", "#3B2A26"))
        if draw.get("frames"):
            for sx in (-1, 1):
                ex = cx + sx * r * 0.34
                d.ellipse([ex - r * 0.21, cy - r * 0.17, ex + r * 0.21, cy + r * 0.15],
                          outline=col, width=max(2, int(r * 0.028)))
            d.line([(cx - r * 0.13, cy - r * 0.02), (cx + r * 0.13, cy - r * 0.02)],
                   fill=col, width=max(2, int(r * 0.025)))
        if draw.get("chain"):
            chest_top = self.tip(sk, "chest")
            ax = cx
            ay = chest_top[1] - r * 0.05
            d.arc([ax - r * 0.42, ay - r * 0.25, ax + r * 0.42, ay + r * 0.42], 20, 160,
                  fill=col, width=max(1, int(r * 0.018)))
            if draw.get("pendant") == "cross":
                py = ay + r * 0.30
                d.line([(ax, py - r * 0.05), (ax, py + r * 0.09)], fill=col,
                       width=max(2, int(r * 0.022)))
                d.line([(ax - r * 0.04, py), (ax + r * 0.04, py)], fill=col,
                       width=max(2, int(r * 0.022)))
        if draw.get("wrap"):
            neck = self.tip(sk, "neck")
            d.rounded_rectangle([neck[0] - r * 0.62, neck[1] - r * 0.18,
                                 neck[0] + r * 0.62, neck[1] + r * 0.34],
                                radius=int(r * 0.20), fill=col)
        if draw.get("straps"):
            for sx in (-1, 1):
                d.line([(cx + sx * r * 1.05, cy - r * 0.35),
                        (cx + sx * r * 2.6, cy + r * 2.3)], fill=col,
                       width=max(3, int(r * 0.12)))


# --------------------------------------------------------------------------- #
# публичные функции
# --------------------------------------------------------------------------- #


def background(width: int, height: int, ground: float = 0.93, mode: str = "studio"):
    """Фон кадра без персонажа — для сцен, где персонажей несколько."""
    if mode == "chroma":
        return Image.new("RGBA", (width, height), (0, 177, 64, 255))
    return _background_cache(width, height, ground).copy()


def render(spec: dict, pose: str = "idle", expression: str = "neutral",
           outfit: dict[str, str] | None = None, set_name: str | None = None,
           opts: RenderOpts | None = None, face_obj: F.Face | None = None,
           background: str | None = None, caption: str | None = None) -> Image.Image:
    p = Painter(spec, opts)
    sk = p.build(pose)
    return p.frame(sk, face_obj, face_expr=expression, outfit=outfit,
                   set_name=set_name, background=background, caption=caption)


def contact_sheet(spec: dict, *, poses: list[str] | None = None,
                  expressions: list[str] | None = None,
                  cell: tuple[int, int] = (300, 480)) -> Image.Image:
    """Сетка «позы × эмоции» — быстрый визуальный контроль гибкости персонажа."""
    poses = poses or ["idle", "wave", "point", "think", "surprise", "carry"]
    expressions = expressions or ["neutral", "joy", "surprise", "anger", "sad", "smirk"]
    cw, ch = cell
    label_h = 26
    sheet = Image.new("RGB", (cw * len(expressions) + 8, (ch + label_h) * len(poses) + 8),
                      (250, 246, 238))
    d = ImageDraw.Draw(sheet)
    font_path = os.path.join(FONT_DIR, "Nunito-700.ttf")
    font = ImageFont.truetype(font_path, 15) if os.path.exists(font_path) else ImageFont.load_default()
    opts = RenderOpts(width=cw, height=ch, ss=2, ground=0.93, margin=0.03, shadow=True, grain=0)
    p = Painter(spec, opts)
    for row, pose_id in enumerate(poses):
        for col, expr_id in enumerate(expressions):
            sk = p.build(pose_id)
            img = p.frame(sk, face_expr=expr_id)
            x, y = 4 + col * cw, 4 + row * (ch + label_h)
            sheet.paste(img, (x, y))
            d.text((x + 6, y + ch + 3), f"{pose_id} · {expr_id}", font=font, fill=(96, 84, 76))
    return sheet


def face_sheet(spec: dict, *, expressions: list[str] | None = None,
               cols: int = 6, cell: int = 230) -> Image.Image:
    """Крупные планы эмоций: видно, что лицо действительно параметрическое."""
    expressions = expressions or list(L.expression_table())
    rows = (len(expressions) + cols - 1) // cols
    label_h = 24
    sheet = Image.new("RGB", (cell * cols + 8, (cell + label_h) * rows + 8), (250, 246, 238))
    d = ImageDraw.Draw(sheet)
    font_path = os.path.join(FONT_DIR, "Nunito-700.ttf")
    font = ImageFont.truetype(font_path, 14) if os.path.exists(font_path) else ImageFont.load_default()

    opts = RenderOpts(width=cell, height=cell, ss=3, ground=0.97, margin=0.02, shadow=False)
    p = Painter(spec, opts)
    sk = p.build("idle")
    for i, expr in enumerate(expressions):
        img = p.frame(sk, face_expr=expr)
        # кадрируем голову: пересчитываем позицию в координатах готового кадра
        cx, cy = p.head_pos(sk)
        r = p.head_radius(sk)
        cx, cy, r = cx / opts.ss, cy / opts.ss, r / opts.ss
        # кадрируем ровно голову: волосы сверху, подбородок снизу, без плеч
        box = (int(cx - r * 1.45), int(max(cy - r * 1.40, 0)),
               int(cx + r * 1.45), int(max(cy - r * 1.40, 0) + r * 2.60))
        img = img.crop(box).resize((cell, cell), Image.LANCZOS)
        x, y = 4 + (i % cols) * cell, 4 + (i // cols) * (cell + label_h)
        sheet.paste(img, (x, y))
        d.text((x + 5, y + cell + 3), expr, font=font, fill=(96, 84, 76))
    return sheet


def _load_spec(char_id: str) -> dict:
    import kit
    return kit.load_character(char_id)


def main() -> None:
    ap = argparse.ArgumentParser(description="процедурная кукла персонажа")
    ap.add_argument("cmd", choices=["preview", "sheet", "faces", "outfit"])
    ap.add_argument("--char", required=True)
    ap.add_argument("--pose", default="idle")
    ap.add_argument("--expr", default="neutral")
    ap.add_argument("--top")
    ap.add_argument("--bottom")
    ap.add_argument("--shoes")
    ap.add_argument("--outer")
    ap.add_argument("--headwear")
    ap.add_argument("--accessory")
    ap.add_argument("--set", dest="set_name")
    ap.add_argument("--background", default=None)
    ap.add_argument("--caption", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    spec = _load_spec(args.char)
    out_dir = os.path.join(STUDIO, "out")
    os.makedirs(out_dir, exist_ok=True)

    if args.cmd == "faces":
        img = face_sheet(spec)
        path = args.out or os.path.join(out_dir, f"puppet-faces-{args.char}.png")
        img.save(path)
        print("✓", path, img.size)
        return

    if args.cmd == "sheet":
        img = contact_sheet(spec)
        path = args.out or os.path.join(out_dir, f"puppet-sheet-{args.char}.png")
        img.save(path)
        print("✓", path, img.size)
        return

    overrides = {k: v for k, v in {
        "top": args.top, "bottom": args.bottom, "shoes": args.shoes,
        "outer": args.outer, "headwear": args.headwear, "accessory": args.accessory,
    }.items() if v}
    suffix = "-" + "-".join(sorted(overrides)) if overrides else ""
    img = render(spec, pose=args.pose, expression=args.expr, outfit=overrides or None,
                 set_name=args.set_name, background=args.background, caption=args.caption)
    path = args.out or os.path.join(out_dir, f"puppet-{args.char}-{args.pose}-{args.expr}{suffix}.png")
    img.save(path)
    print("✓", path, img.size)


if __name__ == "__main__":
    main()
