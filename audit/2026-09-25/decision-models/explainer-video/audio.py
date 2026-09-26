"""Score and sound design for the Smriti explainer, synthesised from the video's own cue list.

Music: a D-minor pulse bed (pad, bass, kick, hats) whose sections follow the scenes.
SFX: whooshes, whips, slams, ticks, pops, locks, glitches, chimes, placed from cues.json.
Writes audio.wav (48 kHz, 16-bit stereo).
"""
import json
import os
import wave

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
CUES = json.load(open(os.path.join(HERE, "cues.json")))
DUR = CUES["dur"]
SC = CUES["sc"]
N = int(SR * (DUR + 1.0))
rng = np.random.default_rng(11)


def t_(d):
    return np.arange(int(SR * d)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def sweep_sine(f0, f1, d, curve="exp"):
    t = t_(d)
    f = f0 * (f1 / f0) ** (t / d) if curve == "exp" else f0 + (f1 - f0) * t / d
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def svf_sweep(x, f0, f1, q=0.9, shape=None):
    """Time-varying band-pass (Chamberlin SVF) with centre frequency gliding f0 -> f1."""
    n = len(x)
    s = np.linspace(0, 1, n) if shape is None else shape
    fc = f0 * (f1 / f0) ** s
    F = 2 * np.sin(np.pi * np.minimum(fc, SR / 6) / SR)
    low = band = 0.0
    out = np.empty(n)
    for i in range(n):
        high = x[i] - low - q * band
        band += F[i] * high
        low += F[i] * band
        out[i] = band
    return out


def stereo(m, pan=0.0):
    a = (pan + 1) * np.pi / 4
    return np.stack([m * np.cos(a), m * np.sin(a)], 1)


def pan_sweep(m, p0, p1):
    p = np.linspace(p0, p1, len(m))
    a = (p + 1) * np.pi / 4
    return np.stack([m * np.cos(a), m * np.sin(a)], 1)


def norm(x, peak=1.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


# ------------------------------------------------------------------ SFX
def sfx_whoosh(d=0.8, f0=300, f1=2600, peak=0.6, p0=-0.6, p1=0.6, soft=False):
    n = int(SR * d)
    x = rng.standard_normal(n)
    s = np.sin(np.linspace(0, np.pi, n)) ** 1.2
    shape = np.linspace(0, 1, n) ** 0.8
    y = svf_sweep(x, f0, f1, q=0.7, shape=shape) * s ** (1.6 if soft else 1.2)
    return pan_sweep(norm(y, peak), p0, p1)


def sfx_whip(pan=0.0):
    n = int(SR * 0.42)
    x = rng.standard_normal(n)
    env = np.exp(-((np.linspace(0, 1, n) - 0.35) ** 2) / 0.02)
    y = svf_sweep(x, 900, 5200, q=0.5, shape=np.linspace(0, 1, n) ** 0.5) * env
    return pan_sweep(norm(y, 0.75), pan + 0.7, pan - 0.7)


def sfx_whoosh_up(pan=0.5):
    return sfx_whoosh(0.55, 500, 4200, 0.45, pan - 0.3, pan + 0.3)


def reverb_ir(d=1.6, damp=4500, seed=3):
    r = np.random.default_rng(seed)
    t = t_(d)
    ir = np.stack([r.standard_normal(len(t)), r.standard_normal(len(t))], 1) * np.exp(-t / (d / 5.5))[:, None]
    ir[:, 0] = lp(ir[:, 0], damp); ir[:, 1] = lp(ir[:, 1], damp)
    return ir / np.sqrt(np.sum(ir ** 2, 0))


def sfx_impact(big=False):
    d = 2.2
    t = t_(d)
    body = sweep_sine(150 if big else 110, 38, d) * np.exp(-t / (0.45 if big else 0.35))
    click = lp(rng.standard_normal(len(t)), 2500) * np.exp(-t / 0.012) * 0.8
    thwack = bp(rng.standard_normal(len(t)), 300, 3200) * np.exp(-t / (0.09 if big else 0.05)) * (0.9 if big else 0.4)
    y = body * 1.0 + click + thwack
    if big:
        y = np.tanh(y * 1.6)
    return stereo(norm(y, 0.95))


def sfx_slam():
    pre_d = 0.14
    pre = rng.standard_normal(int(SR * pre_d)) * np.linspace(0, 1, int(SR * pre_d)) ** 3
    pre = hp(pre, 1500) * 0.35
    hit = sfx_impact(big=True)
    out = np.zeros((len(pre) + len(hit), 2))
    out[: len(pre)] += stereo(pre)
    out[len(pre):] += hit
    return out, -pre_d


def sfx_tick(pan=0.0, pitch=1.0, g=1.0):
    t = t_(0.045)
    y = hp(rng.standard_normal(len(t)), 3000) * np.exp(-t / 0.006) * 0.8 + np.sin(2 * np.pi * 2600 * pitch * t) * np.exp(-t / 0.01) * 0.4
    return stereo(norm(y, 0.5 * g), pan)


def sfx_pop(pan=0.0):
    t = t_(0.16)
    f = 520 * (1.75 ** np.minimum(t / 0.04, 1))
    y = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.05)
    y += 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.03)
    return stereo(norm(y, 0.55), pan)


