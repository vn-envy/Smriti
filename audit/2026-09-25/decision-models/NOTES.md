# Experiment 01 — decision models as memory judges

**Question.** Can a "System One" decision model (Laya, Jev, CLM-8B) re-rank
Smriti's top memories well enough to justify an optional extra, or a
permanent place in the read path?

**Setup.** The judge answers one `noul` question per candidate: "does the
memory contain information that helps answer the question?". It re-ranks
Smriti's top `rerank_depth` turns (default 48). `rerank_weight` blends the
judge's P(true) with Smriti's max-normalised fused score: 1.0 replaces it,
0.5 mixes them equally.

| Contender | Runs | License | Status on 2026-09-25 |
|---|---|---|---|
| [Laya](https://github.com/NandhaKishorM/laya) 0.3.20, 421M ModernBERT-large | Local CPU/GPU | Apache-2.0 | Blocked: weights on huggingface.co, which this sandbox cannot reach |
| Jev (TypeSafe, `jev-latest`) | Hosted, `api.typesafe.ai` | Closed | Blocked: API host not allowed by the sandbox network policy |
| [CLM-8B](https://github.com/Contrastive-LM/CLM) v0.1 (Contrastive-LM) | Local GPU: vLLM Qwen3-8B + 75 MB heads | Apache-2.0 | Needs a GPU; weights on huggingface.co |

## Results so far (dev splits, no model calls)

The **oracle** judge knows the gold evidence turns. It shows the most any
judge can add at depth 48. The **word-overlap** judge is a naive floor.

Evidence complete in context (`ctx_full`):

| Dataset · budget | Smriti today | Perfect judge | Word-overlap judge |
|---|---:|---:|---:|
| LoCoMo · 1,500 chars | 69.0 | 88.0 | 57.6 |
| LoCoMo · 3,000 chars | 77.9 | 88.1 | 71.0 |
| LoCoMo · 9,000 chars | 88.8 | 89.0 | 88.7 |
| LME-X · 1,500 chars | 67.4 | 93.1 | 36.6 |
| LME-X · 3,000 chars | 82.8 | 97.9 | 50.9 |
| LME-X · 9,000 chars | 93.2 | 97.9 | 68.6 |

Evidence in the top 5 `search()` results: LoCoMo 62.6 → 88.0 with a
perfect judge (overlap 53.1); LME-X 82.1 → 99.1 (overlap 60.4).

Takeaways:

1. At 9,000 characters, LoCoMo's top 48 turns already fit, so judging barely
   changes the context. The payoff is **smaller contexts**: a perfect judge
   holds 97.9% of LME-X evidence in 3,000 characters, above today's 93.2%
   at 9,000.
2. Top-5 precision for `search()` callers has large headroom on both datasets.
3. A weak judge is harmful (LME-X 93.2 → 68.6), so any model must be
   gated on measured wins and blended with Smriti's own score.

**Projected Jev cost** (dry run: request sizes counted, nothing sent; about
4 characters per token, $0.042 per 1M input tokens): LoCoMo 5.1k tokens per
query in `noul` mode ($0.22 per 1,000 queries), 4.1k in `fanout` mode
($0.17). LME-X 12.1k ($0.51) and 10.7k ($0.45).

Summaries: `dev-ceiling-summary.json`. Page snapshot: `judge-trials-page.html`.

## Round 1 — Laya-family judge (LME-X dev, 3,000 characters)

Official Laya weights sit on huggingface.co (blocked), so round 1 used a
**community fine-tune of laya-multilingual**: `MacJev-322M-4K-Laya`
(mmBERT-base, 322M, Apache-2.0), downloaded from its public GitHub release
mirror and verified by SHA-256. Zero-shot `noul` relevance judge over
Smriti's top 20 turns, CPU only (4 threads).

| Arm | Evidence complete in context | All evidence | Answer in context | Recall@5 |
|---|---:|---:|---:|---:|
| Smriti today | 82.8 | 73.5 | 97.1 | 82.1 |
| Judge replaces Smriti's order | 8.0 | 5.9 | 39.1 | 19.7 |
| Judge blended 50% | 68.4 | 53.4 | 88.4 | 71.6 |
| Judge blended 25% | 79.1 | 68.1 | 94.2 | 80.7 |
| Perfect judge (top 20) | 93.9 | 89.1 | 100.0 | 95.1 |

Diagnosis on 40 questions (AUC of scores on gold vs other top-20 turns):
judge 0.470 with A/B labels, 0.485 with default labels, 0.415 as a yes/no
choice; Smriti's fused score 0.910. The judge is at chance, not inverted.
Non-gold candidates average 955 characters against 319 for gold, so a
guessing judge fills a small context with long irrelevant turns.
Latency: 399 ms per judgement, 8.0 s per question (p50) on CPU.

**Verdict:** this checkpoint stays off. Official Laya (421M English), Jev
and CLM-8B remain untested. Files: `round1-laya-family-lmex-dev.json`,
`round1-card.png`.

## Round 2 — teach the judge our task (LME-X, held-out test)

The same Laya-family encoder, frozen, reads every (question, top-20 candidate)
pair once (`bench/lab/judge_head/extract.py`, 296 ms per pair on 4 CPU
cores). Logistic heads train on 256 dev questions (5,120 labelled pairs; L2
picked by 5-fold CV grouped by question) and are judged once on 244 test
questions (`train.py`).

**Ranking skill on 228 held-out questions** (AUC within Smriti's top 20):

| Ranker | AUC | Right memory first | Recall@5 of pool |
|---|---:|---:|---:|
| Smriti's fused order | 0.890 | 63.6% | 83.6% |
| Head on Smriti's signals only | 0.897 | 60.1% | 84.3% |
| Laya-family head alone | 0.871 | 54.4% | 76.5% |
| **Laya-family + Smriti signals** | **0.928** | **70.2%** | **88.7%** |

Laya + Smriti vs Smriti's order: AUC +0.038 (95% CI +0.023 to +0.053),
better on 97 questions, worse on 34 (sign p = 3×10⁻⁸). The Smriti-only
head adds +0.007 (CI touches zero). Training took zero-shot 0.47 to 0.87.

**End to end** (evidence complete in context, 232 held-out questions, judge
re-ranks the top 20):

| Budget | Smriti (assistant prior 0.55) | + Smriti-signals head | + Laya + Smriti head | Assistant prior 0.2, no head |
|---|---:|---:|---:|---:|
| 1,500 | 64.8 | 66.6 | **72.5** | 67.4 |
| 3,000 | 78.5 | 83.2 | **84.5** | 83.4 |
| 9,000 | 87.6 | 89.9 | 89.4 | **93.0** |

At 3,000 characters the Laya + Smriti head gains +6.0 (CI +3.3 to +8.8,
35 better / 5 worse), but +4.7 of that comes from the Smriti-only head, and
Laya's own increment (+1.2, CI −1.4 to +3.8) is not proven there. It is
largest at 1,500 characters. Cost: 277 ms per pair, 5.5 s per question on CPU.

**The free win.** The Smriti-only head's largest weight was "assistant
turn" (−1.1 per standard deviation): demote assistant replies harder. On the
dev split, lowering `RecallConfig.assistant_prior` from 0.55 to 0.4 / 0.3 /
0.2 / 0.1 raised evidence-in-context at 3,000 characters from 82.8% to
87.2 / 87.6 / 88.1 / 88.6%, with assistant-addressed questions unchanged
(the prior is lifted for them). 0.2 was chosen on dev and tested once:

| LME-X test | 0.55 | 0.2 | Change | Better / worse | p |
|---|---:|---:|---:|---:|---:|
| 1,500 chars | 64.8 | 67.4 | +2.6 (CI +0.7 to +4.6) | 13 / 1 | 0.002 |
| 3,000 chars | 78.5 | 83.4 | +4.9 (CI +2.6 to +7.4) | 25 / 1 | 8×10⁻⁷ |
| 9,000 chars | 87.6 | 93.0 | +5.4 (CI +3.2 to +7.9) | 26 / 0 | 3×10⁻⁸ |

LoCoMo test (no assistant turns) is unchanged at every budget
(63.7 / 73.5 / 84.7 → 63.8 / 73.6 / 84.7). The default is now 0.2.

**Verdicts.** Ship the prior change (free, significant, no regression).
Keep the trained Laya head as an opt-in experiment for tight budgets: it is
the best arm at 1,500 characters but costs seconds per question on CPU, was
trained on one dataset, and has not been retrained against the new prior.
Files: `round2-summary.json`, `round2-head_*.npz`, `round2-*.png`.

## Correction — lab variants skipped the aggregation header (fixed 2026-09-25)

Until commit `04b8926`, `ev(...)` lab variants built a profile named after
the variant spec. Smriti's aggregation routing is keyed on the profile name
`evidence`, so variants skipped the ~150-character counting header that the
shipped path (and the `evidence` baseline) adds for aggregation questions.
Variants therefore had slightly more budget at tight contexts. Variants now
keep the shipped profile name, and `ev()` reproduces the baseline exactly.
Re-measured on cached judgements (no model or API calls):

| Figure | First reported | Corrected |
|---|---:|---:|
| Perfect judge, top 48, LME-X dev, 1,500 chars | 93.1 | 91.9 |
| Perfect judge, top 48, LME-X dev, 3,000 chars | 97.9 | 97.9 |
| Word-overlap judge, LME-X dev, 3,000 chars | 50.9 | 50.3 |
| Round 1: Laya-family alone / 50% / 25% blend (dev, 3,000) | 8.0 / 68.4 / 79.1 | 7.9 / 68.1 / 78.6 |
| Round 2: Smriti-signals head, test, 1,500 / 3,000 / 9,000 | 66.6 / 83.2 / 89.9 | 64.8 / 83.1 / 89.6 |
| Round 2: Laya + Smriti head, test, 1,500 / 3,000 / 9,000 | 72.5 / 84.5 / 89.4 | 71.0 / 84.5 / 89.4 |
| 0.4.1 prior change, test, 1,500 / 3,000 / 9,000 | +2.6 / +4.9 / +5.4 | +0.9 (n.s.) / +4.7 / +5.4 |

Ranking-skill (AUC) figures are unaffected: they do not involve packing.
Corrected run files: `round3-fixed-summary.json`.

## Round 3 — official Laya vs hosted Jev (network opened)

Candidates are Smriti 0.4.1's top 20 (assistant prior 0.2). Zero-shot
`noul` relevance judge, same instructions as earlier rounds.

**Jev** (`jev-latest`, TypeSafe API, 10 parallel requests):

| Split | AUC Jev | AUC Smriti order | Right memory first | Better / worse questions | Bill |
|---|---:|---:|---:|---:|---:|
| Dev (256 q, 5,120 judgements) | 0.953 | 0.899 | 77.8% vs 64.2% | 115 / 48 | $0.094 |
| Held-out test (244 q, 4,880) | 0.954 | 0.891 | 72.5% vs 63.8% | 104 / 49 (p = 1×10⁻⁵) | $0.090 |

About 436 input tokens per judgement, 70 ms wall time per judgement and
1.4 s per question at 10-way concurrency, zero errors. On dev the blend
weight was chosen end to end at 3,000 characters (replace 89.4, 75% 90.3,
50% 91.8, **35% 92.7**, 25% 92.1; Smriti 87.7). Held-out, 35% Jev blend:

| Budget | Smriti 0.4.1 | + Jev (35%) | Change | Better / worse | Perfect judge (top 20) |
|---|---:|---:|---:|---:|---:|
| 1,500 chars | 65.6 | **74.8** | +9.2 (CI +6.0 to +12.5), p = 2×10⁻⁹ | 41 / 3 | 87.1 |
| 3,000 chars | 83.2 | **86.5** | +3.4 (CI +1.8 to +5.1), p = 6×10⁻⁶ | 22 / 1 | 91.3 |
| 9,000 chars | 93.0 | 93.0 | 0 (the top 20 already fit) | 0 / 0 | – |

Recall@5 rises from 79.9% to 86.6%. Jev captures about 42% of the
perfect-judge headroom at 1,500 and 3,000 characters. It costs about $0.37
per 1,000 questions and sends each candidate memory to a hosted API.

**Official Laya** (`convaiinnovations/laya`, 421M ModernBERT-large, CPU): see below.

## Run once access opens

```bash
# Laya in-process (pip install laya; weights from huggingface.co)
SMRITI_LAB_LAYA_THREADS=4 python -m bench.lab.run --dataset lmex --split dev --workers 1 --budget 3000 \
  --systems "evidence,ev(rerank=laya),ev(rerank=laya,rerank_weight=0.5)" --out lmex-dev-laya.json

# Hosted Jev (key from a private file; never committed)
SMRITI_LAB_JEV_KEY_FILE=/path/to/key python -m bench.lab.run --dataset lmex --split dev --workers 2 --budget 3000 \
  --systems "ev(rerank=jev),ev(rerank=jev,rerank_mode=fanout),ev(rerank=jev,rerank_weight=0.5)" --out lmex-dev-jev.json

# CLM-8B on a GPU host: vllm serve Qwen/Qwen3-8B --runner pooling ...; clm-serve
CLM_BASE_URL=http://gpu-host:8700 python -m bench.lab.run --dataset lmex --split dev \
  --systems "ev(rerank=clm),ev(rerank=clm,rerank_mode=noul)" --out lmex-dev-clm.json
```

Rows record `rerank_ms`, `rerank_requests`, `rerank_tokens`, `rerank_usd`
per question; `aggregate()` adds p50/p95 and dollars per 1,000 queries.
Decide on dev; report the winner on the test split.
