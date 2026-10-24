"""Генерация музыки и саунд-дизайна для ролика + микс с озвучкой.

Всё синтезируется программно (numpy) и привязано к timeline.py, поэтому
удары и переходы попадают точно в монтажные склейки.

Запуск:  python scripts/make_music.py
Результат: audio/music.wav, audio/mix.wav
"""

import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline as tl  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(HERE, "audio")
SR = 48000
N = int(tl.TOTAL * SR) + SR // 2
BPM = 100.0
BEAT = 60.0 / BPM


def ffmpeg_bin():
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


rng = np.random.default_rng(7)


# ---------------------------------------------------------------- утилиты
def t_axis():
    return np.arange(N) / SR


def note_hz(name):
    """'A2', 'C#4' -> частота."""
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
             "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    pitch, octave = name[:-1], int(name[-1])
    midi = 12 * (octave + 1) + names[pitch]
    return 440.0 * 2 ** ((midi - 69) / 12)


def place(buf, sig, at, gain=1.0):
    """Добавить сигнал в буфер с указанного времени (сек)."""
    i = int(round(at * SR))
    if i >= buf.shape[0]:
        return
    if i < 0:
        sig = sig[-i:]
        i = 0
    n = min(sig.shape[0], buf.shape[0] - i)
    if n <= 0:
        return
    buf[i:i + n] += sig[:n] * gain


def env_exp(n, decay_s, attack_s=0.002):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack_s, 1e-6), 0, 1)
    return a * np.exp(-t / decay_s)


def stereo(sig, pan=0.0):
    """pan: -1 (лево) .. 1 (право). Равномощное панорамирование."""
    ang = (pan + 1) * np.pi / 4
    return np.stack([sig * np.cos(ang), sig * np.sin(ang)], axis=-1)


def fft_filter(x, curve_fn, block=8192):
    """Фильтрация через спектральную маску (overlap-add, окно Ханна 50%)."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) == 0:
        return x
    block = max(256, 1 << int(np.ceil(np.log2(max(min(len(x), block), 256)))))
    win = np.hanning(block)
    freqs = np.fft.rfftfreq(block, 1 / SR)
    mask = curve_fn(freqs)
    out = np.zeros(len(x) + block)
    hop = block // 2
    for s in range(0, max(len(x), 1), hop):
        seg = x[s:s + block]
        if len(seg) < block:
            seg = np.pad(seg, (0, block - len(seg)))
        spec = np.fft.rfft(seg * win) * mask
        out[s:s + block] += np.fft.irfft(spec, block)
    return out[: len(x)]


def reverb(x, seconds=2.1, mix=0.22, seed=3):
    """Свёрточный реверб с синтетическим импульсным откликом."""
    r = np.random.default_rng(seed)
    n_ir = int(seconds * SR)
    t = np.arange(n_ir) / SR
    ir = r.normal(0, 1, n_ir) * np.exp(-t * (6.0 / seconds)) * 0.5
    ir = fft_filter(ir, lambda f: np.exp(-(f / 5200.0) ** 1.6) * (f > 90))
    ir[: int(0.006 * SR)] *= np.linspace(0, 1, int(0.006 * SR))
    size = 1 << int(np.ceil(np.log2(len(x) + n_ir)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    wet /= max(np.max(np.abs(wet)), 1e-9)
    return x * (1 - mix) + wet * mix * max(np.max(np.abs(x)), 1e-9) * 1.4


# ---------------------------------------------------------------- инструменты
def pad_chord(notes, dur, gain=1.0, bright=1.0):
    """Мягкий синтезаторный пэд из нескольких расстроенных голосов."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for nm in notes:
        f0 = note_hz(nm)
        for det in (-0.0025, 0.0, 0.0031):
            f = f0 * (1 + det)
            ph = 2 * np.pi * f * t + rng.uniform(0, 6.28)
            vib = 1 + 0.0015 * np.sin(2 * np.pi * 0.21 * t + rng.uniform(0, 6))
            sig += np.sin(ph * vib)
            sig += 0.34 * bright * np.sin(2 * ph) * 0.9
            sig += 0.16 * bright * np.sin(3 * ph)
            sig += 0.07 * bright * np.sin(4 * ph)
    sig /= len(notes) * 3.2
    a = np.clip(t / 0.9, 0, 1) ** 1.5
    rel = np.clip((dur - t) / 1.4, 0, 1) ** 1.4
    return sig * a * rel * gain


def pluck(freq, dur=1.1, gain=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t)
           + 0.12 * np.sin(6 * np.pi * freq * t))
    return sig * env_exp(n, 0.20, 0.004) * gain


def kick(gain=1.0, punch=1.0):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 118 * np.exp(-t * 26) + 46
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7.0)
    click = rng.normal(0, 1, n) * np.exp(-t * 220) * 0.25 * punch
    return np.tanh((body + click) * 1.6) * gain


