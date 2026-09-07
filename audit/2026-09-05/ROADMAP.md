# Smriti: evidence-led build roadmap

Audit started 2026-09-05; implementation continued 2026-09-06.
Baseline: GitHub main a2afb3d5f7d2b896585c91abb8bcce2f7c4a9585, core 0.3.2, enterprise 0.1.0.
User authorized continuing the build, with Sol implementing and the parent independently testing. New scope includes a 30-second Three.js/WebGPU launch video. This document is a plan, not proof of completion.

## Product decision

Build a small, inspectable temporal-memory kernel for local agents: explicit history, evidence provenance, predictable operation, and portable storage. Make correctness and verifiability its reason to exist. Do not claim universal superiority, zero bugs, or benchmark leadership without matching evidence.

The strongest current positioning is: **“Local agent memory that preserves what changed—and lets you inspect the evidence.”** A single SQLite file and a small Python dependency surface remain useful, but zero external database setup is no longer unique: GBrain now has PGLite, Hindsight has embedded PostgreSQL, and Mem0 supports local stores. Graphify addresses code structure rather than replacing conversational temporal memory.

## Phase 1 — Correctness and installation (P0, in progress)

- Fix historical fact insertion, including chronology and interval-chain consistency; preserve newer current state when older evidence arrives late.
- Refresh semantic caches after writes through another connection; test concurrent readers/writers and rollback.
- Apply redaction to all direct fact fields before embedding/persistence; validate configuration before side effects.
- Make direct writes atomic and reject invalid model/vector configurations clearly.
- Preserve MCP profiles and validate actual stdio behavior with a real SDK client; expose machine-readable results honestly.
- Close enterprise fail-open policy, hold, signed-receipt, and pack-verification gaps. Test core/enterprise integration together.
- Verify clean wheel and source installs outside checkout, examples, dependency consistency, and persisted restart.

Exit: all original and new regression tests pass on the combined source and non-editable package installs; independently reproduce original defects against baseline and verify fixes. No result inferred solely from an editable install or a mocked protocol handler.

## Phase 2 — Reproducible evaluation (P0, in progress)

- Pin versions, data hashes, runtime and retrieval configuration, report raw per-query results and errors.
- Run a matched raw-document retrieval track against simple lexical retrieval and real local Mem0; attempt real GBrain keyless setup and Graphify code extraction in their proper task categories.
- Measure Smriti temporal correctness independently of answer-model skill; include stale facts, late arrivals, abstention and multi-hop evidence.
- Fix benchmark methodology: seeded corpus, accurate storage including WAL, correct CLI parsing, no label leakage, explicit error denominators.
- Run LongMemEval full-history and LoCoMo with one shared answer/judge configuration once a suitable local or authorized paid runtime is available. Oracle split results and vendor headlines are not head-to-head results.

Exit: reproducible local results for executable tracks; missing services/models explicitly marked blocked or not measured, never scored as zero or replaced by mocks. Full model-backed comparison remains unfinished until actually executed.

## Phase 3 — Maintainable operator experience (P1)

- Public resource lifecycle (close/context manager), read-only doctor command, actionable errors.
- Embedder compatibility metadata and clear migration/re-embedding boundaries.
- Separate policy, storage, retrieval and formatting responsibilities with small interfaces; refactor only with coverage and measurable reason.
- Update installation and competitive claims to match live reality; distinguish source version, GitHub release, package availability and website deployment.
- Keep evidence receipts tied to actual returned context; distinguish operational controls from compliance guarantees.

Exit: fresh user can install, diagnose, write, query, restart, export and restore without hidden setup or unsupported promises. Documentation commands exercised verbatim.

## Phase 4 — Thirty-second launch film (P1, parallel)

Deliver an exactly 30-second 3D teaser and runnable preview using the existing site's design language, improved typography, motion and composition. Story: conversations accumulate → an old fact becomes history → four retrieval channels converge → portable, inspectable memory. Use real Three.js WebGPU support with explicit feature detection/fallback and report which renderer was tested. Produce a playable MP4, check duration/resolution and inspect representative frames. Avoid unverified accuracy or speed superiority claims in the film.

## Next architecture investments, gated by results

1. **Evidence and abstention:** returned source IDs, provenance, uncertainty and query-specific abstention. Measure false-positive evidence and answer contamination before enabling defaults.
2. **Durable chronology:** normalized temporal types, same-time tie policy, late corrections and precise system-known history; migration tests from real old database layouts.
3. **Selective retrieval:** session-start synthesis and on-demand recall with cache invalidation; compare against no memory and a simple text/wiki baseline. Avoid injecting unrelated memory on every turn.
4. **Useful graph edges:** typed explicit/inferred relationships and provenance; only add richer graph traversal if it improves multi-hop workload accuracy.
5. **Scaling:** evaluate 768/1536-dimension embeddings, interleaved writes and concurrency before adding optional ANN/quantization. Preserve an exact-search oracle for recall regression checks.
6. **Distribution:** reliable agent integration and import/export first; hosted multi-tenant service, broad connectors and a proprietary runtime are separate product decisions.

Do not treat this list as permission to ship every speculative feature without evaluation. “Perfect” is an aspiration; completion requires concrete verified behavior, not a universal defect-free claim.
