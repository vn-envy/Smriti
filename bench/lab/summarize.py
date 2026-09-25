"""Summarize lab reports by split: ``python -m bench.lab.summarize report.json``."""
from __future__ import annotations

import json
import sys
from collections import defaultdict

from .run import aggregate, in_split

COLS = ["r@5", "r@10", "all@10", "sr@5", "ctx_full", "ctx_all_full", "ans_in_ctx", "query_ms_p50"]


def summarize(path: str, split: str = "test") -> dict:
    rep = json.load(open(path))
    out = {}
    for name, sysrep in rep["systems"].items():
        rows = [r for r in sysrep["rows"]
                if split == "all" or rep.get("split") == split
                or in_split(rep["dataset"], r["qid"].rsplit("-q", 1)[0] if rep["dataset"] == "locomo"
                            else r["qid"], split)]
        by = defaultdict(list)
        for r in rows:
            by[r["category"]].append(r)
        out[name] = {"overall": aggregate(rows), "by_category": {c: aggregate(v) for c, v in by.items()}}
    return out


def main():
    path = sys.argv[1]
    split = sys.argv[2] if len(sys.argv) > 2 else "test"
    res = summarize(path, split)
    names = list(res)
    w = max(len(n) for n in names) + 2
    print(f"{path} split={split}")
    print(f"{'system':{w}s}" + "".join(f"{c:>13s}" for c in COLS) + f"{'n':>6s}")
    for n in names:
        o = res[n]["overall"]
        print(f"{n:{w}s}" + "".join(f"{(o.get(c) if o.get(c) is not None else float('nan')):13.4f}" for c in COLS)
              + f"{o['n_scored']:6d}")
    cats = sorted({c for n in names for c in res[n]["by_category"]})
    print("\nctx_full / r@10 by category")
    print(f"{'system':{w}s}" + "".join(f"{c[:16]:>18s}" for c in cats))
    for n in names:
        bc = res[n]["by_category"]
        print(f"{n:{w}s}" + "".join(f"{bc[c]['ctx_full']:9.3f}/{bc[c]['r@10']:.3f}" if c in bc else " " * 18 for c in cats))


if __name__ == "__main__":
    main()
