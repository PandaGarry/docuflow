"""Разрезать лист кадров (walk/run cycle sheet) на отдельные позы.

    python studio/tools/slice_sheet.py dad sheets/walk-cycle.png \
        walk-contact walk-down walk-passing walk-up \
        walk-contact-R walk-down-R walk-passing-R walk-up-R

Зачем так. По одной позе модель не держит чередование ног: если попросить
«вторую половину цикла», она перерисовывает ту же фазу (проверено: IoU силуэта
0.99 у бега). На листе фаз модель рисует всю последовательность сразу и сама
держит чередование. Остаётся разрезать лист и разложить кадры по именам.

Порядок кадров — слева направо, сверху вниз.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import characters as ch
import cutout as C


def _biggest_blob(mask: np.ndarray, scale: int = 4) -> np.ndarray:
    """Оставить самую большую связную область: отрезает куски соседних фигур."""
    h, w = mask.shape
    ch_, cw = h // scale, w // scale
    if ch_ < 1 or cw < 1:
        return mask
    small = mask[:ch_ * scale, :cw * scale].reshape(ch_, scale, cw, scale).any(axis=(1, 3))
    seen = np.zeros_like(small)
    best, best_n = None, 0
    for sy in range(ch_):
        for sx in range(cw):
            if not small[sy, sx] or seen[sy, sx]:
                continue
            q = deque([(sy, sx)])
            seen[sy, sx] = True
            cells_ = []
            while q:
                y, x = q.popleft()
                cells_.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < ch_ and 0 <= nx < cw and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
            if len(cells_) > best_n:
                best_n, best = len(cells_), cells_
    if not best:
        return mask
    keep = np.zeros_like(small)
    ys = [c[0] for c in best]
    xs = [c[1] for c in best]
    for (yy, xx) in best:
        keep[yy, xx] = True
    full = np.repeat(np.repeat(keep, scale, axis=0), scale, axis=1)
    full = np.pad(full, ((0, max(h - full.shape[0], 0)), (0, max(w - full.shape[1], 0))))[:h, :w]
    out = mask & full
    return out if out.any() else mask


def _erode(mask: np.ndarray, r: int = 1) -> np.ndarray:
    out = mask.copy()
    for _ in range(r):
        u = np.zeros_like(out)
        u[1:, :] |= out[:-1, :]
        v = np.zeros_like(out)
        v[:-1, :] |= out[1:, :]
        l = np.zeros_like(out)
        l[:, 1:] |= out[:, :-1]
        rr = np.zeros_like(out)
        rr[:, :-1] |= out[:, 1:]
        out = out & u & v & l & rr
    return out


def _dilate(mask: np.ndarray, r: int = 1) -> np.ndarray:
    out = mask.copy()
    for _ in range(r):
        u = np.zeros_like(out)
        u[1:, :] = out[:-1, :]
        v = np.zeros_like(out)
        v[:-1, :] = out[1:, :]
        l = np.zeros_like(out)
        l[:, 1:] = out[:, :-1]
        rr = np.zeros_like(out)
        rr[:, :-1] = out[:, 1:]
        out = out | u | v | l | rr
    return out


def _clean_alpha(img: Image.Image) -> Image.Image:
    """Убрать налипшие куски соседей: тонкие перемычки рвём эрозией."""
    a = np.asarray(img).copy()
    m = a[..., 3] > 40
    core = _biggest_blob(_erode(m, 2), scale=1)
    keep = _dilate(core, 2) & m
    if keep.sum() < 0.5 * m.sum():
        return img
    a[..., 3] = np.where(keep, a[..., 3], 0)
    return Image.fromarray(a, "RGBA")


def _bands(profile: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """Непрерывные полосы ненулевого профиля, разделённые зазором >= gap."""
    idx = np.where(profile > 0)[0]
    if not len(idx):
        return []
    out, start = [], idx[0]
    for a, b in zip(idx, idx[1:]):
        if b - a > gap:
            out.append((int(start), int(a) + 1))
            start = b
    out.append((int(start), int(idx[-1]) + 1))
    return out


def cells(mask: np.ndarray, row_gap: int = 24, col_gap: int = 10,
          per_row: int = 0) -> list[tuple[int, int, int, int]]:
    """Ячейки сетки листа: сначала полосы строк, внутри — полосы столбцов.

    По связности резать ненадёжно: две соседние фигуры на листе иногда касаются
    друг друга и склеиваются в одну область, и тогда в кадр попадает кусок
    соседа. Сетка по пустым строкам и столбцам такого не даёт.
    """
    out = []
    for y0, y1 in _bands(mask.any(axis=1).astype(int), row_gap):
        band = mask[y0:y1]
        if per_row:
            # Лист рисуется равномерно, но фигуры часто касаются друг друга и
            # склеиваются — тогда режем ряд на равные доли. Это надёжнее, чем
            # искать зазоры: сосед перестаёт попадать в кадр.
            w = band.shape[1]
            step = w / per_row
            prof = band.sum(axis=0)
            # Границы ячеек уточняем по минимуму вертикального профиля около
            # равного деления: так линия разреза попадает в зазор между
            # фигурами, а не режет соседа пополам.
            bounds = [0]
            for i in range(1, per_row):
                xe = int(i * step)
                lo = max(0, xe - int(0.14 * step))
                hi = min(w, xe + int(0.14 * step))
                xe = lo + int(np.argmin(prof[lo:hi])) if hi > lo else xe
                bounds.append(xe)
            bounds.append(w)
            for i in range(per_row):
                x0, x1 = bounds[i], bounds[i + 1]
                sub = band[:, x0:x1]
                if not sub.any():
                    continue
                xs = np.where(sub.any(axis=0))[0]
                out.append((x0 + int(xs[0]), y0, x0 + int(xs[-1]) + 1, y1))
            continue
        for x0, x1 in _bands(band.any(axis=0).astype(int), col_gap):
            out.append((x0, y0, x1, y1))
    return out


def main(char_key: str, sheet: str, keys: list[str], *, min_area: int = 60,
         write: bool = True, normalize: bool = True, per_row: int = 0) -> list[Path]:
    char = ch.CHARACTERS[char_key]
    src = char.dir / sheet if not Path(sheet).is_absolute() else Path(sheet)
    rgba = C.trim(C.key_green(Image.open(src)))
    mask = np.asarray(rgba)[..., 3] > 60
    ordered = [c for c in cells(mask, per_row=per_row)
               if (c[2] - c[0]) * (c[3] - c[1]) > min_area * 40]
    if len(ordered) != len(keys):
        raise SystemExit(f"нашёл {len(ordered)} фигур, а ключей {len(keys)}: "
                         f"поправь лист или список ключей")
    crops = []
    for (x0, y0, x1, y1) in ordered:
        pad = 6
        x0c, y0c = max(x0 - pad, 0), max(y0 - pad, 0)
        x1c, y1c = min(x1 + pad, rgba.width), min(y1 + pad, rgba.height)
        cell = rgba.crop((x0c, y0c, x1c, y1c))
        # внутри ячейки оставляем только главную фигуру
        m = np.asarray(cell)[..., 3] > 40
        keep = _biggest_blob(m, scale=2)
        if keep.any():
            ys, xs = np.where(keep)
            cell = cell.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
        cell = _clean_alpha(cell)
        crops.append(C.trim(cell))

    # Лист часто нарисован рядами в разном масштабе: фигуры второго ряда бывают
    # на 10–15 % крупнее. Для фазы шага рост почти не меняется (покачивание
    # ~2 %), поэтому выравниваем кадры по медианной высоте, привязывая низ
    # (подошвы) к общей линии — иначе персонаж прыгает размером между половинами.
    if normalize and crops:
        hs = sorted(c.height for c in crops)
        target = hs[len(hs) // 2]
        fixed = []
        for c in crops:
            if abs(c.height - target) / target <= 0.03:
                fixed.append(c)
                continue
            k = target / c.height
            new = c.resize((max(int(c.width * k), 1), target), Image.LANCZOS)
            fixed.append(new)
        crops = fixed

    paths = []
    for key, crop in zip(keys, crops):
        if write:
            p = ch.pose_path(char, key)
            p.parent.mkdir(parents=True, exist_ok=True)
            crop.save(p)
            paths.append(p)
    return paths


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    per_row = 0
    args = sys.argv[3:]
    if "--per-row" in args:
        i = args.index("--per-row")
        per_row = int(args[i + 1])
        args = args[:i] + args[i + 2:]
    paths = main(sys.argv[1], sys.argv[2], args, per_row=per_row)
    for p in paths:
        print(p)