def sfx_lock():
    t = t_(0.7)
    click = hp(rng.standard_normal(len(t)), 2000) * np.exp(-t / 0.004)
    ring = (np.sin(2 * np.pi * 1760 * t) + 0.6 * np.sin(2 * np.pi * 2663 * t) + 0.3 * np.sin(2 * np.pi * 4410 * t)) * np.exp(-t / 0.18)
    thump = np.sin(2 * np.pi * 80 * t) * np.exp(-t / 0.08)
    return stereo(norm(click * 0.8 + ring * 0.35 + thump * 0.8, 0.8))


def sfx_riser(d=1.0):
    t = t_(d)
    x = rng.standard_normal(len(t))
    y = svf_sweep(x, 400, 5000, q=0.6, shape=(t / d) ** 1.5) * (t / d) ** 2
    y += sweep_sine(300, 1300, d) * (t / d) ** 2 * 0.3
    return stereo(norm(y, 0.5))


def sfx_shimmer(d=3.0):
    t = t_(d)
    y = np.zeros(len(t))
    for f, a in ((2093, 1), (2637, .8), (3136, .7), (4186, .5), (5274, .3)):
        y += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * (0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(5, 9) * t))
    env = np.minimum(t / 0.8, 1) * np.exp(-np.maximum(t - 0.8, 0) / 0.9)
    L = y * env
    R = np.roll(L, 480)
    return norm(np.stack([L, R], 1), 0.3)


def sfx_sparkle(d=2.6):
    out = np.zeros((int(SR * d), 2))
    k = 0
    tt = 0.0
    while tt < d - 0.05:
        f = rng.uniform(3000, 8000)
        b = t_(0.03)
        blip = np.sin(2 * np.pi * f * b) * np.exp(-b / 0.006)
        i = int(tt * SR)
        out[i:i + len(b)] += stereo(blip * rng.uniform(0.2, 0.5), rng.uniform(-0.8, 0.8))
        tt += max(0.012, 0.12 * (1 - tt / d) ** 2)
        k += 1
    return norm(out, 0.35)


def sfx_sweep_down(d=0.8):
    t = t_(d)
    y = (sweep_sine(900, 110, d) + 0.7 * sweep_sine(905, 112, d)) * np.exp(-t / 0.35)
    return stereo(norm(y, 0.5))


def sfx_glitch(d=0.9):
    n = int(SR * d)
    y = np.zeros(n)
    i = 0
    while i < n:
        seg = int(SR * rng.uniform(0.015, 0.06))
        kind = rng.integers(0, 3)
        tt = np.arange(seg) / SR
        if kind == 0:
            s = np.sign(np.sin(2 * np.pi * rng.uniform(80, 900) * tt))
        elif kind == 1:
            s = np.round(rng.standard_normal(seg) * 3) / 3
        else:
            s = np.zeros(seg)
        y[i:i + seg] = s[: n - i] * rng.uniform(0.4, 1.0)
        i += seg
    y = lp(y, 6000) * np.exp(-np.arange(n) / SR / 0.6)
    return pan_sweep(norm(y, 0.45), -0.5, 0.5)


def sfx_thud():
    t = t_(0.7)
    y = sweep_sine(75, 42, 0.7) * np.exp(-t / 0.18) + lp(rng.standard_normal(len(t)), 400) * np.exp(-t / 0.05) * 0.5
    return stereo(norm(y, 0.8))


def note(f, d, tau, harm=((1, 1), (2, .35), (3, .15))):
    t = t_(d)
    return sum(a * np.sin(2 * np.pi * f * h * t) for h, a in harm) * np.exp(-t / tau) * np.minimum(t / 0.004, 1)


def sfx_success():
    out = np.zeros(int(SR * 1.6))
    for i, f in enumerate((587.33, 880.0, 1174.66)):
        n = note(f, 1.2, 0.35)
        s = int(SR * 0.075 * i)
        out[s:s + len(n)] += n * (0.8 - 0.1 * i)
    return stereo(norm(out, 0.5))


def sfx_warn():
    out = np.zeros(int(SR * 1.0))
    for i, f in enumerate((220.0, 174.61)):
        t = t_(0.42)
        sq = np.sign(np.sin(2 * np.pi * f * t))
        n = lp(sq, 1200) * np.exp(-t / 0.25) * np.minimum(t / 0.01, 1)
        s = int(SR * 0.3 * i)
        out[s:s + len(n)] += n
    return stereo(norm(out, 0.45))


