# pariksha-lab — offline memory benchmarks

LLM-free, deterministic benchmarks that measure what a memory layer actually
hands the reader model: does the supporting utterance come back, and does it
survive — complete — into the packed context under a fixed budget? Everything
runs on a laptop CPU; answer-quality runs plug in any reader/judge.

## Data

| Dataset | Source | What is scored |
|---|---|---|
| `locomo` | LoCoMo10 (`snap-research/locomo`, `data/locomo10.json`), 10 conversations, 1,540 answerable QA (categories 1–4) | QA `evidence` dialog ids → turn-level evidence |
| `lmex` | LongMemEval evidence sessions (500 questions) with **48 cross-question distractor sessions per question**, re-dated before the question date (`load_lmex`) | `has_answer` turns and `answer_session_ids` |

`lmex` exists because the full LongMemEval-S haystack was not reachable from
the evaluation environment. It is harder than the oracle split but is **not**
the official LongMemEval-S haystack — label results `LME-X`.

Paths default to `/home/user/data/...`; override with `SMRITI_LAB_LOCOMO`,
`SMRITI_LAB_LME`, `SMRITI_LAB_ONNX` (model dir with `model.onnx` +
`tokenizer.json`) and `SMRITI_LAB_EMBCACHE`.

## Metrics (per question, averaged)

- `r@k` — share of evidence turns in the top-k ranked turns; `all@k` — all of
  them; `sr@k` — share of evidence sessions touched by the top-k turns.
- `ctx_full` — share of evidence turns whose **complete** text appears in the
  packed context (resolved-date annotations are ignored); `ctx_all_full` —
  every evidence turn complete; `ans_in_ctx` — for questions whose gold answer
  string occurs verbatim in an evidence turn, whether it survives into the
  context (catches useful excerpts that `ctx_full` counts as misses).
- `query_ms_p50/p95` — wall time of `search` + `context` for the question.

## Systems

`configs.py` names every arm; all arms share the same turns, question date,
character budget and cached vectors.

- `smriti` / `smriti_fusion` — the 0.3.x rank-fusion read path.
- `evidence` — the evidence-first engine (`smriti/recall.py`, now the default).
- `ev(key=value,...)` — the evidence engine with `RecallConfig` overrides, e.g.
  `ev(session_weight=0.5,neighbors=0)`; `ctx_embed=N` enables contextual
  episode embeddings.
- `bm25`, `dense` — plain baselines with a rank-order packer.
- `mem0` — Mem0 OSS (`mem0ai`) with `infer=False`: Mem0's own hybrid
  semantic + spaCy-lemmatized BM25 scoring over the same turns, local Qdrant.
  Its BM25 half needs fastembed's `Qdrant/bm25` encoder; when Hugging Face is
  unreachable, point `SMRITI_LAB_QDRANT_BM25` at a directory containing
  `english.txt` (the NLTK English stopword list).

`SMRITI_IMPL=/path/to/checkout python -m bench.lab.run ...` evaluates another
Smriti tree with the same harness.

## Commands

```bash
# retrieval + context survival (dev half for tuning, test half for reporting)
python -m bench.lab.run --dataset locomo --split dev --systems "smriti_fusion,evidence,ev(session_weight=0.5)"
python -m bench.lab.run --dataset lmex --split test --systems "smriti_fusion,evidence,bm25,dense,mem0" --out lmex.json
python -m bench.lab.summarize lmex.json test
python -m bench.lab.report retrieval lmex.json test   # markdown tables

# blinded answer quality: export -> read -> judge -> score
python -m bench.lab.qa export --dataset locomo --split test --sample 200 --systems "smriti_fusion,evidence,mem0" --out qa/locomo
python -m bench.lab.qa export-fullctx --dir qa/locomo          # LoCoMo full-conversation reference
#   reader writes qa/locomo/answers_XX.jsonl for every batch_XX.txt
python -m bench.lab.qa judge-export --dir qa/locomo
#   judge writes qa/locomo/verdicts_XX.jsonl for every judge_XX.jsonl
python -m bench.lab.qa score --dir qa/locomo --out qa-locomo.json
python -m bench.lab.report qa qa-locomo.json

# reader drift between runs is large (identical contexts moved 10 points):
# re-read saved contexts in one fresh blinded run, then pool the reads
python -m bench.lab.qa rebatch --src qa/locomo:smriti_fusion,evidence,mem0 --out qa/locomo_rerun
#   read + judge qa/locomo_rerun as above, score -> qa-locomo-rerun.json
python -m bench.lab.qa pool qa-locomo.json qa-locomo-rerun.json --out qa-locomo-pooled.json
python -m bench.lab.report pooled qa-locomo-pooled.json

# latency / footprint as the store grows
python -m bench.lab.scale --sizes 10000,36500,100000 --out scale.json
```

Splits: LoCoMo dev = conversations 26, 41, 43, 47, 49; test = 30, 42, 44, 48,
50. LME-X splits by a hash of the question id. Every tuning decision recorded
in `audit/2026-09-25/` was made on the dev half.
