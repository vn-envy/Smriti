#!/usr/bin/env python3
"""
SMRITI Enterprise film score -> public/audio/enterprise-score.wav

Upbeat hip-hop with a narrative arc:
  bars 0-2   intro        · logo
  bars 2-8   PAIN         · minor, lowpass-filtered (muffled tension)
  bar  8-9   THE TURN     · filter opens, major resolution, impact
  bars 9-13  groove       · bright
  bars 13-17 THE DROP     · full energy, 3D hero shot
  bars 17-28 body         · features
  bars 28-32 breakdown + outro

90 BPM: 1 beat = 0.6667s = exactly 20 frames @30fps, so every scene cut in
the film lands on a beat (80 frames = 1 bar).

v2 fixes: removed the constant white-noise bed, crackle reduced from ~70/s to
~4/s and warmed with a lowpass, noisy riser replaced with a tonal one, and
the low end substantially reinforced (deeper kick, louder 808 + sub layer,
low-shelf bass boost on the master).

Pure numpy, deterministic, no samples, no licensing.
"""
import wave
import numpy as np

SR = 44100
BPM = 90.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT
BARS = 32                      # 2560 frames @30fps = 85.33 s
DUR = BARS * BAR
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(7)

# section boundaries (bars) — mirrors SCENES in src/enterprise/etheme.ts
PAIN_START, TURN, DROP, DROP_END, BREAKDOWN = 2, 8, 13, 17, 28

L = np.zeros(N)
R = np.zeros(N)
# the pain section renders into its own buffer so it can be filtered as a
# whole ("the filter opens" on the turn) instead of faking it per-instrument
PL = np.zeros(N)
PR = np.zeros(N)


def add(bl, br, sig, start_s, pan=0.0, gain=1.0):
    i = int(start_s * SR)
    if i >= N:
        return
    seg = sig[: max(0, N - i)] * gain
    lg, rg = np.sqrt((1 - pan) / 2), np.sqrt((1 + pan) / 2)
    bl[i : i + len(seg)] += seg * lg * 1.414
    br[i : i + len(seg)] += seg * rg * 1.414


def env(n, a=0.002, d=0.12, s=0.0, r=0.05, curve=3.0):
    e = np.zeros(n)
    ai, di = max(1, int(a * SR)), int(d * SR)
    ai = min(ai, n)
    e[:ai] = np.linspace(0, 1, ai)
    if di > 0 and ai < n:
        k = min(di, n - ai)
        e[ai : ai + k] = (1 - np.linspace(0, 1, k)) ** curve * (1 - s) + s
        if s > 0 and ai + k < n:
            ri = min(int(r * SR), n - ai - k)
            e[ai + k : ai + k + ri] = s * (1 - np.linspace(0, 1, ri)) ** 2
    return e


