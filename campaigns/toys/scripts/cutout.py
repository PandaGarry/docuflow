"""Вырезание персонажей/игрушек по зелёному фону (chroma key).

На входе — PNG на плоском зелёном фоне (#00B140), на выходе — RGBA с
обрезанными полями, мягкой кромкой и подавлением зелёного ореола (despill).

Запуск: python scripts/cutout.py [источник...]
"""

import glob
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "assets", "raw")
OUT = os.path.join(HERE, "assets", "chars")


def chroma_key(path):
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    # зелёный фон: заметное превосходство G над R и B
    green_dom = g - np.maximum(r, b)
    mask = (green_dom > 0.10) & (g > 0.22)

    alpha = np.where(mask, 0.0, 1.0)
    # мягкая кромка
    a_img = Image.fromarray((alpha * 255).astype(np.uint8))
    a_img = a_img.filter(ImageFilter.MinFilter(3))          # убрать остатки фона
    a_img = a_img.filter(ImageFilter.GaussianBlur(1.2))     # сгладить
    a = np.asarray(a_img, dtype=np.float32) / 255.0
    # вернуть плотность внутри фигуры
    a = np.clip((a - 0.18) / 0.82, 0, 1)
    a = np.where(a > 0.55, 1.0, a)

    # despill: на кромке подмешиваем нейтральный цвет вместо зелёного
    edge = (a > 0.02) & (a < 0.98)
    spill = np.clip(g - np.maximum(r, b), 0, 1)
    g_out = g.copy()
    g_out[edge] = g[edge] - spill[edge] * 0.9
    g_out = np.clip(g_out, 0, 1)

    rgba = np.dstack([r, g_out, b, a])
    out = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")

    # обрезка прозрачных полей
    bbox = out.split()[3].point(lambda v: 255 if v > 8 else 0).getbbox()
    if bbox:
        out = out.crop(bbox)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    paths = sys.argv[1:] or sorted(glob.glob(os.path.join(RAW, "*.png")))
    for p in paths:
        res = chroma_key(p)
        dst = os.path.join(OUT, os.path.splitext(os.path.basename(p))[0] + ".png")
        res.save(dst)
        print(f"  {os.path.basename(p)} -> {os.path.basename(dst)} {res.size}")


if __name__ == "__main__":
    main()
