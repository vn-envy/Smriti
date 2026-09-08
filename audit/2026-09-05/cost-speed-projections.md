# Cost and speed over time

These are bounded corpus-growth simulations, not calendar-long observations.
The measured semantic runs use the same Ollama `nomic-embed-text:v1.5` model
and 768-dimensional output at `http://127.0.0.1:11436`; Mem0 uses local Qdrant
with `infer=False`, and GBrain semantic uses its PGLite hybrid route. GBrain's
lexical/no-embedding track is reported separately. A local
model/API charge of `$0` is shared by the tested local routes; it is not a
unique Smriti advantage and does not mean hardware, electricity, hosting, or
operator cost is zero. Those costs were not measured.

## Measured checkpoints

The rows below come from the validated final summary. Warm p50 and p95 use the
benchmark's empirical nearest-rank statistic (`ceil(p*n)-1` after sorting), not
an averaged median. Smriti and Mem0 cold rows are same-process client/database
reopens; GBrain cold rows restart the worker process. Every row has 20 timed
queries, nonempty results, and all returned hits topic-relevant.

| Track | Docs | Ingest ms | Cumulative ingest ms | Resubmit ms | First ms | Cold ms | Warm p50 / p95 ms (nearest-rank) | Storage MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Smriti semantic / Ollama nomic | 100 | 1,193.997 | 1,193.997 | 0.022 | 17.555 | 10.348 | 10.062 / 10.686 | 0.590 |
| Smriti semantic / Ollama nomic | 1,000 | 17,587.260 | 18,781.257 | 0.022 | 14.184 | 17.884 | 12.059 / 13.557 | 4.563 |
| Smriti semantic / Ollama nomic | 3,000 | 29,645.043 | 48,426.300 | 0.019 | 16.398 | 28.374 | 13.135 / 18.210 | 13.382 |
| Smriti semantic / Ollama nomic | 9,000 | 105,820.300 | 154,246.600 | 0.047 | 65.139 | 302.518 | 24.310 / 34.732 | 39.760 |
| Smriti semantic / Ollama nomic | 36,500 | 539,678.331 | 693,924.931 | 0.050 | 95.481 | 401.904 | 20.474 / 23.726 | 161.075 |
| Mem0 semantic / Ollama nomic / local Qdrant | 100 | 1,317.983 | 1,317.983 | 11.856 | 12.317 | 73.595 | 11.015 / 15.521 | 0.906 |
| Mem0 semantic / Ollama nomic / local Qdrant | 1,000 | 11,136.229 | 12,454.212 | 11.792 | 18.876 | 80.869 | 19.714 / 23.710 | 8.639 |
| Mem0 semantic / Ollama nomic / local Qdrant | 3,000 | 25,026.442 | 37,480.654 | 12.346 | 35.684 | 98.935 | 36.861 / 41.974 | 25.838 |
| Mem0 semantic / Ollama nomic / local Qdrant | 9,000 | 81,580.817 | 119,061.471 | 17.786 | 166.469 | 216.423 | 94.669 / 105.864 | 77.431 |
| Mem0 semantic / Ollama nomic / local Qdrant | 36,500 | 567,911.257 | 686,972.728 | 22.668 | 648.433 | 510.341 | 381.298 / 456.301 | 313.803 |
| GBrain lexical/no embedding, ANALYZE maintained | 100 | 662.906 | 662.906 | 15.913 | 10.121 | 25.914 | 2.861 / 4.939 | 44.368 |
| GBrain lexical/no embedding, ANALYZE maintained | 1,000 | 2,813.286 | 3,476.192 | 18.831 | 6.349 | 23.353 | 3.411 / 5.563 | 62.817 |
| GBrain lexical/no embedding, ANALYZE maintained | 3,000 | 5,418.908 | 8,895.100 | 46.604 | 6.264 | 24.950 | 5.266 / 9.722 | 66.446 |
| GBrain lexical/no embedding, ANALYZE maintained | 9,000 | 20,413.132 | 29,308.232 | 80.683 | 32.547 | 46.017 | 12.220 / 14.333 | 76.792 |
| GBrain lexical/no embedding, ANALYZE maintained | 36,500 | 206,062.343 | 235,370.575 | 347.466 | 47.306 | 97.394 | 39.022 / 47.373 | 206.529 |

GBrain maintenance was measured separately after each checkpoint: cumulative
`executeRaw('ANALYZE')` time was 115.438, 198.001, 286.170, 433.462, and
820.415 ms at the five checkpoints. The default raw GBrain track remains a
separate observation: its independent 5,000-document run had warm p50 1,516.268
ms and p95 1,613.560 ms. Do not merge that untuned query-plan cliff with this
maintained variant or interpolate across it.

## Matched semantic GBrain track

