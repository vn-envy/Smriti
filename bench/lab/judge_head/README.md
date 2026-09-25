# Trained judge head (decision-model trials, round 2)

A frozen Laya-family encoder reads each (question, candidate memory) pair once;
a logistic head is trained on labelled pairs from the dev split and judged on
the held-out test split. Heads: `smriti` (Smriti's own signals only), `laya`
(encoder only), `both`.

```bash
pip install laya                      # plus a Laya checkpoint directory
export SMRITI_LAB_LAYA=/path/to/checkpoint
python bench/lab/judge_head/extract.py dev  OUT      # ~25 min on 4 CPU cores
python bench/lab/judge_head/extract.py test OUT
python bench/lab/judge_head/train.py OUT             # writes head_*.npz + report.json

# plug a head into Smriti end to end
SMRITI_LAB_HEAD_DIR=OUT SMRITI_LAB_FEAT_CACHE=OUT/feat-cache.sqlite \
python -m bench.lab.run --dataset lmex --split test --workers 1 --budget 3000 \
  --systems "evidence,ev(rerank=learned_smriti,rerank_depth=20),ev(rerank=learned_both,rerank_depth=20)"
```

Results and write-up: `audit/2026-09-25/decision-models/NOTES.md`.
