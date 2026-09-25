"""Run lab benchmarks: ``python -m bench.lab.run --dataset locomo --systems a,b``.

Set ``SMRITI_IMPL=/path/to/checkout`` to evaluate a different Smriti tree
(for example a baseline worktree) with this exact harness.
"""
from __future__ import annotations

import os
import sys

if os.environ.get("SMRITI_IMPL"):
    sys.path.insert(0, os.environ["SMRITI_IMPL"])

import argparse
import json
import multiprocessing as mp
import platform
import re
import statistics
import time
from collections import defaultdict
from typing import Dict, List

from .data import load_locomo, load_lmex, sha256_file, stratified

KS = (1, 3, 5, 10, 20, 50)
LOCOMO_PATH = os.environ.get("SMRITI_LAB_LOCOMO", "/home/user/data/locomo10.json")
LME_PATH = os.environ.get("SMRITI_LAB_LME", "/home/user/data/longmemeval_s.json")


_ANNOT = re.compile(r" \[(?:\d{4}-\d{2}-\d{2}(?:\.\.\d{4}-\d{2}-\d{2})?|\d{4}-\d{2}|\d{4})\]")


def _norm(s: str) -> str:
    """Whitespace/case-normalize and drop resolved-date annotations
    (``yesterday [2023-05-07]``) so annotated turns still count as verbatim."""
    return re.sub(r"\s+", " ", _ANNOT.sub("", s)).strip().lower()


def score_question(q, ranked: List[str], ctx: str, turns: Dict, turn_sess: Dict) -> dict:
    ev = list(q.evidence_turns)
    row = {"qid": q.qid, "category": q.category, "n_evidence": len(ev),
           "ctx_chars": len(ctx)}
    if not ev:
        return row
    pos = {tid: i + 1 for i, tid in enumerate(ranked)}
    row["ranks"] = [pos.get(t) for t in ev]
    for k in KS:
        hit = [t for t in ev if pos.get(t, 10**9) <= k]
        row[f"r@{k}"] = len(hit) / len(ev)
        row[f"all@{k}"] = float(len(hit) == len(ev))
        sess_top = {turn_sess[t] for t in ranked[:k] if t in turn_sess}
        evs = set(q.evidence_sessions) or {turn_sess[t] for t in ev}
        row[f"sr@{k}"] = len(evs & sess_top) / len(evs)
    nctx = _norm(ctx)
    full = [t for t in ev if _norm(turns[t].content) in nctx]
    part = [t for t in ev if _norm(turns[t].content)[:120] in nctx]
    ans = _norm(str(q.answer))
    if len(ans) >= 3 and any(ans in _norm(turns[t].content) for t in ev):
        row["ans_in_ctx"] = float(ans in nctx)
    row["ctx_full"] = len(full) / len(ev)
    row["ctx_all_full"] = float(len(full) == len(ev))
    row["ctx_prefix"] = len(part) / len(ev)
    return row


def split_systems(spec: str) -> List[str]:
    """Split "a,ev(x=1,y=2),b" on top-level commas only."""
    out, depth, cur = [], 0, ""
    for ch in spec:
        if ch == "," and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
            continue
        depth += (ch == "(") - (ch == ")")
        cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def make_system(name: str):
    from .configs import SYSTEMS, variant
    if "(" in name:
        return variant(name)
    if name not in SYSTEMS:
        raise SystemExit(f"unknown system {name!r}; known: {sorted(SYSTEMS)}")
    return SYSTEMS[name]()


def _run_case(args):
    case, system_names, budget = args
    turns = case.turn_index()
    turn_sess = case.turn_session()
    out = {}
    for name in system_names:
        sysm = make_system(name)
        t0 = time.perf_counter()
        sysm.build(case)
        build_s = time.perf_counter() - t0
        rows = []
        for q in case.questions:
            t1 = time.perf_counter()
            ranked, ctx = sysm.query(q, budget)
            dt = time.perf_counter() - t1
            row = score_question(q, ranked, ctx, turns, turn_sess)
            row["query_ms"] = round(dt * 1000, 2)
            row.update(getattr(sysm, "last_extra", None) or {})
            row["context"] = ctx if os.environ.get("SMRITI_LAB_KEEP_CTX") else None
            rows.append(row)
        if hasattr(sysm, "close"):
            sysm.close()
        out[name] = {"build_s": build_s, "rows": rows}
    return case.case_id, out


def in_split(dataset: str, case_id: str, split: str) -> bool:
    """Deterministic dev/test halves used for tuning vs. reporting."""
    import hashlib
    if dataset == "locomo":
        idx = LOCOMO_ORDER.index(case_id) if case_id in LOCOMO_ORDER else 0
        is_dev = idx % 2 == 0
    else:
        is_dev = hashlib.sha256(case_id.encode()).digest()[0] % 2 == 0
    return is_dev if split == "dev" else not is_dev


LOCOMO_ORDER = ["conv-26", "conv-30", "conv-41", "conv-42", "conv-43", "conv-44",
                "conv-47", "conv-48", "conv-49", "conv-50"]


