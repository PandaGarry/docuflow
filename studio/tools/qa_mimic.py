"""Контроль кадров мимики: не битые, не обрезанные, не другого масштаба.

    python studio/tools/qa_mimic.py dad

Каждый кадр эмоции и визема сверяется с нейтральным портретом своего ракурса.
Ловит ровно те ошибки, которые уже случались:

- кадр полноростовой вместо портрета (масштаб головы уехал);
- срезан верх головы;
- не снялся зелёный фон (генератор дал другой оттенок);
- пустой или почти пустой кадр;
- фон не зелёный вообще (модель проигнорировала хромакей).

Проверка идёт по СЫРЫМ файлам: у обрезанного кадра углы — это плечи, и
проверка «что в углах» на нём бессмысленна (на этом уже один раз обожглись).
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import characters as ch
import cutout as C
import facefx

# допуски
TOL_BBOX_H = 0.06        # высота содержимого может отличаться на 6 %
TOL_HEAD = 0.12          # ширина головы — на 12 %
MIN_ALPHA = 0.15         # доля непрозрачных пикселей
EDGE_MARGIN = 2          # зазор сверху до края кадра
GREEN_TOL = 0.005        # доля оставшихся зелёных пикселей


def _stats(path: Path) -> dict:
    """Замеры по сырому файлу: кеим сами, кадр не обрезаем."""
    img = Image.open(path).convert("RGB")
    a = np.asarray(C.key_green(img))
    al = a[..., 3] > 40
    ys, xs = np.where(al)
    if not len(ys):
        return {}
    h = int(ys.max() - ys.min() + 1)
    # ширина на уровне лба/глаз — мера «крупности» головы
    band = al[int(ys.min() + 0.05 * h): int(ys.min() + 0.22 * h)]
    head_w = 0
    for row in band:
        idx = np.where(row)[0]
        if len(idx):
            head_w = max(head_w, int(idx.max() - idx.min() + 1))
    # остатки зелёного: пиксель непрозрачен и остался зелёным
    gi = a[..., :3].astype(np.int16)
    green_px = int((al & (gi[..., 1] - gi[..., 0] > 30)
                    & (gi[..., 1] - gi[..., 2] > 40)).sum())
    return {
        "head_w": head_w,
        "bbox_h": h,
        "alpha_frac": float(al.mean()),
        "top_margin": int(ys.min()),
        "green_frac": green_px / al.size,
    }


def check_frame(path: Path, ref: dict) -> list[str]:
    """Список проблем кадра. Пустой список — кадр годный."""
    if not path.exists():
        return ["файла нет"]
    st = _stats(path)
    if not st:
        return ["пустой кадр (нет непрозрачных пикселей)"]
    bad: list[str] = []
    dh = abs(st["bbox_h"] - ref["bbox_h"]) / ref["bbox_h"]
    if dh > TOL_BBOX_H:
        bad.append(f"масштаб: высота содержимого {st['bbox_h']} против "
                   f"{ref['bbox_h']} ({dh * 100:.0f} %) — кадр другого плана")
    dw = abs(st["head_w"] - ref["head_w"]) / max(ref["head_w"], 1)
    if dw > TOL_HEAD:
        bad.append(f"голова: {st['head_w']} против {ref['head_w']} "
                   f"({dw * 100:.0f} %) — другой масштаб или поворот")
    if st["alpha_frac"] < MIN_ALPHA:
        bad.append(f"почти пусто: непрозрачно {st['alpha_frac'] * 100:.0f} %")
    if st["top_margin"] < EDGE_MARGIN:
        bad.append("срезан верх головы")
    if st["green_frac"] > GREEN_TOL:
        bad.append(f"не снялся зелёный фон: {st['green_frac'] * 100:.1f} % кадра")
    return bad


def main(char_key: str, *, write: bool = True) -> int:
    out = HERE.parents[2] / "studio" / "out" / "qa-mimic.md"
    lines = [f"# Контроль мимики: {char_key}", "",
             "Каждый кадр сверяется с нейтральным портретом своего ракурса. "
             "Пересобирается командой `python studio/tools/qa_mimic.py "
             f"{char_key}`.", ""]
    problems = total = 0
    for kind, items, folder in (("эмоции", ch.EMOTIONS, "emotions"),
                                ("виземы", ch.VISEMES, "visemes")):
        for view in ch.VIEWS:
            if view == "back":
                continue
            ref_path = ch.emotion_path(ch.CHARACTERS[char_key], "neutral", view)
            if not ref_path.exists():
                continue
            ref = _stats(ref_path)
            rows = []
            for key in items:
                if kind == "эмоции" and key == "neutral":
                    continue
                path = (ch.emotion_path(ch.CHARACTERS[char_key], key, view)
                        if kind == "эмоции"
                        else ch.viseme_path(ch.CHARACTERS[char_key], key, view))
                if not path.exists():
                    continue
                total += 1
                bad = check_frame(path, ref)
                if bad:
                    problems += 1
                rows.append(f"| {key} | {'ok' if not bad else 'БРАК'} | "
                            f"{'; '.join(bad)} |")
            if rows:
                lines += [f"## {kind} · {view}", "",
                          "| кадр | статус | замечания |", "|---|---|---|", *rows, ""]
    lines.insert(3, f"Проверено кадров: **{total}**, с замечаниями: **{problems}**.")
    lines.insert(4, "")
    if write:
        out.write_text("\n".join(lines) + "\n")
        print(out)
    print(f"проверено {total}, замечаний {problems}")
    return problems


if __name__ == "__main__":
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    raise SystemExit(1 if main(key) else 0)
