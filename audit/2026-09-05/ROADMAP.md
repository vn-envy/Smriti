# Smriti: evidence-led build roadmap

Status checked 2026-09-08. Baseline: GitHub main `a2afb3d` (core 0.3.2,
enterprise 0.1.0). The current candidate has completed the hardening and launch
film work described below. This document remains a build plan and status record,
not a release certificate or benchmark leaderboard.

## Product decision

Build a small, inspectable temporal-memory kernel for local agents: explicit
history, evidence provenance, predictable operation, and portable storage. Make
correctness and verifiability its reason to exist. Do not claim universal
superiority, zero bugs, or benchmark leadership without matching evidence.

The strongest current positioning is:

> **Local agent memory that preserves what changed—and lets you inspect the evidence.**

A single SQLite file and a small Python dependency surface remain useful, but
zero external database setup is no longer unique: GBrain has a local PGLite
default, Hindsight has embedded deployment, and Mem0 supports local stores.
Graphify addresses code structure rather than replacing conversational temporal
memory. Smriti's distinction is the focused combination of explicit validity
history, provenance, and a portable core.

## Phase 1 — Correctness and installation (P0, reopened pending temporal follow-up)

- [x] Fix historical fact insertion, including chronology and interval-chain
  consistency; preserve newer current state when older evidence arrives late.
- [x] Refresh semantic caches after writes through another connection; test
  concurrent readers/writers and rollback.
- [x] Apply redaction to all direct fact fields before embedding/persistence and
  validate configuration before side effects.
- [x] Make direct writes atomic and reject invalid model/vector configurations.
- [x] Preserve MCP profiles and validate stdio behavior with a real SDK client;
  return machine-readable structured results honestly.
- [x] Close the enterprise policy, hold, signed-receipt, and verified-pack
  checks exercised by the candidate; test core/enterprise integration together.
- [x] Verify clean wheel and source installs outside checkout, examples,
  dependency consistency, and persisted restart.

Exit evidence: the historical combined core/enterprise candidate passed **169
tests** after non-editable wheel installation on macOS Python 3.11 and Linux
Python 3.12, and after an isolated Linux Python 3.9 source-distribution install.
That count is retained for its original snapshot. A later working-tree
benchmark candidate passed **203 tests** in an installed-outside-checkout
verification with `pip check` clean; see
[`raw/benchmark-wheel-verification-203.json`](raw/benchmark-wheel-verification-203.json).
PR `9072c85` carries the portable temporary-path fix and all four CI checks
passed, including core/enterprise Python 3.9 and 3.12 jobs.
The temporal journal probes, extraction diagnostics, embedder identity checks,
doctor command, and MCP protocol checks are recorded in
[`VERIFIED-RESULTS.md`](VERIFIED-RESULTS.md) and [`core-hardening.md`](core-hardening.md).
The newer installed-candidate-224 artifact is retained at
[`raw/installed-candidate-224.json`](raw/installed-candidate-224.json), pending
the temporal follow-up and fresh installed-wheel rerun.
The candidate is verified locally; it is not yet published to PyPI or deployed.
The phase is reopened for the installed Mira review: the targeted probe reported
success, but the independent root review rejected the quality pass after finding
an unrelated same-date event invalidated Berlin's `lives_in` fact and a probe
substring assertion misread a structured Python/Rust preference. The original
evidence is preserved in [`raw/smriti-mira-root-review.json`](raw/smriti-mira-root-review.json);
the temporal/consolidation follow-up and a fresh installed-wheel rerun remain
open.

The historical installed scope candidate passed **261 tests** with `pip check` clean
from v5 core and v3 enterprise wheels. Offline scope checks are accepted. The historical
v3 named-Mira model-backed contract was rejected: independent review found the
named third party rewritten as `user`, a light-mode preference inheriting
`project:Atlas`, and an event date encoded as applicability scope. The raw run
and reviews are preserved in [`raw/installed-scope-candidate-261.json`](raw/installed-scope-candidate-261.json),
[`raw/smriti-mira-contract-v3-independent-review.json`](raw/smriti-mira-contract-v3-independent-review.json),
and [`raw/smriti-mira-full-scoped-contract-v3-corrected-review.json`](raw/smriti-mira-full-scoped-contract-v3-corrected-review.json).
The generic fix is installed offline. The subsequent v4 model-backed runtime is
terminal with failures: the direct facts preserve Mira as subject, leave the
light-mode preference unscoped, and retrieve current Rust for Atlas correctly,
but brittle `uses_tool`/Aurora assertions fail and an unsupported inferred
primary-Python fact remains. The model-backed acceptance gate therefore remains
open; this is installation evidence rather than phase completion.

