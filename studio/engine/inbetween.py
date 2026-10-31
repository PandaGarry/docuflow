"""Промежуточные кадры между ключами: оптический поток, а не подмена картинки.

Зачем
-----
Ключевые кадры нарисованы через фазу: контакт → down → пронос. Между ними
пусто, поэтому движение идёт рывками по 5–8 кадров. Раньше «плавность»
имитировалась сдвигом всего спрайта — это и выглядело как пульсация.

Правильный путь — in-between: кадр, которого нет в библиотеке, но который
лежит между двумя ключами. Рисовать его генератором нельзя (лицо и одежда
поплывут заново), поэтому он СЧИТАЕТСЯ:

1. между ключами A и B считается плотное поле смещений (Farneback flow);
2. A сдвигается вперёд на t·flow(A→B), B — назад на (1−t)·flow(B→A);
3. два результата смешиваются с весами (1−t) и t.

Так получается кадр, где нога уже пошла вперёд, но ещё не пришла, — то есть
ровно то, что рисует аниматор между ключами.

Ограничения (честно):
- на тонких деталях (пальцы, шнурки) возможен лёгкий смаз;
- при сильном перекрытии одной части тела другой поток «не видит» закрытую
  часть и тянет её неправильно — для циклов шага/бега это редкий случай;
- альфа интерполируется отдельно, иначе по краю появится кайма.
"""

from __future__ import annotations

import numpy as np
import cv2
from PIL import Image


def _premultiply(rgba: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = rgba[..., 3:4].astype(np.float32) / 255.0  # (h, w, 1)
    rgb = rgba[..., :3].astype(np.float32) * a
    return rgb, a


def _flow(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Поле смещений src → dst по яркости."""
    g1 = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    g2 = cv2.cvtColor(dst, cv2.COLOR_BGR2GRAY)
    return cv2.calcOpticalFlowFarneback(
        g1, g2, None,
        pyr_scale=0.5, levels=4, winsize=21,
        iterations=5, poly_n=7, poly_sigma=1.5, flags=0,
    )


def _warp(img: np.ndarray, flow: np.ndarray, scale: float) -> np.ndarray:
    """Сдвинуть img по полю flow·scale (обратное отображение)."""
    h, w = flow.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xx + flow[..., 0] * scale
    map_y = yy + flow[..., 1] * scale
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


def blend(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """Кадр между a и b: t=0 → a, t=1 → b."""
    t = float(np.clip(t, 0.0, 1.0))
    if t <= 0.001:
        return a.copy()
    if t >= 0.999:
        return b.copy()
    if a.size != b.size:
        raise ValueError(f"кадры разного размера: {a.size} и {b.size}")

    A = np.asarray(a.convert("RGBA"))
    B = np.asarray(b.convert("RGBA"))
    # работаем по цвету на непрозрачных пикселях, альфу ведём отдельно
    flow_ab = _flow(A[..., :3], B[..., :3])
    flow_ba = _flow(B[..., :3], A[..., :3])

    rgb_a, alpha_a = _premultiply(A)
    rgb_b, alpha_b = _premultiply(B)
    alpha_a = alpha_a[..., 0]
    alpha_b = alpha_b[..., 0]

    rgb_a_w = _warp(rgb_a, flow_ab, t)
    rgb_b_w = _warp(rgb_b, flow_ba, 1.0 - t)
    alpha_a_w = _warp(alpha_a, flow_ab, t)
    alpha_b_w = _warp(alpha_b, flow_ba, 1.0 - t)

    # Одно направление, без смешивания двух картинок.
    #
    # Смешивание «A вперёд + B назад» на несогласованных рисунках даёт
    # ДВОЙНИКА: две позы видно одновременно. Поэтому берём цвет только из A,
    # а геометрию тянем к B на долю t: получается один силуэт в промежуточной
    # позе. Для t>0.5 берём B как источник текстуры — так мелкие детали
    # (складки, шнурки) не размазываются на полпути.
    if t <= 0.5:
        rgb = rgb_a_w
        alpha = alpha_a_w
    else:
        rgb = rgb_b_w
        alpha = alpha_b_w
    alpha = np.clip(alpha, 0.0, 1.0)

    # обратно из premultiplied
    denom = np.maximum(alpha, 1e-4)[..., None]
    rgb = np.where(alpha[..., None] > 1e-4, rgb / denom, 0.0)
    out = np.dstack([np.clip(rgb, 0, 255), alpha * 255.0]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def chain(frames: list[Image.Image], sub: int = 1) -> list[Image.Image]:
    """Развернуть список ключей в ленту с `sub` промежуточными кадрами."""
    if sub <= 0:
        return list(frames)
    out: list[Image.Image] = []
    n = len(frames)
    for i in range(n):
        a, b = frames[i], frames[(i + 1) % n]
        out.append(a)
        for k in range(1, sub + 1):
            out.append(blend(a, b, k / (sub + 1)))
    return out
