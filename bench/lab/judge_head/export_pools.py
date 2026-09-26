"""Export Smriti's top-20 candidate pools as a portable file for GPU runs.

A pool is what a reranker judges: for each LME-X question, Smriti's current
top-20 episode hits, built exactly as ``judge_auc.py`` and ``extract.py`` build
them. Each line of the output carries the question, the full candidate texts,
their gold labels and Smriti's own per-candidate signals (the ``X_s`` columns of
``extract.py``), so a GPU host (e.g. Colab) can encode or judge the identical
pools with no dataset, embedder or index. Judge scores come back through the
same SQLite caches the lab reads, keyed by (judge, question, memory text).

Usage: export_pools.py SPLIT OUT.jsonl.gz [LIMIT]
"""
import gzip
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
import numpy as np  # noqa: E402
from bench.lab.data import load_lmex  # noqa: E402
from bench.lab.run import LME_PATH, in_split  # noqa: E402
from bench.lab.systems import SmritiSystem  # noqa: E402
import smriti  # noqa: E402
from smriti import RetrievalProfile  # noqa: E402
from smriti.recall import RecallConfig  # noqa: E402

split, out = sys.argv[1], sys.argv[2]
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
DEPTH = 20

cases = [c for c in load_lmex(LME_PATH) if in_split("lmex", c.case_id, split)]
if limit:
    cases = cases[:limit]
prof = RetrievalProfile(name="judge", engine="evidence", recall=RecallConfig())
n_q = n_pairs = n_pos = 0
with gzip.open(out, "wt", encoding="utf-8") as f:
    for case in cases:
        for q in case.questions:
            s = SmritiSystem("judge", search_kw={"profile": prof}, context_kw={"profile": prof})
            s.build(case)
            hits = [h for h in s.mem.search(q.question, k=DEPTH, now=q.question_date, profile=prof)
                    if h.kind == "episode"][:DEPTH]
            if hits:
                gold = set(q.evidence_turns)
                top = hits[0].score or 1.0
                row = {"qid": q.qid, "category": q.category, "question": q.question,
                       "docs": [h.text for h in hits],
                       "gold": [int(s.ep2turn.get(h.id) in gold) for h in hits],
                       "X_s": [[round(float(h.score), 6), round(float(h.score / top), 6), i,
                                float(h.role == "assistant"), round(float(np.log1p(len(h.text))), 6),
                                float("rerank" in h.channels)] for i, h in enumerate(hits)]}
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                n_q += 1
                n_pairs += len(hits)
                n_pos += sum(row["gold"])
            s.close()

try:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            cwd=os.path.dirname(__file__)).stdout.strip()
except OSError:
    commit = ""
meta = {"split": split, "questions": n_q, "pairs": n_pairs, "positives": n_pos, "depth": DEPTH,
        "smriti": smriti.__version__, "commit": commit, "dataset": os.path.basename(LME_PATH)}
json.dump(meta, open(out.replace(".jsonl.gz", "") + ".meta.json", "w"), indent=1)
print(json.dumps(meta))
