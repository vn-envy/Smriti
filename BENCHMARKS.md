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

## Reproduce

```bash
# one feature, A/B with delta (defaults: multi-session, oracle, full)
bash bench/ab.sh
# larger, all types:
SAMPLE=200 QTYPE= bash bench/ab.sh
# full ladder with the stack on:
SAMPLE=200 FEATURES="--observations --iterative" bash bench/run_all.sh
```
