"""Проверка кадров библиотеки поз: одна фигура, тот же персонаж, тот же формат.

    python studio/tools/pose_qa.py dad
    python studio/tools/pose_qa.py dad --write     # + studio/out/pose-qa.md

Считаем не «красоту», а сходимость: если между кадрами плывёт ширина корпуса
или доля головы, персонаж перестаёт быть одним человеком. Числа сравниваются с
мастером `master-front-v2.png` того же персонажа.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "engine"))

import numpy as np
from PIL import Image

from characters import CHARACTERS


def cutouts(path: Path):
    """Маска фигуры по зелёному фону (без полного хромакея — для замеров)."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    g, r, b = a[..., 1], a[..., 0], a[..., 2]
    bg = (g - r > 45) & (g - b > 45)
    return a, ~bg


def measure(path: Path) -> dict:
    a, body = cutouts(path)
    h, w = body.shape
    ys, xs = np.where(body)
    if len(ys) == 0:
        return {"file": path.name, "error": "пусто"}
    top, bot = int(ys.min()), int(ys.max())
    H = bot - top + 1
    # ширина корпуса на уровне груди (0.42 роста), без рук — берём центральный
    # непрерывный отрезок строки
    rows = {}
    for f in (0.15, 0.42, 0.66):
        y = top + int(f * H)
        row = np.where(body[y])[0]
        if len(row) == 0:
            rows[f] = 0.0
            continue
        gaps = np.where(np.diff(row) > 4)[0]
        segs, s = [], row[0]
        for g in gaps:
            segs.append((s, row[g]))
            s = row[g + 1]
        segs.append((s, row[-1]))
        mid = min(segs, key=lambda sg: abs((sg[0] + sg[1]) / 2 - w / 2))
        rows[f] = (mid[1] - mid[0]) / H
    return {
        "file": path.name,
        "H": H,
        "w_over_h": (xs.max() - xs.min()) / H,
        "head_w": rows[0.15],
        "chest_w": rows[0.42],
        "hip_w": rows[0.66],
        "touches_edge": bool(ys.min() < 3 or xs.min() < 3 or xs.max() > w - 4
                             or ys.max() > h - 4),
        "bg_ok": bool(((a[2, 2, 1] - a[2, 2, 0]) > 45) and
                      ((a[-3, -3, 1] - a[-3, -3, 0]) > 45)),
    }


def report(char_key: str, write: bool = False) -> str:
    char = CHARACTERS[char_key]
    master = char.dir / "master-front-v2.png"
    files = sorted([master] + list((char.dir / "poses").glob("*.png")))
    files = [f for f in files if f.exists()]
    if not files:
        return f"{char_key}: нет кадров"
    ref = measure(master) if master.exists() else None
    lines = [f"# QA кадров: {char.name} ({char_key})", "",
             "| кадр | H px | ΔH | ширина/H | голова | грудь | таз | фон | край |",
             "|---|---|---|---|---|---|---|---|---|"]
    for f in files:
        m = measure(f)
        if "error" in m:
            lines.append(f"| {m['file']} | — | — | — | — | — | — | ошибка |")
            continue
        flag = lambda ok: "ok" if ok else "!"
        dh = (m["H"] - ref["H"]) / ref["H"] if ref else 0.0
        lines.append(
            f"| {m['file']} | {m['H']} | {dh * 100:+.1f}% "
            f"| {m['w_over_h']:.2f} "
            f"| {m['head_w']:.3f} {flag(abs(m['head_w'] - ref['head_w']) < 0.012) if ref else ''} "
            f"| {m['chest_w']:.3f} | {m['hip_w']:.3f} "
            f"| {flag(m['bg_ok'])} | {flag(not m['touches_edge'])} |")
    text = "\n".join(lines)
    if write:
        out = HERE.parents[1] / "out" / "pose-qa.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    return text


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("укажи персонажа: dad / mom / son")
    print(report(sys.argv[1], "--write" in sys.argv))
