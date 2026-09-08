# Social launch films: root verification

Root personally built and reviewed the narrative social film and the separately
requested camera-motion version on 2026-09-08. Both preserve the supplied music
and SFX, four evidence streams, bounded Sketch-to-Figma example, and qualified
36,500-record retrieval chart. The original 30-second teaser is separate.

| Export | Duration | Frames | Format | SHA-256 |
|---|---:|---:|---|---|
| Original social film | 60.000s | 1800 | 1920×1080, 30fps, H.264/AAC | `fac8e1534bc8b0a06bffcf1b3be8fbbc18c78291a7869c4d3c81870f8832b273` |
| Camera-motion version | 60.000s | 1800 | 1920×1080, 30fps, H.264/AAC | `1a7d3aa9090231bc61cbd3addc369ffc8469cd3a3928ea810ce298f3a220f545` |

Both the original export and its explicit `-original.mp4` preservation copy
remain byte-identical to the original hash. The new composition is
`SmritiSocialCamera60`; its output is
`launch-video/out/smriti-social-launch-60s-camera-exact.mp4`.

The camera version adds eased pushes, lateral reframing and pullbacks motivated
by the tool update, four-stream convergence and current/as-of example. The
comparison chart stays fixed for reading. Directional 18-frame wipes replace
8-frame crossfades in the camera version only. Reference contacts were inspected
for their action-close-up, pullback and readable-hold timing. Source scene
components are shared without changing the original composition.

TypeScript checks passed, 20 candidate stills rendered without browser errors,
and root inspected 32 sampled encoded frames, including transition boundaries,
close-ups, historical/current changes, chart and ending. Close-up framing was
widened after review. A final stream-camera timing correction pulls back before
the footer; that corrected encoded frame was inspected separately. The final
export fully decodes without errors. This is sampled visual QA, not an
assertion that every frame was watched at playback speed.

Both exports measure -16.59 LUFS integrated, -1.49 dBFS true peak, LRA 4.4,
48kHz stereo audio. Cue times are unchanged (typing 1.3s, reveal 11.2s, timeline
34s/37.2s, result 51s). Audio verification covers source hashes, cue alignment,
levels and decoding; it does not claim auditory listening.

See [camera receipt](raw/social-camera-export-review.json),
[original receipt](raw/social-original-export-review.json), and
[reproduction/storyboard](../../launch-video/SOCIAL-FILM.md). Video and supplied
source media remain local and ignored by Git; source and verification receipts
are included in the PR. No social publishing is performed.
