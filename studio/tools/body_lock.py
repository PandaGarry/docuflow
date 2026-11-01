"""Привязать корпус кадра к мастеру: одна и та же фигура на всех кадрах цикла.

    python studio/tools/body_lock.py dad walk-contact walk-down --dry
    python studio/tools/body_lock.py dad walk-contact walk-down

Зачем
-----
Генератор при смене позы перерисовывает и корпус: на одном кадре он полнее,
на другом худее. Заказчик видит это сразу — «где-то полный, где-то
накачанный».

Лечится не уговорами в промпте (они не работают), а композитом: берём кадр
целиком (ноги и руки в нужной фазе) и заменяем ТОЛЬКО середину корпуса —
грудь и живот — пикселями мастера. Кадр и мастер выровнены по голове и
масштабу, поэтому шов не виден: свитер — гладкая поверхность.

Маска с пером по краю, и она не доходит до силуэта: край силуэта остаётся
от кадра, иначе обрезка съела бы руку или ногу.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import characters as ch
import cutout
import poselib as pl

ROOT = HERE.parents[2]

# Середина корпуса в долях кадра мастера (профиль). Только грудь и живот:
# края силуэта, плечи, воротник и таз сюда не входят.
CORE = {
    "side": [(0.360, 0.310), (0.640, 0.310), (0.665, 0.420),
             (0.665, 0.555), (0.640, 0.605), (0.375, 0.605),
             (0.350, 0.555), (0.350, 0.420)],
}


def _prep(path: Path) -> Image.Image:
    return cutout.key_green(Image.open(path).convert("RGB"))


def _anchors(img: Image.Image) -> dict:
    return pl.anchors_body(img)


def align_to_master(key: Image.Image, master: Image.Image) -> Image.Image:
    """Привести кадр к масштабу мастера и поставить по голове."""
    ka, ma = _anchors(key), _anchors(master)
    if not ka or not ma:
        return key
    scale = ma["height_px"] / max(1.0, ka["height_px"])
    size = (max(2, int(round(key.width * scale))), max(2, int(round(key.height * scale))))
    resized = key.resize(size, Image.LANCZOS)
    canvas = Image.new("RGBA", master.size, (0, 0, 0, 0))
    dx = int(round(ma["head_cx"] - ka["head_cx"] * scale))
    dy = int(round(ma["head_cy"] - ka["head_cy"] * scale))
    canvas.alpha_composite(resized, (dx, dy))
    return canvas


def body_lock(key_path: Path, master_path: Path, view: str = "side",
              *, feather: int = 18) -> Image.Image:
    master = _prep(master_path)
    key = align_to_master(_prep(key_path), master)
    w, h = master.size
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon(
        [(x * w, y * h) for x, y in CORE[view]], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(feather))

    # Яркость мастера подгоняем под кадр: у кадров разное освещение, и без
    # этого на границе маски остаётся видимая полоса-шов.
    inner = mask.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(6))
    ka = np.asarray(key.convert("RGBA")).astype(np.float32)
    ma = np.asarray(master.convert("RGBA")).astype(np.float32)
    mi = np.asarray(inner).astype(np.float32) / 255.0
    sel = (mi > 0.5) & (ka[..., 3] > 200) & (ma[..., 3] > 200)
    if sel.any():
        dk = float(ka[..., :3][sel].mean())
        dm = float(ma[..., :3][sel].mean())
        if dm > 1.0:
            ma[..., :3] = np.clip(ma[..., :3] * (dk / dm), 0, 255)
    patch = Image.fromarray(ma.astype(np.uint8), "RGBA")
    out = key.copy()
    out.paste(patch, (0, 0), mask)
    return out


def main() -> int:
    key = sys.argv[1] if len(sys.argv) > 1 else "dad"
    dry = "--dry" in sys.argv
    names = [a for a in sys.argv[2:] if not a.startswith("--")]
    char = ch.CHARACTERS[key]
    master = char.dir / ch.VIEW_MASTERS["side"]
    if not names:
        names = [p.stem for p in sorted((char.dir / "poses").glob("walk-*.png"))] + \
                [p.stem for p in sorted((char.dir / "poses").glob("run-*.png"))]
    for name in names:
        p = char.dir / "poses" / f"{name}.png"
        if not p.exists():
            print(f"нет кадра {p}")
            continue
        res = body_lock(p, master)
        out = ROOT / "studio" / "out" / "body-lock" / f"{name}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        res.save(out)
        if not dry:
            # сохраняем на зелёном фоне: конвейер режет кадры по хромакею
            bg = Image.new("RGBA", res.size, (0, 177, 64, 255))
            Image.alpha_composite(bg, res).convert("RGB").save(p)
        print(f"{name}: {'проверка' if dry else 'привязан'} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
