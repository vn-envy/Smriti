# SMRITI

**Structured Memory with Reflective Indexing and Temporal Inference**

*smriti* (स्मृति): Sanskrit for "that which is remembered."

A zero-infrastructure, local-first, Apache-2.0 memory layer for AI agents. One SQLite file. No Neo4j, no Postgres, no Docker, no cloud account, no paywalled tiers. Stdlib HTTP + numpy is the entire dependency surface.

```python
from smriti import Smriti, LLM, OllamaEmbedder

mem = Smriti(path="memory.db",
             embedder=OllamaEmbedder("nomic-embed-text"),
             llm=LLM("qwen3:14b", provider="ollama"))

mem.add([{"role": "user", "content": "I moved to Bengaluru on June 1st."}],
        timestamp="2026-06-02T10:00:00Z")

print(mem.context("where do I live?"))
# KNOWN FACTS:
# - [2026-01-15 | SUPERSEDED on 2026-06-01] The user lives in Hyderabad.
# - [2026-06-01 | CURRENT] The user lives in Bengaluru.
```

## Why another memory layer

Every recent open framework made a bet, and each bet has a documented cost:

| Framework | Their strength | The gap SMRITI closes |
|---|---|---|
| **GBrain** (Garry Tan, Apr 2026) | Self-wiring typed knowledge graph with **zero LLM calls** for extraction; production-proven at 146k+ pages | Requires Postgres + pgvector; you hand-author the markdown skills; no *as-of-date* validity model; coupled to OpenClaw / Hermes |
| **Supermemory** (local build) | Claims #1 on LongMemEval / LoCoMo / ConvoMem; one-binary local mode, RAG + connectors + embedded agent; the mature full-stack option | A large system you trust rather than read; "forgetting" and temporal handling are internal — you can't audit *why* a fact was dropped or which window applied |
| mem0 | Mature extraction pipeline, broad SDK, 90k+ devs | Flat fact store loses time; graph features sit behind the $249/mo Pro tier; local self-host wants Docker + Postgres + Qdrant; knowledge updates leave stale facts competing with fresh ones |
| Zep / Graphiti | Bi-temporal knowledge graph — the right *model* for "what was true when" | Heavy graph-database infrastructure; community edition deprecated; advanced features cloud-only |
| Letta / MemGPT | Self-managing memory tiers | You adopt a whole agent runtime, not a library; every memory op costs LLM inference |

SMRITI's synthesis: **keep Zep's temporal model and GBrain's entity graph, drop the database tax; keep mem0's extraction discipline, add supersession; race Supermemory on transparency rather than on a leaderboard.** One SQLite file, ~1.5k lines you can read in a sitting, validity windows printed into the context the model sees.

### Honest positioning

This is a feature/architecture argument, **not a benchmark claim**. SMRITI has not been run on the full benchmarks yet, so it cannot say it beats Supermemory's local build (which claims SOTA) or GBrain (production-proven). What it *can* say is verifiable by reading the code: single-file zero-infra, bi-temporal supersession surfaced to the model, four-channel fusion, and a shipped harness so you generate the score yourself. See `smriti-dashboard.html` for the full side-by-side, including the panel of competitor numbers to beat.

### Their strengths, challenged

Fairness cuts both ways — the gaps above are real, but the headline strengths deserve scrutiny too:

- **GBrain's "zero-LLM graph extraction"** isn't free; the cost moved to the operator. The graph self-wires only inside hand-authored markdown conventions, and facts that don't fit an existing skill require you to write a new skill. The 146k-page production proof is one single-tenant brain curated by its own author — the most motivated curator possible — and its headline accuracy (P@5 49.1%, R@5 97.9%) comes from BrainBench, a benchmark GBrain wrote for itself. SMRITI's lite mode is also zero-LLM at write time, without asking you to author structure first.
- **Supermemory's "#1 on three benchmarks"** is self-graded — own judge, own answer model, own splits, the standard vendor pattern by which everyone tops a leaderboard simultaneously. And the open local binary is days old; the production track record belongs to the closed cloud product, not the artifact you would actually run. "One binary, zero config" also means every memory decision is made for you, invisibly.
- **mem0's "90k developers"** is a distribution moat, not an architecture one. Maturity hasn't bought accuracy: third-party LongMemEval comparisons place it near 49% against Hindsight's 91.4%, and the graph tier that might close the gap is paid.
- **Zep's "right temporal model"** is right — SMRITI adopts it — but it is no longer practically open (community edition deprecated, advanced temporal features cloud-only), and the purpose-built temporal graph still lands mid-pack (~63.8%). The lesson SMRITI takes: the temporal model alone doesn't win; retrieval fusion does the rest.

