"""LongMemEval runner (ICLR 2025; the de-facto standard for memory layers).

Dataset: https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned
Files:   longmemeval_s_cleaned.json (~115k tokens/question, 30-50 sessions)
         longmemeval_m_cleaned.json (~500 sessions/question)
         longmemeval_oracle.json    (evidence sessions only; fast sanity check)

Protocol per question: build a FRESH memory instance, ingest every haystack
session with its timestamp, then answer the question dated question_date.
An LLM judge scores against the gold answer; *_abs questions are scored
as correct only on abstention. Reports overall and per-question-type
accuracy plus token/latency cost — the numbers that matter for an honest
comparison against published mem0 / Zep / Hindsight results.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Callable, List, Optional

from smriti import Smriti

from .judge import judge

ANSWER_SYSTEM = """You are an assistant answering a question about a user, using ONLY the memory context provided.
- Today's date is {today}. Interpret relative time in the question against this date.
- Facts marked SUPERSEDED were true during their validity window but changed later; use CURRENT facts for present-tense questions and the validity windows for "as of <date>" / "before X" questions.
- Be concise and direct. Give the specific answer (name, number, date, item).
- If the memory context does not contain the answer, say exactly: "I don't have enough information to answer that."
"""


def parse_lme_date(s: Optional[str]) -> Optional[str]:
    """'2023/05/30 (Tue) 23:40' -> '2023-05-30T23:40:00Z'"""
    if not s:
        return None
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})(?:.*?(\d{1,2}):(\d{2}))?", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = int(m.group(4) or 0)
    mm = int(m.group(5) or 0)
    try:
        return datetime(y, mo, d, hh, mm).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def load_longmemeval(path: str) -> List[dict]:
    with open(path) as f:
        return json.load(f)


def stratified_sample(items, n, key):
    """Pick ~n items spread evenly across the value of key(item).

    Round-robins across groups so a small sample touches every question
    type instead of the first-N artifact (LongMemEval is ordered by type).
    Group iteration order is preserved (stable, no RNG) for reproducibility.
    """
    groups = {}
    for it in items:
        groups.setdefault(key(it), []).append(it)
    iters = {k: iter(v) for k, v in groups.items()}
    active = list(groups.keys())
    picked = []
    while len(picked) < n and active:
        for k in list(active):
            try:
                picked.append(next(iters[k]))
            except StopIteration:
                active.remove(k)
                continue
            if len(picked) >= n:
                break
    return picked


def run_longmemeval(
    data: List[dict],
    answer_llm,
    judge_llm,
    memory_factory: Callable[[], Smriti],
    limit: Optional[int] = None,
    k: int = 12,
    char_budget: int = 9000,
    verbose: bool = True,
    out_path: Optional[str] = None,
    sample: Optional[int] = None,
    observations: bool = False,
    iterative: bool = False,
    question_type: Optional[str] = None,
) -> dict:
    if question_type:
        data = [it for it in data if it.get("question_type") == question_type]
    if sample:
        items = stratified_sample(data, sample, lambda it: it.get("question_type", "unknown"))
    else:
        items = data[:limit] if limit else data
    results, per_type = [], {}

    def _flush_partial():
        if not out_path:
            return
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({"summary": {"benchmark": "LongMemEval", "n": len(results),
                                   "partial": True}, "results": results}, f, indent=2)

    for idx, item in enumerate(items):
        try:
            qid = item.get("question_id", str(idx))
            qtype = item.get("question_type", "unknown")
            question = item["question"]
            gold = str(item.get("answer", ""))
            qdate = parse_lme_date(item.get("question_date"))

            mem = memory_factory()
            t0 = time.time()
            dates = item.get("haystack_dates") or []
            for s_idx, session in enumerate(item.get("haystack_sessions", [])):
                ts = parse_lme_date(dates[s_idx]) if s_idx < len(dates) else None
                turns = [{"role": t.get("role", "user"), "content": t.get("content", "")}
                         for t in session if t.get("content")]
                if turns:
                    mem.add(turns, session_id=f"{qid}-s{s_idx}", timestamp=ts)
            if observations and mem.llm is not None:
                mem.refresh_observations()  # Build 1: synthesize entity summaries post-ingest
            ingest_s = time.time() - t0

            t0 = time.time()
            ctx = (mem.context_iterative(question, k=k, now=qdate, char_budget=char_budget)
                   if iterative else
                   mem.context(question, k=k, now=qdate, char_budget=char_budget))
            today = (qdate or "")[:10] or "unknown"
            hypothesis = answer_llm.complete(
                [{"role": "system", "content": ANSWER_SYSTEM.format(today=today)},
                 {"role": "user", "content": f"MEMORY CONTEXT:\n{ctx}\n\nQUESTION ({today}): {question}"}],
                max_tokens=256,
            )
            answer_s = time.time() - t0
            correct = judge(judge_llm, question, gold, hypothesis, question_id=qid)
        except Exception as e:  # one flaky question must not abandon the whole run
            if verbose:
                print(f"[{idx+1}/{len(items)}] ERR {type(e).__name__}: {str(e)[:50]} — skipped")
            continue

        per_type.setdefault(qtype, []).append(correct)
        rec = {
            "question_id": qid, "question_type": qtype, "question": question,
            "gold": gold, "hypothesis": hypothesis.strip(), "correct": correct,
            "ingest_s": round(ingest_s, 2), "answer_s": round(answer_s, 2),
            "memory_stats": mem.stats(),
        }
        results.append(rec)
        if verbose:
            mark = "Y" if correct else "N"
            print(f"[{idx+1}/{len(items)}] {mark} {qtype:<26} {question[:60]}")
        if out_path and (idx + 1) % 10 == 0:
            _flush_partial()  # checkpoint so a wall-clock timeout keeps progress

    summary = {
        "benchmark": "LongMemEval",
        "n": len(results),
        "accuracy": round(sum(r["correct"] for r in results) / max(len(results), 1), 4),
        "per_type": {t: round(sum(v) / len(v), 4) for t, v in sorted(per_type.items())},
        "avg_ingest_s": round(sum(r["ingest_s"] for r in results) / max(len(results), 1), 2),
        "avg_answer_s": round(sum(r["answer_s"] for r in results) / max(len(results), 1), 2),
        "answer_tokens_in": getattr(answer_llm, "tokens_in", 0),
        "answer_tokens_out": getattr(answer_llm, "tokens_out", 0),
    }
    if out_path:
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({"summary": summary, "results": results}, f, indent=2)
    return summary
