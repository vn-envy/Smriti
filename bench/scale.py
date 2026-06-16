"""Scaling harness (pariksha for latency): how retrieval and the packer
hold up as the SQLite file grows.

Synthetic episodes + facts at increasing N, timestamps spread over a
decade, random unit vectors standing in for embeddings (dot-product cost
is identical regardless of embedding quality; dim configurable to match
real models). Measures, per scale:

  * ingest throughput and file size
  * cold first query (includes vector-cache build)
  * warm retrieve() latency, mean and p95, over a mixed query set
  * pack_context() time and emitted chars (the packer's budget is fixed,
    so this should be FLAT regardless of N)
  * write->read penalty (cache rebuild after an interleaved insert)
  * per-channel micro-timings (BM25 / vector / temporal)

Run:  python -m bench.scale            # default scales
      python -m bench.scale 1000 100000 500000 --dim 768
"""
from __future__ import annotations

import os
import random
import statistics as st
import sys
import tempfile
import time

import numpy as np

from smriti.embedder import HashEmbedder
from smriti.retrieval import pack_context, retrieve
from smriti.store import Store
from smriti.types import Episode, Fact

VOCAB = ("project deadline flight ticket gym trainer rent landlord invoice "
         "client meeting doctor appointment recipe dinner friend birthday gift "
         "laptop repair travel visa hotel booking marathon training budget tax "
         "filing course exam interview offer salary lease deposit insurance "
         "policy server deploy bug release sprint review weekend trip mom call "
         "school fees bike service grocery list movie plan team lunch").split()

QUERIES = [
    "where is my passport renewal appointment?",
    "what did the doctor say about my knee?",
    "when is the rent due to the landlord?",
    "what happened in March 2021 with the visa?",
    "details about the marathon training plan",
    "what laptop repair shop did I use?",
    "what was decided in the client meeting about the invoice?",
    "my flight booking for the weekend trip",
]


def rand_text(rng, lo=7, hi=15):
    return " ".join(rng.choice(VOCAB) for _ in range(rng.randint(lo, hi)))


def rand_vec(dim):
    v = np.random.randn(dim).astype("float32")
    return v / np.linalg.norm(v)


def build(N, dim):
    rng = random.Random(42)
    path = os.path.join(tempfile.gettempdir(), f"smriti_scale_{N}.db")
    if os.path.exists(path):
        os.remove(path)
    s = Store(path)
    t0 = time.time()
    s.db.execute("BEGIN")
    for i in range(N):
        yr = 2016 + (i * 10) // N
        ts = f"{yr}-{rng.randint(1,12):02d}-{rng.randint(1,28):02d}T10:00:00Z"
        s.add_episode(Episode(None, f"s{i//8}", "user", rand_text(rng), ts),
                      emb=rand_vec(dim))
    for i in range(N // 4):
        f = Fact(id=None, statement=f"The user's {rng.choice(VOCAB)} is {rand_text(rng,3,6)}.",
                 subject="user", predicate=rng.choice(VOCAB), object=rng.choice(VOCAB),
                 entities=[rng.choice(VOCAB)], valid_from="2024-01-01")
        s.add_fact(f, emb=rand_vec(dim))
    # one findable needle for sanity
    emb_q = HashEmbedder(dim)
    needle = "passport renewal appointment at the Begumpet office on Friday"
    s.add_episode(Episode(None, "needle", "user", needle, "2025-02-01T10:00:00Z"),
                  emb=emb_q.embed([needle])[0])
    s.db.execute("COMMIT")
    build_s = time.time() - t0
    return s, path, build_s, emb_q


def ms(fn, *a, **k):
    t0 = time.perf_counter()
    out = fn(*a, **k)
    return (time.perf_counter() - t0) * 1000, out


def run_scale(N, dim):
    s, path, build_s, embedder = build(N, dim)
    rows = N + N // 4 + 1
    size_mb = os.path.getsize(path) / 1e6

    cold_ms, _ = ms(retrieve, s, embedder, QUERIES[0], k=12)

    warm = []
    for _ in range(3):
        for q in QUERIES:
            t, _ = ms(retrieve, s, embedder, q, k=12)
            warm.append(t)
    results = retrieve(s, embedder, QUERIES[0], k=12)
    pack_ms, ctx = ms(pack_context, results, char_budget=9000)

    # interleaved write -> read (cache rebuild penalty)
    s.add_episode(Episode(None, "x", "user", rand_text(random.Random(7)),
                          "2026-01-01T00:00:00Z"), emb=rand_vec(dim))
    rebuild_ms, _ = ms(retrieve, s, embedder, QUERIES[1], k=12)

    # channel micro-timings
    qv = embedder.embed([QUERIES[0]])[0]
    bm25_ms, _ = ms(s.fts_search, QUERIES[0], "episode", 24)
    vec_ms, _ = ms(s.vector_search, qv, "episode", 24)
    temp_ms, _ = ms(s.episodes_near, "2021-03-15", 12)

    needle_ok = any("Begumpet" in r.text for r in
                    retrieve(s, embedder, "where is my passport renewal appointment?", k=12))

    print(f"\nN={rows:>7,} rows | file {size_mb:7.1f} MB | ingest {rows/build_s:7,.0f} rows/s")
    print(f"  cold first query : {cold_ms:8.1f} ms (vector cache build)")
    print(f"  warm retrieve    : {st.mean(warm):8.1f} ms mean | {st.quantiles(warm, n=20)[18]:6.1f} ms p95")
    print(f"  pack_context     : {pack_ms:8.2f} ms -> {len(ctx):,} chars (budget-capped)")
    print(f"  write->read      : {rebuild_ms:8.1f} ms (cache rebuild penalty)")
    print(f"  channels: bm25 {bm25_ms:.1f} ms | vector {vec_ms:.1f} ms | temporal {temp_ms:.1f} ms")
    print(f"  needle@12 recall : {'OK' if needle_ok else 'MISS'}")
    s.db.close()
    os.remove(path)
    return {"rows": rows, "warm_ms": st.mean(warm), "vec_ms": vec_ms}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dim = 768 if "--dim" in " ".join(sys.argv) and "768" in " ".join(sys.argv) else 256
    scales = [int(a) for a in args] or [1_000, 10_000, 100_000, 250_000]
    print(f"SMRITI scaling pariksha | embedding dim={dim} "
          f"(scale vector ms ~3x for 768-dim models)")
    for N in scales:
        run_scale(N, dim)


if __name__ == "__main__":
    main()
