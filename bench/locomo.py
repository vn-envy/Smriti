"""LoCoMo runner (the benchmark mem0's published numbers use).

Dataset: https://github.com/snap-research/locomo (locomo10.json)
10 long multi-session dialogues between two speakers, ~2k QA pairs in
5 categories (1 multi-hop, 2 temporal, 3 open-domain, 4 single-hop,
5 adversarial/unanswerable).

Protocol: one memory instance per conversation (shared across its
questions), sessions ingested with their timestamps. Category 5 is
scored as correct on abstention.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Callable, List, Optional

from smriti import Smriti

from .judge import is_abstention, judge
from .longmemeval import ANSWER_SYSTEM

CATEGORY_NAMES = {1: "multi-hop", 2: "temporal", 3: "open-domain",
                  4: "single-hop", 5: "adversarial"}


def parse_locomo_date(s: Optional[str]) -> Optional[str]:
    """'1:56 pm on 8 May, 2023' / '8 May 2023' -> ISO."""
    if not s:
        return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", s)
    if not m:
        return None
    months = {mo.lower()[:3]: i + 1 for i, mo in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
    mo = months.get(m.group(2).lower()[:3])
    if not mo:
        return None
    try:
        return datetime(int(m.group(3)), mo, int(m.group(1))).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def load_locomo(path: str) -> List[dict]:
    with open(path) as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("samples", [])


def iter_sessions(conv: dict):
    """Yield (session_key, iso_ts, turns) from a LoCoMo conversation dict."""
    keys = sorted(
        (k for k in conv if re.fullmatch(r"session_\d+", k)),
        key=lambda k: int(k.split("_")[1]),
    )
    for key in keys:
        ts = parse_locomo_date(conv.get(f"{key}_date_time"))
        turns = []
        for t in conv.get(key) or []:
            speaker = t.get("speaker", "user")
            text = t.get("text") or t.get("clean_text") or ""
            if t.get("blip_caption"):
                text = f"{text} [shared an image: {t['blip_caption']}]".strip()
            if text:
                turns.append({"role": "user", "content": f"{speaker}: {text}"})
        if turns:
            yield key, ts, turns


def run_locomo(
    data: List[dict],
    answer_llm,
    judge_llm,
    memory_factory: Callable[[], Smriti],
    limit_questions: Optional[int] = None,
    k: int = 12,
    char_budget: int = 9000,
    verbose: bool = True,
    out_path: Optional[str] = None,
    sample: Optional[int] = None,
) -> dict:
    from .longmemeval import stratified_sample
    results, per_cat = [], {}
    asked = 0

    # stratified plan: pick ~`sample` (conversation, question) pairs spread
    # evenly across category, so a small run isn't dominated by one type.
    selected = None
    if sample:
        refs = [(c_idx, qi, int(q.get("category", 0)))
                for c_idx, it in enumerate(data)
                for qi, q in enumerate(it.get("qa", []))]
        chosen = stratified_sample(refs, sample, key=lambda r: r[2])
        selected = {(r[0], r[1]) for r in chosen}

    for c_idx, item in enumerate(data):
        conv = item.get("conversation", {})
        qa = item.get("qa", [])
        if not conv or not qa:
            continue
        if selected is not None and not any((c_idx, qi) in selected for qi in range(len(qa))):
            continue  # no sampled question in this conversation — skip ingest

        mem = memory_factory()
        t0 = time.time()
        for key, ts, turns in iter_sessions(conv):
            mem.add(turns, session_id=f"c{c_idx}-{key}", timestamp=ts)
        ingest_s = time.time() - t0

        for qi, q in enumerate(qa):
            if selected is not None:
                if (c_idx, qi) not in selected:
                    continue
            elif limit_questions and asked >= limit_questions:
                break
            asked += 1
            question = q.get("question", "")
            gold = str(q.get("answer", q.get("adversarial_answer", "")))
            cat = int(q.get("category", 0))

            ctx = mem.context(question, k=k, char_budget=char_budget)
            hypothesis = answer_llm.complete(
                [{"role": "system", "content": ANSWER_SYSTEM.format(today="unknown")},
                 {"role": "user", "content": f"MEMORY CONTEXT:\n{ctx}\n\nQUESTION: {question}"}],
                max_tokens=256,
            )
            if cat == 5:
                correct = is_abstention(hypothesis)
            else:
                correct = judge(judge_llm, question, gold, hypothesis)
            per_cat.setdefault(cat, []).append(correct)
            results.append({
                "conversation": c_idx, "category": cat, "question": question,
                "gold": gold, "hypothesis": hypothesis.strip(), "correct": correct,
            })
            if verbose:
                mark = "Y" if correct else "N"
                print(f"[{asked}] {mark} cat{cat} {question[:60]}")
        if limit_questions and asked >= limit_questions:
            break

    summary = {
        "benchmark": "LoCoMo",
        "n": len(results),
        "accuracy": round(sum(r["correct"] for r in results) / max(len(results), 1), 4),
        "per_category": {
            CATEGORY_NAMES.get(c, str(c)): round(sum(v) / len(v), 4)
            for c, v in sorted(per_cat.items())
        },
    }
    if out_path:
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2)
    return summary