The completed `gbrain-nomic` run uses the same nomic model and measured 768
dimensions as the Smriti and Mem0 semantic runs. It uses GBrain's hybrid
semantic+keyword search on persistent PGLite, with a process-restart cold
boundary. Every checkpoint has 20/20 nonempty, topic-relevant timed queries;
vector stats report `embedded_count == chunk_count` (100 through 36,500).
The raw artifact and derived three-semantic validation are
[`growth-gbrain-nomic-schema2.json`](growth-gbrain-nomic-schema2.json) and
[`growth-semantic-final-report.json`](growth-semantic-final-report.json).

| Track | Docs | Ingest ms | Cumulative ingest ms | Resubmit ms | First ms | Cold ms | Warm p50 / p95 ms (nearest-rank) | ANALYZE ms | Storage MB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GBrain semantic / nomic / PGLite | 100 | 2,331.867 | 2,331.867 | 4.828 | 41.549 | 66.564 | 25.486 / 29.118 | 52.295 | 45.253 |
| GBrain semantic / nomic / PGLite | 1,000 | 19,481.866 | 21,813.733 | 12.600 | 33.904 | 75.377 | 32.935 / 40.838 | 73.674 | 71.713 |
| GBrain semantic / nomic / PGLite | 3,000 | 45,050.291 | 66,864.024 | 27.625 | 50.068 | 89.282 | 44.231 / 49.984 | 86.965 | 109.765 |
| GBrain semantic / nomic / PGLite | 9,000 | 140,889.773 | 207,753.797 | 79.539 | 48.405 | 97.114 | 43.396 / 51.072 | 114.449 | 223.388 |
| GBrain semantic / nomic / PGLite | 36,500 | 853,001.916 | 1,060,755.713 | 310.472 | 140.356 | 139.753 | 66.268 / 92.448 | 260.591 | 840.246 |

At the 100-adds/day workload equivalents, the measured semantic row is:

| Track | 30 days / 3,000 docs p50 / p95 ms | 90 days / 9,000 docs p50 / p95 ms | 365 days / 36,500 docs p50 / p95 ms | Storage MB at 365 days |
|---|---:|---:|---:|---:|
| GBrain semantic / nomic / PGLite | 44.231 / 49.984 | 43.396 / 51.072 | 66.268 / 92.448 | 840.246 |

These semantic GBrain measurements are comparable on embedder identity and
checkpoint workload to Smriti and Mem0, while storage and process boundaries
remain implementation-specific. The lexical GBrain rows above have no model
calls and remain a separate comparison.

Mem0 also logged that optional spaCy full and lemma models were unavailable.
`infer=False` direct-message embedding and semantic Qdrant search still ran;
search used original query text for BM25 lemmatization and no entity boosts.
No package was installed during measurement. The initial JSON-vs-path config
failure is preserved in [raw/growth-mem0-config-failure.json](./raw/growth-mem0-config-failure.json).

## Exact calendar-equivalent checkpoints

At an illustrative workload of 100 adds/day, 30/90/365 days correspond to
exactly 3,000/9,000/36,500 documents. These are measured checkpoints in the
final artifacts, so the table reports observations rather than interpolation.

| Track | 30 days / 3,000 docs p50 / p95 ms | 90 days / 9,000 docs p50 / p95 ms | 365 days / 36,500 docs p50 / p95 ms | Storage MB at 365 days |
|---|---:|---:|---:|---:|
| Smriti semantic / Ollama nomic | 13.135 / 18.210 | 24.310 / 34.732 | 20.474 / 23.726 | 161.075 |
| Mem0 semantic / Ollama nomic / local Qdrant | 36.861 / 41.974 | 94.669 / 105.864 | 381.298 / 456.301 | 313.803 |
| GBrain lexical / ANALYZE maintained | 5.266 / 9.722 | 12.220 / 14.333 | 39.022 / 47.373 | 206.529 |

The day labels are workload equivalents only; they do not claim that the
corpora were collected over those elapsed periods.

## Managed Mem0 budget scenarios

Managed Mem0 subscription pricing is a separate deployment choice from the
tested local Mem0 OSS route. The checked-in pricing snapshot models 100 adds/day
and 20/100/1,000/2,000 retrievals/day over 31-day months:

| Retrievals/day | 30 days | 90 days | 365 days | Managed tier |
|---:|---:|---:|---:|---|
| 20 | $0 | $0 | $0 | Hobby |
| 100 | $19 | $57 | $228 | Starter |
| 1,000 | $249 | $747 | $2,988 | Pro |
| 2,000 | unknown | unknown | unknown | custom/usage quote |

The full calculation and source snapshot are in
[raw/independent-cost-over-time.json](./raw/independent-cost-over-time.json)
and [raw/cost-source-snapshot.json](./raw/cost-source-snapshot.json).

## Reproduction

The final runs used schema-2 artifacts with fresh databases, the shared local
Ollama listener, and 20 warm samples per checkpoint. The derived validated
summary is [growth-matched-final-report.json](./growth-matched-final-report.json).
The separate three-semantic summary is
[growth-semantic-final-report.json](./growth-semantic-final-report.json), with
charts under [charts/semantic](./charts/semantic/). Charts are generated offline
from these summaries by `python3 -m bench.growth_charts`; no missing checkpoints
are interpolated.
