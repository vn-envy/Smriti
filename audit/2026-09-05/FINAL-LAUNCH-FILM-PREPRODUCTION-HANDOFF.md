# Final launch film — preproduction handoff

Prepared 2026-09-08 from the final brief at
[`FINAL-LAUNCH-FILM-BRIEF.md`](FINAL-LAUNCH-FILM-BRIEF.md). This is an inventory
only. Do not build or render the final film until the memory/comparative gates
close and root authorizes the next production step.

## Existing Remotion entry points

[`launch-video/src/Root.tsx`](../../launch-video/src/Root.tsx) registers three
compositions at 1920×1080 and 30 fps:

- `SmritiLaunch30`: 900 frames / 30 seconds. Preserve this verified teaser and
  its output [`out/smriti-launch-teaser-30s-exact.mp4`](../../launch-video/out/smriti-launch-teaser-30s-exact.mp4).
- `SmritiLaunch`: 3,300 frames / 110 seconds. The original dark narrative film,
  sequenced by [`src/Video.tsx`](../../launch-video/src/Video.tsx).
- `SmritiEnterprise`: 2,560 frames / 85.33 seconds. The bright beat-grid film,
  sequenced by [`src/enterprise/EnterpriseVideo.tsx`](../../launch-video/src/enterprise/EnterpriseVideo.tsx).

The new film should receive a new composition ID and preserve the existing
teaser composition/source unchanged. The brief proposes 60 seconds, with a
30/60/90 preference still optional; lock duration only after the reference
films' motion timing and supplied audio are reviewed.

## Reusable visual system

- [`src/theme.ts`](../../launch-video/src/theme.ts) is the dark paper/ink
  system: `C` palette, `F` font families, 30 fps timing, scene boundaries, and
  deterministic `mulberry32` randomness. Core colors are ink `#0B0F1C`, paper
  `#E9EDF6`, amber `#F4A43C`, teal `#52C7BE`, violet `#B794E0`, rose `#E08AA0`,
  merged `#FFD9A0`, and slate `#4A5570`.
- [`src/components/ui.tsx`](../../launch-video/src/components/ui.tsx) provides
  `Scene`, `FilmChrome` (vignette, grain, brand tag, progress bar), `TypeOn`,
  `Rise`, `Kicker`, `Deva`, `ramp`, and easing helpers. These are the default
  text/transition primitives for a dark narrative cut.
- [`src/enterprise/etheme.ts`](../../launch-video/src/enterprise/etheme.ts)
  provides the bright paper palette, matching font families, a deterministic
  90 BPM beat grid, and scene timing helpers.
- [`src/enterprise/eui.tsx`](../../launch-video/src/enterprise/eui.tsx) is a
  reusable studio typography kit: `Studio`, `Words`, `Kicker`, `Card`, `Chip`,
  `StatBig`, `Mono`, `Deva`, `CutFlash`, `Progress`, `BigType`, `Fragment`,
  `Stamp`, `Strike`, `TypeLine`, and `Brand`.
- [`src/fonts.ts`](../../launch-video/src/fonts.ts) loads the self-hosted
  Space Grotesk, Inter, JetBrains Mono, and Noto Sans Devanagari files under
  [`public/fonts`](../../launch-video/public/fonts). Keep Devanagari labels
  on this offline font path.

## Reusable 3D and shader assets

- [`src/teaser/LaunchTeaser30.tsx`](../../launch-video/src/teaser/LaunchTeaser30.tsx)
  contains the existing `MemoryWorld` R3F scene: four colored particle streams,
  a central icosahedral core, and amber/teal/violet torus rings. Its `Copy`
  component is the old teaser's text treatment. Reuse as a visual reference or
  embedded motif only after preserving the verified 30-second teaser.
- [`src/scenes/S3Reveal.tsx`](../../launch-video/src/scenes/S3Reveal.tsx)
  contains a deterministic `@remotion/three` cube-and-halo reveal over
  `@paper-design/shaders-react` `MeshGradient`. It supplies the one-file/
  inspectable-store reveal language.
- [`src/scenes/S6Sangama.tsx`](../../launch-video/src/scenes/S6Sangama.tsx)
  contains the production four-river scene: 4,200 seeded points, custom GLSL
  point shaders, deterministic camera drift, a confluence pulse, and the
  on-screen channel labels. The exact labels to preserve are:
  `shabda · शब्द` = `word · bm25` (lexical),
  `artha · अर्थ` = `meaning · vectors` (semantic),
  `sambandha · सम्बन्ध` = `relation · entity hop` (entity), and
  `kala · काल` = `time · date proximity` (temporal), converging as
  `sangama · संगम`. Do not rename, reorder, or collapse these four streams.
- [`src/enterprise/ECore.tsx`](../../launch-video/src/enterprise/ECore.tsx)
  contains the brighter procedural hero: a transmissive icosahedral core,
  three rotating time/lifecycle rings, and 220 instanced receipt shards that
  lock into a verified shell. It uses no downloaded 3D models.
- [`webgpu/preview.ts`](../../launch-video/webgpu/preview.ts) and
  [`public/webgpu-preview.html`](../../launch-video/public/webgpu-preview.html)
  are a separate browser WebGPU preview, not a Remotion composition. Reuse its
  four-stream/core idea only if a browser capture is explicitly needed; the
  final export should remain deterministic Remotion/R3F.

## Narrative mapping and evidence constraints

The final brief's motion-studio arc is: developer pain and infrastructure tax;
four evidence streams into a local inspectable store; the validated
Sketch→Figma temporal transition with project boundary and retained history;
measured corpus-growth outcomes; then an invitation grounded in evidence.
Reusable scene candidates are `S1ColdOpen`/`S2InfraTax` for the opening tension,
`S3Reveal` for the store, `S5Badha` for supersession, `S6Sangama` for the four
channels, `S7Receipts` for measured receipts, `S8Honesty` for claim discipline,
and `S9EndCard` for the close. Enterprise `STemporal`, `SCore`, and `SReceipts`
are alternate bright treatments of the same ideas.

Copy must stay tied to terminal raw evidence. The 36,500-document results are
local synthetic corpus measurements; 30/90/365-day labels are 100-adds/day
corpus equivalents, not elapsed longitudinal observations. Local model/API
cost is shared across tested local routes; hardware, electricity, and operator
cost are unmeasured. Avoid universal accuracy, zero-defect, zero-cost,
autonomy, or competitor-superiority claims.

## Audio and source-asset constraints

Current repo audio is [`public/audio/score.wav`](../../launch-video/public/audio/score.wav)
and [`public/audio/enterprise-score.wav`](../../launch-video/public/audio/enterprise-score.wav),
generated by the deterministic scripts in [`launch-video/scripts`](../../launch-video/scripts).
The user-supplied reference films, music, and SFX remain local inputs listed in
the final brief. Inspect their timing, loudness, and clipping before storyboard
lock; do not copy unpublished source assets into Git. The final acceptance pass
must check type legibility, four-stream continuity, evidence qualifications,
audio loudness/clipping, beginning/middle/end frames, scene boundaries,
resolution, codec, synchronization, and a playable MP4.