def aggregate(rows: List[dict]) -> dict:
    scored = [r for r in rows if "r@5" in r]
    agg = {"n": len(rows), "n_scored": len(scored)}
    keys = [f"r@{k}" for k in KS] + [f"all@{k}" for k in KS] + [f"sr@{k}" for k in KS] + \
           ["ctx_full", "ctx_all_full", "ctx_prefix", "ans_in_ctx"]
    for key in keys:
        vals = [r[key] for r in scored if key in r]
        agg[key] = round(statistics.mean(vals), 4) if vals else None
    agg["n_ans"] = sum(1 for r in scored if "ans_in_ctx" in r)
    lat = sorted(r["query_ms"] for r in rows)
    if lat:
        agg["query_ms_p50"] = lat[len(lat) // 2]
        agg["query_ms_p95"] = lat[min(len(lat) - 1, int(0.95 * len(lat)))]
    agg["ctx_chars_mean"] = round(statistics.mean(r["ctx_chars"] for r in rows), 1) if rows else None
    rr = [r for r in rows if "rerank_ms" in r]
    if rr:
        ms = sorted(r["rerank_ms"] for r in rr)
        agg["rerank_ms_p50"] = ms[len(ms) // 2]
        agg["rerank_ms_p95"] = ms[min(len(ms) - 1, int(0.95 * len(ms)))]
        for key in ("rerank_requests", "rerank_docs", "rerank_tokens", "rerank_errors"):
            agg[key + "_mean"] = round(statistics.mean(r[key] for r in rr), 2)
        agg["rerank_usd_per_1k_queries"] = round(1000 * statistics.mean(r["rerank_usd"] for r in rr), 5)
    return agg


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=["locomo", "lmex"], required=True)
    ap.add_argument("--systems", required=True, help="comma-separated names from bench/lab/configs.py")
    ap.add_argument("--budget", type=int, default=9000, help="reader context character budget")
    ap.add_argument("--sample", type=int, default=0, help="lmex: stratified case sample (0 = all)")
    ap.add_argument("--distractors", type=int, default=48)
    ap.add_argument("--categories", default="1,2,3,4", help="locomo categories")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--split", choices=["all", "dev", "test"], default="all",
                    help="dev/test halves (LoCoMo: by conversation; LME-X: by question hash)")
    ap.add_argument("--out", default="")
    ap.add_argument("--tag", default="")
    a = ap.parse_args(argv)
    names = split_systems(a.systems)
    for name in names:  # fail fast in the parent, never inside a pool worker
        make_system(name)
    if a.dataset == "locomo":
        cases = load_locomo(LOCOMO_PATH, categories=[int(c) for c in a.categories.split(",")])
        dpath = LOCOMO_PATH
    else:
        cases = load_lmex(LME_PATH, distractors=a.distractors, include_abstention=False)
        if a.sample:
            cases = stratified(cases, a.sample)
        dpath = LME_PATH
    if a.split != "all":
        cases = [c for c in cases if in_split(a.dataset, c.case_id, a.split)]
    t0 = time.time()
    jobs = [(c, names, a.budget) for c in cases]
    results = {}
    if a.workers > 1:
        with mp.get_context("fork").Pool(a.workers) as pool:
            for cid, out in pool.imap_unordered(_run_case, jobs):
                results[cid] = out
    else:
        for job in jobs:
            cid, out = _run_case(job)
            results[cid] = out
    report = {"dataset": a.dataset, "dataset_sha256": sha256_file(dpath),
              "budget": a.budget, "distractors": a.distractors if a.dataset == "lmex" else None,
              "n_cases": len(cases), "systems": {}, "elapsed_s": round(time.time() - t0, 1),
              "smriti_impl": os.environ.get("SMRITI_IMPL", "checkout"),
              "platform": platform.platform(), "tag": a.tag, "split": a.split}
    for name in names:
        rows = [r for cid in sorted(results) for r in results[cid][name]["rows"]]
        by_cat = defaultdict(list)
        for r in rows:
            by_cat[r["category"]].append(r)
        report["systems"][name] = {
            "overall": aggregate(rows),
            "by_category": {c: aggregate(v) for c, v in sorted(by_cat.items())},
            "build_s_total": round(sum(results[c][name]["build_s"] for c in results), 2),
            "rows": rows,
        }
    # console summary
    cols = ["r@5", "r@10", "all@10", "sr@5", "ctx_full", "ctx_all_full", "ans_in_ctx", "query_ms_p50"]
    print(f"\n{a.dataset} n_cases={len(cases)} budget={a.budget} elapsed={report['elapsed_s']}s")
    print(f"{'system':28s} " + " ".join(f"{c:>12s}" for c in cols))
    width = max([28] + [len(n) for n in names])
    for name in names:
        o = report["systems"][name]["overall"]
        print(f"{name:{width}s} " + " ".join(f"{(o.get(c) if o.get(c) is not None else float('nan')):12.4f}" for c in cols))
    cats = sorted({r["category"] for n in names for r in report["systems"][n]["rows"]})
    for c in cats:
        print(f"  [{c}]")
        for name in names:
            o = report["systems"][name]["by_category"].get(c, {})
            print(f"  {name:{width-2}s} " + " ".join(f"{(o.get(k) if o.get(k) is not None else float('nan')):12.4f}" for k in cols))
    if a.out:
        with open(a.out, "w") as f:
            json.dump(report, f, indent=1)
        print("wrote", a.out)
    return report


if __name__ == "__main__":
    main()
