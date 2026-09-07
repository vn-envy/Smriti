# Cost and speed over time

These are bounded corpus-growth simulations. They are not calendar-long
observations. The 30/90/365-day workload model below assumes 100 adds/day and
the stated retrieval count/day. Arithmetic interpolation is used only as a
clearly labelled illustration between measured checkpoints; it is not a
performance prediction across an observed query-plan cliff.

The measured local routes have observed paid model/API cost of `$0`. That is
not total cost: electricity, hardware, hosting, and operator time were not
measured. Model cache bytes are excluded. Successful model calls/tokens and
failed-attempt usage are unknown where the installed embedding clients expose
no counters.

## Measured speed and storage

All Smriti and mem0 rows use the same five-topic synthetic corpus and ten timed
warm queries, with relevant, nonempty results verified. Independent gbrain
uses 20 timed queries at 100/1,000 documents and 10 at 5,000. Smriti and mem0 cold rows are
same-process client/database reopens; gbrain cold rows are process restarts.
The mem0 row is explicitly BGE-small, not nomic. The gbrain row is a separate
lexical keyword track with no embedding. Raw artifacts are the source of truth.

| Adapter/configuration | Docs | Warm samples | Incremental ingest | Same-payload update | First query | Cold query | Warm p50 / p95 | Storage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Smriti lite + HashEmbedder | 100 | 10 | 19.853 ms | 0.013 ms | 0.472 ms | 0.207 ms | 0.117 / 0.130 ms | 0.319 MB |
| Smriti lite + HashEmbedder | 1,000 | 10 | 184.888 ms | 0.013 ms | 0.333 ms | 0.374 ms | 0.240 / 0.308 ms | 1.827 MB |
| Smriti lite + HashEmbedder | 5,000 | 10 | 881.305 ms | 0.013 ms | 0.652 ms | 0.634 ms | 0.537 / 0.853 ms | 8.466 MB |
| mem0 OSS + FastEmbed BAAI/bge-small-en-v1.5 384d + Qdrant | 100 | 10 | 526.898 ms | 5.769 ms | 6.011 ms | 68.466 ms | 3.535 / 5.557 ms | 0.603 MB |
| mem0 OSS + FastEmbed BAAI/bge-small-en-v1.5 384d + Qdrant | 1,000 | 10 | 5,487.921 ms | 6.276 ms | 16.981 ms | 87.824 ms | 13.855 / 16.290 ms | 5.383 MB |
| mem0 OSS + FastEmbed BAAI/bge-small-en-v1.5 384d + Qdrant | 5,000 | 10 | 24,087.989 ms | 6.295 ms | 70.294 ms | 116.826 ms | 46.365 / 50.461 ms | 26.584 MB |
| gbrain PGLite persistent engine, lexical/no embedding | 100 | 20 | 292.642 ms | — | 11.620 ms | 14.381 ms | 1.203 / 2.928 ms | 44.180 MB |
| gbrain PGLite persistent engine, lexical/no embedding | 1,000 | 20 | 2,019.193 ms | — | 11.450 ms | 15.745 ms | 2.859 / 5.962 ms | 45.695 MB |
| gbrain PGLite persistent engine, lexical/no embedding | 5,000 | 10 | 15,767.901 ms | — | 1,578.239 ms | 1,634.398 ms | 1,516.268 / 1,613.560 ms | 69.321 MB |

Sources: [Smriti hash schema-2 run](./growth-smriti-hash-schema2.json),
[mem0 BGE schema-2 run](./growth-mem0-bge-schema2.json),
[independent gbrain 100/1,000 run](./raw/independent-gbrain-growth.json), and
[independent gbrain 5,000 run](./raw/independent-gbrain-5000.json). The gbrain
5,000 latency increase reproduced independently; it is retained as an
observed default checkpoint, not generalized as an intrinsic scaling law. A
separate diagnostic used the pinned public engine's `executeRaw('ANALYZE')` on
a copy of the 5,000-document database. Maintenance took 231.911 ms; warm p50
changed from 3,613.562 ms before maintenance to 13.289 ms after it, with the
same relevant ranked slugs. A fresh process on the analyzed copy retained the
improvement (startup 372.3 ms, first query 28.664 ms, subsequent queries
7.17–11.64 ms), so this is a separately labelled maintained variant rather
than a cache-only effect. The default and maintained rows must remain separate;
the diagnostic was one ordered, non-isolated run.

