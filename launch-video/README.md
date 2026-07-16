# SMRITI — Launch Film

**"Memory that knows when."** · 1:50 · 1920×1080 · 30fps

A Remotion + three.js + Paper Shaders launch film for
[vn-envy/Smriti](https://github.com/vn-envy/Smriti), built from the repo's own
visual language: the teaser's palette and chrome, the landing page's
four-rivers confluence, and the NOMENCLATURE lexicon. Full scene-by-scene
narrative in [STORYBOARD.md](./STORYBOARD.md).

`smriti-launch-film.mp4` in this folder is a **preview render** (720p,
generated with the bundled pure-Python renderer — same storyboard, timing and
score, approximated fonts/shaders). The master below renders pixel-perfect
with the real Space Grotesk / JetBrains Mono / Devanagari type, WebGL paper
shaders, and the three.js scenes.

## Render the master (on your Mac)

```bash
cd launch-video
npm install          # also copies fonts into public/fonts (postinstall)
npm run dev          # open Remotion Studio — scrub, tweak, play
npm run render       # → out/smriti-launch.mp4 (1080p master)
```

Requires Node 18+. First render downloads Remotion's headless Chrome once.

## Anatomy

| File | What it is |
|---|---|
| `src/theme.ts` | Palette, fonts, **scene timing map** (edit beats here) |
| `src/Video.tsx` | Master timeline — nine `<Sequence>`s + film chrome + score |
| `src/scenes/S1ColdOpen.tsx` | "agents forget." typewriter over drifting motes |
| `src/scenes/S2InfraTax.tsx` | The infrastructure tower: stack, flicker, implosion |
| `src/scenes/S3Reveal.tsx` | three.js amber cube + Paper Shaders MeshGradient (deterministic via `speed={0}` + `frame`) |
| `src/scenes/S4WritePath.tsx` | anubhava → grahana → samskara pipeline |
| `src/scenes/S5Badha.tsx` | The supersession card — the product's soul |
| `src/scenes/S6Sangama.tsx` | Hero shot: four particle rivers → one confluence (ported from `smriti-landing.html`, pure function of frame) |
| `src/scenes/S7Receipts.tsx` | Measured numbers + MCP drop-in |
| `src/scenes/S8Honesty.tsx` | "the benchmark harness ships in the box" |
| `src/scenes/S9EndCard.tsx` | Logo, tagline, repo URL |
| `public/audio/score.wav` | Generated tanpura-style score (`scripts/make-audio.py`) |
| `scripts/render_preview.py` | Chrome-free preview renderer (numpy + PIL + ffmpeg) |

## Tweaking

- **Timing**: every beat lives in `SCENES` (`src/theme.ts`) and per-scene
  local frame numbers. 30fps → frame = seconds × 30.
- **Copy**: all text is plain JSX in the scene files.
- **Score**: regenerate with `python3 scripts/make-audio.py` after editing
  chime notes / arc (scene-boundary seconds are listed in the script).
- **Determinism**: everything is a pure function of `useCurrentFrame()` —
  paper shaders use `speed={0} frame={ms}`, all randomness is seeded
  (`mulberry32`). Renders are reproducible.
- **Vertical cut**: scenes are centered compositions; a 9:16 variant is mostly
  a second `<Composition>` with adjusted font sizes and label positions.

## Preview renderer (what made the mp4 here)

```bash
python3 scripts/render_preview.py --start 0 --end 3300   # frames
ffmpeg -framerate 30 -i scripts/frames/f%05d.jpg -i public/audio/score.wav \
  -c:v libx264 -crf 22 -pix_fmt yuv420p -c:a aac -shortest preview.mp4
```

Useful when there's no Chrome around (CI sanity checks, remote boxes).