## Architecture

Each stage carries its Sanskrit name — not branding, but borrowed precision. The Nyaya account of memory (**anubhava → samskara → smriti**: experience leaves impressions, recollection arises from impressions) *is* the write path; Vedanta's **badha** (sublation: a later cognition invalidates an earlier one without erasing that it occurred) *is* supersession. Full lexicon and the reasoning behind each term: [`NOMENCLATURE.md`](NOMENCLATURE.md).

```
WRITE PATH (consolidation at write time)
  session ──► episodic log · anubhava अनुभव  (append-only, embedded, FTS-indexed)
          └─► fact extraction · grahana ग्रहण  (1 LLM call / session)
                └─► conflict resolution · badha बाध :
                      tier 1: (subject, predicate) key collision  → supersede, 0 tokens
                      tier 2: semantic collision → 1 tiny arbitration call
                    facts are NEVER deleted — invalid_at + superseded_by
                    preserve full bi-temporal history (validity window = avadhi अवधि)
                fact store · samskara संस्कार

READ PATH (reflection at read time) · smarana स्मरण
  query ──► 4 channels in parallel:
              1. shabda  शब्द    BM25 (SQLite FTS5)        over facts + episodes
              2. artha   अर्थ    vectors                    over facts + episodes
              3. sambandha सम्बन्ध entity hop (graph-lite, padartha पदार्थ links)
              4. kala    काल    episodes nearest to dates in the query
        ──► Reciprocal Rank Fusion · sangama संगम
        ──► validity annotation (CURRENT / SUPERSEDED-on-date)
        ──► packed, provenance-rich context · prasanga प्रसंग
```

Two design decisions worth defending:

1. **Facts AND raw episodes are both first-class at retrieval time.** Extraction-only systems lose whatever the extractor missed; episode-only systems fumble knowledge updates. Fusing both gets the precision of consolidated facts with the recall safety net of raw evidence.
2. **Supersession, not mutation.** "Where do I live?" reads CURRENT facts. "Where did I live before March?" reads the validity windows. Same store, zero extra machinery, full audit trail.

### Modes

- **`lite`** (alias `laghu`, लघु — "light") — no LLM at write time at all. Episodic ingest + 4-channel hybrid retrieval. Near-zero cost, fully offline-capable, and retrieval-only hybrids are known to recover most of the benchmark value. Ideal default for high-volume agents.
- **`full`** (alias `purna`, पूर्ण — "complete") — adds fact extraction + write-time consolidation. One extraction call per session, arbitration calls only on semantic collisions. This is where knowledge-update and temporal-reasoning accuracy comes from.

## Install

```bash
pip install -e .          # from this repo
python -m pytest tests/   # 12 offline tests, no network or keys needed
python examples/quickstart.py
```

Works with any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, Groq, OpenRouter, hosted APIs) and any embedding endpoint (Ollama `/api/embed` or OpenAI-style `/embeddings`).

## Benchmarks

