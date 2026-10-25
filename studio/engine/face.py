"""Лицо как параметры, а не как картинка.

Зачем: перегенерировать арт на каждое выражение — дорого и ломает идентичность.
Поэтому лицо — это 19 числовых параметров (брови, веки, зрачки, рот, румянец…).
Из них собираются любые эмоции, липсинк и микромимика, а рисуются они процедурно
(`puppet.py`) или используются как ТЗ для арт-генерации («брови нахмурены,
рот приоткрыт»).

Модуль не зависит от PIL — только математика и библиотека эмоций.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from library import expression as _expression
from library import expression_params, viseme_params, visemes

# порядок важен для читаемых diff'ов и отрисовки
PARAMS: tuple[str, ...] = (
    "brow_raise", "brow_angle", "brow_pinch",
    "eye_open", "squint", "lid", "pupil", "look_x", "look_y",
    "mouth_open", "mouth_wide", "smile", "mouth_skew", "teeth", "tongue",
    "cheek_raise", "blush", "sweat", "tears", "nose_wrinkle",
)

# значения по умолчанию (нейтральное лицо)
DEFAULTS: dict[str, float] = {
    "brow_raise": 0.0, "brow_angle": 0.0, "brow_pinch": 0.0,
    "eye_open": 1.0, "squint": 0.0, "lid": 0.0, "pupil": 1.0,
    "look_x": 0.0, "look_y": 0.0,
    "mouth_open": 0.0, "mouth_wide": 0.0, "smile": 0.0, "mouth_skew": 0.0,
    "teeth": 0.0, "tongue": 0.0,
    "cheek_raise": 0.0, "blush": 0.0, "sweat": 0.0, "tears": 0.0,
    "nose_wrinkle": 0.0,
}

# параметры, которые перекрывает визема (рот говорит — эмоция уступает)
MOUTH_PARAMS = ("mouth_open", "mouth_wide", "smile", "mouth_skew", "teeth", "tongue")


def _clamp_param(name: str, value: float) -> float:
    spec = _PARAM_SPEC.get(name)
    if spec is None:
        return float(value)
    return float(min(max(value, spec["min"]), spec["max"]))


_PARAM_SPEC: dict[str, dict] = {}


def _ensure_spec() -> dict[str, dict]:
    if not _PARAM_SPEC:
        _PARAM_SPEC.update(expression_params())
    return _PARAM_SPEC


def clamp_params(values: dict[str, float]) -> dict[str, float]:
    _ensure_spec()
    out = {}
    for k, v in values.items():
        if k in DEFAULTS:
            out[k] = _clamp_param(k, v)
    return out


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


@dataclass
class Face:
    """Набор параметров лица. Иммутабелен по смыслу: все методы возвращают копию."""

    params: dict[str, float] = field(default_factory=lambda: dict(DEFAULTS))

    # --- создание -------------------------------------------------------- #
    @classmethod
    def neutral(cls) -> "Face":
        return cls(dict(DEFAULTS))

    @classmethod
    def from_expression(cls, expr_id: str | None) -> "Face":
        if not expr_id or expr_id in ("neutral", "none"):
            return cls.neutral()
        f = cls(dict(DEFAULTS))
        f.params.update(clamp_params(_expression(expr_id)))
        return f

    @classmethod
    def from_dict(cls, values: dict[str, float] | None) -> "Face":
        f = cls(dict(DEFAULTS))
        if values:
            f.params.update(clamp_params(values))
        return f

    # --- доступ ---------------------------------------------------------- #
    def __getitem__(self, name: str) -> float:
        return self.params.get(name, DEFAULTS.get(name, 0.0))

    def __setitem__(self, name: str, value: float) -> None:
        if name not in DEFAULTS:
            raise KeyError(f"нет параметра лица '{name}'")
        self.params[name] = _clamp_param(name, value)

    def get(self, name: str, default: float = 0.0) -> float:
        return self.params.get(name, default)

    def copy(self) -> "Face":
        return Face(dict(self.params))

    def to_dict(self) -> dict[str, float]:
        return dict(self.params)

    # --- изменение ------------------------------------------------------- #
    def set(self, **kwargs: float) -> "Face":
        out = self.copy()
        for k, v in kwargs.items():
            out[k] = v
        return out

    def add(self, values: dict[str, float], weight: float = 1.0) -> "Face":
        out = self.copy()
        for k, v in values.items():
            if k in DEFAULTS:
                out[k] = out[k] + v * weight
        return out

    def blend(self, other: "Face", k: float) -> "Face":
        """Смешать два лица: k=0 — self, k=1 — other."""
        k = min(max(k, 0.0), 1.0)
        out = self.copy()
        for name in DEFAULTS:
            out.params[name] = _clamp_param(name, lerp(self[name], other[name], k))
        return out

    def with_viseme(self, v: str, weight: float = 1.0) -> "Face":
        """Наложить визему: рот говорит, остальное выражение сохраняется."""
        target = viseme_params(v)
        if not target:
            return self.copy()
        out = self.copy()
        for name, value in target.items():
            if name in DEFAULTS:
                out.params[name] = _clamp_param(name, lerp(out[name], value, weight))
        return out

    def with_blink(self, amount: float) -> "Face":
        """amount: 1 — глаза открыты, 0 — закрыты."""
        out = self.copy()
        out.params["eye_open"] = _clamp_param("eye_open", out["eye_open"] * max(amount, 0.0))
        return out

    def talk_boost(self, open_ratio: float) -> "Face":
        """Слегка раздвинуть губы в такт громкости (для энергичной речи)."""
        out = self.copy()
        out.params["mouth_open"] = _clamp_param(
            "mouth_open", out["mouth_open"] + 0.25 * open_ratio)
        return out


# --------------------------------------------------------------------------- #
# таймлайн эмоций
# --------------------------------------------------------------------------- #


@dataclass
class FaceKey:
    t: float
    face: Face
    ease: str = "ease"


def _ease(name: str, k: float) -> float:
    from rig import EASINGS
    return EASINGS.get(name, lambda x: x)(k)


class FaceTimeline:
    """Ключи эмоций по времени. `.at(t)` возвращает смешанное лицо."""

    def __init__(self, keys: Sequence[FaceKey] | None = None, ease: str = "ease"):
        self.ease = ease
        self.keys: list[FaceKey] = sorted(keys or [], key=lambda k: k.t)

    @classmethod
    def from_expressions(cls, points: Iterable[tuple[float, str]], ease: str = "ease") -> "FaceTimeline":
        return cls([FaceKey(t, Face.from_expression(e), ease) for t, e in points])

    def add(self, t: float, expr_id: str | Face, ease: str = "ease") -> "FaceTimeline":
        face = expr_id if isinstance(expr_id, Face) else Face.from_expression(expr_id)
        self.keys.append(FaceKey(t, face, ease))
        self.keys.sort(key=lambda k: k.t)
        return self

    def at(self, t: float) -> Face:
        if not self.keys:
            return Face.neutral()
        if t <= self.keys[0].t:
            return self.keys[0].face.copy()
        if t >= self.keys[-1].t:
            return self.keys[-1].face.copy()
        for k0, k1 in zip(self.keys, self.keys[1:]):
            if k0.t <= t <= k1.t:
                span = max(k1.t - k0.t, 1e-6)
                k = _ease(k1.ease, (t - k0.t) / span)
                return k0.face.blend(k1.face, k)
        return self.keys[-1].face.copy()


# --------------------------------------------------------------------------- #
# микро-мимика: чтобы лицо не было «маской»
# --------------------------------------------------------------------------- #


def micro_face(t: float, seed: int = 0, strength: float = 1.0) -> dict[str, float]:
    """Небольшие постоянные колебания: зрачки, брови, губы.

    Это не «дрожь»: амплитуды маленькие (2–4 %), зато лицо перестаёт выглядеть
    застывшим на крупном плане.
    """
    rnd = random.Random(seed * 7919 + 13)
    p1, p2, p3 = (rnd.uniform(0, math.tau) for _ in range(3))
    s = strength
    return {
        "look_x": 0.06 * s * math.sin(t * 0.9 + p1) + 0.02 * s * math.sin(t * 2.7 + p2),
        "look_y": 0.04 * s * math.sin(t * 0.6 + p2),
        "brow_raise": 0.05 * s * math.sin(t * 0.5 + p3),
        "smile": 0.04 * s * math.sin(t * 0.7 + p1),
        "pupil": 1.0 + 0.03 * s * math.sin(t * 1.3 + p3),
    }


# --------------------------------------------------------------------------- #
# липсинк
# --------------------------------------------------------------------------- #


@dataclass
class VisemeSpan:
    t0: float
    t1: float
    viseme: str
    weight: float = 1.0


def lip_sync(text: str,
             start: float = 0.0,
             duration: float | None = None,
             chars_per_sec: float = 13.0,
             min_hold: float = 0.055) -> list[VisemeSpan]:
    """Разложить реплику на виземы по времени.

    Длительность важнее «правильной» фонетики: если известна длина аудио, виземы
    растягиваются на неё, иначе считаются по скорости речи.
    """
    from rig import visemes_for_text
    seq = [(v, w) for v, w in visemes_for_text(text) if v in visemes()]
    if not seq:
        return []
    total_w = sum(w for _, w in seq)
    if duration is None:
        duration = max(len(seq) / chars_per_sec, min_hold * len(seq))
    spans: list[VisemeSpan] = []
    t = start
    for v, w in seq:
        dt = max(duration * w / total_w, min_hold)
        spans.append(VisemeSpan(t, t + dt, v))
        t += dt
    # подгоняем конец ровно под duration
    shift = (start + duration) - (spans[-1].t1 if spans else start + duration)
    if abs(shift) > 1e-6 and spans:
        k = duration / max(spans[-1].t1 - start, 1e-6)
        for s in spans:
            s.t0 = start + (s.t0 - start) * k
            s.t1 = start + (s.t1 - start) * k
    return spans


def viseme_at(spans: Sequence[VisemeSpan], t: float) -> tuple[str, float]:
    """Визема и её вес в момент t (вес плавно спадает к концу — нет «судороги»)."""
    for s in spans:
        if s.t0 <= t <= s.t1:
            span = max(s.t1 - s.t0, 1e-6)
            edge = min((t - s.t0) / span, (s.t1 - t) / span)
            return s.viseme, min(1.0, 0.35 + edge * 1.4)
    return "M", 0.0


def face_at(t: float,
            timeline: FaceTimeline | None = None,
            spans: Sequence[VisemeSpan] | None = None,
            blink: float = 1.0,
            micro: float = 1.0,
            seed: int = 0) -> Face:
    """Итоговое лицо кадра: эмоция + липсинк + мигание + микромимика."""
    face = timeline.at(t) if timeline else Face.neutral()
    if spans:
        v, w = viseme_at(spans, t)
        if w > 0:
            face = face.with_viseme(v, w)
    face = face.with_blink(blink)
    if micro:
        face = face.add(micro_face(t, seed, micro))
    return face
