"""Скульптурное тело: одна непрерывная поверхность из скалярного поля.

Почему отдельный модуль
-----------------------
`body3d` собирает тело из труб и эллипсоидов: рукав, торс, таз — отдельные
оболочки. Любой стык в такой схеме — компромисс: либо щель, либо наложение,
либо «эполеты» на плечах и «зазубрины» на кромке худи.

Здесь тело — ОДНА функция расстояния. Худи, джинсы, рукава, складки —
слагаемые одного поля; границы между ними физически не существует, потому что
нет границ, есть только гладкие объединения и вычитания. Складки ткани тоже
часть поля (`sdf.waves_around`, `sdf.wrinkles`), поэтому они «живут» на
поверхности, а не приклеены к вершинам.

Что здесь собирается
--------------------
* `hoodie_field`  — торс + рукава одним полем (сборка ткани у локтя, манжета);
* `jeans_field`   — таз + штанины одним полем (складки у колена, кромка снизу);
* `body_fields`   — обе оболочки разом, с общими границами;
* `build_sculpt`  — меши из полей + голова/кисти/стопы из `body3d`.

Геометрия берётся из тех же суставов, что и у трубной сборки: поза меняется —
меняется и поле.
"""

from __future__ import annotations

import numpy as np

import body3d as B
import render3d as R3
import sdf as S


# --------------------------------------------------------------------------- #
# профили
# --------------------------------------------------------------------------- #

def _hoodie_profile(p: B.Proportions) -> list[tuple[float, float, float, float]]:
    """Сечения худи в метрах: (y, rx, rz, cz) — корпус БЕЗ плеч.

    Анатомия, а не «труба»: корпус взрослого мужчины ≈ 0.36 м шириной, а полная
    ширина плеч ≈ 0.53 м получается за счёт дельтовидной части, которую даёт
    рукав. Если корпус сделать шириной с плечи, руки утопают в торсе и силуэт
    превращается в мешок — на этом я и споткнулся.
    """
    H = p.height
    hh = p.head_frac * H * p.head_w          # ширина головы, м
    w = hh / 0.82                            # «модуль» ширины (голова/0.82)
    belly = p.belly
    prof = [
        # (y,                   полуширина,  полуглубина,            cz)
        (p.hip_y - 0.055, 0.620 * w, 0.395 * w * 1.06, -0.004),
        (p.hip_y - 0.035, 0.612 * w, 0.392 * w * 1.05, -0.006),
        (p.hip_y - 0.010, 0.602 * w, 0.385 * w, -0.010),
        (p.hip_y + 0.020, 0.592 * w, 0.368 * w, -0.008),
        (p.hip_y + 0.080, 0.580 * w, 0.368 * w * belly, 0.010 * belly),
        (p.hip_y + 0.130, 0.572 * w, 0.362 * w * belly, 0.008 * belly),
        (p.hip_y + 0.180, 0.570 * w, 0.360 * w, 0.004),
        (p.shoulder_y - 0.060, 0.552 * w, 0.350 * w, 0.000),
        (p.shoulder_y - 0.010, 0.520 * w, 0.338 * w, 0.000),
        (p.shoulder_y + 0.010, 0.428 * w, 0.298 * w, -0.004),
        (p.shoulder_y + 0.026, 0.296 * w, 0.228 * w, -0.007),
        (p.shoulder_y + 0.046, 0.148 * w, 0.128 * w, -0.009),
    ]
    return [(y * H, rx, rz, cz) for (y, rx, rz, cz) in prof]


def _jeans_profile(p: B.Proportions) -> list[tuple[float, float, float, float]]:
    """Таз джинсов: (y, rx, rz, cz) в метрах — сжатый, чтобы пояс прятался."""
    H = p.height
    hh = p.head_frac
    hip_y = p.hip_y * H
    # Таз джинсов намеренно уже подола худи: если он глубже/шире подола,
    # джинсы пробивают кромку и в подоле появляются тёмные «вырезы».
    rows = [(p.hip_y - 0.175, 0.052, 0.034, -0.002),
            (p.hip_y - 0.135, 0.074, 0.044, -0.002),
            (p.hip_y - 0.075, 0.084, 0.049, -0.003),
            (p.hip_y - 0.015, 0.086, 0.051, -0.004),
            (p.hip_y + 0.050, 0.080, 0.047, -0.002)]
    return [(y * H, rx * H, rz * H, cz * H) for (y, rx, rz, cz) in rows]


def _ell(y, rx, ry, rz, cz=0.0, cx=0.0):
    """Эллипсоид с центром (cx, y, cz) и полуосями (rx, ry, rz)."""
    c = np.array([cx, y, cz], np.float64)
    r = np.array([rx, ry, rz], np.float64)
    return lambda P: ((np.linalg.norm((np.asarray(P) - c) / r, axis=-1) - 1.0)
                      * float(r.min()))


# --------------------------------------------------------------------------- #
# поля одежды
# --------------------------------------------------------------------------- #

