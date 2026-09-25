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
