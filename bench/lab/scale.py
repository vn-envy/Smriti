"""Latency / footprint probe for the read engines as a store grows.

Builds one on-disk store from real conversation turns (LoCoMo + the
LongMemEval evidence pool, cycled with fresh session ids and dates to reach
the target size), then times warm ``search`` and ``context`` for the evidence
engine and the 0.3.x fusion engine on the same file. Vectors come from the
shared ONNX cache, so no model runs during timing.

``python -m bench.lab.scale --sizes 10000,36500,100000 --out report.json``
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import tempfile
import time
from datetime import datetime, timedelta

from .data import load_lmex, load_locomo
from .embed import lab_embedder
from .run import LME_PATH, LOCOMO_PATH

QUERIES = [
    "When did Caroline go to the LGBTQ support group?",
    "What did I buy for my sister's birthday last month?",
    "How many books did I read in the past two months?",
    "What was the rotation for Admon on a Sunday?",
    "Which cities has John been to?",
    "What is my current commute time?",
    "What did you recommend for my trip to Bandung?",
    "Which did I do first, the pottery class or the yoga retreat?",
    "What pets do I have?",
    "Where did Melanie go camping last weekend?",
]


def corpus():
    sessions = []
    for c in load_locomo(LOCOMO_PATH):
        sessions += [[(t.role, t.content) for t in s.turns] for s in c.sessions]
    seen = set()
    for c in load_lmex(LME_PATH, distractors=0):
        for s in c.sessions:
            if s.session_id not in seen:
                seen.add(s.session_id)
                sessions.append([(t.role, t.content) for t in s.turns])
    return sessions


def pctl(vals, p):
    vals = sorted(vals)
    return round(vals[min(len(vals) - 1, max(0, int(round(p * len(vals))) - 1))], 3)


def main(argv=None):
    from smriti import Smriti
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="10000,36500,100000")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    sizes = [int(x) for x in a.sizes.split(",")]
    sessions = corpus()
    emb = lab_embedder()
    root = tempfile.mkdtemp(prefix="smriti-scale-")
    path = os.path.join(root, "scale.db")
    mem = Smriti(path=path, embedder=emb, mode="lite")
    n, si, report = 0, 0, {"platform": platform.platform(), "embedder": emb.model,
                           "checkpoints": []}
    start = datetime(2022, 1, 1)
    ingest_s = 0.0
    for target in sizes:
        t0 = time.perf_counter()
        while n < target:
            sess = sessions[si % len(sessions)]
            ts = (start + timedelta(hours=7 * si)).strftime("%Y-%m-%dT%H:%M:%SZ")
            msgs = [{"role": r, "content": c} for r, c in sess][: target - n]
            mem.add(msgs, session_id=f"s{si}", timestamp=ts, dedupe=False)
            n += len(msgs)
            si += 1
        ingest_s += time.perf_counter() - t0
        size_mb = sum(os.path.getsize(os.path.join(root, f)) for f in os.listdir(root)) / 1e6
        row = {"episodes": n, "store_mb": round(size_mb, 1), "cumulative_ingest_s": round(ingest_s, 1)}
        for engine in ("evidence", "fusion"):
            mem.read_engine = engine
            for q in QUERIES:  # warm caches (vector matrix, FTS pages)
                mem.search(q, now="2026-01-01")
            s_lat, c_lat = [], []
            for _ in range(a.repeats):
                for q in QUERIES:
                    t = time.perf_counter()
                    mem.search(q, now="2026-01-01")
                    s_lat.append((time.perf_counter() - t) * 1000)
                    t = time.perf_counter()
                    mem.context(q, now="2026-01-01")
                    c_lat.append((time.perf_counter() - t) * 1000)
            row[engine] = {"search_ms_p50": pctl(s_lat, 0.5), "search_ms_p95": pctl(s_lat, 0.95),
                           "context_ms_p50": pctl(c_lat, 0.5), "context_ms_p95": pctl(c_lat, 0.95)}
        mem.read_engine = "evidence"
        report["checkpoints"].append(row)
        print(json.dumps(row), flush=True)
    mem.close()
    if a.out:
        with open(a.out, "w") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
