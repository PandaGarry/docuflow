"""Подгонка кадров лица к общему масштабу набора.

    python studio/tools/fit_portrait.py dad                 # только отчёт
    python studio/tools/fit_portrait.py dad --write          # привести к общему виду
    python studio/tools/fit_portrait.py dad --kind visemes --view side --write

Зачем: генератор отдаёт кадры разного размера и разного масштаба лица. Даже
когда ракурс верный, лицо может оказаться на 20–40 % крупнее соседей, и при
склейке мимика «прыгает». Портрет — это набор, где все кадры обязаны быть
одного масштаба.

Как приводим: каждый кадр вырезается по альфе, масштабируется так, чтобы
высота содержимого совпала с медианой набора, и ставится на холст 768×1400
с тем же положением верхней точки. Масштаб — по глазам, если разметка есть и
видны оба глаза: это точнее, чем высота содержимого (генератор может дать
кадр «по грудь» и «по плечи»).

Важно: подгонка лечит ТОЛЬКО масштаб похожего кадра. Если генератор отдал
другой ракурс или другую компоновку, подгонкой это не исправить — проверено
на виземах 3/4: автоподгонка по коже лица увеличила кадры в 1.3 раза и
сделала их крупнее базы. Правильный способ — генерировать визем по референсу
базового кадра (image-to-image), а не подгонять после.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

import characters as ch
import cutout
import facefx

ROOT = HERE.parents[2]
CANVAS = (768, 1400)


def metrics(char, kind: str, view: str, key: str) -> dict | None:
    path = char.dir / kind / view / f"{key}.png"
    if not path.exists():
        return None
    img = cutout.key_green(Image.open(path).convert("RGB"))
    bb = img.getbbox()
    if bb is None:
        return None
    ipd = None
    try:
        lm = facefx.load_landmarks(char.key, view)
        px = facefx.landmarks_px(lm, img)
        eyes = px.get("eyes") or []
        if len(eyes) >= 2:
            (x1, y1), (x2, y2) = eyes[0], eyes[1]
            ipd = float(np.hypot(x2 - x1, y2 - y1))
    except Exception:
        pass
    return {"path": path, "img": img, "bbox": bb, "ipd": ipd,
            "size": img.size, "key": key}


def fit_one(m: dict, *, target_h: float, target_top: float,
            target_ipd: float | None, write: bool) -> dict:
    bb = m["bbox"]
    chh = bb[3] - bb[1]
    scale = target_h / max(1.0, chh)
    if target_ipd and m["ipd"]:
        scale = target_ipd / m["ipd"]
    content = m["img"].crop(bb)
    nw = max(1, int(round(content.width * scale)))
    nh = max(1, int(round(content.height * scale)))
    content = content.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    x = (CANVAS[0] - nw) // 2
    canvas.alpha_composite(content, (max(0, x), int(round(target_top))))
    if write:
        out = Image.new("RGB", CANVAS, (0, 0, 0))
        # сохраняем зелёный фон: он нужен хромакею на следующих шагах
        bg = Image.new("RGB", CANVAS, ch.BG_HEX)
        out = Image.composite(canvas.convert("RGB"), bg, canvas.getchannel("A"))
        out.save(m["path"])
    return {"key": m["key"], "scale": scale, "size": m["size"],
            "ipd": m["ipd"]}


def run(char_key: str, *, kind: str | None, view: str | None, write: bool) -> int:
    char = {"dad": ch.DAD, "mom": ch.MOM, "son": ch.SON}[char_key]
    kinds = [kind] if kind else ["emotions", "visemes"]
    views = [view] if view else ["front", "three-quarter", "side"]
    for k in kinds:
        items = ch.EMOTIONS if k == "emotions" else ch.VISEMES
        for v in views:
            rows = [m for m in (metrics(char, k, v, key) for key in items) if m]
            if len(rows) < 2:
                continue
            hs = np.array([r["bbox"][3] - r["bbox"][1] for r in rows], float)
            tops = np.array([r["bbox"][1] for r in rows], float)
            ips = np.array([r["ipd"] for r in rows if r["ipd"]], float)
            target_h, target_top = float(np.median(hs)), float(np.median(tops))
            target_ipd = float(np.median(ips)) if len(ips) >= 2 else None
            print(f"\n{k}/{v}: {len(rows)} кадров, высота медиана {target_h:.0f}, "
                  f"верх {target_top:.0f}, ipd {target_ipd or 0:.1f}")
            for r in rows:
                info = fit_one(r, target_h=target_h, target_top=target_top,
                               target_ipd=target_ipd, write=write)
                dev = info["scale"] - 1
                mark = "  " if abs(dev) < 0.06 else "→ "
                print(f"{mark}{info['key']:10s} {info['size']} масштаб x{info['scale']:.2f}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("char", nargs="?", default="dad")
    ap.add_argument("--kind", choices=["emotions", "visemes"])
    ap.add_argument("--view", choices=["front", "three-quarter", "side"])
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    return run(a.char, kind=a.kind, view=a.view, write=a.write)


if __name__ == "__main__":
    raise SystemExit(main())
