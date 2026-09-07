# Final social film — root scene plan

Preproduction draft, 2026-09-08. Root owns this film's implementation and review.
Final production follows the remaining comparative tests and claim review. This
plan does not certify the film, replace the completed 30-second teaser, or close
the memory-system goal. Provisional master: 60 seconds, 1920×1080, 30 fps.

## The story

An agent's memory grows, but its facts also change. Different memory products
emphasize search, relationships, personalization, and managed operation. Smriti
focuses on a small local memory core whose evidence, applicability, and changes
can be inspected. Show that focus through one actual transition and measured
retrieval behavior, rather than presenting an unproven accuracy victory.

The recurring visual object is a thin, translucent memory card. It starts as an
unstructured conversation fragment, becomes a dated fact, joins four evidence
streams, and ends as an inspectable historical record. Match cuts carry this
object between scenes so the film feels continuous.

## Picture and copy

| Time | Picture and motion | On-screen copy | Evidence / limit |
|---|---|---|---|
| 00–05 | One conversation card becomes a fast, layered stack. A new update moves forward; the older card remains visible behind it. Close camera, deliberate impact, then a readable hold. | **Your agent remembers.** → **Does it know what changed?** | An opening question about a developer problem, not a claim that competitors lose history. |
| 05–11 | Three restrained panels suggest search results, a relationship graph, and managed memory. Pull back to reveal an inspectable local record in the foreground. | **Search. Relationships. Personalization.** → **Our focus: memory you can inspect.** | Competitor-specific names or claims require the completed research review. These capabilities are not exclusive categories or unique Smriti inventions. |
| 11–18 | The record becomes a small faceted core over paper and ink. A single SQLite file label resolves beneath it. Four colored paths enter from the frame edges. | **Smriti** / **Local. Temporal. Inspectable.** | Portable SQLite core and explicit validity history are implemented; no hosted-service or deployment claim. |
| 18–29 | Four paths become legible, each briefly carrying its kind of evidence. They converge into one returned-context card. Camera motion settles while labels are read. | **Words. Meaning. Relations. Time.** / **Four paths to the evidence.** | Preserve shabda, artha, sambandha, kala. This illustrates lexical, vector, entity, and temporal retrieval; it does not claim every channel fires on every query. |
| 29–41 | A project:Cedar timeline shows Leila using Sketch on Jan 10 and switching to Figma on Mar 10. Drag the time cursor back and forth; the visible state follows it. Keep the old card in history. | **Then: Sketch.** / **Now: Figma.** → **The change stays visible.** | Reconstruct the actual installed-v7 facts. Label this a verified local example, not a representative benchmark. |
| 41–53 | Memory cards multiply into a corpus counter. Resolve to a large measured latency figure, then a simple comparison at the same corpus size. Give labels and configuration scope a stable hold. | **36,500 records.** / **20.5 ms median retrieval.** | Local synthetic warm-query measurement. Optional GBrain/Mem0 bars use the completed pinned configurations and exact values below. No year-long production or end-to-end answer-speed claim. |
| 53–60 | All four streams return to the core; the retained historical card stays visible. Finish on a quiet, strong brand frame with a repository invitation. | **Remember what changed.** / **Smriti** / **github.com/vn-envy/Smriti** | Invite developers to inspect and run the project. Do not imply the PR candidate is already released on PyPI. |

## Market framing checked against primary sources

The [root market-claim review](raw/final-film-market-claims-review.json)
confirms that Hindsight also uses four retrieval strategies and Mem0 documents
multi-signal retrieval and temporal reasoning. Use Smriti's four streams as
its recognizable visual identity and architecture explanation, without implying
competitors lack those capabilities. Lead with the focused SQLite core and
inspectable fact state/history. The opening panels describe overlapping product
priorities, not mutually exclusive categories.

## Evidence to carry into the composition

The temporal example uses Leila and `project:Cedar`, not a new invented
customer story. The persisted Sketch fact starts at `2025-01-10T12:00:00Z` and
ends at `2025-03-10T12:00:00Z`, with `superseded_by=2`. Figma starts at the
March boundary and remains active. The transition event is also retained.
See [raw installed result](extraction-tool-transition-installed-v7.json) and
[corrected independent review](raw/extraction-tool-transition-v7-corrected-review.json).
The original probe had a historical-assertion bug; the corrected review checks
the real persisted intervals without silently replacing the raw result.

