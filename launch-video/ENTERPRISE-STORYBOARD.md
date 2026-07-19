# SMRITI Enterprise — film storyboard & render guide

**85.33s · 1920×1080 · 30fps · 2560 frames · 90 BPM grid**

Two acts: **the pain** (kinetic typography, minor key, muffled) → **the turn** (filter opens, major chord) → **the solve** (product demo, bright, the drop).

Bright studio palette, Apple-keynote pacing, hip-hop score. Every cut lands on a beat: 20 frames = 1 beat, 80 frames = 1 bar, and the scene map in `src/enterprise/etheme.ts` is the same grid the score generator uses. Measured drift between audio and video: **0 ms**.

## Render

```bash
cd launch-video
npm install                     # if node_modules is stale
python3 scripts/make-enterprise-audio.py     # regenerates the score (deterministic)
npx remotion studio                          # preview / scrub
npx remotion render SmritiEnterprise out/smriti-enterprise.mp4 --concurrency=4
```

Web-optimized version for X / Product Hunt:

```bash
npx remotion render SmritiEnterprise out/smriti-enterprise-web.mp4 \
  --codec=h264 --crf=23 --pixel-format=yuv420p
```

A square cut for feeds — add a composition with `width={1080} height={1080}` reusing `SmritiEnterpriseVideo`, or crop in post.

## Beat map

| # | Scene | Frames | Time | Bars | Beat |
|---|---|---|---|---|---|
| 1 | `open` | 0–160 | 0.0–5.3s | 2 | logo snaps in on the downbeat, gradient rule wipes |
| **ACT I — the pain** ||||| *music: minor, lowpassed to 620 Hz, sparse* |
| 2 | `pain` | 160–480 | 5.3–16.0s | 4 | "MARCH 3" → "What did your agent know?" → five overheard fragments land at angles → **"WE DON'T KNOW"** in red |
| 3 | `cost` | 480–640 | 16.0–21.3s | 2 | three rubber stamps thump down: AUDIT · ERASURE · RESIDENCY, then *"Most memory layers answer: 'trust us.'"* struck through |
| **THE TURN** ||||| *filter opens, major resolution + impact* |
| 4 | `solve` | 640–720 | 21.3–24.0s | 1 | white wipe clears everything → "Memory you can prove." → wordmark |
| **ACT II — the solve** ||||| *bright, full groove* |
| 5 | `temporal` | 720–1040 | 24.0–34.7s | 4 | two clocks: world 2026-06-01 vs knowledge 2026-07-10 |
| 6 | `core` | 1040–1360 | 34.7–45.3s | 4 | **the drop** — three.js memory core, shards lock into a lattice |
| 7 | `receipts` | 1360–1680 | 45.3–56.0s | 4 | receipt fields type in, tamper flashes red, chain verifies green |
| 8 | `hold` | 1680–1920 | 56.0–64.0s | 3 | erase button → shield → `HeldError` |
| 9 | `packs` | 1920–2240 | 64.0–74.7s | 4 | signed pack seal, three stores fuse into one RRF ranking |
| 10 | `stats` | 2240–2400 | 74.7–80.0s | 2 | spec sheet: 124 tests · 0 deps · 1 file · 100% Apache |
| 11 | `end` | 2400–2560 | 80.0–85.3s | 2 | wordmark, claim, URLs |

The score is built from the same bar numbers (`PAIN_START=2, TURN=8, DROP=13, DROP_END=17, BREAKDOWN=28`): sparse intro, **the pain section rendered into its own buffer and lowpass-filtered at 620 Hz**, a 2.2s riser into the turn where the filter sweeps open on a resolved D-major chord, full-energy drop at bar 13 under the 3D hero, breakdown at 28, outro at 30. Verified drift between audio and video: **0 ms**.

## Score

`scripts/make-enterprise-audio.py` — pure numpy, deterministic, no samples, no licences:

- boom-bap kit: pitched-sine kick (down to 38 Hz with a sub layer), snare with body rather than fizz, hats high-passed at 6.5 kHz, layered claps on the drop
- 808 with glide + octave-down layer, minor through Act I, D major after the turn
- Rhodes stabs (additive partials + tine transient) and a pluck arpeggio
- tension pad under the pain section; **tonal** riser (v1's was white noise); impacts on bars 8, 13, 28, 30
- master: gentle low shelf at 110 Hz, presence lift at 0.9–5 kHz, 26 Hz high-pass, soft limiting

**v2 audio fixes:**

| Issue | Cause | Fix |
|---|---|---|
| noise across the whole track | a constant broadband `hiss` layer at every sample | removed; replaced with band-limited air at ~-66 dB |
| crackle overdone | pop density 0.0016 ≈ **70/sec** (frying, not vinyl) | 0.00009 ≈ **4/sec**, lowpassed to 5.2 kHz so pops are warm clicks |
| noisy risers | riser was mostly white noise | rebuilt tonal: rising sine stack + air lowpassed at 4 kHz |
| thin low end | 808 and kick under-weighted | deeper kick, louder 808 with octave layer, low shelf; low band now ~69% of energy |

The generator prints its own QA line each run — noise-bed level relative to the mix, pops/sec, and low-end share. Change `BPM` here and in `etheme.ts` together; the grid is shared.

## 3D

`src/enterprise/ECore.tsx` — **all geometry is procedural**: icosahedron core with transmission/iridescence, three torus rings (the three time axes), 220 instanced octahedron "receipt shards" that fly in and lock into a verified shell. No downloaded models, no licence surface, no binaries in the repo — the same zero-dependency principle the product ships on.

## Files

```
src/enterprise/
  etheme.ts            bright palette, beat grid, scene map
  eui.tsx              Studio bg, Words, Card, Chip, StatBig, CutFlash, beat springs
  ECore.tsx            three.js hero (R3F + @remotion/three)
  EScenes.tsx          the nine scenes
  EnterpriseVideo.tsx  sequencing + audio + flash cuts
scripts/make-enterprise-audio.py
public/audio/enterprise-score.wav
```

Registered as composition **`SmritiEnterprise`** in `src/Root.tsx` alongside the original `SmritiLaunch`.

## Notes

- `npx tsc --noEmit` passes.
- Scenes use a few emoji (🌍 🧠 🛡️ 📦) — they render via Apple Color Emoji on macOS. If you ever render in Linux CI, install `fonts-noto-color-emoji` or swap them for SVG glyphs.
- Everything is a pure function of `frame`, so renders are byte-identical across machines.
