"""Judge exported candidate pools (``export_pools.py``) and score the judge's ranking.

Same measurements as ``judge_auc.py`` (per-question AUC against gold evidence,
right memory first, next to Smriti's own order), but read from a pools file,
so it runs on a GPU host with no dataset, embedder or index. The first
``--probe`` questions run one at a time to measure single-stream latency; the
rest run ``--workers`` at a time. With ``SMRITI_LAB_JUDGE_CACHE`` set, every
score lands in the lab's judge cache, so the end-to-end lab run on the CPU box
replays the GPU judgements without a model.

Usage: pool_eval.py JUDGE[:MODE] POOLS.jsonl.gz OUT.json [--workers N] [--probe K] [--limit N]
Writes OUT.json and OUT.progress.json while running.
"""
import argparse
import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from bench.lab.rerankers import make_reranker  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("judge")
ap.add_argument("pools")
ap.add_argument("out")
ap.add_argument("--workers", type=int, default=8)
ap.add_argument("--probe", type=int, default=30)
ap.add_argument("--limit", type=int, default=0)
a = ap.parse_args()
name, _, mode = a.judge.partition(":")
judge = make_reranker(name, mode or None)

pools = [json.loads(line) for line in gzip.open(a.pools, "rt", encoding="utf-8")]
if a.limit:
    pools = pools[:a.limit]


def auc(pos, neg):
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def judge_one(p):
    t0 = time.perf_counter()
    errors_before = judge.stats.errors
    scores = judge.rerank(p["question"], p["docs"])
    ms = 1000 * (time.perf_counter() - t0)
    errors = getattr(judge, "last_errors", None)      # this call's own failures, thread-safe
    if errors is None:                                # judges without it never fail concurrently:
        errors = judge.stats.errors - errors_before   # lab oracles, or --workers 1
    return p, scores, ms, errors


rows, t_start = [], time.time()


def record(p, scores, ms, errors, timed):
    lab = p["gold"]
    row = {"qid": p["qid"], "category": p["category"], "n": len(lab), "n_gold": sum(lab),
           "scores": [round(float(x), 6) for x in scores], "errors": errors}
    if timed:
        row["judge_ms"] = round(ms, 1)
    if 0 < sum(lab) < len(lab):
        row["auc_judge"] = auc([x for x, g in zip(scores, lab) if g], [x for x, g in zip(scores, lab) if not g])
        order = [-k for k in range(len(lab))]
        row["auc_smriti"] = auc([x for x, g in zip(order, lab) if g], [x for x, g in zip(order, lab) if not g])
    if sum(lab):
        best = max(range(len(scores)), key=lambda k: scores[k])
        row["top1_judge"], row["top1_smriti"] = int(lab[best]), int(lab[0])
    rows.append(row)
    if len(rows) % 10 == 0 or len(rows) == len(pools):
        json.dump({"judge": a.judge, "pools": os.path.basename(a.pools), "done": len(rows),
                   "total": len(pools), "errors": sum(r["errors"] for r in rows),
                   "elapsed_s": round(time.time() - t_start, 1)},
                  open(a.out + ".progress.json", "w"))


probe, rest = pools[:a.probe], pools[a.probe:]
for p in probe:                                   # single stream: honest per-question latency
    record(*judge_one(p), timed=True)
with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
    for res in ex.map(judge_one, rest):
        record(*res, timed=False)


def mean(xs):
    return round(sum(xs) / len(xs), 4) if xs else None


a_rows = [r for r in rows if "auc_judge" in r]
t_rows = [r for r in rows if "top1_judge" in r]
timed = sorted(r["judge_ms"] for r in rows if "judge_ms" in r)
summary = {
    "judge": a.judge, "pools": os.path.basename(a.pools), "questions": len(rows),
    "auc_judge": mean([r["auc_judge"] for r in a_rows]),
    "auc_smriti": mean([r["auc_smriti"] for r in a_rows]),
    "better_worse_tied": [sum(r["auc_judge"] > r["auc_smriti"] for r in a_rows),
                          sum(r["auc_judge"] < r["auc_smriti"] for r in a_rows),
                          sum(r["auc_judge"] == r["auc_smriti"] for r in a_rows)],
    "top1_judge": mean([r["top1_judge"] for r in t_rows]),
    "top1_smriti": mean([r["top1_smriti"] for r in t_rows]),
    "ms_per_question_p50": timed[len(timed) // 2] if timed else None,
    "ms_per_question_p95": timed[min(len(timed) - 1, int(0.95 * len(timed)))] if timed else None,
    "latency_probe_questions": len(timed),
    "wall_s": round(time.time() - t_start, 1), "workers": a.workers,
    "input_tokens": judge.stats.input_tokens, "errors": sum(r["errors"] for r in rows),
}
json.dump({"summary": summary, "rows": rows}, open(a.out, "w"), indent=1)
print(json.dumps(summary, indent=1))