def hoodie_field(p: B.Proportions, joints: dict | None = None,
                 with_sleeves: bool = True, folds: bool = True) -> "callable":
    """Худи: торс и рукава — одно поле, без шва на плече."""
    H = p.height
    prof = _hoodie_profile(p)
    body_half = max(row[1] for row in prof)
    body = S.loft(prof, power=1.25, round_cap=0.016 * H)

    # подол — резинка: то же сечение, чуть шире, с мягкой кромкой
    y0, rx0, rz0, cz0 = prof[0]
    # резинка подола: почти без расширения — «колоколом» она читается как юбка
    hem = S.loft([(y0 - 0.002 * H, rx0 * 1.004, rz0 * 1.004, cz0),
                  (y0 + 0.038 * H, rx0 * 1.002, rz0 * 1.002, cz0)],
                 power=1.25, round_cap=0.010 * H)
    body = S.smooth_union(body, hem, k=0.012 * H)

    y_top, rx_t, rz_t, cz_t = prof[-1]

    # капюшон: лежит на спине «полумесяцем» по линии плеч. Ширина берётся от
    # полуширины КОРПУСА, а не от радиуса ворота: на радиусе ворота капюшон
    # получается узким «плавником» посередине спины.
    y_h = (p.shoulder_y + 0.004) * H
    for t, share in ((-0.66, 0.46), (0.0, 0.62), (0.66, 0.46)):
        body = S.smooth_union(
            body,
            _ell(y_h - abs(t) * 0.012 * H, share * body_half, 0.046 * H, 0.036 * H,
                 cx=t * body_half * 0.52, cz=cz_t - 0.052 * H),
            k=0.030)

    # ворот: плотное кольцо у шеи
    collar = S.torus((0, (p.shoulder_y + 0.028) * H, cz_t),
                     major=0.62 * rx_t, minor=0.019 * H, axis=1)
    body = S.smooth_union(body, collar, k=0.012 * H)

    if folds:
        # мягкие складки ткани: длинная волна вдоль корпуса, без «стиральной доски»
        body = S.wrinkles(body, (0, (p.hip_y + 0.01) * H, 0),
                          (0, (p.hip_y + 0.30) * H, 0), 0.0011,
                          freq=(3.5, 2.2), seed=11)

    if with_sleeves and joints is not None:
        for side in ("L", "R"):
            body = S.smooth_union(body, _sleeve_field(p, joints, side, folds=folds),
                                  k=0.030)
    return body


def _sleeve_field(p: B.Proportions, joints: dict, side: str, *,
                  folds: bool = True):
    """Рукав: плавная цепочка плечо → локоть → запястье.

    Узлов много и радиус убывает монотонно: на 4–5 узлах каждый стык читается
    «сарделькой», на семи со сглаживанием — уже гладкая рука.
    """
    H = p.height
    sgn = 1.0 if side == "L" else -1.0
    sh = np.asarray(joints[f"shoulder.{side}"], np.float64)
    el = np.asarray(joints[f"elbow.{side}"], np.float64)
    wr = np.asarray(joints[f"wrist.{side}"], np.float64)
    out = np.array([sgn * 0.016 * H, 0.0, 0.0])   # смещение рукава наружу
    # Рукав начинается ВНУТРИ корпуса (у оси тела) и выходит наружу: тогда его
    # торец нигде не виден. Раньше он начинался снаружи, и торец торчал из
    # плеча плоской «доской» — особенно в позах с махом руки.
    # старт ниже и ближе к оси: скруглённый торец должен утонуть внутри торса,
    # иначе над плечом появляется «бугор» от его сферы
    inner = np.array([sgn * 0.018 * H, sh[1] - 0.105 * H, 0.0])
    pts = [inner, sh + out, sh + (el - sh) * 0.30 + out,
           sh + (el - sh) * 0.62 + out, el + out,
           el + (wr - el) * 0.45 + out, wr + out - (wr - el) * 0.10,
           wr + out - (wr - el) * 0.19]
    ts = np.array([0.00, 0.22, 0.38, 0.52, 0.66, 0.80, 0.90, 1.00])
    rad = 0.0520 * H * p.bulk * (1.0 - 0.26 * ts ** 0.9)
    rad[0] = 0.040 * H * p.bulk          # тонкий «корень» рукава в глубине торса
    f = S.sweep(pts, rad)

    if folds:
        # сборка ткани у локтя: одна-две едва заметные складки. Заметные
        # кольца превращали рукав в «гусеницу» — ткани нужно меньше, не больше.
        f = S.waves_around(f, el - (wr - el) * 0.20, wr + (wr - el) * 0.02,
                           n=2, amp=0.0007 * p.bulk, taper=(0.35, 0.9))
        # манжета
        axis = (wr - el) / max(np.linalg.norm(wr - el), 1e-9)
        cuff_a = wr + out - axis * 0.030 * H
        f = S.smooth_union(f, S.chain([cuff_a, wr + out - axis * 0.012 * H],
                                      [0.029 * H * p.bulk, 0.027 * H * p.bulk],
                                      k=0.006), k=0.008)
        f = S.wrinkles(f, inner, wr + out - (wr - el) * 0.06, 0.0004 * p.bulk, freq=(3.0, 2.0),
                       seed=7 + int(sgn))
    return f


