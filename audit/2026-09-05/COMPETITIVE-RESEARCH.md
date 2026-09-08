# Competitive position and recent architecture lessons

Evidence captured September 5–7, 2026. Popularity is a dated adoption signal,
not a quality ranking. Local measurements are reported separately from vendor
claims and are not directly comparable unless the dataset, model, judge, and
measurement boundary match.

## What is actually live

The public GitHub snapshot used for comparison is `a2afb3d` (July 19); the most
recent public GitHub release observed was v0.3.0 (July 16), while the source
candidate identifies as 0.3.2. The `smriti-agents` PyPI JSON endpoint returned
404 at this snapshot, so repository installation remains the documented path.
Both GitHub Pages and the documented Netlify site returned HTTP 200. Raw
metadata and public-site responses are saved in `raw/`.

The historical local candidate passed 169 tests across non-editable wheel and
source-distribution installations. The current installed-v7 candidate passes
276 offline core/enterprise tests with clean dependency checks; bounded Mira,
generalization, and corrected prior-tool reviews are recorded in
[verified results](VERIFIED-RESULTS.md). The original 30-second teaser/browser
preview was verified; the newly requested social film remains pending. These
checks describe local candidates, not a published release or deployment.

The independent growth evidence now includes a persistent GBrain lexical run at
100 and 1,000 documents with process-restart timing. It uses no embeddings and
does not establish parity with Smriti or Mem0; the raw run is
[`raw/independent-gbrain-growth.json`](raw/independent-gbrain-growth.json).

## Installation and operator boundary

The core package metadata is `smriti-agents` 0.3.2 and the optional enterprise
package is `smriti-enterprise` 0.1.0. Until a PyPI release is verified, install
from a checkout:

```bash
python -m pip install -e '.[dev]'
python -m pip install -e enterprise/
```

For a clean package check, build a wheel or source distribution and install it
outside the checkout. The verified candidate passed the combined core and
enterprise suite with:

```bash
PYTHONPATH=.:enterprise python -m pytest tests enterprise/tests --import-mode=importlib -q
```

`smriti-doctor --db memory.db` is read-only and reports integrity, schema,
counts, WAL mode, embedding dimensions, and whether embedder identity is
tracked. A legacy database with vectors but no identity requires explicit
adoption after the operator verifies the original embedder:

```python
from smriti import Smriti

Smriti(path="memory.db", embedder=embedder,
       adopt_legacy_embedder=True)
```

For MCP-managed stores, the equivalent one-time flag is
`smriti-mcp --adopt-legacy-embedder --db memory.db`.

Core JSON export/import preserves the core schema, embeddings, and supersession
chains. Enterprise governance metadata is outside that format. Enterprise
operators should use `EnterpriseSmriti.snapshot(path)` for a consistent SQLite
backup, or `enterprise_mem.build_pack(path, name=...)` with `verify_pack()` /
`open_pack()` for a checksummed, optionally signed, read-only knowledge pack.
Core JSON is not an enterprise governance backup format.

## Current comparison

| System | Verified current direction | What Smriti should learn | Defensible distinction |
|---|---|---|---|
| GBrain | Typed graph, synthesis and gap analysis; local PGLite default; optional Postgres deployments; CLI/MCP surfaces | Operational doctor, degraded-mode reporting, and query-level evidence | A smaller Python/SQLite kernel focused on inspectable temporal fact history rather than a broad personal/company brain |
| Graphify | Deterministic local AST graph for code; explicit versus inferred edges; assistant/model processing for documents | Preserve source locations and explain edge origin | Code structure is adjacent to, rather than a replacement for, conversational temporal memory |
| Mem0 | Open-source SDK plus managed platform, broad integrations, and multiple local storage options | Mature integrations, disciplined extraction, and fixed-budget same-judge comparisons | Explicit validity intervals and inspectable history are the focus here; cross-system superiority is unproven |
| Hindsight | Retain/recall/reflect, observations and Knowledge Pages; embedded or server deployment | Session synthesis, progressive ingest, stale-view refresh, and evidence-delivery checks | A smaller kernel with customer-visible history and optional evidence controls |

