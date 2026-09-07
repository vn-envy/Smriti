# Benchmark methodology audit

## What can be claimed

The checked-in comparison is a small deterministic diagnostic: 20 synthetic
documents and 12 queries. It isolates evidence retrieval and is useful for
regression detection. It is not a complete benchmark and must not support a
claim that any system is broadly superior. The configurations are also not
embedding-parity runs: Smriti uses its deterministic `HashEmbedder`, mem0 uses
BAAI bge-small-en-v1.5, and keyless gbrain is keyword-only.

Observed recall@5 / MRR were Smriti 0.85 / 0.85, mem0 1.00 / 0.95, gbrain
0.95 / 0.90, and the token-overlap control 0.95 / 0.95. Every retriever scored
zero on strict abstention because a top-k retriever returns plausible documents;
answer-layer abstention requires a separate calibrated answer protocol.

Latency is comparable only for the in-process Smriti, mem0, and control calls.
gbrain's reported latency includes Bun process startup and CLI/database opening,
and is explicitly labeled that way in its raw file. Storage includes Smriti's
SQLite sidecars and gbrain's full temporary home. mem0 includes local Qdrant and
history SQLite, but excludes the shared FastEmbed model cache.

## Problems in the prior harness

`bench/longmemeval.py` and `bench/locomo.py` measure an inseparable combination
of extraction, retrieval, context packing, answer generation, and judge behavior.
They catch exceptions and skip failed questions, so the denominator can shrink
silently. LongMemEval timings use `time.time`, round each sample to 10 ms before
aggregation, report means only, and combine context retrieval with answer-model
latency. The LLM judge accepts any output containing the token `yes`; malformed
or verbose judge responses are not rejected. The router sees the benchmark
question text and its hand-authored aggregation regex, so router evaluation is
not independent ground truth. First-N sampling is acknowledged as ordered;
stratified sampling remains deterministic but is not randomized or bootstrapped.

Published vendor numbers use different models, judges, versions, and dataset
splits and cannot be placed in the same result table as locally measured values.
The LongMemEval oracle split contains evidence sessions only and therefore does
not represent full-haystack retrieval.

## Remaining evidence

A bounded paired LoCoMo50 answer/judge baseline is now recorded for the frozen
installed v4 candidate: both adapters completed the same 50 selected questions
with zero operational or cleanup failures; Smriti recorded 27/50 and Mem0 26/50
correct. Independent review verified the same IDs, dataset, gold labels, and
reader/judge models, with 24 questions correct for both, 21 for neither, 3
Smriti-only, and 2 Mem0-only; the exploratory question bootstrap for Smriti minus
Mem0 was [-0.06, 0.10]. This is not a superiority result because questions share
conversations, the bootstrap does not model that dependence, and the labels
include known judge errors such as `conv-30-q0`.

The remaining answer-quality evidence needs shared paired LongMemEval-S50
full-history QA, GBrain held-out20 semantic retrieval QA, and Hindsight
comparative probes (20/12). Each
full-history question must use its complete haystack under the pinned retrieval
and context budgets; this does not require scoring every question in a source
dataset. All runs need one pinned dataset file and hash, identical embedding and
top-k budgets where APIs allow, failure-inclusive denominators, retrieval
evidence labels derived from the dataset rather than answer strings, and the
same Qwen3 8B answer/judge settings across products with judge-output
validation. Qwen3 8B is suitable for a local engineering baseline, not a
definitive leaderboard judge; a human-audited subset and judge agreement should
accompany publication.

Graphify is designed to construct/query code and document graphs and has no
matched raw episodic memory ingestion contract. Hindsight's core retain path is
LLM-backed and no honest extraction-bypass equivalent was established in this
run. Both are recorded as unscored rather than replaced with mocks.
