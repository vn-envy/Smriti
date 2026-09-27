"""Sound for the Smriti 0.4 trailer.

Music: "Funky Launch Groove" (120 BPM), cut on its own bar lines so the drops land on the picture:
  video 0-32 s   <- track bars 0-15   (intro, first drop at 8 s, break at 16 s)
  video 32-54 s  <- track bars 53-63  (breakdown, drop at 42 s)
  video 54-69 s  <- track bars 72-end (break, final drop at 58 s, ending stab at 66 s)
SFX: the supplied glass, keyboard and UI-bubble recordings, plus synthesised whooshes, hits and risers,
placed from cues.json (exported from trailer.html, so sound and picture share one timeline).
Writes audio.wav (48 kHz, 16-bit stereo), mastered to about -14 LUFS with a -1 dBFS ceiling.
"""
import glob
import json
import os
import wave

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import butter, fftconvolve, lfilter, resample_poly, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "assets")
SR = 48000
CUES = json.load(open(os.path.join(HERE, "cues.json")))
DUR = CUES["dur"]
N = int(SR * DUR)
rng = np.random.default_rng(17)

BAR0 = 0.145                                  # first bar line in the track
SEGMENTS = [(BAR0, 0.0), (106.154, 32.0), (144.157, 54.0)]   # (track start, video start)
XF = 0.010                                    # crossfade before each cut, seconds


def read_wav(path):
    w = wave.open(path)
    sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
    raw = w.readframes(w.getnframes())
    x = np.frombuffer(raw, {2: np.int16, 4: np.int32}[sw]).astype(np.float64) / (2 ** (8 * sw - 1))
    x = x.reshape(-1, ch)
    if ch == 1:
        x = np.repeat(x, 2, 1)
    if sr != SR:
        g = np.gcd(SR, sr)
        x = resample_poly(x, SR // g, sr // g, axis=0)
    return x


def t_(d):
    return np.arange(int(SR * d)) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x, axis=0)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x, axis=0)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x, axis=0)


def norm(x, peak=1.0):
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def stereo(m, pan=0.0):
    a = (pan + 1) * np.pi / 4
    return np.stack([m * np.cos(a), m * np.sin(a)], 1)


def pan_sweep(m, p0, p1):
    p = np.linspace(p0, p1, len(m))
    a = (p + 1) * np.pi / 4
    return np.stack([m * np.cos(a), m * np.sin(a)], 1)


def sweep_sine(f0, f1, d):
    t = t_(d)
    f = f0 * (f1 / f0) ** (t / d)
    return np.sin(2 * np.pi * np.cumsum(f) / SR)


def svf_sweep(x, f0, f1, q=0.9, shape=None):
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


def repitch(x, p):
    if abs(p - 1) < 1e-3:
        return x
    n = int(len(x) / p)
    src = np.arange(n) * p
    return np.stack([np.interp(src, np.arange(len(x)), x[:, c]) for c in range(2)], 1)


# ------------------------------------------------------------------ samples
SFX_DIR = os.path.join(A, "sfx")
GLASS = {i: read_wav(os.path.join(SFX_DIR, f"Glass Plate Smash Shatter 0{i}.wav")) for i in range(1, 6)}
KEYS = []
for f in sorted(glob.glob(os.path.join(SFX_DIR, "Keyboard Button Press SFX", "*.wav"))):
    k = read_wav(f)
    on = np.argmax(np.abs(k).max(1) > 0.04)
    KEYS.append(k[max(0, on - int(0.004 * SR)):])
_b = read_wav(os.path.join(SFX_DIR, "Ui Click Bubble 02.wav"))
BUBBLE = _b[: int(0.105 * SR)].copy()
BUBBLE[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))[:, None]


# ------------------------------------------------------------------ synthesised
def sfx_whoosh(d=0.8, f0=300, f1=2600, peak=0.6, p0=-0.6, p1=0.6, soft=False):
    n = int(SR * d)
    x = rng.standard_normal(n)
    s = np.sin(np.linspace(0, np.pi, n)) ** 1.2
    y = svf_sweep(x, f0, f1, q=0.7, shape=np.linspace(0, 1, n) ** 0.8) * s ** (1.6 if soft else 1.2)
    return pan_sweep(norm(y, peak), p0, p1)


def sfx_whip(pan=0.0, vert=False):
    n = int(SR * 0.42)
    x = rng.standard_normal(n)
    env = np.exp(-((np.linspace(0, 1, n) - 0.35) ** 2) / 0.02)
    y = svf_sweep(x, 900, 5200, q=0.5, shape=np.linspace(0, 1, n) ** 0.5) * env
    return pan_sweep(norm(y, 0.75), 0 if vert else pan + 0.7, 0 if vert else pan - 0.7)


