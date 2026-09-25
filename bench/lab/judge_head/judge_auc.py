"""Zero-shot ranking skill of a decision-model judge over Smriti's top-N candidates.

For each LME-X question in a split, rebuild Smriti's current top-N (the pool a
reranker would judge), score it with the named judge (``bench.lab.rerankers``
names: laya, jev, clm, ...), and report per-question AUC against gold evidence
next to Smriti's own order, plus latency, tokens and dollars. With
``SMRITI_LAB_JUDGE_CACHE`` set, judgements persist, so a later end-to-end run
over the same pools costs nothing extra.

Usage: judge_auc.py JUDGE SPLIT OUT.json [LIMIT] [DEPTH]
Writes OUT.json and OUT.progress.json while running.
"""
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from bench.lab.data import load_lmex  # noqa: E402
from bench.lab.rerankers import make_reranker  # noqa: E402
from bench.lab.run import LME_PATH, in_split  # noqa: E402
from bench.lab.systems import SmritiSystem  # noqa: E402
from smriti import RetrievalProfile  # noqa: E402
from smriti.recall import RecallConfig  # noqa: E402

judge_name, split, out = sys.argv[1], sys.argv[2], sys.argv[3]
limit = int(sys.argv[4]) if len(sys.argv) > 4 else 0
depth = int(sys.argv[5]) if len(sys.argv) > 5 else 20
judge = make_reranker(judge_name)
stats = judge.stats


def auc(pos, neg):
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


cases = [c for c in load_lmex(LME_PATH) if in_split("lmex", c.case_id, split)]
if limit:
    random.Random(7).shuffle(cases)
    cases = cases[:limit]
prof = RetrievalProfile(name="judge", engine="evidence", recall=RecallConfig())
rows, t0 = [], time.time()
for i, case in enumerate(cases):
    for q in case.questions:
        s = SmritiSystem("judge", search_kw={"profile": prof}, context_kw={"profile": prof})
        s.build(case)
        hits = [h for h in s.mem.search(q.question, k=depth, now=q.question_date, profile=prof)
                if h.kind == "episode"][:depth]
        gold = set(q.evidence_turns)
        lab = [s.ep2turn.get(h.id) in gold for h in hits]
        before = stats.as_dict()
        scores = judge.rerank(q.question, [h.text for h in hits]) if hits else []
        after = stats.as_dict()
        row = {"qid": q.qid, "category": q.category, "n": len(hits), "n_gold": sum(lab),
               "judge_ms": round(1000 * (after["seconds"] - before["seconds"]), 1),
               "judged": after["docs"] - before["docs"],
               "tokens": after["input_tokens"] - before["input_tokens"],
               "errors": after["errors"] - before["errors"]}
        if 0 < sum(lab) < len(lab):
            row["auc_judge"] = auc([x for x, g in zip(scores, lab) if g], [x for x, g in zip(scores, lab) if not g])
            order = [-k for k in range(len(hits))]
            row["auc_smriti"] = auc([x for x, g in zip(order, lab) if g], [x for x, g in zip(order, lab) if not g])
        if sum(lab):
            best = max(range(len(scores)), key=lambda k: scores[k])
            row["top1_judge"], row["top1_smriti"] = int(lab[best]), int(lab[0])
        rows.append(row)
        s.close()
    json.dump({"judge": judge_name, "split": split, "done": i + 1, "total": len(cases),
               "judged": stats.docs, "tokens": stats.input_tokens, "errors": stats.errors,
               "elapsed_s": round(time.time() - t0, 1)}, open(out + ".progress.json", "w"))

a = [r for r in rows if "auc_judge" in r]
t = [r for r in rows if "top1_judge" in r]
fresh = [r for r in rows if r["judged"]]
summary = {
    "judge": judge_name, "split": split, "questions": len(rows), "depth": depth,
    "auc_judge": round(sum(r["auc_judge"] for r in a) / len(a), 4),
    "auc_smriti": round(sum(r["auc_smriti"] for r in a) / len(a), 4),
    "top1_judge": round(sum(r["top1_judge"] for r in t) / len(t), 4),
    "top1_smriti": round(sum(r["top1_smriti"] for r in t) / len(t), 4),
    "ms_per_judgement_p50": sorted(r["judge_ms"] / r["judged"] for r in fresh)[len(fresh) // 2] if fresh else None,
    "ms_per_question_p50": sorted(r["judge_ms"] for r in fresh)[len(fresh) // 2] if fresh else None,
    "tokens_per_judgement": round(sum(r["tokens"] for r in fresh) / max(1, sum(r["judged"] for r in fresh)), 1),
    "usd": round(getattr(judge, "cost_usd", 0.0), 6), "errors": stats.errors,
}
json.dump({"summary": summary, "rows": rows}, open(out, "w"), indent=1)
print(json.dumps(summary, indent=1))