At 36,500 synthetic records, measured warm-query p50 values are Smriti
20.474 ms, GBrain semantic 66.268 ms, and Mem0 OSS `infer=False` / local Qdrant
381.298 ms. Display rounding may use 20.5 / 66.3 / 381.3 ms, with a zero-origin
bar chart if all three are shown. Every bar must use the same linear scale.
Use a clear caption: **Local synthetic test · warm retrieval · pinned configs**.
The benchmark notes must identify the separate GBrain semantic track and the
frozen snapshots; these are not current-code or universal speed guarantees.
See [cost and speed report](cost-speed-projections.md).

If the film includes cost, say **Local model API spend: $0 for all tested
routes**. Hardware, electricity, and operator costs were not measured. Do not
present shared local API cost as a unique Smriti advantage. Corpus checkpoints
can be shown as record counts; avoid calendar labels in this short film.

LoCoMo's 27/50 versus 26/50 is not a demonstrated quality lead. LongMemEval's
64% Smriti score includes 20 abstention questions in a 50-question sample.
Neither is proposed as a headline. Final comparison results may refine the
positioning, but only after root review.

## Craft decisions

- Use the existing Space Grotesk, Inter, JetBrains Mono, and Noto Sans
  Devanagari fonts and paper/ink/amber identity. Keep teal, violet, and rose
  distinct so four channels remain visually traceable.
- Open on light paper with dark type, use the dark core reveal for contrast,
  and return to paper for the temporal example and measured results. The
  reference films inform clean layouts, focused UI close-ups, and type scale;
  their footage, brands, and exact compositions are not source material.
- Give each scene one dominant idea. Use large, short headlines; reserve a
  stable area for necessary measurement labels. Test downscaled readability,
  not only full-resolution stills.
- Use continuous object motion and a few decisive cuts. Avoid multiple text
  blocks entering simultaneously, constant camera drift behind small labels,
  or a rapid montage that makes the actual outcome unreadable.
- Keep the four streams in the established order: shabda, artha, sambandha,
  kala. Decorative particles may move continuously; labels and results need
  readable holds. No generated stock footage is necessary.
- Build a new composition and separate scene files. Preserve the existing
  `SmritiLaunch30` source and verified export unchanged.

## Reference motion sampled by root

Root inspected eight-frame contact sequences at quarter-second spacing from
approximately 00–02 seconds of `2A91Ayycc-S8put_.mp4` and 15–17 seconds of
`CUUcx351uoNp1a-5.mp4`. The first reveals three simple forms quickly against
substantial white space, then lets their motion settle. The second follows a
specific UI action with a close-up, pulls back to the response, and gives the
result room to develop. Apply the action → reveal → readable result pattern to
the temporal switch, rather than adding camera movement without a narrative
purpose. These samples inform pacing; they are not a full playback or audio
review, and do not establish exact source easing curves.

## Sound plan, not yet locked

Use the supplied Funky Launch Groove as the leading music candidate. Align
scene impacts to measured musical accents after inspecting its timing; do not
invent a BPM. Evaluate the supplied technology track for a short opening or
transition only if it forms a coherent mix. The source tracks have materially
different loudness, so a crossfade requires gain matching and headroom.

Use supplied keyboard typing briefly for the first factual update, a keypress
for the current-state change, and a notification for the resolved evidence
card. SFX should punctuate meaning rather than every word. The measured source
levels are recorded in [audio measurements](raw/final-film-source-audio-measurements.json).
A first-minute energy analysis found a dominant 0.5-second periodicity
(120 BPM candidate, with the expected 60 BPM ambiguity) and strong accents
near x.12 seconds. This gives a provisional beat-alignment reference, not a
listening-verified tempo; see [timing candidates](raw/final-film-funky-timing-candidates.json).
The final mix needs measured loudness, true-peak headroom, fade continuity, and
picture synchronization checks. This plan is not evidence of listening or a
finished audio mix.

## Production gate and delivery

After the remaining comparison outputs are terminal and independently
reviewed, lock the copy, inspect reference motion timing, assemble the audio,
and implement the new Remotion composition personally. Preview scene
boundaries and representative frames, render the complete film, inspect motion
and readability, verify audio and export metadata, and provide the playable
MP4 with reproducible composition source. User-supplied source media stays out
of Git.
