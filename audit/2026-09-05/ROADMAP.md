# Smriti: evidence-led build roadmap

Status checked 2026-09-07. Baseline: GitHub main `a2afb3d` (core 0.3.2,
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

## Phase 1 — Correctness and installation (P0, complete for current candidate)

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
The candidate is verified locally; it is not yet published to PyPI or deployed.

## Phase 2 — Reproducible evaluation (P0, in progress)

- [x] Pin versions, data hashes, runtime and retrieval configuration for the
  completed synthetic and oracle tracks; retain raw per-query results and errors.
- [x] Run a matched raw-document diagnostic against simple lexical retrieval,
  local Mem0, and keyless GBrain. Results use different embedding/search
  configurations and remain diagnostic rather than a quality ranking.
- [x] Run the bounded paired LongMemEval-S public50 retrieval route with the
  same selected IDs, dataset hash, nomic embedding, retrieval budgets, and
  failure-inclusive denominator. Smriti and Mem0 each completed 48/50; the
  results do not establish superiority.
- [x] Measure targeted Smriti temporal correctness independently of answer-model
  skill, including stale facts and late arrivals. Broad abstention and full
  multi-hop quality still need representative evaluation.
- [~] Fix benchmark methodology: seeded corpus, accurate storage including WAL,
  correct CLI parsing, no label leakage, and explicit error denominators are in
  the current harness; embedding parity and process-boundary reporting still
  need to be completed for growth comparisons.
- [ ] Run LongMemEval full-history and LoCoMo with one shared answer/judge
  configuration. The 500-question oracle run bypasses extraction and answer
  generation, so it is evidence-only and not full-haystack QA.

The independent GBrain persistent run now covers 100 and 1,000 documents with
process-restart timing and a lexical, no-embedding configuration; see
[`raw/independent-gbrain-growth.json`](raw/independent-gbrain-growth.json).
This improves the measurement boundary over the earlier single-checkpoint CLI
run, but it still does not establish embedding-parity speed or cost. The current
Smriti/Mem0 growth artifacts also use different effective embedding setups.

Exit: reproducible local results for executable tracks; missing services/models
are marked unmeasured, never scored as zero or replaced by mocks. Full
model-backed comparison remains unfinished until actually executed with a fixed
reader and judge.

The paired public50 review found a multi-session recall gap (Smriti 0.6111,
Mem0 0.7407 across nine questions) and seven questions with fewer than five
unique returned sessions. This is a follow-up hypothesis about session
diversity, chunk allocation, and truncation, not an accepted superiority claim;
the raw review is [`raw/multi-session-gap-review.json`](raw/multi-session-gap-review.json).

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
   old database layouts. Targeted temporal journal corrections pass; this broader
   contract remains a priority.
3. **Selective retrieval:** session-start synthesis and on-demand recall with
   cache invalidation; compare against no memory and a simple text/wiki baseline.
   Avoid injecting unrelated memory on every turn.
4. **Useful graph edges:** typed explicit/inferred relationships and provenance;
   add richer graph traversal only if it improves multi-hop workload accuracy.
5. **Scaling:** evaluate 768/1536-dimension embeddings, interleaved writes, and
   concurrency before adding optional ANN/quantization. Preserve an exact-search
   oracle for recall regression checks. The new persistent GBrain run is useful
   context, but matched Smriti/Mem0/GBrain growth and cost evidence is still open.
6. **Distribution:** reliable agent integration and import/export first; hosted
   multi-tenant service, broad connectors, and a proprietary runtime are separate
   product decisions.

The current documentation records completed evidence without closing these
engineering priorities. Each future feature requires workload evidence, tests,
and a stated migration boundary before it is described as shipped.
