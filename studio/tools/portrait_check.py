"""Проверка кадров лица: один масштаб, один ракурс, один размер кадра.

    python studio/tools/portrait_check.py dad

Зачем: генератор умеет отдать в одном наборе и мелкую фигурку в полный рост,
и крупное лицо, и горизонтальный кадр. Такой набор выглядит как брак, но
формально «файл есть», и манифест считает его готовым. Здесь проверяются
три вещи, по которым брак виден сразу:

1. **Пропорции кадра** — горизонтальный кадр для портрета невозможен.
2. **Заполнение кадра** — высота содержимого относительно высоты кадра.
   Если в кадре фигурка в полный рост, а не лицо, число сильно меньше.
3. **Масштаб лица** — расстояние между глазами в долях высоты содержимого
   (по разметке `face.json`). Разный масштаб = лицо «прыгает» при склейке.

Модуль ничего не правит: он даёт список «переснять» с числами, чтобы решение
принималось глазами, а не на веру.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import characters as ch
import facefx

ROOT = HERE.parents[2]


def measure(path: Path) -> dict:
    img = Image.open(path).convert("RGB")
    from cutout import key_green
    cut = key_green(img)
    bb = cut.getbbox()
    w, h = img.size
    if bb is None:
        return {"file": path.name, "empty": True}
    cw, chh = bb[2] - bb[0], bb[3] - bb[1]
    return {
        "file": path.name,
        "size": [w, h],
        "landscape": w > h,
        "fill": chh / h,
        "aspect": cw / chh,
        "content_h": chh,
    }


def eye_scale(char: ch.Character, view: str, path: Path) -> float | None:
    """Межзрачковое расстояние в долях высоты содержимого."""
    try:
        lm = facefx.load_landmarks(char.key, view)
        img = Image.open(path).convert("RGB")
        from cutout import key_green
        cut = key_green(img)
        bb = cut.getbbox()
        px = facefx.landmarks_px(lm, cut)
    except Exception:
        return None
    eyes = px.get("eyes") or []
    if len(eyes) < 2:
        return None
    (x1, y1), (x2, y2) = eyes[0], eyes[1]
    ipd = float(np.hypot(x2 - x1, y2 - y1))
    return ipd / max(1.0, bb[3] - bb[1])


def check(char_key: str) -> int:
    char = {"dad": ch.DAD, "mom": ch.MOM, "son": ch.SON}[char_key]
    bad = 0
    for view in ("front", "three-quarter", "side"):
        for kind, items in (("emotions", ch.EMOTIONS), ("visemes", ch.VISEMES)):
            rows = []
            for key in items:
                path = char.dir / kind / view / f"{key}.png"
                if not path.exists():
                    continue
                m = measure(path)
                m["ipd"] = eye_scale(char, view, path)
                m["key"] = key
                rows.append(m)
            if not rows:
                continue
            fills = np.array([r["fill"] for r in rows])
            med = float(np.median(fills))
            ips = np.array([r["ipd"] for r in rows if r["ipd"]], dtype=float)
            ipd_med = float(np.median(ips)) if len(ips) else 0.0
            print(f"\n{kind}/{view}: {len(rows)} кадров, "
                  f"заполнение медиана {med:.2f}, ipd медиана {ipd_med:.3f}")
            for r in rows:
                why = []
                if r["landscape"]:
                    why.append("горизонтальный кадр")
                if abs(r["fill"] - med) > 0.15:
                    why.append(f"заполнение {r['fill']:.2f} против {med:.2f}")
                if r["ipd"] and ipd_med and abs(r["ipd"] / ipd_med - 1) > 0.15:
                    why.append(f"масштаб лица x{r['ipd'] / ipd_med:.2f}")
                if why:
                    bad += 1
                    print(f"  ✗ {r['key']:10s} {r['size']} — " + ", ".join(why))
    print(f"\nк пересъёмке: {bad}")
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if check(sys.argv[1] if len(sys.argv) > 1 else "dad") else 0)