The latest installed v7 candidate passes **276 tests** across the core and
enterprise suites offline, with `pip check` clean. Its scope guard checks
model-generated applicability scopes against the source and fact statement,
allows one bounded correction call, preserves the raw episode, and reports
unresolved candidates through the `add()`/MCP result plus detailed diagnostics.
This is an operational extraction safeguard, not a semantic quality claim;
explicit `add_fact()` writes remain trusted caller input. The bounded paired
LoCoMo50 answer/judge baseline is now complete on the frozen installed v4
candidate for both adapters: 50/50 questions and zero operational or cleanup
failures each; Smriti recorded 27/50 correct and Mem0 26/50. Independent review
verified the same selected IDs, gold labels, reader/judge models, and dataset,
with 24 questions correct for both, 21 for neither, 3 Smriti-only, and 2
Mem0-only; the exploratory question bootstrap for Smriti minus Mem0 was
[-0.06, 0.10]. This does not establish superiority because questions share
conversations, the bootstrap does not model that dependence, and the judge
labels include known errors such as `conv-30-q0`. The v7 operational safeguard is bounded-verified; remaining comparative QA
remains open.

A bounded installed-v7 Mira v5 rerun passes all 26 recorded assertions, and
independent review checked 8 extracted facts. This remains a bounded result rather
than a universal semantic claim: inferred Aurora applicability remains a
lexical/semantic limitation, and the single model-backed run is not a general
quality estimate. The installed-v7 scope guard and offline tests cover bounded
correction behavior; the v5 run itself made no real correction retry. The raw run
and review are preserved in
[`smriti-mira-full-scoped-contract-v5.json`](smriti-mira-full-scoped-contract-v5.json)
and [`raw/smriti-mira-v5-independent-review.json`](raw/smriti-mira-v5-independent-review.json).
The installed-v7 extraction generalization independently passes 8/8 checks:
Leila/Omar remain distinct active cities, Figma usage and the Sketch transition
both carry `project:Cedar`, global dark is unscoped, and user self-scope is empty.
A corrected offline review of the persisted v7 transition rows verifies Sketch
valid Jan 10 through Mar 10, superseded by active Figma from Mar 10, with the
historical transition retained; negative controls pass. The original raw v7
artifact remains unchanged and retains its obsolete historical-assertion failure
status. See [`raw/extraction-tool-transition-v7-corrected-review.json`](raw/extraction-tool-transition-v7-corrected-review.json).

## Phase 2 — Reproducible evaluation (P0, in progress)

- [x] Pin versions, data hashes, runtime and retrieval configuration for the
  completed synthetic and oracle tracks; retain raw per-query results and errors.
- [x] Run the matched raw-document diagnostic and the completed growth track.
  The final growth comparison uses the same Ollama `nomic-embed-text:v1.5`
  768-dimensional route for Smriti and local Mem0/Qdrant; GBrain is a separate
  lexical/no-embedding track with an explicitly maintained `ANALYZE` variant.
  These are speed/storage diagnostics, not a quality ranking. A separate
  independently reviewed GBrain nomic semantic growth run checked 100 queries
  and 500 relevant hits across the same five checkpoints with verified vector
  counts; it remains a synthetic retrieval/storage diagnostic with no
  answer-quality conclusion. See
  [`raw/gbrain-semantic-growth-independent-review.json`](raw/gbrain-semantic-growth-independent-review.json).
- [x] Run the bounded paired LongMemEval-S public50 retrieval route with the
  same selected IDs, dataset hash, nomic embedding, retrieval budgets, and
  failure-inclusive denominator. Smriti and Mem0 each completed 48/50; the
  results do not establish superiority.
- [~] Measure targeted Smriti temporal correctness independently of answer-model
  skill, including stale facts and late arrivals. The targeted probes are
  preserved, but the installed Mira root review rejected the quality pass after
  finding temporal/consolidation errors; broader abstention and full multi-hop
  quality still need representative evaluation.
- [x] Fix benchmark methodology: seeded corpus, accurate storage including WAL,
  correct CLI parsing, no label leakage, explicit error denominators, measured
  embedding parity, and process-boundary reporting are in the current harness.
  The matched growth artifacts cover 100, 1,000, 3,000, 9,000, and 36,500
  documents with durable partial outputs and per-query relevance evidence.
