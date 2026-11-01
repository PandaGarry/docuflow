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


def _gray(rgba: np.ndarray) -> np.ndarray:
    """Седина по цвету БЕЗ фона: прозрачные пиксели не должны давать контраст
    на краю силуэта, иначе поток цепляется за хромакей."""
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    rgb = np.clip(rgba[..., :3].astype(np.float32) * a, 0, 255).astype(np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)


def _flow(src_gray: np.ndarray, dst_gray: np.ndarray) -> np.ndarray:
    """Плотное поле смещений src → dst.

    DIS (Dense Inverse Search) вместо Farneback: на одежде с мелкой складкой
    он держит край рукава и шнурки, а Farneback размазывал их в кашу.
    """
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    dis.setUseSpatialPropagation(True)
    return dis.calc(src_gray, dst_gray, None)


def _sample(field: np.ndarray, at: np.ndarray) -> np.ndarray:
    """Взять значения поля field в точках at (x, y) — с линейной подмешкой."""
    h, w = field.shape[:2]
    grid_x = np.clip(at[..., 0], 0, w - 1).astype(np.float32)
    grid_y = np.clip(at[..., 1], 0, h - 1).astype(np.float32)
    x0 = np.floor(grid_x).astype(np.int32)
    y0 = np.floor(grid_y).astype(np.int32)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    fx = (grid_x - x0)[..., None]
    fy = (grid_y - y0)[..., None]
    v00 = field[y0, x0]
    v10 = field[y0, x1]
    v01 = field[y1, x0]
    v11 = field[y1, x1]
    return (v00 * (1 - fx) * (1 - fy) + v10 * fx * (1 - fy) +
            v01 * (1 - fx) * fy + v11 * fx * fy)


def _warp(img: np.ndarray, flow: np.ndarray, scale: float) -> np.ndarray:
    """Сдвинуть img по полю flow·scale (обратное отображение)."""
    h, w = flow.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xx + flow[..., 0] * scale
    map_y = yy + flow[..., 1] * scale
    return cv2.remap(img, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


def _visibility(flow_ab: np.ndarray, flow_ba: np.ndarray) -> np.ndarray:
    """Карта видимости пикселей A в кадре B.

    Проверка «туда-обратно»: если смещение A→B и обратное смещение из той же
    точки не гасят друг друга, пиксель в B закрыт другой частью тела — его
    нельзя тащить в промежуточный кадр, иначе получится двойник.
    """
    h, w = flow_ab.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    at = np.dstack([xx + flow_ab[..., 0], yy + flow_ab[..., 1]])
    back = _sample(flow_ba, at)
    err = np.linalg.norm(flow_ab + back, axis=2)
    return np.exp(-err / 2.0)


def blend(a: Image.Image, b: Image.Image, t: float) -> Image.Image:
    """Кадр между a и b: t=0 → a, t=1 → b.

    Считается симметрично и с учётом перекрытий, а не «до половины из A, после
    из B»: рывок ровно на t=0.5 (подмена источника текстуры) был виден в
    движении как щелчок. Здесь оба кадра сдвигаются навстречу, а вклад каждого
    определяется видимостью пикселя, поэтому силуэт один и переход ровный.
    """
    t = float(np.clip(t, 0.0, 1.0))
    if t <= 0.001:
        return a.copy()
    if t >= 0.999:
        return b.copy()
    if a.size != b.size:
        raise ValueError(f"кадры разного размера: {a.size} и {b.size}")

    A = np.asarray(a.convert("RGBA"))
    B = np.asarray(b.convert("RGBA"))
    g_a, g_b = _gray(A), _gray(B)
    flow_ab = _flow(g_a, g_b)
    flow_ba = _flow(g_b, g_a)
    vis_a = _visibility(flow_ab, flow_ba)
    vis_b = _visibility(flow_ba, flow_ab)

    rgb_a, alpha_a = _premultiply(A)
    rgb_b, alpha_b = _premultiply(B)
    alpha_a, alpha_b = alpha_a[..., 0], alpha_b[..., 0]

    rgb_a_w = _warp(rgb_a, flow_ab, t)
    rgb_b_w = _warp(rgb_b, flow_ba, 1.0 - t)
    alpha_a_w = _warp(alpha_a, flow_ab, t)
    alpha_b_w = _warp(alpha_b, flow_ba, 1.0 - t)
    vis_a_w = _warp(vis_a, flow_ab, t)
    vis_b_w = _warp(vis_b, flow_ba, 1.0 - t)

    # Вес по видимости, но с полом: на ровной ткани поток «неуверен», и
    # чистый вес по видимости выбивал в силуэте дыры (чёрные пятна).
    # Видимость только сдвигает вклад, но никогда не обнуляет его.
    vis_a_w = 0.25 + 0.75 * vis_a_w
    vis_b_w = 0.25 + 0.75 * vis_b_w
    wa = (1.0 - t) * vis_a_w * alpha_a_w
    wb = t * vis_b_w * alpha_b_w
    total = wa + wb
    norm = np.maximum(total, 1e-3)
    wa = wa / norm
    wb = wb / norm
    rgb = rgb_a_w * wa[..., None] + rgb_b_w * wb[..., None]
    alpha = alpha_a_w * wa + alpha_b_w * wb
    # где оба кадра пусты — просто максимум альфы (край силуэта)
    empty = total <= 1e-3
    alpha = np.where(empty, np.maximum(alpha_a_w, alpha_b_w), alpha)
    rgb = np.where(empty[..., None], np.maximum(rgb_a_w, rgb_b_w), rgb)
    alpha = np.clip(alpha, 0.0, 1.0)

    denom = np.maximum(alpha, 2e-3)[..., None]
    rgb = np.where(alpha[..., None] > 2e-3, rgb / denom, 0.0)
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