def jeans_field(p: B.Proportions, joints: dict | None = None, *,
                folds: bool = True) -> "callable":
    """Джинсы: таз и штанины одним полем, складки у колена и у кромки."""
    H = p.height
    f = S.loft(_jeans_profile(p), power=2.2, round_cap=0.010 * H)

    if joints is not None:
        for side in ("L", "R"):
            sgn = 1.0 if side == "L" else -1.0
            hip = np.asarray(joints[f"hip.{side}"], np.float64)
            kn = np.asarray(joints[f"knee.{side}"], np.float64)
            an = np.asarray(joints[f"ankle.{side}"], np.float64)
            start = hip - (hip - kn) * 0.34
            pts = [start, hip, hip + (kn - hip) * 0.5, kn,
                   kn + (an - kn) * 0.5, an + (an - kn) * 0.04]
            # сверху нога тоньше: подол худи должен перекрывать её с запасом,
            # иначе бедро пробивает кромку и в подоле появляются «дыры»
            rad = np.array([0.031, 0.040, 0.043, 0.044, 0.036, 0.035]) * H * p.bulk
            leg = S.sweep(pts, rad)
            if folds:
                leg = S.waves_around(leg, kn - (kn - hip) * 0.15,
                                     kn + (an - kn) * 0.45,
                                     n=5, amp=0.0030 * p.bulk, taper=(0.05, 0.9))
                leg = S.wrinkles(leg, start, an, 0.0007 * p.bulk,
                                 freq=(4.0, 2.5), seed=13 + int(sgn))
            f = S.smooth_union(f, leg, k=0.030)
    return f


def body_fields(p: B.Proportions, joints: dict | None = None, *,
                hoodie: bool = True, jeans: bool = True,
                folds: bool = True) -> dict:
    """Поля частей тела: {'hoodie': field, 'jeans': field}."""
    out = {}
    if hoodie:
        out["hoodie"] = hoodie_field(p, joints, folds=folds)
    if jeans:
        out["jeans"] = jeans_field(p, joints, folds=folds)
    return out


# --------------------------------------------------------------------------- #
# сборка мешей
# --------------------------------------------------------------------------- #

def _bounds(field, center, radius, res=44):
    return S.auto_bounds(field, center, radius, res=res)


def build_sculpt(p: B.Proportions, colors: dict, joints: dict, *,
                 cell: float = 0.006, folds: bool = True,
                 verbose: bool = False) -> list[R3.Mesh]:
    """Собрать скульптурное тело: худи + джинсы (голова и конечности — снаружи).

    `cell` — шаг сетки в метрах: мельче 5 мм складки уже не читаются, крупнее
    8 мм начинает «мылить» силуэт. 6 мм — рабочий компромисс для стилла.
    """
    H = p.height
    meshes: list[R3.Mesh] = []
    fields = body_fields(p, joints, folds=folds)

    for name, field in fields.items():
        lo, hi = _bounds(field, (0, H * 0.55, 0), H * 1.05)
        res = np.maximum(np.ceil((hi - lo) / cell).astype(int) + 1, 8)
        color = colors["top"] if name == "hoodie" else colors["bottom"]
        rough = 0.96 if name == "hoodie" else 0.98
        meshes.append(S.mesh_from_sdf(field, lo, hi, res, color=color,
                                      rough=rough, name=name, verbose=verbose,
                                      ao_radius=3.2))
    return meshes


def sculpt_character(char, pose=None, *, cell: float = 0.006,
                     folds: bool = True, verbose: bool = False) -> list[R3.Mesh]:
    """Полный персонаж: SDF-тело + голова, кисти, стопы, капюшон из `body3d`.

    Голова и кисти остаются мешами: череп не гнётся и не «течёт», а на лице
    нужна мелкая детализация, которой на сетке 6 мм не бывает.
    """
    import rig3d as RIG

    pose = pose or RIG.Pose()
    fk = RIG.forward_kinematics(char.skel, pose)
    joints = char._joints(fk)
    rots = char._rots(fk)
    colors = char.colors
    p = char.p

    out = build_sculpt(p, colors, joints, cell=cell, folds=folds, verbose=verbose)

    # капюшон и шнурки уже в поле: старые меши имеют прежние пропорции и
    # торчат из нового силуэта (шнурок читался белой петлёй на спине)
    for m in char.torso:
        if m.name in ():
            out.append(m)
    # шея
    out.append(char._neck(joints))
    # голова — жёстко на кости
    rest_head = char.skel.bones["head"].head
    for m in char.head:
        from character import rigid
        out.append(rigid(m, rest_head, fk["head"]["head"], fk["head"]["rot"]))
    # кисти и стопы — из трубной сборки (они мелкие и жёсткие)
    import body3d as BB
    limbs = BB.limb_parts(p, colors, joints, rots)
    for m in limbs:
        if m.name in ("hand", "finger", "thumb", "shoe", "sole", "lace"):
            out.append(m)
    return out
