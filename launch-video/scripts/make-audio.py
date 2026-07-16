#!/usr/bin/env python3
"""
Generates the SMRITI launch-film score: public/audio/score.wav

A tanpura-inspired drone in D (Sa–Pa), soft pentatonic chimes on scene
boundaries, and one deep confluence swell for the sangama hero shot.
Pure numpy — no dependencies beyond the standard scientific stack.
Deterministic: same file every run.
"""
import wave
import numpy as np

SR = 44100
DUR = 110.0
N = int(SR * DUR)
t = np.arange(N) / SR

rng = np.random.default_rng(2026)

# ————————————————— drone —————————————————
def partial(f, amp, vib_rate, vib_depth, phase):
    return amp * np.sin(2 * np.pi * f * t + vib_depth * np.sin(2 * np.pi * vib_rate * t + phase))

def drone_voice(f0, gain):
    out = np.zeros(N)
    for n in range(1, 11):
        amp = 1.0 / (n ** 1.55)
        # each partial breathes at its own slow rate (jvari-like shimmer)
        vib_rate = 0.05 + 0.028 * n
        vib_depth = 0.25 + 0.06 * n
        ph = float(rng.uniform(0, 2 * np.pi))
        out += partial(f0 * n * (1 + 0.0004 * (n - 1)), amp, vib_rate, vib_depth, ph)
    # gentle 5.5 Hz buzz on upper partials, very low level
    buzz = 0.05 * np.sin(2 * np.pi * f0 * 6 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 5.5 * t))
    return gain * (out + buzz)

D2, A2, D3 = 73.4162, 110.0, 146.832
droneL = drone_voice(D2 * 0.9995, 0.50) + drone_voice(A2 * 1.0004, 0.34) + drone_voice(D3, 0.14)
droneR = drone_voice(D2 * 1.0005, 0.50) + drone_voice(A2 * 0.9996, 0.34) + drone_voice(D3 * 1.0003, 0.14)

# slow swell of the whole drone (breathing)
breath = 0.86 + 0.14 * np.sin(2 * np.pi * 0.045 * t + 1.2)
droneL *= breath
droneR *= breath

# high shimmer (D5) that only appears mid-film
shimmer_env = np.interp(t, [0, 30, 55, 80, 100, 110], [0, 0.0, 0.35, 0.4, 0.1, 0])
shimmer = shimmer_env * 0.06 * np.sin(2 * np.pi * 587.33 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.9 * t))

# ————————————————— chimes on scene boundaries —————————————————
# scene starts (s): 8, 20, 34, 48, 64, 82, 94, 103
CHIME_NOTES = {
    8: 587.33,   # D5
    20: 493.88,  # B4  (tension: the tax)
    34: 880.00,  # A5  (reveal — bright)
    48: 659.26,  # E5
    64: 739.99,  # F#5 (badha resolution)
    82: 880.00,  # A5  (sangama)
    94: 587.33,  # D5
    103: 1174.66,# D6  (end card)
}

def bell(freq, at, gain=0.16, decay=2.6):
    i0 = int(at * SR)
    dur = min(N - i0, int(4.0 * SR))
    tt = np.arange(dur) / SR
    env = np.exp(-tt / (decay * 0.45))
    x = (
        1.0 * np.sin(2 * np.pi * freq * tt)
        + 0.42 * np.sin(2 * np.pi * freq * 2.756 * tt) * np.exp(-tt / (decay * 0.22))
        + 0.18 * np.sin(2 * np.pi * freq * 5.404 * tt) * np.exp(-tt / (decay * 0.11))
    )
    y = gain * env * x
    return i0, y

chimesL = np.zeros(N)
chimesR = np.zeros(N)
for k, (at, f) in enumerate(sorted(CHIME_NOTES.items())):
    i0, y = bell(f, at)
    pan = 0.35 if k % 2 == 0 else 0.65  # alternate gently L/R
    chimesL[i0:i0 + len(y)] += y * (1 - pan)
    chimesR[i0:i0 + len(y)] += y * pan

# ————————————————— confluence swell + boom (sangama flash ≈ 69.7s) —————————————————
BOOM_AT = 69.7
# noise swell rising into the flash
sw0, sw1 = int(66.5 * SR), int(BOOM_AT * SR)
noise = rng.standard_normal(sw1 - sw0) * 0.25
# cheap lowpass: cumulative smoothing
kernel = np.exp(-np.arange(400) / 120.0)
kernel /= kernel.sum()
noise = np.convolve(noise, kernel, mode="same")
swell_env = (np.linspace(0, 1, sw1 - sw0) ** 2.4) * 0.30
swell = noise * swell_env

boom_i = int(BOOM_AT * SR)
bt = np.arange(int(3.0 * SR)) / SR
boom = 0.4 * np.exp(-bt / 0.9) * np.sin(2 * np.pi * 55 * bt * (1 - 0.12 * np.exp(-bt / 0.25)))

fxL = np.zeros(N)
fxR = np.zeros(N)
fxL[sw0:sw1] += swell
fxR[sw0:sw1] += swell
fxL[boom_i:boom_i + len(boom)] += boom
fxR[boom_i:boom_i + len(boom)] += boom

# ————————————————— mix —————————————————
# narrative arc: quiet → build → peak at sangama → resolve
arc = np.interp(t, [0, 4, 20, 48, 64, 76, 90, 103, 106.5, 110],
                   [0, 0.62, 0.66, 0.72, 0.80, 0.88, 0.70, 0.62, 0.5, 0.0])

L = (droneL * 0.32 + shimmer + chimesL + fxL) * arc
R = (droneR * 0.32 + shimmer + chimesR + fxR) * arc

peak = max(np.abs(L).max(), np.abs(R).max())
L = L / peak * 0.30
R = R / peak * 0.30

stereo = np.empty(N * 2, dtype=np.int16)
stereo[0::2] = (L * 32767).astype(np.int16)
stereo[1::2] = (R * 32767).astype(np.int16)

import os
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "public", "audio"), exist_ok=True)
out_path = os.path.join(os.path.dirname(__file__), "..", "public", "audio", "score.wav")
with wave.open(out_path, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(stereo.tobytes())
print("wrote", out_path, f"{DUR}s @ {SR}Hz stereo")