def sfx_chime_low():
    f = 440.0
    y = note(f, 1.8, 0.6, ((1, 1), (2.76, .5), (5.4, .25)))
    return stereo(norm(y, 0.3))


def sfx_sub():
    t = t_(2.6)
    y = sweep_sine(52, 40, 2.6) * np.minimum(t / 0.25, 1) * np.exp(-t / 1.1)
    return stereo(norm(y, 0.9))


def make(c):
    k, pan = c["type"], c.get("pan", 0)
    if k == "whoosh": return sfx_whoosh(0.8, 300, 2600, 0.6, pan - 0.6, pan + 0.6), 0
    if k == "whoosh_soft": return sfx_whoosh(0.6, 400, 1700, 0.35, pan - 0.4, pan + 0.4, soft=True), 0
    if k == "whip": return sfx_whip(pan), -0.12
    if k == "whoosh_up": return sfx_whoosh_up(pan), 0
    if k == "impact": return sfx_impact(), 0
    if k == "slam": return sfx_slam()
    if k == "tick": return sfx_tick(pan, 1.0), 0
    if k == "type": return sfx_tick(pan, rng.uniform(0.7, 1.3), 0.7), 0
    if k == "pop": return sfx_pop(pan), 0
    if k == "lock": return sfx_lock(), 0
    if k == "riser_short": return sfx_riser(1.0), 0
    if k == "shimmer": return sfx_shimmer(), 0
    if k == "sparkle": return sfx_sparkle(), 0
    if k == "sweep_down": return sfx_sweep_down(), 0
    if k == "glitch": return sfx_glitch(), 0
    if k == "thud": return sfx_thud(), 0
    if k == "success": return sfx_success(), 0
    if k == "warn": return sfx_warn(), 0
    if k == "chime_low": return sfx_chime_low(), 0
    if k == "sub": return sfx_sub(), 0
    raise ValueError(k)


TYPE_GAIN = {"slam": 0.5, "impact": 0.55, "sub": 0.6, "thud": 0.7, "whoosh": 1.2, "whoosh_soft": 1.3, "whip": 1.1,
             "tick": 1.3, "type": 1.3, "pop": 1.2, "success": 1.2, "chime_low": 1.3, "warn": 1.1, "lock": 1.0}
sfx = np.zeros((N, 2))
for c in CUES["cues"]:
    snd, off = make(c)
    snd = snd * TYPE_GAIN.get(c["type"], 1.0)
    i = int((c["t"] + off) * SR)
    if i < 0:
        snd, i = snd[-i:], 0
    j = min(N, i + len(snd))
    sfx[i:j] += snd[: j - i] * c["g"]
# a little room on the effects
ir = reverb_ir(1.4)
wet = np.stack([fftconvolve(sfx[:, 0], ir[:, 0])[:N], fftconvolve(sfx[:, 1], ir[:, 1])[:N]], 1)
sfx = sfx + wet * 0.18

# ------------------------------------------------------------------ music bed
BPM = 120.0
BEAT = 60 / BPM
TT = np.arange(N) / SR


def midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


CHORDS = [  # D minor: i - VI - III - VII, 2 bars (4 s) each
    ([50, 57, 62, 65, 69, 76], 38),   # Dm(add9)  D3 A3 D4 F4 A4 E5 · bass D2
    ([46, 53, 58, 62, 65, 69], 34),   # Bbmaj7    · bass Bb1
    ([53, 57, 60, 64, 69, 72], 41),   # Fmaj7     · bass F2
    ([48, 55, 60, 64, 67, 74], 36),   # C(add9)   · bass C2
]
CH_LEN = 4.0


def section_level(t):
    """(pad cutoff Hz, bass, kick, hats) by time."""
    s0 = SC["s1"][0]; s_rules_end = SC["s4"][1]; s_r1 = SC["s5"][0]; s_out = SC["s11"][0]
    if t < s0: return 500, 0.0, 0.0, 0.0
    if t < SC["s2"][0]: return 900, 0.6, 0.0, 0.0
    if t < s_r1: return 1400, 0.8, 0.5, 0.6 if t >= SC["s3"][0] else 0.0
    if t < s_out: return 2200, 1.0, 1.0, 1.0
    return 700, 0.0, 0.0, 0.0


def saw(f, t, nh=10):
    return sum(np.sin(2 * np.pi * f * h * t) / h for h in range(1, nh + 1))


