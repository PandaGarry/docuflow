"""Звук студии: фоновая музыка и сборка mp4 со звуком.

Зачем свой синтез, а не стоковые треки
--------------------------------------
Музыка должна быть **своей** (лицензии, Content ID на Shorts) и ровно нужной
длины — под монтаж, а не «нарезать по вкусу». Поэтому трек синтезируется:
аккорды, бас, перкуссия и мелодия считаются numpy, экспортируются в WAV 48 кГц.

Правила громкости — как у платформ: `loudnorm I=-14 LUFS, TP=-1.5 dBTP`.
Это то же значение, что в `docs/10-AUDIO.md`, поэтому ролик не «прыгает» по
громкости относительно других.

Команды
-------
    python studio/engine/audio.py bed --seconds 20 --out studio/out/bed.wav
    python studio/engine/audio.py mux --video v.mp4 --audio bed.wav --out final.mp4
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
OUT = os.path.join(STUDIO, "out")

SR = 48_000

# C-мажор: I–V–vi–IV — «добрый» оборот, который не приедается в 20-секундном ролике
CHORDS = {
    "C": (0, (261.63, 329.63, 392.00), 130.81),
    "G": (0, (246.94, 293.66, 392.00), 98.00),
    "Am": (0, (220.00, 261.63, 329.63), 110.00),
    "F": (0, (174.61, 220.00, 261.63), 87.31),
}
PROGRESSION = ("C", "G", "Am", "F")


# --------------------------------------------------------------------------- #
# инструменты
# --------------------------------------------------------------------------- #


def _env_exp(n: int, decay: float) -> np.ndarray:
    return np.exp(-np.arange(n) / SR * decay)


def pluck(freq: float, dur: float, amp: float = 0.25) -> np.ndarray:
    """Щипковый слой: основной тон + октава + квинта, экспоненциальный спад."""
    n = max(int(dur * SR), 1)
    t = np.arange(n) / SR
    w = (np.sin(2 * math.pi * freq * t)
         + 0.35 * np.sin(4 * math.pi * freq * t)
         + 0.14 * np.sin(6 * math.pi * freq * t))
    attack = np.clip(t / 0.008, 0, 1)          # 8 мс атаки — без щелчка
    return amp * w * _env_exp(n, 5.5) * attack


def bass(freq: float, dur: float, amp: float = 0.34) -> np.ndarray:
    n = max(int(dur * SR), 1)
    t = np.arange(n) / SR
    w = np.sin(2 * math.pi * freq * t) + 0.22 * np.sin(4 * math.pi * freq * t)
    return amp * w * _env_exp(n, 2.2) * np.clip(t / 0.01, 0, 1)


def kick(amp: float = 0.55) -> np.ndarray:
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    freq = 130 * np.exp(-t * 28) + 44
    w = np.sin(2 * math.pi * np.cumsum(freq) / SR)
    return amp * w * _env_exp(n, 16)


def shaker(amp: float = 0.10) -> np.ndarray:
    n = int(0.05 * SR)
    rng = np.random.default_rng(4)
    noise = rng.standard_normal(n)
    noise = np.diff(np.concatenate([[0.0], noise]))      # грубый high-pass
    return amp * noise * _env_exp(n, 60)


def clap(amp: float = 0.22) -> np.ndarray:
    n = int(0.12 * SR)
    rng = np.random.default_rng(9)
    noise = rng.standard_normal(n)
    env = _env_exp(n, 22) * (1 + 0.6 * np.exp(-np.arange(n) / SR * 60))
    return amp * noise * env


def _add(buf: np.ndarray, clip: np.ndarray, at: float) -> None:
    i = int(at * SR)
    if i >= buf.size:
        return
    end = min(i + clip.size, buf.size)
    buf[i:end] += clip[:end - i]


# --------------------------------------------------------------------------- #
# трек
# --------------------------------------------------------------------------- #


def make_bed(seconds: float = 20.0, bpm: float = 112.0, *, seed: int = 7,
             fade_out: float = 1.6) -> np.ndarray:
    """Фоновая музыка ровно `seconds` секунд (моно, float32 в -1..1)."""
    beat = 60.0 / bpm
    bar = beat * 4
    total = int(seconds * SR)
    mix = np.zeros(total, dtype=np.float64)

    bars = int(math.ceil(seconds / bar))
    for b in range(bars):
        t0 = b * bar
        name = PROGRESSION[b % len(PROGRESSION)]
        _, tones, root = CHORDS[name]

        # бас: 1 и 3 доля
        _add(mix, bass(root, beat * 1.4), t0)
        _add(mix, bass(root, beat * 1.2), t0 + beat * 2)

        # арпеджио восьмыми
        for i in range(8):
            note = tones[i % len(tones)]
            acc = 0.16 if i % 4 == 0 else 0.11
            _add(mix, pluck(note, beat * 0.9, acc), t0 + i * beat / 2)

        # мелодия: короткий мотив во второй половине каждого второго такта
        if b % 2 == 1:
            motif = (tones[2], tones[1], tones[0], tones[1])
            for i, note in enumerate(motif):
                _add(mix, pluck(note * 2, beat * 0.6, 0.13), t0 + beat * (i * 0.75))

        # перкуссия
        _add(mix, kick(), t0)
        _add(mix, kick(0.42), t0 + beat * 2)
        _add(mix, clap(), t0 + beat)
        _add(mix, clap(), t0 + beat * 3)
        for i in range(8):
            _add(mix, shaker(0.08 if i % 2 else 0.05), t0 + i * beat / 2)

    # мягкое начало и затухание в конце
    fade_in = int(0.35 * SR)
    mix[:fade_in] *= np.linspace(0, 1, fade_in)
    out_n = int(max(fade_out, 0) * SR)
    if out_n > 1:
        mix[-out_n:] *= np.linspace(1, 0, out_n)

    # нормализация с запасом и мягкий лимитер вместо клиппинга
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * 1.25
    mix = np.tanh(mix * 1.1) * 0.82
    return mix.astype(np.float32)


def write_wav(path: str, mono: np.ndarray, *, width: float = 0.35) -> str:
    """WAV 48 кГц, стерео: правый канал чуть тише/с задержкой (Хаас) — шире по панораме."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    delay = int(0.011 * SR)
    left = mono
    right = np.concatenate([np.zeros(delay, dtype=mono.dtype), mono[:-delay]]) * (1 - width)
    stereo = np.stack([left, right], axis=1)
    pcm = np.clip(stereo, -1, 1)
    pcm = (pcm * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    return path


def mux(video: str, audio: str, out: str, *, offset: float = 0.0,
        gain_db: float = 0.0, loudnorm: bool = True) -> str:
    """Подложить звук в видео: AAC 192k, нормализация -14 LUFS, faststart."""
    from imageio_ffmpeg import get_ffmpeg_exe

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    filters = []
    if offset:
        filters.append(f"adelay={int(offset * 1000)}|{int(offset * 1000)}")
    if gain_db:
        filters.append(f"volume={gain_db}dB")
    if loudnorm:
        filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    cmd = [get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
           "-i", video, "-i", audio,
           "-map", "0:v:0", "-map", "1:a:0",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR),
           "-af", ",".join(filters) if filters else "anull",
           "-shortest", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)
    return out


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _cmd_bed(args) -> None:
    mono = make_bed(args.seconds, args.bpm, seed=args.seed)
    path = args.out or os.path.join(OUT, "bed.wav")
    write_wav(path, mono)
    print(f"✓ {path} · {args.seconds:.1f} с · {args.bpm:.0f} BPM · {len(mono) / SR:.2f} с звука")


def _cmd_mux(args) -> None:
    out = args.out or args.video.replace(".mp4", "-audio.mp4")
    mux(args.video, args.audio, out, offset=args.offset, gain_db=args.gain)
    print("✓", out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="музыка и звук студии")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("bed")
    p.add_argument("--seconds", type=float, default=20.0)
    p.add_argument("--bpm", type=float, default=112.0)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", default=None)
    p.set_defaults(func=_cmd_bed)

    p = sub.add_parser("mux")
    p.add_argument("--video", required=True)
    p.add_argument("--audio", required=True)
    p.add_argument("--out", default=None)
    p.add_argument("--offset", type=float, default=0.0)
    p.add_argument("--gain", type=float, default=0.0)
    p.set_defaults(func=_cmd_mux)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
