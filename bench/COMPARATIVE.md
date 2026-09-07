# Comparative benchmark

This is an evidence-retrieval benchmark, not an answer-quality leaderboard. It
uses a checked-in synthetic corpus, no private data, no answer model, and no LLM
judge. `smriti-episodes` and `mem0` both index the same payload without automatic
fact extraction. This matched track therefore measures raw-document retrieval;
it does not measure either product's full natural-language memory pipeline.

```bash
python3 -m bench.comparative --adapter smriti-episodes --out audit/2026-09-05/benchmark-smriti.json
python3 -m bench.comparative --adapter lexical --out audit/2026-09-05/benchmark-lexical-control.json
GBRAIN_BENCH_CLI=/path/to/gbrain/src/cli.ts python3 -m bench.comparative --adapter gbrain --out audit/2026-09-05/benchmark-gbrain.json
```

For mem0, create an isolated environment and install the version pinned in
`audit/2026-09-05/benchmark-manifest.json`. Set `MEM0_BENCH_CONFIG` to an
explicit local vector-store and embedder configuration, then run adapter
`mem0`. A missing configuration or dependency produces a `status=blocked` raw
JSON result and is never converted into a score.

Metrics exclude unanswerable queries from recall/MRR. `abstention_precision`
is strict: an adapter must return zero documents. That is intentionally hard
for retrievers and should not be confused with answer-layer abstention.

Graphify is a knowledge-graph construction library, an adjacent task without a
matched memory search API, so it is documented rather than assigned a forced
retrieval score. gbrain and Hindsight require their documented services/model
prerequisites; record failures as blockers instead of substituting mocks.
