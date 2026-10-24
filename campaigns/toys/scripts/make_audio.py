"""Музыка и комикс-саунд-дизайн для мультика «Уборка» (numpy, без сэмплов).

Музыка: весёлая укулеле-тема (пиццикато + бас + шейкер + клэпы) в C-dur.
Эффекты: pop, конфетти, скретч, хлопок двери, сверчок, стинг, boing, whoosh,
искры. Всё синхронизировано с timeline.py.

Запуск: python scripts/make_audio.py  ->  audio/music.wav, audio/mix.wav
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
BPM = 112.0
BEAT = 60.0 / BPM
BAR = BEAT * 4
rng = np.random.default_rng(11)


# ------------------------------------------------------------------ утилиты
def place(buf, sig, at, gain=1.0):
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
    return np.clip(t / max(attack_s, 1e-6), 0, 1) * np.exp(-t / decay_s)


def stereo(sig, pan=0.0):
    ang = (pan + 1) * np.pi / 4
    return np.stack([sig * np.cos(ang), sig * np.sin(ang)], axis=-1)


def fft_filter(x, curve_fn, block=4096):
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
        out[s:s + block] += np.fft.irfft(np.fft.rfft(seg * win) * mask, block)
    return out[: len(x)]


def reverb(x, seconds=1.5, mix=0.16, seed=3):
    r = np.random.default_rng(seed)
    n_ir = int(seconds * SR)
    t = np.arange(n_ir) / SR
    ir = r.normal(0, 1, n_ir) * np.exp(-t * (6.0 / seconds)) * 0.5
    ir = fft_filter(ir, lambda f: np.exp(-(f / 6000.0) ** 1.6) * (f > 120))
    size = 1 << int(np.ceil(np.log2(len(x) + n_ir)))
    wet = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    wet /= max(np.max(np.abs(wet)), 1e-9)
    return x * (1 - mix) + wet * mix * max(np.max(np.abs(x)), 1e-9) * 1.3


def note_hz(name):
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
             "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    pitch, octave = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((12 * (octave + 1) + names[pitch] - 69) / 12)


# ------------------------------------------------------------------ инструменты
def uke(freq, dur=0.5, gain=1.0, bright=0.7, decay=0.16):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for k, amp in ((1, 1.0), (2, 0.42 * bright), (3, 0.26 * bright), (4, 0.14 * bright),
                   (5, 0.07 * bright)):
        sig += amp * np.sin(2 * np.pi * freq * k * t + rng.uniform(0, 6.28))
    sig *= env_exp(n, decay, 0.003)
    click = rng.normal(0, 1, n) * np.exp(-t * 300) * 0.12
    return (sig + click) * gain / 2.1


def bass(freq, dur=0.6, gain=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.sin(2 * np.pi * freq * t) + 0.32 * np.sin(4 * np.pi * freq * t)
    return sig * env_exp(n, 0.28, 0.006) * gain * 0.55


def shaker(gain=1.0):
    n = int(0.08 * SR)
    s = rng.normal(0, 1, n) * env_exp(n, 0.022, 0.002)
    s = fft_filter(s, lambda f: (f > 3800) * np.exp(-((np.log((f + 1) / 8200)) ** 2) / 0.5))
    s /= max(np.max(np.abs(s)), 1e-9)
    return s * gain


def clap(gain=1.0):
    n = int(0.18 * SR)
    s = rng.normal(0, 1, n)
    envs = np.zeros(n)
    for off in (0.0, 0.011, 0.023):
        i = int(off * SR)
        envs[i:] += np.exp(-(np.arange(n - i) / SR) * 42) * (1.0 - off * 12)
    s = s * envs
    s = fft_filter(s, lambda f: (f > 900) * (f < 6500) * np.exp(-((f / 2600.0) ** 2)))
    s /= max(np.max(np.abs(s)), 1e-9)
    return s * gain * 0.5


# ------------------------------------------------------------------ эффекты
def sfx_pop(gain=1.0):
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = 480 + 900 * np.exp(-t * 26)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 22)
    return s * gain * 0.7


def sfx_confetti(gain=1.0):
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    noise = rng.normal(0, 1, n) * np.exp(-t * 6) * 0.5
    noise = fft_filter(noise, lambda f: np.exp(-((np.log((f + 1) / 4200)) ** 2) / 0.7))
    chime = np.zeros(n)
    for i, nm in enumerate(["C6", "E6", "G6", "B6"]):
        st = int(i * 0.075 * SR)
        seg = np.arange(n - st) / SR
        chime[st:] += np.sin(2 * np.pi * note_hz(nm) * seg) * np.exp(-seg * 7) * 0.30
    s = noise / max(np.max(np.abs(noise)), 1e-9) + chime
    return s * gain * 0.55


def sfx_scratch(gain=1.0):
    """Винтажный скретч пластинки: быстрый свип шума вниз + торможение тона."""
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    noise = rng.normal(0, 1, n)
    seg = 900
    out = np.zeros(n)
    for i in range(0, n, seg):
        prog = i / n
        fc = 6000 * (1 - prog) ** 1.6 + 320
        chunk = noise[i:i + seg]
        out[i:i + seg] = fft_filter(chunk, lambda f, c=fc: np.exp(
            -((np.log((f + 1) / c)) ** 2) / 0.35))[: len(chunk)]
    out /= max(np.max(np.abs(out)), 1e-9)
    tone = np.sin(2 * np.pi * np.cumsum(420 * (1 - t / 0.42) ** 2) / SR) * 0.35
    env = np.sin(np.linspace(0, np.pi, n)) ** 0.6
    return (out * 0.8 + tone) * env * gain


def sfx_slam(gain=1.0, soft=False):
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    f = (120 if soft else 150) * np.exp(-t * 12) + 42
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * (3.0 if soft else 4.5))
    crack = rng.normal(0, 1, n) * np.exp(-t * (70 if soft else 40))
    crack = fft_filter(crack, lambda fr: (fr > 300) * (fr < 4200) * np.exp(-(fr / 1800.0)))
    crack /= max(np.max(np.abs(crack)), 1e-9)
    return np.tanh((body * 1.3 + crack * 0.5) * 1.4) * gain


def sfx_cricket(gain=1.0):
    """Сверчки: три коротких чириканья в высоком регистре."""
    n = int(1.3 * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for start in (0.02, 0.30, 0.58, 0.86):
        i = int(start * SR)
        seg = np.arange(n - i) / SR
        chirp = np.sin(2 * np.pi * 4300 * seg + 6 * np.sin(2 * np.pi * 60 * seg))
        env = np.exp(-seg * 34) * (np.sin(np.pi * np.clip(seg / 0.12, 0, 1)) ** 0.5)
        s[i:] += chirp * env * 0.5
    s = fft_filter(s, lambda f: (f > 2500) * (f < 7000))
    s /= max(np.max(np.abs(s)), 1e-9)
    return s * gain * 0.5


def sfx_sting(gain=1.0):
    """Короткий «драматический» аккорд для появления мамы."""
    n = int(1.4 * SR)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for nm in ["A2", "E3", "A3", "C4"]:
        f = note_hz(nm)
        s += np.sin(2 * np.pi * f * t) * (1.0 + 0.3 * np.sin(2 * np.pi * 5.5 * t))
    s *= env_exp(n, 0.45, 0.01)
    s /= max(np.max(np.abs(s)), 1e-9)
    return s * gain * 0.6


def sfx_boing(gain=1.0):
    n = int(0.7 * SR)
    t = np.arange(n) / SR
    f = 180 + 260 * np.sin(2 * np.pi * 3.2 * t) * np.exp(-t * 4)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.4)
    s += 0.25 * np.sin(2 * np.pi * np.cumsum(f * 2.02) / SR) * np.exp(-t * 6)
    return s * gain * 0.55


def sfx_whoosh(gain=1.0, dur=0.6, up=True):
    n = int(dur * SR)
    noise = rng.normal(0, 1, n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 1.4
    seg = 600
    out = np.zeros(n)
    for i in range(0, n, seg):
        prog = i / n
        fc = 500 + 4200 * (prog if up else 1 - prog)
        chunk = noise[i:i + seg]
        out[i:i + seg] = fft_filter(chunk, lambda f, c=fc: np.exp(
            -((np.log((f + 1) / c)) ** 2) / 0.5))[: len(chunk)]
    return out / max(np.max(np.abs(out)), 1e-9) * env * gain


def sfx_sparkle(gain=1.0):
    n = int(0.8 * SR)
    s = np.zeros(n)
    for i, nm in enumerate(["C6", "G6", "E7", "B7"]):
        st = int(i * 0.06 * SR)
        seg = np.arange(n - st) / SR
        s[st:] += np.sin(2 * np.pi * note_hz(nm) * seg) * np.exp(-seg * 9) * 0.4
    return s * gain


SFX = {
    "pop": lambda g: sfx_pop(g),
    "confetti": lambda g: sfx_confetti(g),
    "scratch": lambda g: sfx_scratch(g),
    "slam": lambda g: sfx_slam(g),
    "slam_soft": lambda g: sfx_slam(g, soft=True),
    "cricket": lambda g: sfx_cricket(g),
    "sting": lambda g: sfx_sting(g),
    "boing": lambda g: sfx_boing(g),
    "whoosh": lambda g: sfx_whoosh(g),
    "sparkle": lambda g: sfx_sparkle(g),
}


# ------------------------------------------------------------------ музыка
PROG = [  # такт: (аккорд для укулеле, бас)
    (["C4", "E4", "G4", "C5"], "C3"),
    (["G3", "B3", "D4", "G4"], "G2"),
    (["A3", "C4", "E4", "A4"], "A2"),
    (["F3", "A3", "C4", "F4"], "F2"),
]


def intensity_at(t):
    for a, b, v in tl.MUSIC:
        if a <= t < b:
            return v
    return 0.0


def make_music():
    out = np.zeros((N, 2))
    n_bars = int(np.ceil(tl.TOTAL / BAR)) + 1
    for bar_i in range(n_bars):
        t0 = bar_i * BAR
        chord, bass_note = PROG[bar_i % 4]
        lvl = intensity_at(t0 + 0.2)
        if lvl <= 0:
            continue
        # пиццикато-перебор: 8 восьмых с рисунком
        pattern = [0, 2, 1, 3, 0, 2, 1, 3]
        for k, idx in enumerate(pattern):
            t_note = t0 + k * BEAT / 2
            if intensity_at(t_note) <= 0:
                continue
            nm = chord[idx % len(chord)]
            hz = note_hz(nm)
            g = (0.30 if k % 2 == 0 else 0.22) * lvl
            place(out, stereo(uke(hz, 0.5, g, bright=0.75), pan=-0.35 + 0.7 * (idx / 3)),
                  t_note)
        # бас на 1 и 3
        for k, beat in enumerate((0, 2)):
            t_note = t0 + beat * BEAT
            if intensity_at(t_note) <= 0:
                continue
            place(out, stereo(bass(note_hz(bass_note), 0.7, 0.55 * lvl), 0.0), t_note)
        # шейкер
        for k in range(8):
            t_note = t0 + k * BEAT / 2
            if intensity_at(t_note) < 0.4:
                continue
            place(out, stereo(shaker(0.10 * lvl), pan=0.35 if k % 2 else -0.25), t_note)
        # клэпы во «взрослых» секциях
        if lvl >= 0.8:
            for beat in (1, 3):
                t_note = t0 + beat * BEAT
                if intensity_at(t_note) >= 0.8:
                    place(out, stereo(clap(0.5 * lvl), -0.1), t_note)

    # глиссандо перед финалом
    place(out, stereo(sfx_whoosh(0.25, 0.9, up=True), 0.0), 30.1)
    out = np.stack([reverb(out[:, 0], 1.5, 0.15, 5), reverb(out[:, 1], 1.5, 0.15, 6)],
                   axis=-1)
    # мягкие фейды на паузах
    for a, b, v in tl.MUSIC:
        if v == 0:
            i0, i1 = int(a * SR), int(b * SR)
            fade = int(0.03 * SR)
            out[max(0, i0 - fade):i0] *= np.linspace(1, 0.02, min(fade, i0))[:, None]
            out[i0:i1] *= 0.02
    fade_in = int(0.12 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    t_end = int(1.2 * SR)
    out[-t_end:] *= (np.linspace(1, 0, t_end) ** 1.2)[:, None]
    return out


# ------------------------------------------------------------------ микс
def read_wav(path):
    raw = subprocess.run(
        [ffmpeg_bin(), "-v", "error", "-i", path, "-f", "f32le", "-acodec", "pcm_f32le",
         "-ac", "2", "-ar", str(SR), "-"], check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype="<f4").reshape(-1, 2).astype(np.float64)


def ffmpeg_bin():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def write_wav(path, data):
    data = np.clip(data, -1, 1).astype("<f4")
    subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-f", "f32le", "-ar", str(SR),
                    "-ac", "2", "-i", "-", "-c:a", "pcm_s16le", path],
                   input=data.tobytes(), check=True)


def make_mix(music):
    voice = np.zeros((N, 2))
    spans = []
    for item in tl.VO:
        src = os.path.join(AUDIO, item["file"])
        tmp = os.path.join(AUDIO, "_vo_tmp.wav")
        # детский голос — чуть выше и звонче, мамин — теплее и ниже
        if item["who"] == "kid":
            af = ("asetrate=24000*1.07,aresample=48000,atempo=0.945,"
                  "highpass=f=140,treble=g=2.0:width_type=q:w=0.7,"
                  "acompressor=threshold=-18dB:ratio=2.5:attack=5:release=120:makeup=3")
        else:
            af = ("asetrate=24000*0.97,aresample=48000,atempo=1.031,"
                  "highpass=f=110,treble=g=1.2:width_type=q:w=0.7,"
                  "acompressor=threshold=-18dB:ratio=2.2:attack=8:release=160:makeup=3")
        subprocess.run([ffmpeg_bin(), "-y", "-v", "error", "-i", src, "-ac", "2",
                        "-ar", str(SR), "-af", af, tmp], check=True)
        sig = read_wav(tmp)
        peak = max(np.max(np.abs(sig)), 1e-9)
        sig = sig / peak * 0.72
        place(voice, sig, item["start"])
        spans.append((item["start"], item["start"] + len(sig) / SR))
        os.remove(tmp)

    voice = np.stack([reverb(voice[:, 0], 1.1, 0.07, 21),
                      reverb(voice[:, 1], 1.1, 0.07, 22)], axis=-1)

    duck = np.ones(N)
    for a, b in spans:
        i0, i1 = int(a * SR), int(min(b, tl.TOTAL) * SR)
        ramp = int(0.22 * SR)
        env = np.ones(i1 - i0) * 0.40
        if i0 - ramp > 0:
            env[:ramp] = np.linspace(1, 0.40, ramp)
        tail = min(ramp, N - i1)
        if tail > 0:
            env[-tail:] = np.linspace(0.40, 1, tail)
        duck[i0:i1] = np.minimum(duck[i0:i1], env)

    mix = music * duck[:, None] * 0.95 + voice * 1.15
    mix = np.tanh(mix * 1.1) * 0.94
    mix *= 0.89 / max(np.max(np.abs(mix)), 1e-9)
    return mix, spans


def main():
    os.makedirs(AUDIO, exist_ok=True)
    print("• музыка…")
    music = make_music()
    write_wav(os.path.join(AUDIO, "music.wav"), music)

    print("• эффекты…")
    sfx_bus = np.zeros((N, 2))
    gains = {"pop": 0.55, "confetti": 0.75, "scratch": 0.8, "slam": 0.95,
             "slam_soft": 0.7, "cricket": 0.55, "sting": 0.7, "boing": 0.6,
             "whoosh": 0.45, "sparkle": 0.6}
    pans = {"pop": -0.2, "confetti": 0.0, "scratch": 0.1, "slam": 0.0,
            "slam_soft": 0.0, "cricket": 0.45, "sting": -0.1, "boing": 0.2,
            "whoosh": -0.3, "sparkle": 0.25}
    for t, kind in tl.SFX:
        fn = SFX.get(kind) or SFX["pop"]
        place(sfx_bus, stereo(fn(gains.get(kind, 0.6)), pans.get(kind, 0.0)), t)
    # сверчки в тишине «после хлопка»
    place(sfx_bus, stereo(sfx_cricket(0.5), 0.4), 16.55)
    place(sfx_bus, stereo(sfx_cricket(0.35), 0.5), 17.15)
    music += sfx_bus

    print("• микс с озвучкой…")
    mix, spans = make_mix(music)
    write_wav(os.path.join(AUDIO, "mix.wav"), mix)
    for a, b in spans:
        print(f"  голос: {a:5.2f}–{b:5.2f} с")
    print(f"✓ audio/mix.wav ({tl.TOTAL:.1f} с)")


if __name__ == "__main__":
    main()
