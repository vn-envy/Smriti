# Smriti social launch films

Both compositions are 60 seconds, 1920×1080, 30 fps. The original 30-second
teaser remains separate. Root built the social films, including the camera pass.

| Composition | Final local export | Direction |
|---|---|---|
| `SmritiSocial60` | `out/smriti-social-launch-60s-exact.mp4` | Original layouts and short fades |
| `SmritiSocialCamera60` | `out/smriti-social-launch-60s-camera-exact.mp4` | Motivated pushes, lateral reframing, eased pullbacks and 18-frame directional wipes |

A byte-identical preservation copy of the original is also saved as
`out/smriti-social-launch-60s-original.mp4`. Camera exports use different names
and do not modify the original composition or its export.

## Story and camera

- 0–5s: Sketch changes to Figma. Push toward the update after the opening settles.
- 5–11s: search, relationships and personalization introduce developer choices.
- 11–18s: pull back from the Smriti core into its local, temporal, inspectable proposition.
- 18–29s: reframe from the four evidence inputs toward their convergence, then return wide before the caption.
- 29–41s: push during the historical/current-tool change; pull back for the as-of query.
- 41–53s: a short push highlights 20.5ms; return wide and hold the entire comparison chart steady.
- 53–60s: settle into the closing identity and repository URL.

The supplied references informed the close-up → action → pullback → readable
hold rhythm. No reference footage or third-party branding is included. Motion is
frame-derived and deterministic; the original offers the quieter alternative.

## Reproduce

```sh
npm ci
npm run audio:social -- --assets-dir /path/to/user-assets
npm run typecheck
npm run stills:camera
npm run render:camera
```

FFmpeg/ffprobe must be on PATH. Local supplied media is deliberately ignored by
Git. The audio preparer expects the original filenames and folders documented
in `audit/2026-09-05/FINAL-LAUNCH-FILM-BRIEF.md` at the repository root. Its manifest
records source hashes, cue times and mixing settings. `render:camera` produces
its own raw MP4 and remuxes the video without re-encoding to exactly 60 seconds,
using the shared stereo mix. `render:social` explicitly regenerates the original
export; it is not part of the camera workflow.

## Evidence in the picture

20.474ms / 66.268ms / 381.298ms are the measured Smriti / GBrain semantic /
Mem0 OSS p50 warm-retrieval times at 36,500 synthetic records. The chart uses a
zero-origin linear scale. The on-screen qualifiers disclose local synthetic data,
20 queries, Apple M5, the same nomic model, pinned configurations and Mem0
`infer=False` with Qdrant. These are retrieval latencies, not answer speed or
quality rankings. The tool-history scene illustrates the bounded installed-v7
Leila/Cedar check. See the audit directory for raw results and limitations.