pad = np.zeros((N, 2))
bass = np.zeros(N)
nch = int(np.ceil((DUR + 1) / CH_LEN))
for k in range(nch):
    notes, broot = CHORDS[k % 4]
    if k * CH_LEN >= SC["s11"][0]:
        notes, broot = CHORDS[0]
    a, b = k * CH_LEN, (k + 1) * CH_LEN + 1.2
    i0, i1 = int(a * SR), min(N, int(b * SR))
    t = TT[i0:i1] - a
    env = np.minimum(t / 0.9, 1) * np.clip((b - a - t) / 1.2, 0, 1)
    for m in notes:
        for det, pan in ((-0.07, -0.5), (0.0, 0.0), (0.07, 0.5)):
            f = midi(m + det)
            v = saw(f, t, 8) * env * 0.06
            pad[i0:i1] += stereo(v, pan)
    # bass: 8th-note pulse
    bt = np.zeros(i1 - i0)
    for s in np.arange(0, CH_LEN, BEAT / 2):
        j0 = int(s * SR)
        if j0 >= len(bt): break
        tt = np.arange(min(int(0.22 * SR), len(bt) - j0)) / SR
        bt[j0:j0 + len(tt)] += (np.sin(2 * np.pi * midi(broot) * tt) + 0.25 * np.sin(4 * np.pi * midi(broot) * tt)) * np.exp(-tt / 0.12) * np.minimum(tt / 0.005, 1)
    bass[i0:i1] += bt[: i1 - i0]

# pad filter by section: filter once per cutoff, crossfade smoothly between them
blk = SR // 2
cut_t = np.array([section_level(i / SR)[0] for i in range(0, N, blk)])
cutoffs = sorted(set(cut_t))
ramp = int(0.8 * SR)
kern = np.ones(ramp) / ramp
filtered = np.zeros_like(pad)
for fc in cutoffs:
    w = np.repeat((cut_t == fc).astype(float), blk)[:N]
    w = np.convolve(w, kern, mode="same")
    for ch in range(2):
        filtered[:, ch] += lp(pad[:, ch], fc, 2) * w
pad = filtered

kick = np.zeros(N)
hats = np.zeros(N)
kenv = np.zeros(N)
ncount = int((DUR + 1) / BEAT)
R1_DROP = (SC["s5"][0] + 6.0, SC["s5"][0] + 7.6)     # silence after the round-1 glitch
for n in range(ncount):
    t0 = n * BEAT
    _, bl, kl, hl = section_level(t0)
    drop = R1_DROP[0] <= t0 < R1_DROP[1]
    if kl > 0 and not drop and (kl >= 1.0 or n % 2 == 0):
        tt = np.arange(int(0.35 * SR)) / SR
        k = np.sin(2 * np.pi * np.cumsum(45 + 90 * np.exp(-tt / 0.03)) / SR) * np.exp(-tt / 0.16)
        k += hp(rng.standard_normal(len(tt)), 3000) * np.exp(-tt / 0.003) * 0.3
        i = int(t0 * SR); j = min(N, i + len(tt))
        kick[i:j] += k[: j - i] * kl
        kenv[i:j] = np.maximum(kenv[i:j], np.exp(-tt[: j - i] / 0.18) * kl)
    if hl > 0 and not drop:
        tt = np.arange(int(0.04 * SR)) / SR
        h = hp(rng.standard_normal(len(tt)), 7000) * np.exp(-tt / 0.012)
        i = int((t0 + BEAT / 2) * SR); j = min(N, i + len(tt))
        hats[i:j] += h[: j - i] * hl * 0.5

bl_arr = np.array([section_level(i / SR)[1] for i in range(0, N, blk)])
bass *= np.convolve(np.repeat(bl_arr, blk)[:N], np.ones(SR // 4) / (SR // 4), mode='same')
drop_mask = np.ones(N)
d0, d1 = int(R1_DROP[0] * SR), int(R1_DROP[1] * SR)
drop_mask[d0:d1] = 0.15
duck = 1 - 0.55 * kenv
music = pad * (duck * drop_mask)[:, None] * 1.0 + stereo(bass * duck * drop_mask * 0.55) + stereo(kick * 0.9) + pan_sweep(hats, -0.3, 0.3) * 0.6
music = norm(music, 1.0) * 0.42
# fade in / out
fade = np.ones(N)
fi = int(1.0 * SR); fade[:fi] = np.linspace(0, 1, fi)
fo0 = int((DUR - 2.5) * SR); fade[fo0:] = np.linspace(1, 0, N - fo0)
music *= fade[:, None]

mix = music + sfx * 0.85
mix = np.tanh(mix * 1.9) / np.tanh(1.9)
mix = norm(mix, 0.93)[: int(SR * DUR)]
pcm = (mix * 32767).astype(np.int16)
with wave.open(os.path.join(HERE, "audio.wav"), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print("audio.wav", pcm.shape[0] / SR, "s", "rms dB", round(20 * np.log10(np.sqrt(np.mean(mix ** 2))), 1))