def spectral(x, cutoff, kind="low", order=4):
    """Zero-phase FFT filter — clean, fast, no IIR loop in Python."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    if kind == "low":
        mask = 1.0 / (1.0 + (f / cutoff) ** order)
    else:
        mask = 1.0 / (1.0 + (cutoff / np.maximum(f, 1e-6)) ** order)
    return np.fft.irfft(X * mask, n=len(x))


# ————————————————————————————— drums —————————————————————————————
def kick(dur=0.5, f0=125.0, f1=38.0):
    """Deeper and longer than v1: f1 38Hz (was 44), more sustain in the body."""
    n = int(dur * SR)
    x = np.arange(n) / SR
    f = f1 + (f0 - f1) * np.exp(-x * 30)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, dur * 0.95, curve=1.9)
    sub = np.sin(2 * np.pi * (f1 * 0.5) * x) * env(n, 0.004, dur * 0.8, curve=2.2) * 0.35
    click = spectral(rng.normal(0, 1, n), 1800, "high") * env(n, 0.0004, 0.005, curve=4) * 0.22
    return np.tanh((body * 1.15 + sub + click) * 1.3) * 1.05


def snare(dur=0.22):
    n = int(dur * SR)
    noise = spectral(rng.normal(0, 1, n), 1400, "high")
    noise += spectral(rng.normal(0, 1, n), 380, "low") * 0.5   # body, not fizz
    tone = (np.sin(2 * np.pi * 196 * np.arange(n) / SR) * 0.5
            + np.sin(2 * np.pi * 331 * np.arange(n) / SR) * 0.28)
    return (noise * 0.55 + tone * 0.5) * env(n, 0.001, dur * 0.8, curve=2.8) * 0.68


def hat(dur=0.05, bright=1.0, open_=False):
    d = 0.17 if open_ else dur
    n = int(d * SR)
    x = spectral(rng.normal(0, 1, n), 6500, "high")   # tight, no low fizz
    return x * env(n, 0.0004, d * 0.85, curve=5.0) * 0.16 * bright


def clap(dur=0.26):
    n = int(dur * SR)
    out = np.zeros(n)
    for off in (0.0, 0.012, 0.024):
        i = int(off * SR)
        seg = spectral(rng.normal(0, 1, n - i), 1100, "high")
        out[i:] += seg * env(n - i, 0.0006, 0.08, curve=3.5)
    return out * 0.3


# ————————————————————————————— tonal —————————————————————————————
NOTE = {"D1": 36.71, "G1": 49.0, "A1": 55.0, "B1": 61.74, "F#1": 46.25,
        "D2": 73.42, "A2": 110.0, "B2": 123.47, "G2": 98.0, "F#2": 92.5,
        "D3": 146.83, "F#3": 185.0, "A3": 220.0, "B3": 246.94, "G3": 196.0,
        "C#4": 277.18, "D4": 293.66, "E4": 329.63, "F#4": 369.99,
        "A4": 440.0, "B4": 493.88, "C#5": 554.37, "D5": 587.33}


def sub808(freq, dur, glide_from=None, gain=1.0):
    """Louder, fatter: octave-down layer + saturation for audible weight on
    laptop speakers while keeping the true sub for good systems."""
    n = int(dur * SR)
    x = np.arange(n) / SR
    f = np.full(n, freq)
    if glide_from:
        f = freq + (glide_from - freq) * np.exp(-x * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    sig = np.sin(ph)
    sig += 0.38 * np.sin(ph * 0.5)          # octave down = the weight
    sig += 0.26 * np.sin(ph * 2)            # harmonic so it reads on small speakers
    e = env(n, 0.005, dur * 0.92, s=0.35, r=0.12, curve=1.4)
    return np.tanh(sig * 1.5) * e * 0.78 * gain


def rhodes(freqs, dur, gain=1.0):
    n = int(dur * SR)
    x = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for h, amp, dec in ((1, 1.0, 1.0), (2, 0.3, 0.7), (3, 0.1, 0.5), (4.02, 0.06, 0.35)):
            out += amp * np.sin(2 * np.pi * f * h * x) * np.exp(-x * (2.2 / dec))
    tine = np.sin(2 * np.pi * freqs[0] * 6.1 * x) * np.exp(-x * 44) * 0.13
    return (out / len(freqs) + tine) * env(n, 0.004, dur * 0.85, curve=1.3) * 0.42 * gain


def pluck(freq, dur, gain=1.0):
    n = int(dur * SR)
    x = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * freq * x)
           + 0.42 * np.sin(2 * np.pi * freq * 2 * x) * np.exp(-x * 9)
           + 0.18 * np.sin(2 * np.pi * freq * 3 * x) * np.exp(-x * 14))
    return sig * env(n, 0.002, dur * 0.8, curve=2.4) * 0.30 * gain


def pad(freqs, dur, gain=1.0):
    """Slow tension bed for the pain section — tonal, not noise."""
    n = int(dur * SR)
    x = np.arange(n) / SR
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        det = 1 + (i - 1) * 0.0015
        out += np.sin(2 * np.pi * f * det * x) * (0.6 ** i)
        out += np.sin(2 * np.pi * f * 0.5 * det * x) * 0.25 * (0.6 ** i)
    swell = np.sin(np.pi * np.clip(x / dur, 0, 1)) ** 1.5
    return out / len(freqs) * swell * 0.2 * gain


def riser(dur=1.8):
    """Tonal riser (v1 was mostly white noise): rising sine stack + a soft,
    lowpassed air layer that never gets brighter than 4 kHz."""
    n = int(dur * SR)
    x = np.arange(n) / SR
    p = x / dur
    f = 180 * np.exp(p * 2.6)
    ph = 2 * np.pi * np.cumsum(f) / SR
    tone = np.sin(ph) + 0.4 * np.sin(ph * 1.5) + 0.2 * np.sin(ph * 2.02)
    air = spectral(rng.normal(0, 1, n), 4000, "low") * 0.18
    return (tone * 0.5 + air) * (p ** 2.2) * 0.55


def impact(dur=1.6):
    n = int(dur * SR)
    x = np.arange(n) / SR
    f = 95 * np.exp(-x * 5.5) + 32
    body = np.sin(2 * np.pi * np.cumsum(f) / SR)
    tail = spectral(rng.normal(0, 1, n), 900, "low") * np.exp(-x * 7) * 0.35
    return (body * 1.1 + tail) * np.exp(-x * 2.1) * 0.85


# ———————————————————————— arrangement ————————————————————————
PROG = [  # (bar_start, bar_end, chord, bass) — minor through the pain, D major after the turn
    (0, 2,   ["D4", "F#4", "A4"], "D2"),      # intro
    (2, 4,   ["B3", "D4", "F#4"], "B2"),      # pain — B minor
    (4, 6,   ["G3", "B3", "D4"], "G2"),       # pain — G
    (6, 8,   ["F#3", "A3", "C#5"], "F#2"),    # cost — F# minor tension
    (8, 9,   ["D4", "F#4", "A4"], "D2"),      # THE TURN — resolves major
    (9, 13,  ["A3", "C#5", "E4"], "A2"),
    (13, 17, ["D4", "F#4", "A4"], "D2"),      # drop
    (17, 21, ["G3", "B3", "D4"], "G2"),
    (21, 24, ["A3", "C#5", "E4"], "A2"),
    (24, 28, ["B3", "D4", "F#4"], "B2"),
    (28, 30, ["G3", "B3", "D4"], "G2"),
    (30, 32, ["D4", "F#4", "A4"], "D2"),
]

for bar in range(BARS):
    b0 = bar * BAR
    pain = PAIN_START <= bar < TURN
    turn = bar == TURN
    drop = DROP <= bar < DROP_END
    outro = bar >= 30
    breakdown = BREAKDOWN <= bar < 30
    intro = bar < PAIN_START
    sparse = intro or breakdown
    # pain and turn render into the filtered buffer
    bl, br = (PL, PR) if (pain or turn) else (L, R)

    chord, bass = None, None
    for s, e, ch, ba in PROG:
        if s <= bar < e:
            chord, bass = ch, ba
    freqs = [NOTE[c] for c in chord]

    # ——— pain: sparse, heavy, no hats, no sparkle ———
    if pain:
        add(bl, br, kick(), b0, 0.0, 0.85)
        add(bl, br, kick(), b0 + 2.5 * BEAT, 0.0, 0.7)
        if bar >= PAIN_START + 1:
            add(bl, br, snare(), b0 + 2.0 * BEAT, 0.0, 0.55)
        add(bl, br, sub808(NOTE[bass], BEAT * 2.2), b0, 0.0, 1.0)
        add(bl, br, pad(freqs, BAR * 1.05), b0, 0.0, 1.0)
        if bar >= 6:  # the cost bars: add a ticking clock feel
            for i in range(4):
                add(bl, br, hat(bright=0.5), b0 + i * BEAT, 0.0, 0.5)
        continue

    # ——— the turn: one huge resolved chord + impact, no drums ———
    if turn:
        add(bl, br, rhodes(freqs, 2.4, gain=1.6), b0, 0.0, 1.0)
        add(bl, br, sub808(NOTE[bass], BEAT * 3.4), b0, 0.0, 1.1)
        add(bl, br, pad([f * 2 for f in freqs], BAR * 0.9, gain=1.2), b0, 0.0, 1.0)
        continue

    # ——— everything after the turn: the groove ———
    kicks = [0.0, 2.5] if sparse else [0.0, 1.75, 2.5]
    if drop:
        kicks = [0.0, 1.5, 1.75, 2.5, 3.75]
    for kb in kicks:
        add(bl, br, kick(), b0 + kb * BEAT, 0.0, 1.0 if not sparse else 0.75)

    if not intro:
        for sb in (1.0, 3.0):
            add(bl, br, snare(), b0 + sb * BEAT, 0.0, 0.85)
            if drop:
                add(bl, br, clap(), b0 + sb * BEAT, 0.0, 0.55)

    if not intro or bar == 1:
        for i in range(8):
            acc = 1.2 if i % 2 == 0 else 0.7
            add(bl, br, hat(bright=acc), b0 + i * 0.5 * BEAT,
                0.18 * (1 if i % 2 else -1), 0.9 if not sparse else 0.5)
        if bar % 4 == 3:
            for j in range(4):
                add(bl, br, hat(bright=0.85), b0 + (3.5 + j * 0.125) * BEAT, -0.15, 0.75)
        if drop and bar % 2 == 1:
            add(bl, br, hat(open_=True), b0 + 3.5 * BEAT, 0.2, 0.65)

    stabs = [0.0, 2.5] if not drop else [0.0, 1.5, 2.5, 3.75]
    for i, sb in enumerate(stabs):
        add(bl, br, rhodes(freqs, 0.9, gain=1.0 if i == 0 else 0.7),
            b0 + sb * BEAT, -0.12, 0.9 if not sparse else 0.55)

    # bass: root on 1 (long), fifth on 3 — louder than v1 across the board
    add(bl, br, sub808(NOTE[bass], BEAT * 1.9), b0, 0.0, 1.15 if not sparse else 0.8)
    if not sparse:
        add(bl, br, sub808(NOTE[bass] * 1.5, BEAT * 0.95, glide_from=NOTE[bass]),
            b0 + 2.5 * BEAT, 0.0, 0.9)
    if drop:
        add(bl, br, sub808(NOTE[bass], BEAT * 0.7), b0 + 3.75 * BEAT, 0.0, 0.85)

    if not outro and not intro:
        arp = [freqs[0] * 2, freqs[1] * 2, freqs[2] * 2, freqs[1] * 2]
        for i, f in enumerate(arp):
            add(bl, br, pluck(f, 0.32, gain=0.95 if drop else 0.6),
                b0 + (0.5 + i * 0.75) * BEAT, 0.22 * (1 if i % 2 else -1), 0.9)

# ——— the filter opens: pain buffer is muffled, sweeping open into the turn ———
PL_f = spectral(PL, 620, "low")
PR_f = spectral(PR, 620, "low")
# crossfade the last half-bar into the unfiltered version = "the veil lifts"
sweep_start = int((TURN * BAR - BAR * 0.5) * SR)
sweep_end = int((TURN * BAR + BAR * 0.75) * SR)
w = np.zeros(N)
w[sweep_start:sweep_end] = np.linspace(0, 1, sweep_end - sweep_start)
w[sweep_end:] = 1.0
L += PL_f * (1 - w) + PL * w
R += PR_f * (1 - w) + PR * w

# transitions
add(L, R, riser(2.2), TURN * BAR - 2.2, 0.0, 0.85)      # into the turn
add(L, R, riser(1.6), DROP * BAR - 1.6, 0.0, 0.7)       # into the drop
for hit in (TURN, DROP, BREAKDOWN, 30):
    add(L, R, impact(), hit * BAR, 0.0, 0.6)

# ——— vinyl bed: ~4 pops/sec (v1 had ~70/s), lowpassed to warm clicks ———
pops = (rng.random(N) < 0.00009) * rng.normal(0, 1, N)
pops = np.convolve(pops, np.exp(-np.arange(90) / 30), mode="same")
pops = spectral(pops, 5200, "low") * 0.12
# a whisper of tape air, band-limited and only ~-66 dB, not broadband hiss
air = spectral(rng.normal(0, 1, N), 900, "low") * 0.0016
L += pops + air
R += np.roll(pops, 1279) + np.roll(air, 337)

# ——— master ———
L = L - np.mean(L)
R = R - np.mean(R)
# low-shelf: add a filtered copy back = more bass without burying the melody
L += spectral(L, 110, "low") * 0.22
R += spectral(R, 110, "low") * 0.22
# presence lift so the Rhodes/pluck sit above the sub on laptop speakers
L += spectral(spectral(L, 900, "high"), 5000, "low") * 0.35
R += spectral(spectral(R, 900, "high"), 5000, "low") * 0.35
# clear sub-rumble below hearing
L = spectral(L, 26, "high")
R = spectral(R, 26, "high")


def soft_limit(x, ceil=0.94):
    return np.tanh(x / ceil) * ceil


L, R = soft_limit(L * 0.52), soft_limit(R * 0.52)
fade_in = np.clip(t / 0.2, 0, 1)
fade_out = np.clip((DUR - t) / 1.8, 0, 1)
L *= fade_in * fade_out
R *= fade_in * fade_out

stereo = np.stack([L, R], axis=1)
pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")

out = "public/audio/enterprise-score.wav"
with wave.open(out, "wb") as w_:
    w_.setnchannels(2)
    w_.setsampwidth(2)
    w_.setframerate(SR)
    w_.writeframes(pcm.tobytes())

# ——— report: prove the noise bed is inaudible and the low end is present ———
bed = np.abs(pops + air)
bed_db = 20 * np.log10(max(np.sqrt(np.mean((pops + air) ** 2)), 1e-9))
mix_db = 20 * np.log10(np.sqrt(np.mean(stereo ** 2)))
low = spectral(L, 160, "low")
low_ratio = np.sqrt(np.mean(low ** 2)) / np.sqrt(np.mean(L ** 2))
print(f"wrote {out}  {DUR:.2f}s  {BARS} bars @ {BPM:.0f} BPM")
print(f"peak={np.max(np.abs(stereo)):.3f}  rms={np.sqrt(np.mean(stereo**2)):.3f} ({mix_db:.1f} dBFS)")
print(f"noise bed: {bed_db:.1f} dBFS  ({bed_db - mix_db:+.1f} dB vs mix)  pops/sec≈{0.00009*SR:.1f}")
print(f"low-end energy (<160 Hz): {low_ratio*100:.1f}% of total")
