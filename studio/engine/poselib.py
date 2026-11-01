"""Библиотека кадров персонажа: загрузка, якоря, манифест.

Зачем якоря. Движку нужно ставить персонажа в кадр самому: знать, где у него
подошвы (чтобы не «висел» над полом), где центр головы (чтобы наложить эмоцию
или визем), какой у него рост в кадре (чтобы один персонаж не оказался вдвое
больше другого). Эти числа считаются один раз при сборке библиотеки и
сохраняются в `manifest.json` рядом с картинками.

Соглашение: картинки лежат в долях роста, движок никогда не двигает их на глаз.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

import characters as ch
import cutout as C


def load_cut(path) -> Image.Image:
    """Открыть кадр и вырезать фон — один раз.

    Кадры библиотеки уже лежат с альфой (RGBA). Повторный хромакей им вреден:
    у прозрачных пикселей цвет не определён, и «зелёность» считается по мусору.
    Поэтому кеим только картинки без альфы (мастера, сырые листы).
    """
    img = Image.open(path)
    if img.mode == "RGBA":
        a = np.asarray(img)[..., 3]
        if (a < 10).any():
            return C.trim(img)
    return C.trim(C.key_green(img))

ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# подсчёт якорей
# --------------------------------------------------------------------------- #

def _mask(img: Image.Image) -> np.ndarray:
    return np.asarray(img)[..., 3] > 40


def anchors_body(img: Image.Image) -> dict:
    """Якоря полноростового кадра (по уже вырезанной фигуре)."""
    m = _mask(img)
    ys, xs = np.where(m)
    if not len(ys):
        return {}
    top, bot = int(ys.min()), int(ys.max())
    H = bot - top + 1
    cx_all = float(np.median(xs))
    # Голова: берём ЦЕНТРАЛЬНЫЙ отрезок строки, а не весь размах. Иначе у позы
    # с поднятой рукой «ширина головы» считается вместе с кистью (получалось
    # 466 px вместо 250). Центральный отрезок — это всегда сама голова.
    head_w, head_y, head_cx = 0, top, cx_all
    for y in range(top, top + max(int(0.25 * H), 8)):
        row = np.where(m[y])[0]
        if not len(row):
            continue
        seg = _central_segment(row, cx_all)
        if seg and seg[1] - seg[0] > head_w:
            head_w = int(seg[1] - seg[0] + 1)
            head_y = y
            head_cx = float((seg[0] + seg[1]) / 2)
    # центр корпуса — по нему ставим персонажа в кадр: голова и торс не
    # гуляют от взмаха рук, в отличие от центра всего силуэта
    band = (ys > top + 0.22 * H) & (ys < top + 0.62 * H)
    body_cx = float(np.median(xs[band])) if band.any() else float(np.median(xs))
    # опорная стопа: у земли в нижних 12 % силуэта ищем кластеры (стопы) и
    # берём тот, что ниже всего — он и стоит на полу. Нужен для «локтя стопы»:
    # в анимации опорная стопа не должна ездить по полу.
    low_mask = ys > bot - 0.12 * H
    plant_x = None
    feet = []
    if low_mask.any():
        lx = np.sort(xs[low_mask])
        gaps = np.where(np.diff(lx) > 4)[0]
        segs, s0 = [], lx[0]
        for g in gaps:
            segs.append((int(s0), int(lx[g])))
            s0 = lx[g + 1]
        segs.append((int(s0), int(lx[-1])))
        segs = [sg for sg in segs if sg[1] - sg[0] > 6]
        for x0, x1 in segs:
            col = m[:, x0:x1 + 1]
            yy = np.where(col.any(axis=1))[0]
            feet.append({"cx": (x0 + x1) / 2, "bottom": int(yy.max()) if len(yy) else bot})
        if feet:
            plant_x = float(max(feet, key=lambda f: f["bottom"])["cx"])

    # подошвы: центр низа
    low = np.where(m[bot - 2])[0]
    foot_cx = float((low.min() + low.max()) / 2) if len(low) else (xs.min() + xs.max()) / 2
    return {
        "height_px": H,
        "head_top": top,
        "head_w": head_w,
        "head_cy": float(head_y),
        "head_cx": head_cx,
        "foot_y": bot,
        "foot_cx": foot_cx,
        "body_cx": body_cx,
        "plant_cx": plant_x,
        "feet": feet,
        "width_px": int(xs.max() - xs.min() + 1),
    }


def _central_segment(row: np.ndarray, cx: float) -> tuple[int, int] | None:
    """Непрерывный отрезок строки, ближайший к центру фигуры."""
    if not len(row):
        return None
    gaps = np.where(np.diff(row) > 4)[0]
    segs, s = [], row[0]
    for g in gaps:
        segs.append((int(s), int(row[g])))
        s = row[g + 1]
    segs.append((int(s), int(row[-1])))
    return min(segs, key=lambda sg: abs((sg[0] + sg[1]) / 2 - cx))


def anchors_head(img: Image.Image) -> dict:
    """Якоря портрета: центр и размер головы в кадре.

    Портрет — это голова и плечи, поэтому голова занимает кадр гораздо крупнее,
    чем на полном росте. Чтобы вклеить мимику в полный кадр, нужен масштаб:
    `head_w` портрета к `head_w` позы. Пишем его здесь, а не считаем на глаз.
    """
    m = _mask(img)
    ys, xs = np.where(m)
    if not len(ys):
        return {}
    h = int(ys.max() - ys.min() + 1)
    head_w = 0
    for y in range(int(ys.min()), int(ys.min() + 0.55 * h)):
        row = np.where(m[y])[0]
        if len(row):
            head_w = max(head_w, int(row.max() - row.min() + 1))
    return {
        "head_w": head_w,
        "x0": int(xs.min()), "x1": int(xs.max()),
        "y0": int(ys.min()), "y1": int(ys.max()),
        "cx": float((xs.min() + xs.max()) / 2),
        "cy": float((ys.min() + ys.max()) / 2),
        "w": int(xs.max() - xs.min() + 1),
        "h": int(ys.max() - ys.min() + 1),
    }


# --------------------------------------------------------------------------- #
# манифест
# --------------------------------------------------------------------------- #

def build_manifest(char_key: str, *, write: bool = True) -> dict:
    """Пройти по папкам персонажа, посчитать якоря, собрать manifest.json."""
    char = ch.CHARACTERS[char_key]
    out: dict = {"character": char_key, "height_heads": char.height_heads,
                 "bg": ch.BG_HEX, "poses": {},
                 "emotions": {v: {} for v in ch.VIEWS},
                 "visemes": {v: {} for v in ch.VIEWS}}

    body_keys = [p.key for p in ch.POSES]
    for key in body_keys:
        path = ch.pose_path(char, key)
        if path.exists():
            img = load_cut(path)
            out["poses"][key] = {"file": str(path.relative_to(ROOT)),
                                 **anchors_body(img)}
    for view in ch.VIEWS:
        if view == "back":
            continue          # у спины нет лица: мимика к ней не относится
        for emo in ch.EMOTIONS:
            path = ch.emotion_path(char, emo, view)
            if path.exists():
                img = load_cut(path)
                out["emotions"][view][emo] = {
                    "file": str(path.relative_to(ROOT)), **anchors_head(img)}
        for v in ch.VISEMES:
            path = ch.viseme_path(char, v, view)
            if path.exists():
                img = load_cut(path)
                out["visemes"][view][v] = {
                    "file": str(path.relative_to(ROOT)), **anchors_head(img)}

    if write:
        mp = char.dir / "manifest.json"
        mp.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    return out


# --------------------------------------------------------------------------- #
# загрузка для движка
# --------------------------------------------------------------------------- #

@dataclass
class Frame:
    key: str
    img: Image.Image | np.ndarray
    anchor: dict

    @property
    def height(self) -> float:
        return float(self.anchor.get("height_px", self.anchor.get("h", 1)))

    def flipped(self) -> "Frame":
        """Зеркальный кадр.

        Второй полуцикл ходьбы и бега НЕ генерируется: это отражение первого.
        Отсюда же направление «идёт влево» без отдельной картинки.
        """
        img = self.img.transpose(Image.FLIP_LEFT_RIGHT)
        w = img.width
        a = dict(self.anchor)
        if "head_cx" in a:
            a["head_cx"] = w - a["head_cx"]
            a["foot_cx"] = w - a.get("foot_cx", a["head_cx"])
            a["body_cx"] = w - a.get("body_cx", a["head_cx"])
        if "cx" in a:
            a["cx"] = w - a["cx"]
        return Frame(self.key + ":mirror", img, a)


class Library:
    """Кадры одного персонажа. Кэш по ключу, ленивая загрузка с диска."""

    def __init__(self, char_key: str):
        self.char = ch.CHARACTERS[char_key]
        self.key = char_key
        mp = self.char.dir / "manifest.json"
        self.manifest = json.loads(mp.read_text()) if mp.exists() else {}
        self._cache: dict[str, Frame] = {}

    def _load(self, kind: str, key: str, view: str = "front") -> Frame | None:
        rec = self.manifest.get(kind, {})
        if kind in ("emotions", "visemes"):
            rec = rec.get(view, {}).get(key)
        else:
            rec = rec.get(key)
        if rec is None:
            if kind == "poses":
                path = ch.pose_path(self.char, key)
            else:
                path = {"emotions": ch.emotion_path,
                        "visemes": ch.viseme_path}[kind](self.char, key, view)
            if not path.exists():
                return None
            img = load_cut(path)
            anchor = anchors_body(img) if kind == "poses" else anchors_head(img)
        else:
            img = load_cut(ROOT / rec["file"])
            anchor = {k: v for k, v in rec.items() if k != "file"}
        return Frame(f"{kind}:{key}", img, anchor)

    def pose(self, key: str, facing: str = "right") -> Frame | None:
        """Кадр позы. `facing="left"` — зеркало (для ходьбы/бега в другую сторону)."""
        k = f"poses:{key}"
        if k not in self._cache:
            fr = self._load("poses", key)
            if fr is None:
                return None
            self._cache[k] = fr
        fr = self._cache[k]
        return fr.flipped() if facing == "left" else fr

    def emotion(self, key: str, view: str = "front") -> Frame | None:
        k = f"emotions:{view}:{key}"
        if k not in self._cache:
            fr = self._load("emotions", key, view)
            if fr is None:
                return None
            self._cache[k] = fr
        return self._cache[k]

    def viseme(self, key: str, view: str = "front") -> Frame | None:
        k = f"visemes:{view}:{key}"
        if k not in self._cache:
            fr = self._load("visemes", key, view)
            if fr is None:
                return None
            self._cache[k] = fr
        return self._cache[k]

    def face(self, view: str = "front") -> dict:
        """Разметка лица персонажа для ракурса (канон, см. docs/27-FACE.md)."""
        import facefx
        return facefx.load_landmarks(self.key, view)

    def missing(self) -> dict[str, list[str]]:
        """Чего не хватает — чтобы добивать библиотеку по списку, а не на глаз."""
        have = self.manifest
        miss: dict[str, list[str]] = {
            "poses": [p.key for p in ch.POSES if p.key not in have.get("poses", {})],
        }
        # мимика по ракурсам: «нет эмоций» без ракурса ничего не говорит
        for kind, items in (("emotions", ch.EMOTIONS), ("visemes", ch.VISEMES)):
            for view in ch.VIEWS:
                if view == "back":
                    continue
                got = have.get(kind, {}).get(view, {})
                left = [i for i in items if i not in got]
                if left:
                    miss[f"{kind}:{view}"] = left
        return miss


def contact_sheet(char_key: str, *, cell_h: int = 420,
                  path: Path | None = None) -> Path:
    """Сводный лист библиотеки: все кадры в один PNG, для визуальной проверки."""
    char = ch.CHARACTERS[char_key]
    tiles: list[Image.Image] = []
    for key in [p.key for p in ch.POSES]:
        p = ch.pose_path(char, key)
        if p.exists():
            tiles.append(load_cut(p))
    for emo in ch.EMOTIONS:
        p = ch.emotion_path(char, emo)
        if p.exists():
            tiles.append(load_cut(p))
    if not tiles:
        raise SystemExit(f"у {char_key} нет кадров")
    tiles = [t.resize((max(int(t.width * cell_h / t.height), 1), cell_h),
                      Image.LANCZOS) for t in tiles]
    # раскладка рядами по 8
    per_row = 8
    rows = [tiles[i:i + per_row] for i in range(0, len(tiles), per_row)]
    W = max(sum(t.width for t in r) for r in rows) + 20 * per_row
    H = cell_h * len(rows) + 20 * len(rows)
    sheet = Image.new("RGB", (W, H), (250, 248, 244))
    y = 10
    for r in rows:
        x = 10
        for t in r:
            sheet.paste(t, (x, y), t.getchannel("A") if t.mode == "RGBA" else None)
            x += t.width + 20
        y += cell_h + 20
    out = path or (ROOT / "studio" / "out" / f"{char_key}-library.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out
