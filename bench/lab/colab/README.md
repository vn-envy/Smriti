# GPU runs on Google Colab (decision-model trials, round 4)

Two notebooks run the GPU-bound arms of the decision-model trials on a Colab
runtime. Both judge the **same fixed candidate pools** as rounds 1–3: Smriti
0.4.1's top 20 memories for 256 dev and 244 held-out test LongMemEval
questions (`audit/2026-09-25/decision-models/pools/`, made by
`bench/lab/judge_head/export_pools.py`). Colab only encodes or judges texts,
so hardware or library differences cannot change which candidates are judged,
and the numbers compare directly with Jev (0.954 held-out AUC) and Smriti's
own order (0.891).

| Notebook | GPU | Time | What it measures |
|---|---|---|---|
| [`laya_head.ipynb`](laya_head.ipynb) | any (T4 is enough) | 15–25 min | Frozen official Laya encoder (`convaiinnovations/laya` @ `55cf4c4`) + logistic head trained on dev, scored on test; zero-shot Laya on the full pools; GPU latency |
| [`clm_8b.ipynb`](clm_8b.ipynb) | L4 or A100 (≥ 22 GB) | 30–45 min on L4 | CLM-8B zero-shot (`clm-serve` over vLLM 0.19.1 + Qwen3-8B), `rank`, `choice` and `noul` modes, dev and test; latency |

**Run:** open the notebook in Colab (File → Open notebook → GitHub, or the
links in the session), Runtime → Change runtime type → GPU, Runtime → Run all,
approve the Google sign-in pop-up in step 1.

**Results:** `runner.DriveResults` zips the output folder into one file in the
runner's Google Drive (`smriti-colab-laya-head.zip`, `smriti-colab-clm8b.zip`),
shares it view-only by link, and re-uploads it every 5 minutes, so progress
survives a disconnect and the lab box can fetch it over HTTPS. The zip holds
encoder features, judge scores, head weights, timings and logs; no credentials.
Delete the Drive file (or turn off link sharing) once the results are pulled.

**Replay on the CPU box** (no model needed; every score comes from the caches):

```bash
unzip smriti-colab-clm8b.zip -d round4
# ranking skill, recomputed from the cache
SMRITI_LAB_JUDGE_CACHE=round4/clm8b/judge-cache.sqlite CLM_BASE_URL=http://127.0.0.1:9 \
python bench/lab/judge_head/pool_eval.py clm:choice audit/2026-09-25/decision-models/pools/pools-test.jsonl.gz out.json
# end to end: evidence reaching the LLM at a context budget
SMRITI_LAB_JUDGE_CACHE=round4/clm8b/judge-cache.sqlite CLM_BASE_URL=http://127.0.0.1:9 \
python -m bench.lab.run --dataset lmex --split test --budget 1500 \
  --systems "evidence,ev(rerank=clm,rerank_mode=noul,rerank_depth=20,rerank_weight=0.65)"

unzip smriti-colab-laya-head.zip -d round4
python bench/lab/judge_head/train.py round4/laya-head          # same heads, same report
SMRITI_LAB_HEAD_DIR=round4/laya-head SMRITI_LAB_FEAT_CACHE=round4/laya-head/feat-cache.sqlite \
SMRITI_LAB_LAYA=/path/to/laya@55cf4c4 python -m bench.lab.run --dataset lmex --split test --budget 1500 \
  --systems "evidence,ev(rerank=learned_both,rerank_depth=20)"
```

A cache miss in the end-to-end run (a candidate outside the exported pools)
shows up as `rerank_errors` for CLM, or as fresh CPU encoder work for the head.