def sfx_impact(big=False):
    d = 2.2
    t = t_(d)
    body = sweep_sine(150 if big else 110, 38, d) * np.exp(-t / (0.45 if big else 0.3))
    click = lp(rng.standard_normal(len(t)), 2500) * np.exp(-t / 0.012) * 0.8
    thwack = bp(rng.standard_normal(len(t)), 300, 3200) * np.exp(-t / (0.09 if big else 0.05)) * (0.9 if big else 0.4)
    y = body + click + thwack
    if big:
        y = np.tanh(y * 1.6)
    return stereo(norm(y, 0.95))


def sfx_slam():
    pre_d = 0.1
    pre = hp(rng.standard_normal(int(SR * pre_d)) * np.linspace(0, 1, int(SR * pre_d)) ** 3, 1500) * 0.35
    hit = sfx_impact(big=True)
    out = np.zeros((len(pre) + len(hit), 2))
    out[: len(pre)] += stereo(pre)
    out[len(pre):] += hit
    return out, -pre_d


def sfx_tick(pan=0.0, pitch=1.0):
    t = t_(0.045)
    y = hp(rng.standard_normal(len(t)), 3000) * np.exp(-t / 0.006) * 0.8 + np.sin(2 * np.pi * 2600 * pitch * t) * np.exp(-t / 0.01) * 0.4
    return stereo(norm(y, 0.5), pan)


def sfx_riser(d=1.0):
    t = t_(d)
    x = rng.standard_normal(len(t))
    y = svf_sweep(x, 300, 6000, q=0.55, shape=(t / d) ** 1.4) * (t / d) ** 2
    y += (sweep_sine(220, 1400, d) + 0.5 * sweep_sine(223, 1410, d)) * (t / d) ** 2.4 * 0.25
    return stereo(norm(y, 0.55))


def sfx_rev(d=0.45):
    """Reverse cymbal-style swell that ends on the cue."""
    t = t_(d)
    y = hp(rng.standard_normal(len(t)), 2500) * (t / d) ** 3
    return stereo(norm(y, 0.5)), -d


def sfx_shimmer(d=3.0):
    t = t_(d)
    y = np.zeros(len(t))
    for f, a in ((2093, 1), (2637, .8), (3136, .7), (4186, .5), (5274, .3)):
        y += a * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * (0.6 + 0.4 * np.sin(2 * np.pi * rng.uniform(5, 9) * t))
    env = np.minimum(t / 0.5, 1) * np.exp(-np.maximum(t - 0.5, 0) / 0.9)
    L = y * env
    return norm(np.stack([L, np.roll(L, 480)], 1), 0.3)


def sfx_sparkle(d=2.2):
    out = np.zeros((int(SR * d), 2))
    tt = 0.0
    while tt < d - 0.05:
        b = t_(0.03)
        blip = np.sin(2 * np.pi * rng.uniform(3000, 8000) * b) * np.exp(-b / 0.006)
        i = int(tt * SR)
        out[i:i + len(b)] += stereo(blip * rng.uniform(0.2, 0.5), rng.uniform(-0.8, 0.8))
        tt += max(0.012, 0.1 * (tt / d + 0.1))
    return norm(out, 0.35)


def sfx_sweep_down(d=0.7):
    t = t_(d)
    y = (sweep_sine(900, 110, d) + 0.7 * sweep_sine(905, 112, d)) * np.exp(-t / 0.3)
    return stereo(norm(y, 0.5))


def sfx_glitch(d=0.5):
    n = int(SR * d)
    y = np.zeros(n)
    i = 0
    while i < n:
        seg = int(SR * rng.uniform(0.012, 0.05))
        tt = np.arange(seg) / SR
        kind = rng.integers(0, 3)
        s = np.sign(np.sin(2 * np.pi * rng.uniform(80, 900) * tt)) if kind == 0 else (np.round(rng.standard_normal(seg) * 3) / 3 if kind == 1 else np.zeros(seg))
        y[i:i + seg] = s[: n - i] * rng.uniform(0.4, 1.0)
        i += seg
    y = lp(y, 6000) * np.exp(-np.arange(n) / SR / 0.4)
    return pan_sweep(norm(y, 0.45), -0.5, 0.5)