## Bounded 30/90/365-day interpolation

At 100 adds/day, 30/90/365 days imply 3,000/9,000/36,500 documents. Only the
3,000-document target is inside the measured 1,000–5,000 interval. The values
below are arithmetic interpolation, not additional measurements. Values for
9,000 and 36,500 are intentionally reported as outside the measured range.

| Track | Target corpus | Warm p50 | Warm p95 | Storage | Bound |
|---|---:|---:|---:|---:|---|
| Smriti Hash | 3,000 | ~0.391 ms | ~0.579 ms | ~5.147 MB | interpolated between 1k and 5k |
| mem0 BGE | 3,000 | ~29.546 ms | ~33.376 ms | ~15.974 MB | interpolated between 1k and 5k |
| gbrain lexical | 3,000 | — | — | — | not projected; the measured 1k–5k cliff makes linear interpolation unsuitable |
| All tracks | 9,000 | — | — | — | outside measured range |
| All tracks | 36,500 | — | — | — | outside measured range |

## Managed mem0 budget scenarios

This is conditional subscription budgeting from the checked-in pricing
snapshot, separate from the tested mem0 OSS deployment. It uses 31-day months,
no overage/custom rate, and one request per operation. Local model/API budget
is `$0`; local total cost remains unknown.

| Adds/day | Retrievals/day | 30 days | 90 days | 365 days | Managed tier |
|---:|---:|---:|---:|---:|---|
| 100 | 20 | $0 | $0 | $0 | Hobby |
| 100 | 100 | $19 | $57 | $228 | Starter |
| 100 | 1,000 | $249 | $747 | $2,988 | Pro |
| 100 | 2,000 | unknown | unknown | unknown | custom/usage quote |

The full request-by-request calculation and source snapshot are in
[raw/independent-cost-over-time.json](./raw/independent-cost-over-time.json)
and [raw/cost-source-snapshot.json](./raw/cost-source-snapshot.json).

## Matched nomic rerun

The reproducible semantic command is intentionally separate from the BGE
control. Run it only with the confirmed local listener and with localhost
access approved by the execution environment:

```bash
GROWTH_OLLAMA_URL=http://127.0.0.1:11436 \
GROWTH_EMBED_MODEL=nomic-embed-text:v1.5 \
python3 -m bench.growth --adapter smriti-nomic --checkpoints 100 1000 5000 \
  --repeats 10 --out audit/2026-09-05/growth-smriti-nomic-schema2.json
```

For mem0, use `infer=False`, Qdrant local, and an explicit Ollama embedder
config with model `nomic-embed-text:v1.5`, endpoint
`http://127.0.0.1:11436`, and the model's measured 768 dimensions. The output
must retain the effective provider/model/dimensions/endpoint and must not be
merged with the BGE table if the listener or model call fails.

For the maintained lexical GBrain overtime variant, set `GBRAIN_ROOT` to the
pinned checkout and use the optional maintenance path. It runs the public
engine's `executeRaw('ANALYZE')` after each checkpoint and records maintenance
time in a separate artifact; omit the flag for the default raw track:

```bash
GBRAIN_ROOT=/path/to/pinned/gbrain \
python3 -m bench.growth --adapter gbrain \
  --checkpoints 3000 9000 36500 --repeats 20 --gbrain-analyze \
  --out audit/2026-09-05/growth-gbrain-analyze-overtime-schema2.json
```
