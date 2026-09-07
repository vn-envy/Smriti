# Cost and speed over time

`bench/growth.py` measures growing-corpus checkpoints in one run. These are
simulations of corpus growth, not observations collected across 30, 90, or 365
calendar days. Each artifact records whether timing is in-process or includes
CLI startup. Storage excludes shared model caches and reports those separately.

For an assumed workload of 100 memory adds and 20 retrievals per day, corpus
sizes are 3,000 / 9,000 / 36,500 records at 30 / 90 / 365 days, and operation
counts are 600 / 1,800 / 7,300 retrievals. Project latency and storage only by
interpolation between measured checkpoints; do not extrapolate beyond the last
checkpoint as a vendor performance claim.

Local Smriti, mem0 OSS, and gbrain are open-source/self-hosted paths in these
runs, so observed paid API cost is $0. Electricity, hardware purchase or rental,
and depreciation were not measured and are unknown rather than zero. Local
Ollama model calls consume local compute but no per-token API charge. mem0's
managed-plan prices are separate from this OSS measurement.

No full-mode cost estimate should use successful-completion token counters as a
complete bill: failed and retried model attempts may consume tokens that the
current counters cannot observe. Report successful calls/tokens and unknown
failed-attempt usage separately.

## Measured checkpoints

| Adapter/configuration | Documents | Incremental ingest | Warm p50 | Warm p95 | Storage |
|---|---:|---:|---:|---:|---:|
| Smriti lite + HashEmbedder | 100 | 18 ms | 0.105 ms | 0.137 ms | 4.11 MB |
| Smriti lite + HashEmbedder | 1,000 | 166 ms | 0.210 ms | 0.262 ms | 6.00 MB |
| Smriti lite + HashEmbedder | 5,000 | 919 ms | 0.827 ms | 1.854 ms | 12.60 MB |
| mem0 infer=False + BGE-small + Qdrant | 100 | 534 ms | 3.831 ms | 6.272 ms | 0.54 MB |
| mem0 infer=False + BGE-small + Qdrant | 1,000 | 3,964 ms | 10.621 ms | 11.147 ms | 5.03 MB |
| gbrain keyless PGLite, CLI process per operation | 20 | 12,738 ms | 586.857 ms | 645.318 ms | 44.21 MB |

These rows are not a quality-parity comparison: the embedding strategies differ,
and gbrain includes process startup. The raw JSON files are the source of truth.
The gbrain point is retained to quantify the tested CLI workflow, not to infer
persistent-server latency or scaling.