def sfx_thud():
    t = t_(0.7)
    y = sweep_sine(80, 42, 0.7) * np.exp(-t / 0.16) + lp(rng.standard_normal(len(t)), 500) * np.exp(-t / 0.04) * 0.6
    return stereo(norm(y, 0.85))


def sfx_sub():
    t = t_(2.4)
    y = sweep_sine(58, 36, 2.4) * np.minimum(t / 0.01, 1) * np.exp(-t / 0.9)
    return stereo(norm(y, 0.9))


def sfx_crack():
    """A sharp glass crack: bright transient, a short ring and a few tinkles."""
    t = t_(0.5)
    click = hp(rng.standard_normal(len(t)), 3500) * np.exp(-t / 0.004)
    ring = sum(np.sin(2 * np.pi * f * t) * np.exp(-t / 0.05) for f in (3100, 4870, 6230)) * 0.2
    y = click + ring
    for _ in range(5):
        i = int(rng.uniform(0.02, 0.3) * SR)
        b = t_(0.02)
        y[i:i + len(b)] += np.sin(2 * np.pi * rng.uniform(4000, 9000) * b) * np.exp(-b / 0.004) * rng.uniform(0.1, 0.3)
    return stereo(norm(y, 0.6))


def sfx_stamp():
    t = t_(0.6)
    y = sweep_sine(140, 60, 0.6) * np.exp(-t / 0.08) + bp(rng.standard_normal(len(t)), 400, 4000) * np.exp(-t / 0.03) * 0.8
    return stereo(norm(y, 0.8))


def sfx_strike(pan=0.0):
    n = int(SR * 0.16)
    x = rng.standard_normal(n)
    env = np.sin(np.linspace(0, np.pi, n)) ** 2
    y = svf_sweep(x, 1500, 5000, q=0.35) * env
    return stereo(norm(y, 0.45), pan)


def whoosh_dir(c, f0, f1, d=0.7, peak=0.6):
    return sfx_whoosh(d, f0, f1, peak, c.get("p0", c["pan"] - 0.5), c.get("p1", c["pan"] + 0.5))


def make(c):
    k, pan, p = c["type"], c.get("pan", 0), c.get("p", 1.0)
    if k.startswith("glass"): return GLASS[int(k[-1])], 0
    if k == "key": return repitch(KEYS[c.get("v", 0) % len(KEYS)], p) * np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)]) * 1.41, 0
    if k == "bubble": return repitch(BUBBLE, p) * np.array([np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)]) * 1.41, 0
    if k == "whoosh": return whoosh_dir(c, 300, 2600, 0.8, 0.6), -0.4
    if k == "whoosh_soft": return sfx_whoosh(0.6, 400, 1700, 0.35, pan - 0.4, pan + 0.4, soft=True), -0.25
    if k == "whoosh_up": return sfx_whoosh(0.5, 500, 4200, 0.45, pan - 0.2, pan + 0.2), -0.2
    if k == "whoosh_down": return sfx_whoosh(0.4, 3000, 400, 0.5, pan, pan), -0.05
    if k == "whip": return sfx_whip(pan, bool(c.get("vert"))), -0.15
    if k == "impact": return sfx_impact(), 0
    if k == "impact_big": return sfx_impact(big=True), 0
    if k == "slam": return sfx_slam()
    if k == "tick": return sfx_tick(pan, p), 0
    if k == "riser": return sfx_riser(c.get("d", 1.0)), 0
    if k == "rev": return sfx_rev(c.get("d", 0.45))
    if k == "shimmer": return sfx_shimmer(), 0
    if k == "sparkle": return sfx_sparkle(), 0
    if k == "sweep_down": return sfx_sweep_down(), 0
    if k == "glitch": return sfx_glitch(), 0
    if k == "thud": return sfx_thud(), 0
    if k == "sub": return sfx_sub(), 0
    if k == "crack": return sfx_crack(), 0
    if k == "stamp": return sfx_stamp(), 0
    if k == "strike": return sfx_strike(pan), 0
    raise ValueError(k)


TYPE_GAIN = {"glass1": 0.9, "glass2": 0.9, "glass3": 0.9, "glass4": 0.9, "glass5": 0.9, "impact_big": 0.55, "impact": 0.5, "slam": 0.45,
             "sub": 0.7, "thud": 0.7, "whoosh": 1.0, "whoosh_soft": 1.1, "whoosh_up": 1.0, "whoosh_down": 1.0, "whip": 1.0, "key": 0.9,
             "bubble": 0.8, "tick": 1.0, "crack": 1.0, "riser": 0.7, "rev": 0.8, "shimmer": 0.9, "sparkle": 0.9, "stamp": 0.8, "strike": 0.8,
             "glitch": 0.9, "sweep_down": 0.8}

