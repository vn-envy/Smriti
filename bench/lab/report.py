"""Render lab result files as markdown tables (no hand-copied numbers).

``python -m bench.lab.report retrieval RUN.json [test|dev|all]``
``python -m bench.lab.report qa SCORED.json``
"""
from __future__ import annotations

import json
import sys

from .summarize import summarize

LABELS = {
    "smriti_fusion": "Smriti 0.3.x read path (fusion)",
    "smriti": "Smriti 0.3.x read path (fusion)",
    "evidence": "**Smriti evidence-first (new default)**",
    "ev(ctx_embed=150)": "Smriti evidence-first + contextual embeddings",
    "bm25": "BM25 (rank-order packer)",
    "dense": "Dense MiniLM (rank-order packer)",
    "mem0": "Mem0 OSS 2.2.0 hybrid (`infer=False`)",
    "fullctx": "Full conversation in context (reference)",
}


def _pct(v):
    return "–" if v is None else f"{100 * v:.1f}"


def retrieval_table(path: str, split: str = "test") -> str:
    res = summarize(path, split)
    cols = [("ctx_full", "Evidence fully in context"), ("ctx_all_full", "All evidence in context"),
            ("ans_in_ctx", "Answer string in context"), ("r@5", "Recall@5"), ("r@10", "Recall@10"),
            ("query_ms_p50", "p50 ms")]
    out = ["| System | " + " | ".join(c[1] for c in cols) + " |",
           "|---|" + "---:|" * len(cols)]
    for name, r in res.items():
        o = r["overall"]
        vals = [(f"{o[c]:.1f}" if c == "query_ms_p50" else _pct(o.get(c))) for c, _ in cols]
        out.append(f"| {LABELS.get(name, name)} | " + " | ".join(vals) + " |")
    n = next(iter(res.values()))["overall"]["n_scored"]
    out.append(f"\n_n = {n} questions with evidence labels; split = {split}; percentages._")
    cats = sorted({c for r in res.values() for c in r["by_category"]})
    out.append("\n| Evidence fully in context by category | " + " | ".join(cats) + " |")
    out.append("|---|" + "---:|" * len(cats))
    for name, r in res.items():
        bc = r["by_category"]
        out.append(f"| {LABELS.get(name, name)} | "
                   + " | ".join(_pct(bc[c]["ctx_full"]) if c in bc else "–" for c in cats) + " |")
    return "\n".join(out)


def qa_table(path: str) -> str:
    rep = json.load(open(path))
    cats = sorted({c for s in rep["systems"].values() for c in s["by_category"]})
    out = ["| System | Accuracy | 95% CI | " + " | ".join(cats) + " |",
           "|---|---:|---:|" + "---:|" * len(cats)]
    for name, s in rep["systems"].items():
        out.append(f"| {LABELS.get(name, name)} | {_pct(s['accuracy'])} | "
                   f"{_pct(s['ci95'][0])}–{_pct(s['ci95'][1])} | "
                   + " | ".join(_pct(s["by_category"].get(c)) for c in cats) + " |")
    out.append(f"\n_n = {rep['n_questions']} questions; split = {rep['split']}; "
               f"context budget = {rep['budget']} characters._")
    out.append("\n| Pair | only first correct | only second correct | McNemar p |")
    out.append("|---|---:|---:|---:|")
    for pair, v in rep["pairs"].items():
        a, b = pair.split(" vs ")
        out.append(f"| {LABELS.get(a, a).strip('*')} vs {LABELS.get(b, b).strip('*')} | "
                   f"{v['only_first']} | {v['only_second']} | {v['mcnemar_p']:.4f} |")
    return "\n".join(out)


if __name__ == "__main__":
    kind, path = sys.argv[1], sys.argv[2]
    if kind == "retrieval":
        print(retrieval_table(path, sys.argv[3] if len(sys.argv) > 3 else "test"))
    else:
        print(qa_table(path))