- [x] Run a bounded six-question LongMemEval-S answer/judge preflight for both
  adapters with the same reader/judge configuration. Smriti scored 4/6 overall
  (2/4 answerable; 2/2 `_abs` questions judged by the abstention heuristic) and
  Mem0 scored 3/6 (1/4 answerable; 2/2 `_abs` questions judged by the
  abstention heuristic); this is exploratory and does not close full QA.
- [x] Run the bounded Smriti LongMemEval-S50 answer/judge track with the shared
  frozen-v4 harness: 50/50 completed with zero operational and cleanup failures;
  32/50 recorded correct (64%), 14/30 answerable (46.67%), and 18/20
  abstention rows (90%). The selected sample is exploratory because 40% of its
  rows are abstention questions. The paired frozen-v4 Mem0 run uses the same
  harness, models, and budgets and is active.
- [ ] Run LongMemEval full-history and LoCoMo with one shared answer/judge
  configuration. The bounded paired LoCoMo50 answer/judge baseline is complete
  for frozen v4; paired LongMemEval-S50 full-history QA remains open pending the
  Mem0 side. The 500-question oracle
  run bypasses extraction and answer generation, so it is evidence-only and
  not full-haystack QA. Here “full-history” means that each selected question
  receives its complete haystack under the pinned retrieval/context budgets;
  it does not mean scoring every question in the source dataset.

A bounded paired LoCoMo50 answer/judge baseline completed from the immutable
installed v4 candidate: both adapters completed 50/50 questions with zero
operational or cleanup failures; Smriti recorded 27/50 correct (54%), 21/40
answerable correct (52.5%), and 6/10 abstention rows correct (60%), while Mem0
recorded 26/50 correct (52%). Independent review verified the same selected IDs,
gold labels, reader/judge models, and dataset: 24 questions were correct for
both, 21 for neither, 3 Smriti-only, and 2 Mem0-only. The exploratory question
bootstrap for Smriti minus Mem0 was [-0.06, 0.10]. These figures do not close
quality evaluation: questions share conversations, the bootstrap does not model
that dependence, and the recorded judge labels contain known errors including
`conv-30-q0`. Failure analysis classifies the Smriti failed answerable rows as 7
retrieved-supported reader failures, 11 missing-evidence failures, and 1
ambiguous case. Smriti's bounded LongMemEval-S50 side is also complete:
32/50 recorded correct (64%), 14/30 answerable (46.67%), and 18/20 abstention
rows (90%), with zero operational or cleanup failures. The 40% abstention share
makes this an exploratory sample rather than a broad accuracy estimate. The
paired frozen-v4 Mem0 run is active under the same harness, models, and budgets;
Smriti's total elapsed time was 3994.4346 seconds, with extreme host load
observed during the final question, so it is not a controlled speed comparison. GBrain held-out20
semantic retrieval QA and Hindsight comparative probes (20/12) remain pending.

The final matched growth report covers 100, 1,000, 3,000, 9,000, and 36,500
documents for Smriti and Mem0 with the same local Ollama nomic model and for a
separate lexical/no-embedding GBrain route. GBrain's maintained variant records
`executeRaw('ANALYZE')` time separately at each checkpoint; the untuned default
5,000-document cliff remains a separate raw observation. See
[`growth-matched-final-report.json`](growth-matched-final-report.json),
[`cost-speed-projections.md`](cost-speed-projections.md), and the rendered
[`charts`](charts/). Calendar labels are corpus equivalents under 100 adds/day,
not elapsed longitudinal observations. All three local routes use the same
local-model API cost of $0; hardware/electricity cost remains unknown.

Exit: reproducible local results for executable tracks; missing services/models
are marked unmeasured, never scored as zero or replaced by mocks. The bounded
growth speed/storage comparison is complete for these routes; the separate
GBrain nomic semantic growth artifact is complete as a retrieval/storage
diagnostic but excluded from the matched three-track report. The six-question
QA preflight and the bounded Smriti LongMemEval-S50 side are recorded, but full
model-backed quality comparison remains unfinished while the paired frozen-v4
Mem0 LongMemEval-S50 run is active and the remaining GBrain/Hindsight probes are
pending.

The paired public50 review found a multi-session recall gap (Smriti 0.6111,
Mem0 0.7407 across nine questions) and seven questions with fewer than five
unique returned sessions. This is a follow-up hypothesis about session
diversity, chunk allocation, and truncation, not an accepted superiority claim;
the raw review is [`raw/multi-session-gap-review.json`](raw/multi-session-gap-review.json).