sfx = np.zeros((N + SR, 2))
for c in CUES["cues"]:
    snd, off = make(c)
    snd = snd * TYPE_GAIN.get(c["type"], 1.0) * c["g"]
    i = int(round((c["t"] + off) * SR))
    if i < 0:
        snd, i = snd[-i:], 0
    j = min(len(sfx), i + len(snd))
    sfx[i:j] += snd[: j - i]
sfx = sfx[:N]
# a little room on the synthetic effects (the recordings carry their own)
ir_t = t_(1.2)
r2 = np.random.default_rng(3)
ir = np.stack([r2.standard_normal(len(ir_t)), r2.standard_normal(len(ir_t))], 1) * np.exp(-ir_t / 0.22)[:, None]
ir = lp(ir, 5000) / np.sqrt(np.sum(ir ** 2, 0))
wet = np.stack([fftconvolve(sfx[:, c], ir[:, c])[:N] for c in range(2)], 1)
sfx = sfx + wet * 0.12

# ------------------------------------------------------------------ music edit
track = read_wav(os.path.join(A, "funky_launch.wav"))
music = np.zeros((N, 2))
xf = int(XF * SR)
for k, (src0, v0) in enumerate(SEGMENTS):
    v1 = SEGMENTS[k + 1][1] if k + 1 < len(SEGMENTS) else DUR
    i0, n = int(round(v0 * SR)), int(round(v1 * SR)) - int(round(v0 * SR))
    s0 = int(round(src0 * SR))
    body = track[s0:s0 + n].copy()
    if k + 1 < len(SEGMENTS):                 # old segment fades out over the last XF before the cut
        body[-xf:] *= np.cos(np.linspace(0, np.pi / 2, xf))[:, None]
    music[i0:i0 + len(body)] += body
    if k:                                     # new segment fades in over the same window
        music[i0 - xf:i0] += track[s0 - xf:s0] * np.sin(np.linspace(0, np.pi / 2, xf))[:, None]
music[: int(0.005 * SR)] *= np.linspace(0, 1, int(0.005 * SR))[:, None]

# the intro starts muffled and opens up into the first drop
TT = np.arange(N) / SR
w_lp = np.interp(TT, [0, 3.9, 4.0, 7.9, 8.0], [1.0, 1.0, 0.6, 0.0, 0.0])
music = music * (1 - w_lp)[:, None] + lp(music, 1400, 2) * w_lp[:, None]

# level: quieter under the chat typing, ducked briefly under the big hits
gain = np.interp(TT, [0, 3.8, 4.0, 69], [0.62, 0.62, 0.78, 0.78])
for t0, depth in ((8.0, 0.55), (42.0, 0.6), (58.0, 0.55), (4.0, 0.8), (4.5, 0.8)):
    u = TT - t0
    m = (u >= 0) & (u < 0.8)
    gain[m] *= 1 - (1 - depth) * np.exp(-u[m] / 0.22)
music *= gain[:, None]
fo = int(1.0 * SR)
music[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5

# ------------------------------------------------------------------ master
mix = music + sfx * 0.8


def lufs(x):
    """Integrated loudness, ITU-R BS.1770-4 (48 kHz K-weighting, gated)."""
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    y = lfilter(b2, a2, lfilter(b1, a1, x, axis=0), axis=0)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    z = np.array([np.mean(y[i:i + blk] ** 2, 0).sum() for i in range(0, len(y) - blk, hop)])
    L = -0.691 + 10 * np.log10(z + 1e-12)
    z = z[L > -70]
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    z = z[-0.691 + 10 * np.log10(z) > rel]
    return -0.691 + 10 * np.log10(z.mean())


def limit(x, ceiling=10 ** (-1.2 / 20)):
    peak = np.abs(x).max(1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    w = int(0.03 * SR) | 1
    g = uniform_filter1d(minimum_filter1d(need, size=2 * w + 1), size=w)
    return np.clip(x * g[:, None], -ceiling, ceiling)


target = -14.0
for _ in range(3):
    mix = mix * 10 ** ((target - lufs(mix)) / 20)
    mix = limit(mix)
L = lufs(mix)
pcm = (mix * 32767).astype(np.int16)
with wave.open(os.path.join(HERE, "audio.wav"), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
print(f"audio.wav {len(pcm) / SR:.2f}s  loudness {L:.1f} LUFS  peak {20 * np.log10(np.abs(mix).max()):.2f} dBFS")
