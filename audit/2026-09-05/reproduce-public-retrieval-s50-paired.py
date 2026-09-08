#!/usr/bin/env python3
"""Reproduce the failure-inclusive paired s50 recall analysis.

This reads preserved result artifacts only; it never calls a model.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("smriti", type=Path)
    parser.add_argument("mem0", type=Path)
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--replicates", type=int, default=20000)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    smriti, mem0 = load(args.smriti), load(args.mem0)
    ids = smriti["dataset"]["selected_items"]
    checks = {
        "selected_ids": ids == mem0["dataset"]["selected_items"],
        "dataset_sha256": smriti["dataset"]["sha256"] == mem0["dataset"]["sha256"],
        "embedding": smriti["embedding"] == mem0["embedding"],
        "budgets": smriti["budgets"] == mem0["budgets"],
    }
    if not all(checks.values()):
        raise SystemExit(f"matched-input check failed: {checks}")
    sm_rows = {row["question_id"]: row for row in smriti["results"]}
    m0_rows = {row["question_id"]: row for row in mem0["results"]}
    sm_failures = {row["question_id"]: row for row in smriti["failure_records"]}
    m0_failures = {row["question_id"]: row for row in mem0["failure_records"]}

    def recall(rows: dict, qid: str) -> float:
        return float(rows.get(qid, {}).get("recall_at_k") or 0.0)

    paired = [(qid, recall(sm_rows, qid), recall(m0_rows, qid)) for qid in ids]
    differences = [sm - m0 for _, sm, m0 in paired]
    rng = random.Random(args.seed)
    samples = sorted(
        sum(differences[rng.randrange(len(differences))] for _ in differences)
        / len(differences)
        for _ in range(args.replicates)
    )
    endpoint = lambda p: samples[max(0, min(len(samples) - 1,
                                             math.ceil(p * len(samples)) - 1))]

    by_type: dict[str, list[tuple[float, float]]] = {}
    for qid, sm, m0 in paired:
        row = sm_rows.get(qid) or m0_rows.get(qid) or sm_failures.get(qid) or m0_failures[qid]
        kind = row["question_type"]
        by_type.setdefault(str(kind), []).append((sm, m0))
    per_type = {
        kind: {
            "n": len(rows),
            "smriti_mean_recall_at_k": round(sum(sm for sm, _ in rows) / len(rows), 6),
            "mem0_mean_recall_at_k": round(sum(m0 for _, m0 in rows) / len(rows), 6),
            "recall_difference_smriti_minus_mem0": round(
                sum(sm - m0 for sm, m0 in rows) / len(rows), 6),
        }
        for kind, rows in sorted(by_type.items())
    }
    result = {
        "method": {
            "resampling_unit": "selected question id",
            "replicates": args.replicates,
            "seed": args.seed,
            "interval": "nearest-rank percentile 95%",
            "failure_policy": "missing result contributes zero",
        },
        "checks": checks,
        "requested": len(ids),
        "smriti_failures": len(sm_failures),
        "mem0_failures": len(m0_failures),
        "smriti_mean_recall_at_k": round(sum(sm for _, sm, _ in paired) / len(paired), 6),
        "mem0_mean_recall_at_k": round(sum(m0 for _, _, m0 in paired) / len(paired), 6),
        "recall_difference_smriti_minus_mem0": round(sum(differences) / len(differences), 6),
        "bootstrap_ci95": [round(endpoint(0.025), 4), round(endpoint(0.975), 4)],
        "per_question_type": per_type,
        "caveat": "Exploratory s50 analysis; no model calls and no leaderboard or speed claim.",
    }
    encoded = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