The harness ships in `bench/` for **LongMemEval** (ICLR 2025 — the de-facto standard: 500 questions over ~115k-token histories testing extraction, multi-session reasoning, temporal reasoning, knowledge updates, abstention) and **LoCoMo** (the benchmark behind mem0's published numbers).

```bash
# 1. get datasets (LongMemEval from HuggingFace, LoCoMo from GitHub)
python -m bench.download            # oracle + locomo (small, fast)
python -m bench.download --all      # every split, or name one: longmemeval_s

# 2. fast sanity pass on the oracle split, fully local
python -m bench.run --bench longmemeval --data data/longmemeval_oracle.json \
    --mode lite --limit 50 --answer-model qwen3:14b --judge-model qwen3:14b

# 3. the comparable number: full mode on longmemeval_s
python -m bench.run --bench longmemeval --data data/longmemeval_s_cleaned.json \
    --mode full --provider groq --api-key $GROQ_API_KEY \
    --memory-model llama-3.3-70b-versatile \
    --answer-model llama-3.3-70b-versatile --judge-model llama-3.3-70b-versatile

# 4. LoCoMo
python -m bench.run --bench locomo --data data/locomo10.json --mode full --limit 200
```

Output: overall accuracy, **per-question-type accuracy** (the honest view — temporal-reasoning and knowledge-update are where flat stores die), ingest/answer latency, and token counts, plus a full per-question JSONL for error analysis.

**Honesty section.** SMRITI has not yet been run on the full benchmarks — the harness exists precisely so the numbers come from your hardware, not from marketing. Published reference points to beat or match: Zep ~63.8% and Hindsight ~91.4% on LongMemEval vs. mem0's ~49%; mem0 reports J≈66.9 on LoCoMo. Vendor numbers use different judges, answer models, and splits, so the only comparison that counts is the one you run yourself with a fixed judge. Run lite and full modes side by side; report both.

## Repo layout

```
smriti/             core library
  store.py          SQLite bi-temporal store — anubhava + samskara (FTS5 + vectors)
  extraction.py     grahana: single-pass session → atomic facts
  consolidation.py  badha: ADD / SUPERSEDE / SKIP conflict resolution
  retrieval.py      smarana: 4-channel retrieval + sangama (RRF) + prasanga packing
  memory.py         public Smriti API (modes: lite/laghu, full/purna)
  embedder.py       Ollama / OpenAI-compatible / offline hash
  llm.py            OpenAI-compatible client + mock
bench/              pariksha: LongMemEval + LoCoMo runners, nyaya judge, CLI
tests/              offline test suite (mock LLM, hash embedder) — 12 tests
examples/           runnable quickstart
NOMENCLATURE.md     the full lexicon and why each term is load-bearing
smriti-dashboard.html  feature-level comparison dashboard (open in any browser)
smriti-landing.html    three.js landing page — the four rivers of sangama (vendor/three.min.js fallback included, works offline)
smriti-teaser.html     36-second self-contained launch teaser — open, it plays and loops; screen-record at 1080p or share the link
```

## Roadmap

### Shipped (research-driven builds)

Informed by Hindsight (observation paradigm), StructMem / MemGAS (multi-granularity, cross-event consolidation), and the multi-hop RAG literature:

- [x] Observation/summary layer — per-entity synthesized summaries (`refresh_observations`)
- [x] Observations additive + enumerate — own context section, list instances instead of asserting totals
- [x] Multi-granularity digests — per-`(subject, predicate)` enumerations for cross-entity aggregation
- [x] 2-hop entity traversal — graph-lite multi-hop over the entity table
- [x] Optional cross-encoder reranking channel — RRF + rerank (`reranker=`)
- [x] Iterative retrieval — LLM-seeded second pass for multi-hop (`search_iterative`)
- [x] Benchmark harness hardening — stratified `--sample`, `--question-type`, A/B (`bench/ab.sh`), DeepSeek preset

### Next (post-benchmark)

- [ ] Publish LongMemEval-S and LoCoMo numbers (lite + full, local + hosted; observations on/off)
- [ ] **Entity canonicalization** — confidence-scored alias merge at write time ("Rachel" / "my cousin Rachel" / "Rachel Smith" → one entity). Attacks the fragmentation that limits cross-entity aggregation. *(adapted from Codebase-Memory's resolution cascade)*
- [ ] **Recursive-CTE N-hop traversal** — replace Python 2-hop with arbitrary-depth traversal in pure SQL. *(Codebase-Memory technique)*
- [ ] **`sqlite-vec` ANN backend** — optional, fixes the O(N) vector scan past ~100k rows; falls back to numpy. Keeps single-file zero-infra.
- [ ] **Incremental observation refresh** — content-hash so only changed entities/predicates are re-summarized. *(XXH3 pattern from Codebase-Memory)*
- [ ] **MCP server** — typed memory tools (`recall`, `context`, `facts_about`, `timeline`, `why_superseded`) returning structured JSON, with a least-privilege/verification security posture for a tool that runs with the agent's permissions. *(design + security blueprint from Codebase-Memory)*
- [ ] Embedding-dimension guard (reject silent model swaps) + async ingest queue and batched embeddings
- [ ] Multi-user namespacing (`user_id` scoping) and concurrency-safe store

## License

Apache 2.0. Everything. No gated tiers — the temporal model, the entity graph, and the benchmark harness are the product.