def impact(gain=1.0, dur=2.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 74 * np.exp(-t * 3.2) + 32
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.1)
    boom = rng.normal(0, 1, n) * np.exp(-t * 12)
    boom = fft_filter(boom, lambda fr: (fr > 60) * (fr < 900) * np.exp(-(fr / 420.0)))
    return np.tanh(sub * 1.4 + boom / max(np.max(np.abs(boom)), 1e-9) * 0.30) * gain


def whoosh(dur=0.9, gain=1.0, up=True):
    n = int(dur * SR)
    noise = rng.normal(0, 1, n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 1.6
    seg = 480
    out = np.zeros(n)
    for i in range(0, n, seg):
        chunk = noise[i:i + seg]
        if len(chunk) == 0:
            continue
        prog = i / n
        fc = (380 + 5200 * (prog if up else 1 - prog))
        band = fft_filter(chunk, lambda f, fc=fc: np.exp(-((np.log((f + 1) / fc)) ** 2) / 0.42))
        out[i:i + seg] = band[: len(chunk)] * env[i:i + seg][: len(chunk)]
    return out / max(np.max(np.abs(out)), 1e-9) * gain


def riser(dur=4.8, gain=0.5):
    n = int(dur * SR)
    t = np.arange(n) / SR
    prog = t / dur
    noise = rng.normal(0, 1, n)
    fc = 500 + 9000 * prog ** 2
    seg = 2400
    out = np.zeros(n)
    for i in range(0, n, seg):
        chunk = noise[i:i + seg]
        f_here = float(fc[i])
        out[i:i + seg] = fft_filter(chunk, lambda f, c=f_here: (f > c * 0.4) * (f < c * 2.2))[: len(chunk)]
    sweep = np.sin(2 * np.pi * np.cumsum(180 + 900 * prog ** 2.4) / SR) * 0.25
    sig = out / max(np.max(np.abs(out)), 1e-9) + sweep
    return sig * (prog ** 2.2) * gain


def tick(gain=1.0):
    n = int(0.05 * SR)
    t = np.arange(n) / SR
    s = rng.normal(0, 1, n) * np.exp(-t * 160)
    s = fft_filter(s, lambda f: (f > 6000) * np.exp(-f / 16000.0))
    return s / max(np.max(np.abs(s)), 1e-9) * gain


# ---------------------------------------------------------------- аранжировка
def make_music():
    music = np.zeros((N, 2))

    # Гармония: Am – F – C – G, по 2 такта на аккорд
    prog = [
        (["A2", "E3", "A3", "C4", "E4"], 0),
        (["F2", "C3", "F3", "A3", "C4"], 1),
        (["C3", "G3", "C4", "E4", "G4"], 2),
        (["G2", "D3", "G3", "B3", "D4"], 3),
    ]
    bar = BEAT * 4
    n_bars = int(np.ceil(tl.TOTAL / bar)) + 1

    # --- Пэды
    for b in range(n_bars):
        notes, _ = prog[b % 4]
        start = b * bar
        bright = 0.5 if start < 5.4 else (0.85 if start > 21 else 0.7)
        level = 0.30 if start < 5.4 else 0.42
        if start > 38.2:
            level *= 0.85
        place(music, stereo(pad_chord(notes, bar + 1.2, level, bright), 0.0), start)

    # --- Воздушный слой (шум-пэд)
    t = t_axis()[:N]
    air = rng.normal(0, 1, N)
    air = fft_filter(air, lambda f: (f > 2500) * (f < 9000) * np.exp(-(f / 6500.0) ** 2))
    lfo = 0.55 + 0.45 * np.sin(2 * np.pi * 0.045 * t + 1.1)
    air = air / max(np.max(np.abs(air)), 1e-9) * lfo * 0.045
    music += np.stack([air, np.roll(air, 900)], axis=-1)[:N]

    # --- Арпеджио (появляется со 2-й сцены)
    step = BEAT / 4
    k = 0
    tm = 5.4
    while tm < 38.2:
        bar_i = int(tm // bar) % 4
        notes = prog[bar_i][0]
        nm = notes[[1, 3, 4, 2][k % 4] if len(notes) > 4 else 2]
        f = note_hz(nm) * (2 if k % 8 in (3, 6) else 1)
        lvl = 0.10 if tm < 15 else 0.13
        place(music, stereo(pluck(f, 0.9, lvl), pan=0.35 * np.sin(k * 0.7)), tm)
        tm += step
        k += 1

    # --- Ритм: кик с 5.4 с, тики с 15 с
    tm = 5.4
    i = 0
    while tm < 38.2:
        if i % 4 in (0, 2):
            place(music, stereo(kick(0.52, 0.7), 0.0), tm)
        tm += BEAT
        i += 1
    tm = 15.0
    i = 0
    while tm < 38.2:
        place(music, stereo(tick(0.05 if i % 2 else 0.075), 0.35 if i % 2 else -0.3), tm)
        tm += BEAT / 2
        i += 1

    # --- Импакты на склейках
    for hit in tl.HITS:
        place(music, stereo(impact(0.55), 0.0), hit - 0.02)

    # --- Whoosh-переходы
    for (a, b) in tl.WHOOSHES:
        w = whoosh(0.85, 0.30)
        place(music, stereo(w, -0.45), a)
        place(music, stereo(w, 0.45), a + 0.04)

    # --- Райзер перед финальной карточкой
    r = riser(tl.RISER[1] - tl.RISER[0], 0.42)
    place(music, stereo(r, 0.0), tl.RISER[0])
    place(music, stereo(whoosh(0.7, 0.28), 0.0), tl.RISER[1] - 0.25)
    place(music, stereo(impact(0.75, 2.8), 0.0), tl.RISER[1])

    # --- Реверб на музыкальную шину
    music = np.stack([reverb(music[:, 0], 2.0, 0.20, seed=11),
                      reverb(music[:, 1], 2.0, 0.20, seed=12)], axis=-1)

    # Фейды
    fade_in = int(0.35 * SR)
    music[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    t_end = int(1.9 * SR)
    fade = np.linspace(1, 0, t_end) ** 0.8
    music[-t_end:] *= fade[:, None]
    return music


# ---------------------------------------------------------------- озвучка
def read_wav_mono_stereo(path):
    """Чтение WAV без внешних зависимостей (через ffmpeg -> float32 raw)."""
    raw = subprocess.run(
        [ffmpeg_bin(), "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", "2", "-ar", str(SR), "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).astype(np.float64)


def make_mix(music):
    voice = np.zeros((N, 2))
    spans = []
    for item in tl.VO:
        path = os.path.join(AUDIO, item["file"])
        wav = os.path.join(AUDIO, "_vo_tmp.wav")
        subprocess.run(
            [ffmpeg_bin(), "-y", "-v", "error", "-i", path, "-ac", "2", "-ar", str(SR),
             "-af", "highpass=f=80,lowpass=f=15000,treble=g=2.0:width_type=q:w=0.6,"
                    "acompressor=threshold=-18dB:ratio=2.6:attack=6:release=160:makeup=3",
             wav], check=True)
        sig = read_wav_mono_stereo(wav)
        sig /= max(np.max(np.abs(sig)), 1e-9)
        sig *= 0.62
        place(voice, sig, item["start"])
        spans.append((item["start"], item["start"] + len(sig) / SR))
        os.remove(wav)

    # лёгкий реверб на голос для «студийности»
    voice = np.stack([reverb(voice[:, 0], 1.4, 0.09, seed=21),
                      reverb(voice[:, 1], 1.4, 0.09, seed=22)], axis=-1)

    # Дакинг музыки под голос
    duck = np.ones(N)
    for (a, b) in spans:
        i0, i1 = int(a * SR), int(min(b, tl.TOTAL) * SR)
        ramp = int(0.28 * SR)
        env = np.ones(i1 - i0) * 0.42
        if i0 - ramp > 0:
            env[:ramp] = np.linspace(1, 0.42, ramp)
        tail = min(ramp, N - i1)
        if tail > 0:
            env[-tail:] = np.linspace(0.42, 1, tail)
        duck[i0:i1] = np.minimum(duck[i0:i1], env)

    mix = music * duck[:, None] + voice * 1.05

    # мастер: мягкая сатурация + нормализация
    mix = np.tanh(mix * 1.12) * 0.92
    peak = np.max(np.abs(mix))
    mix *= 0.89 / max(peak, 1e-9)
    return mix, spans


def write_wav(path, data):
    data = np.clip(data, -1, 1).astype("<f4")
    subprocess.run(
        [ffmpeg_bin(), "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2",
         "-i", "-", "-c:a", "pcm_s16le", path],
        input=data.tobytes(), check=True)


def main():
    os.makedirs(AUDIO, exist_ok=True)
    print("• синтез музыки и саунд-дизайна…")
    music = make_music()
    write_wav(os.path.join(AUDIO, "music.wav"), music)
    print("• микс с озвучкой…")
    mix, spans = make_mix(music)
    write_wav(os.path.join(AUDIO, "mix.wav"), mix)
    for a, b in spans:
        print(f"  голос: {a:5.2f}–{b:5.2f} с")
    print(f"✓ audio/music.wav, audio/mix.wav  ({tl.TOTAL:.1f} с)")


if __name__ == "__main__":
    main()