The opt-in session-diverse read path is available for held-out ablations with
`memory.search(query, k=12, session_diverse=True, session_overfetch=3)` or the
equivalent `memory.context(...)` call. It is disabled by default, and the
iterative search/context APIs reject the option until a merged-result policy is
defined; keep `session_overfetch` bounded when measuring the ablation.

Facts now carry an optional persisted `scope` (for example
`project:Atlas`). An empty scope retains legacy unscoped behavior; scoped
conflict resolution keys on subject, predicate, and scope together. Scope is
applicability context, while the predicate carries the fact category, so a
project-specific programming-language state can coexist with a global
preference. Extraction leaves scope empty unless the statement establishes it.

## Phase 3 — Maintainable operator experience (P1, complete for current candidate; documentation kept current)

- [x] Public resource lifecycle (`close` and context manager), read-only doctor
  command, and actionable errors.
- [x] Embedder compatibility metadata and clear migration/re-embedding boundary,
  including explicit legacy adoption for pre-metadata databases.
- [x] Keep policy, storage, retrieval, and formatting behind small interfaces;
  refactor only with coverage and a measurable reason.
- [x] Align installation and competitive claims with live reality; distinguish
  source version, GitHub release, package availability, and website deployment.
- [x] Keep evidence receipts tied to returned context and distinguish operational
  controls from compliance guarantees.

Operator boundary: core JSON export/import is lossless for the core schema.
Enterprise governance metadata requires `enterprise_mem.snapshot()` or
`enterprise_mem.build_pack()` plus verification; core JSON is not an enterprise
governance backup format. Documentation commands and this boundary are kept in
the main README and competitive research record.

Exit: the installed candidate can be diagnosed, written, queried, restarted,
exported, and restored without hidden setup. A PyPI release and deployment are
separate distribution steps and are not implied by this phase.

## Phase 4 — Thirty-second launch film (P1, complete)

The teaser is exactly 30 seconds at 1920×1080, 30 fps, and 900 frames, with the
story conversations accumulate → an old fact becomes history → four retrieval
channels converge → portable, inspectable memory. The browser preview uses
Three.js `WebGPURenderer` with explicit WebGPU detection and a WebGL2 fallback;
Chrome reported `WEBGPU · ACTIVE`. See [`video.md`](video.md). The film makes no
accuracy or speed-superiority claim.

## Next architecture investments, gated by results

1. **Evidence and abstention:** returned source IDs, provenance, uncertainty, and
   query-specific abstention. Measure false-positive evidence and answer
   contamination before enabling defaults.
2. **Durable chronology:** normalized temporal types, same-time tie policy, late
   corrections, and precise system-known history; add migration tests from real
   old database layouts. Some targeted temporal journal corrections pass, but the
   installed Mira review keeps consolidation/extraction follow-up open; this
   broader contract remains a priority.
3. **Selective retrieval:** session-start synthesis and on-demand recall with
   cache invalidation; compare against no memory and a simple text/wiki baseline.
   Avoid injecting unrelated memory on every turn.
4. **Useful graph edges:** typed explicit/inferred relationships and provenance;
   add richer graph traversal only if it improves multi-hop workload accuracy.
5. **Scaling:** evaluate 768/1536-dimension embeddings, interleaved writes, and
   concurrency before adding optional ANN/quantization. Preserve an exact-search
   oracle for recall regression checks. The new persistent GBrain run is useful
   context; the matched growth and cost evidence is now recorded for the bounded
   local semantic and maintained lexical routes. Further scaling and concurrency
   work remains gated by workload evidence.
6. **Distribution:** reliable agent integration and import/export first; hosted
   multi-tenant service, broad connectors, and a proprietary runtime are separate
   product decisions.

The current documentation records completed evidence without closing these
engineering priorities. Each future feature requires workload evidence, tests,
and a stated migration boundary before it is described as shipped.

## Final social launch film — added user requirement

After memory-system and comparative validation, root will personally build a new narrative motion-studio launch film. It will use the supplied reference films, music and SFX, Smriti's four retrieval streams, and completed evidence to explain developer pain points, the product opportunity, and concrete outcomes. The existing verified 30-second teaser remains preserved.

- [ ] Finalize narrative and claims against completed comparisons.
- [ ] Root builds the composition, animation, and supplied audio mix.
- [ ] Render and validate timing, readability, motion, sound, and final export.

See [final film brief](FINAL-LAUNCH-FILM-BRIEF.md) and [preproduction inventory](FINAL-LAUNCH-FILM-PREPRODUCTION-HANDOFF.md). The provisional duration is 60 seconds, pending optional user preference. This new deliverable remains required before marking the overall goal complete.