Official sources: [GBrain architecture](https://github.com/garrytan/gbrain#architecture),
[Graphify](https://github.com/Graphify-Labs/graphify),
[Mem0](https://github.com/mem0ai/mem0), and
[Hindsight](https://github.com/vectorize-io/hindsight).

Recorded stars in the dated repository snapshots were Smriti 12; GBrain 29,602;
Graphify 114,841; Mem0 64,727; Hindsight 22,662. These numbers describe
adoption signals only and do not establish which system is best.

## Claims to retire

- GBrain does **not** universally require an external Postgres server. Its
  observed default is local PGLite, with Postgres available for other
  deployments and keyless keyword search available.
- Mem0 does **not** universally require Docker plus Postgres plus Qdrant.
  Distinguish its SDK storage options, local setup, and managed tiers; do not
  describe all graph support as paid-only without checking the selected edition.
- Hindsight is not limited to a separately operated database/server; embedded
  deployment exists, though model and runtime dependencies remain.
- The offline quickstart uses a scripted model to demonstrate full-mode wiring
  and supersession. It is not measured extraction quality from a real LLM.
- “History never rots,” “no bugs,” “every feature validated,” and universal
  low-model-cost claims exceed the evidence. Preserve measured scope, corpus,
  hardware, model, and mode with every numerical claim.

## Recent architecture lessons

**GBrain, September 2:** the official changelog reports a reranker-provider
migration with visible degraded-mode status. Its LongMemEval retrieval-only
evaluation reports 93.19% recall-all@5 without reranking and 95.32% with
reranking; multi-query expansion falls to 54.89%. These are vendor-run retrieval
metrics over 470 scored questions, not answer accuracy or a Smriti comparison.
The useful lesson is to ablate expansion and expose skipped components.
[Changelog](https://github.com/garrytan/gbrain/blob/master/CHANGELOG.md)

**Hindsight, August 6:** Knowledge Pages and a unified coding-agent integration
prioritize synthesized project knowledge. Its release account describes an
early per-prompt recall configuration performing worse than no memory, followed
by session-start reflection and cached synthesis. Its coding benchmark checks
that retrieved evidence reached the agent. Smriti should apply that evaluation
discipline before adding automatic context injection. These are vendor-reported
experiments. [Release article](https://hindsight.vectorize.io/blog/2026/08/06/hindsight-0-9-0)

**Mem0, August–September:** the Python release v2.0.20 landed September 2, and
the current README labels its 94.4 LongMemEval / 92.5 LoCoMo figures as managed
platform results with proprietary optimizations and a top-200 retrieval budget.
Those figures cannot be compared with Smriti's oracle retrieval run or local SDK
diagnostic. [Releases](https://github.com/mem0ai/mem0/releases) ·
[benchmark scope](https://github.com/mem0ai/mem0#new-memory-algorithm-april-2026)

**Graphify:** v0.9.54 appeared September 5. Its local AST extraction and
explicit/inferred edge distinction are useful as a complementary code-memory
input, not evidence that it outperforms conversational systems on LongMemEval.
[Releases](https://github.com/Graphify-Labs/graphify/releases)

**Research, August 28:** a systematic study of unanswerable questions finds
memory benefits depend on representation and dataset shift. This supports
dedicated abstention and shift tests instead of treating an empty retrieval list
as answer reliability. [Paper](https://arxiv.org/abs/2608.27924)

**Research, August 30:** Hindsight Memory-PRM uses retrieval/citation trails and
intervention-calibrated credit for memory operations and version chains. It is a
separate research paper, not evidence about the Vectorize Hindsight product.
Treat trainable memory policies as a later experiment; first capture trustworthy
operation and evidence traces. [Paper](https://arxiv.org/abs/2608.29605)

## Final-film source recheck — September 8

Root rechecked the official repositories before locking launch claims.
[Hindsight](https://github.com/vectorize-io/hindsight#recall) also describes
semantic, keyword, graph, and temporal retrieval, with retained evidence behind
observations. [Mem0](https://github.com/mem0ai/mem0#new-memory-algorithm-april-2026)
also describes fused retrieval and temporal reasoning; its managed benchmark
scope remains distinct from the local OSS configuration tested here. Smriti's
four streams explain its design, but do not establish architectural novelty.
The defensible emphasis is the focused implementation and observable behavior
under disclosed conditions. See the [root claim review](raw/final-film-market-claims-review.json).

## Recommended positioning

**Local agent memory that preserves what changed—and lets you inspect the evidence.**

Lead with transparent temporal behavior, portable SQLite storage, modest
dependencies, and agent interoperability. Target personal/desktop agents and
embedded applications where operators want control and inspectability. Show
late-arriving correction handling, current-versus-historical evidence, restart
persistence, lineage-aware removal, and the operator backup boundary.

The current advantage is a promising combination of constraints, not a proven
accuracy lead. The highest-priority work is trustworthy behavior, comparable
measurements, and documentation that lets an operator reproduce them. ANN,
always-on autonomous behavior, broad connectors, and enterprise-scale serving
should wait for workload evidence.
