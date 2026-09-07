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
import platform
import re
import time
import traceback
from datetime import datetime
from typing import Callable, List, Optional
from urllib.parse import urlsplit, urlunsplit

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


def _sample_id(item: dict, conversation_index: int) -> str:
    return str(item.get("sample_id") or item.get("conversation_id")
               or f"locomo-sample-{conversation_index}")


def _question_id(item: dict, question: dict, conversation_index: int,
                 question_index: int) -> str:
    if not isinstance(question, dict):
        question = {}
    return str(question.get("question_id") or question.get("id")
               or f"{_sample_id(item, conversation_index)}-q{question_index}")


def _category(question: object) -> int:
    if not isinstance(question, dict):
        return 0
    try:
        return int(question.get("category", 0))
    except (TypeError, ValueError):
        return 0


def _safe_endpoint(value: object) -> Optional[str]:
    if not value:
        return None
    parsed = urlsplit(str(value))
    host = parsed.hostname or ""
    try:
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError:
        pass
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _llm_provenance(llm: object) -> dict:
    if llm is None:
        return {"configured": False}
    return {
        "configured": True,
        "class": type(llm).__name__,
        "model": getattr(llm, "model", None),
        "provider": getattr(llm, "provider", None),
        "endpoint": _safe_endpoint(getattr(llm, "base_url", None)),
        "temperature": getattr(llm, "temperature", None),
        "max_tokens": getattr(llm, "max_tokens", None),
    }


def _memory_provenance(mem: object) -> dict:
    embedder = getattr(mem, "embedder", None)
    return {
        "class": type(mem).__name__,
        "mode": getattr(mem, "mode", None),
        "embedder": {
            "class": type(embedder).__name__ if embedder is not None else None,
            "model": getattr(embedder, "model", None),
            "endpoint": _safe_endpoint(getattr(embedder, "base_url", None)),
        },
        "llm": _llm_provenance(getattr(mem, "llm", None)),
    }


def _llm_usage(llm: object) -> dict:
    return {
        "calls": getattr(llm, "calls", 0),
        "attempts": getattr(llm, "attempts", 0),
        "http_attempts": getattr(llm, "http_attempts", None),
        "tokens_in": getattr(llm, "tokens_in", 0),
        "tokens_out": getattr(llm, "tokens_out", 0),
        "usage_missing": getattr(llm, "usage_missing", 0),
    }


