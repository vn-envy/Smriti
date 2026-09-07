# Competitive position and recent architecture lessons

Evidence captured September 5, 2026. Popularity is a dated adoption signal, not a quality ranking. Local benchmark results are reported separately from the vendor claims below.

## What is actually live

GitHub main matches the local baseline commit a2afb3d (July 19). The most recent GitHub release is v0.3.0 (July 16), while source identifies itself as 0.3.2. The smriti-agents PyPI JSON endpoint returned 404. Both GitHub Pages and the documented Netlify site returned HTTP 200. There are no main-branch commits during August 5–September 5; later CI runs belong to other revisions. Therefore we cannot claim Smriti shipped architectural progress during the last month. Its June/July work includes retrieval profiles, observation gating, hardening and enterprise modules. Raw GitHub metadata and public-site responses are saved in `raw/`.

The baseline passes 85 core and 39 enterprise tests, ordinary package installation, quickstart, enterprise demo, and a real MCP 2.1.1 SDK session covering all six tools plus process restart. Additional probes expose cross-connection semantic-cache staleness, direct-write redaction bypass and chronological supersession errors. Passing the existing suite alone did not establish production readiness.

## Current comparison

| System | Verified current direction | What Smriti should learn | Defensible distinction |
|---|---|---|---|
| GBrain | Local PGLite default; Postgres for shared/large deployments; CLI/MCP, typed graph, synthesis and gap analysis | Operational doctor, explicit degraded-mode reporting, query-level evidence | Smaller Python/SQLite kernel rather than a broad personal/company brain |
| Graphify | Deterministic local AST graph for code; assistant/model processing for documents; extracted vs inferred edges | Explain each edge, preserve source locations, make code graph an optional evidence source | Temporal conversation/fact history is a different job from code structure |
| Mem0 | Open-source SDK plus managed platform; broad integrations, local store options | Mature integration surface, disciplined extraction, realistic fixed-budget comparison | Explicit inspectable temporal intervals and compact local storage; superiority unproven |
| Hindsight | Retain/recall/reflect; observations and Knowledge Pages; embedded or server deployment | Goal-aware session synthesis, progressive git/session ingest, stale-view refresh | A lighter kernel with customer-visible history and optional evidence controls |

Official sources: [GBrain architecture](https://github.com/garrytan/gbrain#architecture), [Graphify](https://github.com/Graphify-Labs/graphify), [Mem0](https://github.com/mem0ai/mem0), [Hindsight](https://github.com/vectorize-io/hindsight).

Recorded stars: Smriti 12; GBrain 29,602; Graphify 114,841; Mem0 64,727; Hindsight 22,662. Repository API snapshots are in `raw/*-repo.json`; these numbers do not establish which system is best.

## Claims to retire

- GBrain does **not** universally require an external Postgres server. Its current default is PGLite, with keyless keyword search available.
- Mem0 does **not** universally require Docker plus Postgres plus Qdrant. Distinguish SDK storage options and hosted tiers; do not describe all graph support as a paid-only feature without checking the selected edition.
- Hindsight is not restricted to a separately operated database/server: embedded deployment exists, though it still has model/runtime dependencies.
- The offline quickstart uses a scripted model to demonstrate full-mode behavior. That is not measured extraction quality from a real LLM.
- “History never rots,” “no bugs,” “every feature validated” and universal low-model-cost claims exceed the evidence. Preserve measured scope, corpus, hardware, model and mode in every numerical claim.

## What changed in the last month

**GBrain, September 2:** its official changelog reports a reranker-provider migration with visible degraded-mode status. Its LongMemEval retrieval-only evaluation reports 93.19% recall-all@5 without reranking and 95.32% with reranking; multi-query expansion falls to 54.89%. These are vendor-run retrieval metrics over 470 scored questions, not answer accuracy and not a Smriti comparison. The lesson is to ablate expansion and expose skipped components rather than assume extra retrieval improves results. [Changelog](https://github.com/garrytan/gbrain/blob/master/CHANGELOG.md)

**Hindsight, August 6:** Knowledge Pages and a unified coding-agent integration prioritize synthesized project knowledge. The release account describes an early per-prompt recall configuration performing worse than no memory, followed by session-start reflection and cached synthesis. Its coding benchmark measures correction rounds with deterministic tests and verifies that retrieved evidence actually reached the agent. Smriti should adopt that evaluation discipline before adding automatic context injection. These are vendor-reported experiments. [Release article](https://hindsight.vectorize.io/blog/2026/08/06/hindsight-0-9-0)

**Mem0, August–September:** current Python release v2.0.20 landed September 2; integration releases include Strands and DeepSeek in late August. The current README explicitly says its 94.4 LongMemEval / 92.5 LoCoMo numbers are managed-platform results with proprietary optimizations and a top-200 retrieval budget. They cannot be compared with Smriti's small-context oracle A/B or a local SDK run. [Releases](https://github.com/mem0ai/mem0/releases), [benchmark scope](https://github.com/mem0ai/mem0#new-memory-algorithm-april-2026)

**Graphify:** v0.9.54 appeared September 5, following frequent August releases. Its local AST extraction and explicit/inferred edge distinction provide a useful complementary code-memory input, not evidence it outperforms conversational systems on LongMemEval. [Releases](https://github.com/Graphify-Labs/graphify/releases)

**Research, August 28:** a systematic study of unanswerable questions finds memory benefits depend on representation and dataset shift; procedural/rule guidance can matter more than storing more experience. This suggests dedicated abstention and shift tests, rather than using an empty retrieval list as a substitute for answer reliability. [Paper](https://arxiv.org/abs/2608.27924)

**Research, August 30:** Hindsight Memory-PRM uses retrieval/citation trails and intervention-calibrated credit for memory operations and version chains. It is a separate research paper, not evidence about the Vectorize Hindsight product. Treat trainable memory policies as a later experiment; first capture trustworthy operation/evidence traces. [Paper](https://arxiv.org/abs/2608.29605)

## Recommended positioning

**Local agent memory that preserves what changed—and lets you inspect the evidence.**

Lead with transparent temporal behavior, portable SQLite storage, modest dependencies and agent interoperability. Target personal/desktop agents and embedded applications where operators want control and inspectability. Demonstrate late-arriving correction handling, current-versus-historical evidence, restart persistence and lineage-aware removal. Avoid positioning as a replacement for every hosted platform, code graph or agent runtime.

The current competitive advantage is a promising combination of constraints, not a proven accuracy lead. The highest-priority investment is trustworthy behavior plus comparable measurements; distribution and selective synthesis follow. ANN, an always-on autonomous brain and broad enterprise infrastructure should wait for workload evidence.
