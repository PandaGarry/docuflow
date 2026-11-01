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


_MICRO_PHASES: dict[int, tuple[float, float, float]] = {}


def _micro_phases(seed: int) -> tuple[float, float, float]:
    """Случайные фазы для микромимики — считаются один раз на seed.

    Раньше Random создавался на каждый кадр: 1350 кадров = 1350 объектов зря.
    """
    if seed not in _MICRO_PHASES:
        rnd = random.Random(seed * 7919 + 13)
        _MICRO_PHASES[seed] = (rnd.uniform(0, math.tau), rnd.uniform(0, math.tau),
                               rnd.uniform(0, math.tau))
    return _MICRO_PHASES[seed]


def micro_face(t: float, seed: int = 0, strength: float = 1.0) -> dict[str, float]:
    """Небольшие постоянные колебания: зрачки, брови, губы.

    Это не «дрожь»: амплитуды маленькие (2–4 %), зато лицо перестаёт выглядеть
    застывшим на крупном плане.
    """
    p1, p2, p3 = _micro_phases(seed)
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
    ровно заполняют её без щелей и наложений; иначе длительность считается по
    числу букв и скорости речи (а не по числу визем — так точнее).

    Гарантии (проверяются в selftest):
    * первый интервал начинается ровно в ``start``;
    * последний заканчивается ровно в ``start + duration``;
    * интервалы не пересекаются и не имеют щелей;
    * каждый интервал не короче ``min_hold`` (если это позволяет длительность).
    """
    from rig import visemes_for_text
    table = visemes()
    seq = [(v, w) for v, w in visemes_for_text(text) if v in table]
    if not seq:
        return []

    if duration is None:
        letters = sum(1 for ch in text if ch.isalpha())
        duration = max(letters / chars_per_sec, min_hold * len(seq))
    duration = max(duration, 1e-3)

    n = len(seq)
    total_w = sum(w for _, w in seq) or 1.0
    if duration <= min_hold * n:
        holds = [duration / n] * n                  # очень короткая реплика
    else:
        free = duration - min_hold * n
        holds = [min_hold + free * w / total_w for _, w in seq]

    spans: list[VisemeSpan] = []
    t = float(start)
    for (v, _w), hold in zip(seq, holds):
        spans.append(VisemeSpan(t, t + hold, v))
        t += hold
    # компенсация накопленной ошибки float — конец должен совпасть точно
    spans[-1].t1 = float(start) + duration
    return spans


class LipSync:
    """Готовая дорожка визем с поиском за O(log n) — для покадрового рендера."""

    def __init__(self, spans: Sequence[VisemeSpan] | None = None):
        self.spans: list[VisemeSpan] = sorted(spans or [], key=lambda s: s.t0)
        self._starts = [s.t0 for s in self.spans]
        self.start = self._starts[0] if self.spans else 0.0
        self.end = self.spans[-1].t1 if self.spans else 0.0

    @classmethod
    def from_text(cls, text: str, **kwargs) -> "LipSync":
        return cls(lip_sync(text, **kwargs))

    def at(self, t: float) -> tuple[str, float]:
        """(визема, вес) в момент t. Вес плавно спадает к краям интервала."""
        if not self.spans:
            return "M", 0.0
        import bisect
        i = bisect.bisect_right(self._starts, t) - 1
        if i < 0:
            return "M", 0.0
        s = self.spans[i]
        if t > s.t1:
            return "M", 0.0
        span = max(s.t1 - s.t0, 1e-6)
        edge = min((t - s.t0) / span, (s.t1 - t) / span)
        return s.viseme, min(1.0, 0.35 + edge * 1.4)

    def __len__(self) -> int:
        return len(self.spans)


def viseme_at(spans: Sequence[VisemeSpan], t: float) -> tuple[str, float]:
    """Визема и её вес в момент t (совместимость со старым API)."""
    if isinstance(spans, LipSync):
        return spans.at(t)
    return LipSync(spans).at(t)


def face_at(t: float,
            timeline: FaceTimeline | None = None,
            spans: "LipSync | Sequence[VisemeSpan] | None" = None,
            blink: float = 1.0,
            micro: float = 1.0,
            seed: int = 0) -> Face:
    """Итоговое лицо кадра: эмоция + липсинк + мигание + микромимика."""
    face = timeline.at(t) if timeline else Face.neutral()
    if spans:
        v, w = spans.at(t) if isinstance(spans, LipSync) else viseme_at(spans, t)
        if w > 0:
            face = face.with_viseme(v, w)
    face = face.with_blink(blink)
    if micro:
        face = face.add(micro_face(t, seed, micro))
    return face
