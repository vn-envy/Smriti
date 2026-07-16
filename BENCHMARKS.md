# SMRITI — Benchmark Results

Numbers you can reproduce with `bench/ab.sh` and `bench/run_all.sh`. Everything
here is **self-run with a fixed judge**; vendor numbers use different judges,
answer models, and splits and are not directly comparable (see the dashboard's
honesty panel).

## Observation stack A/B (LongMemEval oracle, full mode)

The "observation stack" = Builds 1/6/7/8: per-entity observation summaries +
additive injection + enumerate-don't-assert + multi-granularity `(subject,
predicate)` digests + Python-computed numeric totals. Measured baseline-vs-stack
on the **same** stratified questions; only `--observations` differs.

Backend: DeepSeek `deepseek-v4-flash` (answer + judge + memory), Ollama
`nomic-embed-text` embeddings.

### n = 200, all question types (`SAMPLE=200 QTYPE= bash bench/ab.sh`)

| Category | baseline | + observation stack | Δ |
|---|---|---|---|
| temporal-reasoning | 0.588 | 0.765 | **+17.6** |
| multi-session | 0.176 | 0.242 | +6.6 |
| single-session-assistant | 0.676 | 0.735 | +5.9 |
| knowledge-update | 0.853 | 0.882 | +2.9 |
| single-session-user | 0.941 | 0.941 | 0.0 |
| single-session-preference | 0.433 | 0.367 | −6.7 |
| **Overall** | **0.615** | **0.663** | **+4.8** |

Per-question flips: **19 helped, 10 hurt (net +9)**, 29 discordant.

### Honesty / caveats

- **Significance:** McNemar on the 29 discordant pairs gives z ≈ 1.67, **p ≈ 0.095**
  — directionally strong and near-significant, *not yet* below 0.05. One more
  n≈200 run pooled with this one is expected to cross p < 0.05. Treat the +4.8
  as "very likely real, not yet proven."
- **Split:** this is the *oracle* (evidence-only) split — absolute numbers are
  easy-mode; the **delta** is the transferable result, not the level. A
  full-haystack `longmemeval_s` run is still pending (it is slow and has timed
  out once; the harness now retries + checkpoints).
- **Safety:** the highest-value recall category (single-session-user, 94%) is
  unchanged — the stack supplements rather than displaces. The only regression
  is single-session-preference (open-ended recommendations, a noisy/judging-
  sensitive category), ~2 questions on n=30.
- **Sample size per category** is 30–34, so per-type deltas are indicative, not
  precise. The overall n=200 figure is the more reliable number.

## Per-type router (Builds 11/12) — the precision/recall fix

The n=300 full-stack run exposed a tradeoff: multi-session jumped but knowledge-update
regressed (−13, then −9 after first gating). Root cause (diagnosed on a focused
knowledge-update slice): the recall stack — key expansion and especially observation/
digest summaries — laundered **stale, superseded values** onto current-state questions
(served $350k not the current $400k mortgage; "every two weeks" not the current weekly).

Fix: route by question type. Aggregation queries get the recall profile (high-k +
key-expansion channel + semantic-entity linking + observations); every other query takes
the precision path (clean statement index, raw CURRENT/SUPERSEDED-annotated facts, **no
observation summaries**). Key expansion was also moved to a separate index so it never
pollutes precision queries.

Focused A/B (DeepSeek `deepseek-v4-flash`, fixed judge, oracle, full mode):

| Slice | base → treat | result |
|---|---|---|
| knowledge-update (n=78) | 0.833 → 0.846 | **+1.3** — regression gone (was −5.1) |
| multi-session (n=78) | 0.359 → 0.462 | **+10.3**, McNemar p=0.046 (significant); abstentions 37→20 |

Net: the multi-session breakthrough **without** the knowledge-update tax. This is the
configuration shipped on by default; the recall levers (key expansion, semantic entities,
aggregation path) are intent-gated so precision-sensitive queries are unaffected.

## Reproduce

```bash
# one feature, A/B with delta (defaults: multi-session, oracle, full)
bash bench/ab.sh
# larger, all types:
SAMPLE=200 QTYPE= bash bench/ab.sh
# full ladder with the stack on:
SAMPLE=200 FEATURES="--observations --iterative" bash bench/run_all.sh
```

## Scaling envelope (0.3.1 — from an external agent run, 256-dim vectors)

| Stored rows | Warm query mean | Cold query | DB size |
|---|---|---|---|
| 12,501 | 3.2 ms | 27 ms | 18.3 MB |
| 125,001 | 29.4 ms | 264 ms | 182.6 MB |
| 312,501 | 78.4 ms | 639 ms | 457.2 MB |

Needle retrieval correct at every size; sustained ingest ~50k rows/sec after
startup. The vector channel is an exact numpy scan (O(N)) — larger embedding
dims (768/1536), high concurrency, or multi-million stores will cost
proportionally more. Honest tiers: **excellent** for personal/desktop/coding
agents (tens of thousands of memories), **acceptable** to low hundreds of
thousands with moderate query volume, **not yet** for multi-million-row
multi-tenant serving. Numpy int8/binary quantization is roadmap item #2;
reproduce with `python -m bench.scale`.
