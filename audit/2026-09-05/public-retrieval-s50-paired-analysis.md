# Paired LongMemEval-S s50 analysis

This is an exploratory, failure-inclusive analysis of the preserved 50-question full-haystack runs. It is not a leaderboard result.

- Same selected question ids: **yes (50)**
- Same dataset SHA-256: **yes** (`d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442`)
- Same embedding and budgets: **yes** (`nomic-embed-text:v1.5`, `16000` session chars, `4000` chunk chars, k=5)
- Completion: Smriti **48/50**, Mem0 **48/50**; each has two raw failures included as zero.
- Unanswerable sample: **0**; no abstention or empty-retrieval claim is made.

## Failure-inclusive quality

| Adapter | Mean recall@5 | Mean MRR |
|---|---:|---:|
| Smriti | 0.8383 | 0.8300 |
| Mem0 | 0.8300 | 0.8333 |
| Smriti − Mem0 | **0.0083** | -0.0033 |

Paired bootstrap (20,000 resamples, fixed seed `20260907`, question-level resampling) gives a 95% percentile interval of **[-0.0500, 0.0800]** for the mean recall@5 difference (Smriti − Mem0).

## Recall by question type

| Type | n | Smriti | Mem0 | Difference |
|---|---:|---:|---:|---:|
| knowledge-update | 8 | 0.9375 | 1.0000 | -0.0625 |
| multi-session | 9 | 0.6111 | 0.7407 | -0.1296 |
| single-session-assistant | 8 | 0.8750 | 0.8750 | 0.0000 |
| single-session-preference | 8 | 0.8750 | 0.7500 | 0.1250 |
| single-session-user | 9 | 1.0000 | 1.0000 | 0.0000 |
| temporal-reasoning | 8 | 0.7396 | 0.6042 | 0.1354 |

The multi-session stratum is **0.6111 vs 0.7407** (Smriti vs Mem0). With nine questions, this is a follow-up hypothesis about cross-session/chunk handling, not a general performance claim. The temporal and preference differences are similarly small-stratum observations, with one raw failure in each temporal/assistant affected stratum.

Latency p50/p95 values are retained in the JSON for provenance but excluded from speed ranking because the runs shared a non-isolated host. Both adapters used the same 4,000-character exploratory budget, where the two repeated failures occurred; the frozen harness now defaults to a conservative 1,000-character chunk budget for future matched reruns.

Source artifacts: [`public-retrieval-smriti-s50.json`](public-retrieval-smriti-s50.json) and [`public-retrieval-mem0-s50.json`](public-retrieval-mem0-s50.json).