def _error_payload(stage: str, exc: BaseException) -> dict:
    return {
        "stage": stage,
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }


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
    observations: bool = False,
    iterative: bool = False,
    provenance: Optional[dict] = None,
) -> dict:
    from .longmemeval import stratified_sample

    # Build the plan before ingest. This makes the denominator explicit and
    # ensures an ingest/answer/judge failure still occupies its question slot.
    refs = [(c_idx, qi, _category(q))
            for c_idx, it in enumerate(data)
            for qi, q in enumerate(it.get("qa", []) or [])]
    if sample:
        chosen = stratified_sample(refs, sample, key=lambda r: r[2])
        planned_pairs = {(r[0], r[1]) for r in chosen}
        planned_refs = [r for r in refs if (r[0], r[1]) in planned_pairs]
    elif limit_questions:
        planned_refs = refs[:limit_questions]
    else:
        planned_refs = refs
    planned_by_conversation: dict[int, list[int]] = {}
    for c_idx, qi, _ in planned_refs:
        planned_by_conversation.setdefault(c_idx, []).append(qi)

    results, per_cat, cleanup, memory_instances = [], {}, [], []
    selected_question_ids = [
        _question_id(data[c_idx], data[c_idx].get("qa", [])[qi], c_idx, qi)
        for c_idx, qi, _ in planned_refs
    ]

    def add_failure(item: dict, c_idx: int, qi: int, q: dict,
                    cat: int, question: str, gold: str, sample_id: str,
                    qid: str, error: dict, ingest_s: Optional[float] = None,
                    hypothesis: str = "", answer_s: Optional[float] = None) -> None:
        per_cat.setdefault(cat, []).append(False)
        row = {
            "sample_id": sample_id, "question_id": qid,
            "conversation": c_idx, "question_index": qi,
            "category": cat, "question": question, "gold": gold,
            "hypothesis": hypothesis, "correct": False, "error": error,
        }
        if ingest_s is not None:
            row["ingest_s"] = round(ingest_s, 2)
        if answer_s is not None:
            row["answer_s"] = round(answer_s, 2)
        results.append(row)

    for c_idx, item in enumerate(data):
        qindices = planned_by_conversation.get(c_idx, [])
        if not qindices:
            continue
        conv = item.get("conversation", {})
        qa = item.get("qa", []) or []
        sample_id = _sample_id(item, c_idx)
        mem = None
        ingest_s = None
        ingest_error = None
        t0 = time.time()
        try:
            if not conv:
                raise ValueError("conversation is missing or empty")
            mem = memory_factory()
            memory_instances.append({"sample_id": sample_id,
                                     **_memory_provenance(mem)})
            for key, ts, turns in iter_sessions(conv):
                mem.add(turns, session_id=f"c{c_idx}-{key}", timestamp=ts)
            if observations and mem.llm is not None:
                mem.refresh_observations()
        except Exception as exc:  # retain the raw ingest failure per question
            ingest_error = _error_payload("ingest", exc)
        finally:
            ingest_s = time.time() - t0

        try:
            for qi in qindices:
                q = qa[qi] if qi < len(qa) and isinstance(qa[qi], dict) else {}
                qid = _question_id(item, q, c_idx, qi)
                question = q.get("question", "")
                gold = str(q.get("answer", q.get("adversarial_answer", "")))
                cat = _category(q)
                if ingest_error is not None:
                    add_failure(item, c_idx, qi, q, cat, question, gold,
                                sample_id, qid, ingest_error, ingest_s)
                    continue

                try:
                    ctx = (mem.context_iterative(question, k=k, char_budget=char_budget)
                           if iterative else
                           mem.context(question, k=k, char_budget=char_budget))
                except Exception as exc:
                    add_failure(item, c_idx, qi, q, cat, question, gold,
                                sample_id, qid, _error_payload("retrieval", exc), ingest_s)
                    continue
                try:
                    answer_started = time.time()
                    hypothesis = answer_llm.complete(
                        [{"role": "system", "content": ANSWER_SYSTEM.format(today="unknown")},
                         {"role": "user", "content": f"MEMORY CONTEXT:\n{ctx}\n\nQUESTION: {question}"}],
                        max_tokens=256,
                    )
                    answer_s = time.time() - answer_started
                except Exception as exc:
                    add_failure(item, c_idx, qi, q, cat, question, gold,
                                sample_id, qid, _error_payload("answer", exc), ingest_s)
                    continue

                try:
                    if cat == 5:
                        correct = is_abstention(hypothesis)
                    else:
                        correct = judge(judge_llm, question, gold, hypothesis,
                                        question_id=qid)
                except Exception as exc:
                    add_failure(item, c_idx, qi, q, cat, question, gold,
                                sample_id, qid, _error_payload("judge", exc), ingest_s,
                                hypothesis=hypothesis.strip(), answer_s=answer_s)
                    continue

                per_cat.setdefault(cat, []).append(correct)
                try:
                    memory_stats = mem.stats()
                except Exception as exc:
                    memory_stats = {"error": _error_payload("memory_stats", exc)}
                results.append({
                    "sample_id": sample_id, "question_id": qid,
                    "conversation": c_idx, "question_index": qi,
                    "category": cat, "question": question,
                    "gold": gold, "hypothesis": hypothesis.strip(),
                    "correct": correct, "ingest_s": round(ingest_s, 2),
                    "answer_s": round(answer_s, 2),
                    "memory_stats": memory_stats,
                })
                if verbose:
                    mark = "Y" if correct else "N"
                    print(f"[{len(results)}/{len(planned_refs)}] {mark} cat{cat} {question[:60]}")
        finally:
            cleanup_row = {"sample_id": sample_id, "conversation": c_idx,
                           "attempted": mem is not None, "ok": True}
            if mem is not None:
                cleanup_row["memory"] = _memory_provenance(mem)
                try:
                    mem.close()
                except Exception as exc:
                    cleanup_row.update({"ok": False, "error": _error_payload("cleanup", exc)})
            cleanup.append(cleanup_row)

    cleanup_errors = [row for row in cleanup if not row["ok"]]
    summary = {
        "benchmark": "LoCoMo",
        "n": len(results),
        "selected_n": len(planned_refs),
        "accuracy": round(sum(r["correct"] for r in results) / max(len(results), 1), 4),
        "errors": sum(1 for r in results if "error" in r),
        "cleanup_errors": len(cleanup_errors),
        "per_category": {
            CATEGORY_NAMES.get(c, str(c)): round(sum(v) / len(v), 4)
            for c, v in sorted(per_cat.items())
        },
        "usage": {"answer": _llm_usage(answer_llm),
                  "judge": _llm_usage(judge_llm)},
    }
    report = {
        "summary": summary,
        "provenance": {
            "benchmark": "LoCoMo",
            "dataset_format": "locomo10.json-compatible",
            "python": platform.python_version(),
            "usage_scope": "Cumulative counters on shared answer/judge objects; not per-question deltas.",
            "models": {"answer": _llm_provenance(answer_llm),
                       "judge": _llm_provenance(judge_llm)},
            "config": {"k": k, "char_budget": char_budget,
                       "limit_questions": limit_questions, "sample": sample,
                       "observations": observations, "iterative": iterative,
                       "answer_max_tokens": 256, "judge_max_tokens": 8},
            "caller": provenance or {},
            "memory_instances": memory_instances,
        },
        "selection": {"selected_question_ids": selected_question_ids,
                       "selected_n": len(planned_refs)},
        "cleanup": cleanup,
        "usage": summary["usage"],
        "results": results,
    }
    if out_path:
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    return summary
