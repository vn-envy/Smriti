"""Matched answer/judge evaluation over public LongMemEval-S or LoCoMo data.

This is a preparation-ready route: it reuses the raw-session adapters and
chunking rules from ``public_retrieval`` and applies the same context, answer,
and judge budgets to one selected question set. It performs no work at import
time; model calls occur only when this CLI is explicitly run.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import platform
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Mapping, Sequence

from smriti import LLM, OllamaEmbedder

from .judge import is_abstention, judge
from .locomo import iter_sessions, load_locomo, parse_locomo_date
from .longmemeval import ANSWER_SYSTEM, load_longmemeval, parse_lme_date
from .public_retrieval import (
DEFAULT_BASE_URL,
    DEFAULT_CHUNK_CHAR_BUDGET,
    DEFAULT_EMBED_MODEL,
    DEFAULT_K,
    DEFAULT_SAMPLE,
    DEFAULT_SESSION_CHAR_BUDGET,
    Mem0Adapter,
    SmritiAdapter,
    _read_mem0_config,
    chunk_session,
    iter_index_rows,
)

SCHEMA_VERSION = 1
DEFAULT_QWEN_MODEL = "qwen3:8b"
DEFAULT_SESSION_OVERFETCH = 3
MAX_SESSION_OVERFETCH = 8


def _error(stage: str, exc: BaseException) -> dict[str, Any]:
    return {"stage": stage, "type": type(exc).__name__,
            "message": str(exc), "traceback": traceback.format_exc()}


def _endpoint(value: object) -> str | None:
    if not value:
        return None
    from urllib.parse import urlsplit, urlunsplit
    parsed = urlsplit(str(value))
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _llm_meta(llm: object) -> dict[str, Any]:
    return {"class": type(llm).__name__, "model": getattr(llm, "model", None),
            "provider": getattr(llm, "provider", None),
            "endpoint": _endpoint(getattr(llm, "base_url", None)),
            "temperature": getattr(llm, "temperature", None),
            "max_tokens": getattr(llm, "max_tokens", None),
            "extra_body": getattr(llm, "extra_body", None)}


def _redact_config(value: Any) -> Any:
    """Keep adapter provenance while removing credentials and secret values."""
    if isinstance(value, dict):
        return {str(key): ("<redacted>" if any(token in str(key).lower()
                            for token in ("key", "token", "secret", "password"))
                           else _redact_config(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_config(item) for item in value]
    return value


def _usage(llm: object) -> dict[str, Any]:
    return {key: getattr(llm, key, None) for key in
            ("calls", "attempts", "http_attempts", "tokens_in", "tokens_out", "usage_missing")}


def _atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Replace a JSON artifact atomically after flushing its temporary file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _write_progress_checkpoint(path: str | Path | None, *, raw: bytes,
                               benchmark: str, adapter_name: str,
                               selected: Sequence[Mapping[str, Any]],
                               results: Sequence[Mapping[str, Any]],
                               cleanup: Sequence[Mapping[str, Any]],
                               answer_llm: object, judge_llm: object,
                               session_diverse: bool,
                               session_overfetch: int) -> None:
    """Persist an in-flight result without presenting it as a completed run."""
    if path is None:
        return
    failed = sum(bool(row.get("errors")) for row in results)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "running",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "progress": {
            "processed_questions": len(results),
            "requested_questions": len(selected),
            "failed_questions": failed,
            "cleanup_failures": sum(not bool(row.get("ok")) for row in cleanup),
            "last_question_id": results[-1].get("question_id") if results else None,
        },
        "selection": {
            "question_ids": [str(item.get("question_id", "")) for item in selected],
            "sample_ids": list(dict.fromkeys(str(item.get("sample_id", ""))
                                             for item in selected)),
        },
        "provenance": {
            "benchmark": benchmark,
            "adapter": adapter_name,
            "retrieval": {"session_diverse": session_diverse,
                           "session_overfetch": session_overfetch},
            "models": {"answer": _llm_meta(answer_llm),
                        "judge": _llm_meta(judge_llm)},
        },
        "usage": {"answer": _usage(answer_llm), "judge": _usage(judge_llm)},
        "cleanup": list(cleanup),
        "results": list(results),
    }
    _atomic_write_json(path, payload)


def stratified_answerable_sample(items: Sequence[Mapping[str, Any]], n: int) -> list[Mapping[str, Any]]:
    """Stable round-robin sample over type, answerability, and source strata.

    LoCoMo has many questions per conversation.  Sampling only by question
    category would therefore consume the first conversation's questions before
    reaching any other conversation.  Cycling through ``sample_id`` buckets
    keeps a small pilot broad across conversations while retaining the stable
    category/answerability allocation used by the matched route.
    """
    if n < 1 or n > len(items):
        raise ValueError(f"sample must be between 1 and {len(items)}")
    groups: dict[tuple[str, bool], dict[str, list[Mapping[str, Any]]]] = {}
    for item in items:
        key = (str(item.get("question_type", "unknown")),
               bool(item.get("unanswerable", False)))
        source = str(item.get("sample_id", ""))
        groups.setdefault(key, {}).setdefault(source, []).append(item)
    source_cursors = {key: {source: 0 for source in buckets}
                      for key, buckets in groups.items()}
    source_positions = {key: 0 for key in groups}
    active = list(groups)
    selected: list[Mapping[str, Any]] = []
    while active and len(selected) < n:
        for key in list(active):
            buckets = groups[key]
            sources = list(buckets)
            if not sources:
                active.remove(key)
                continue
            start = source_positions[key] % len(sources)
            picked = None
            for offset in range(len(sources)):
                source = sources[(start + offset) % len(sources)]
                pos = source_cursors[key][source]
                if pos < len(buckets[source]):
                    picked = source
                    break
            if picked is None:
                active.remove(key)
                continue
            selected.append(buckets[picked][source_cursors[key][picked]])
            source_cursors[key][picked] += 1
            source_positions[key] = (sources.index(picked) + 1) % len(sources)
            if len(selected) >= n:
                break
    return selected


def _locomo_questions(data: Sequence[Mapping[str, Any]], session_budget: int,
                     chunk_budget: int) -> list[dict[str, Any]]:
    questions = []
    for c_idx, item in enumerate(data):
        sample_id = str(item.get("sample_id") or item.get("conversation_id")
                       or f"locomo-sample-{c_idx}")
        rows = []
        for key, ts, turns in iter_sessions(item.get("conversation", {})):
            text = "\n".join(turn["content"] for turn in turns)
            chunks, _ = chunk_session(text, session_budget, chunk_budget)
            for chunk_index, chunk in enumerate(chunks):
                rows.append({"session_id": f"c{c_idx}-{key}", "timestamp": ts,
                             "chunk_index": chunk_index, "text": chunk})
        for q_idx, question in enumerate(item.get("qa", []) or []):
            if not isinstance(question, dict):
                question = {}
            qid = str(question.get("question_id") or question.get("id")
                       or f"{sample_id}-q{q_idx}")
            questions.append({"sample_id": sample_id, "question_id": qid,
                              "question_index": q_idx,
                              "question": question.get("question", ""),
                              "gold": str(question.get("answer", question.get("adversarial_answer", ""))),
                              "question_type": str(question.get("category", "unknown")),
                              "unanswerable": qid.lower().endswith("_abs") or str(question.get("category")) == "5",
                              "rows": rows})
    return questions


def _longmemeval_questions(data: Sequence[Mapping[str, Any]], session_budget: int,
                           chunk_budget: int) -> list[dict[str, Any]]:
    questions = []
    for index, item in enumerate(data):
        rows, _ = iter_index_rows(item, session_budget, chunk_budget)
        qid = str(item["question_id"])
        questions.append({"sample_id": qid, "question_id": qid,
                          "question_index": index,
                          "question": item["question"],
                          "gold": str(item.get("answer", "")),
                          "question_type": str(item.get("question_type", "unknown")),
                          "unanswerable": qid.lower().endswith("_abs"),
                          "question_date": item.get("question_date"),
                          "rows": rows})
    return questions


def _smriti_context(adapter: SmritiAdapter, query: str, k: int, *,
                    session_diverse: bool,
                    session_overfetch: int) -> Sequence[object]:
    """Call Smriti's real selector with the requested opt-in controls."""
    return adapter.memory.search(query, k=k, session_diverse=session_diverse,
                                 session_overfetch=session_overfetch)


def _context(adapter: object, query: str, k: int, char_budget: int,
             rows: Sequence[Mapping[str, Any]],
             source_labels: Mapping[str, str], *,
             session_diverse: bool = False,
             session_overfetch: int = DEFAULT_SESSION_OVERFETCH) -> tuple[str, list[str], list[dict[str, Any]], list[dict[str, Any]]]:
    row_meta = {(str(row["session_id"]), int(row["chunk_index"])): row for row in rows}
    returned: list[str] = []
    retrieved_rows: list[dict[str, Any]] = []
    texts: list[str] = []
    source_map = [{"source_label": label, "session_id": sid,
                   "timestamps": sorted({str(row.get("timestamp")) for row in rows
                                          if str(row["session_id"]) == sid})}
                  for sid, label in source_labels.items()]
    if isinstance(adapter, SmritiAdapter):
        hits = _smriti_context(adapter, query, k,
                               session_diverse=session_diverse,
                               session_overfetch=session_overfetch)
        for hit in hits:
            episode = adapter.memory.store.get_episode(hit.id)
            sid = str(episode.session_id) if episode else None
            if not sid:
                continue
            if sid not in returned:
                returned.append(sid)
            label = source_labels.get(sid, "source-unknown")
            content = getattr(episode, "content", None) or hit.text
            timestamp = getattr(episode, "ts", None)
            texts.append(f"[{label} @ {timestamp or 'unknown'}] {content}")
            matches = [row for (row_sid, _), row in row_meta.items()
                       if row_sid == sid and row.get("text") == content]
            if matches:
                retrieved_rows.extend(
                    {"source_label": label, "session_id": sid,
                     "chunk_index": row["chunk_index"], "timestamp": row.get("timestamp"),
                     "match": "exact"} for row in matches
                )
            else:
                retrieved_rows.append({"source_label": label, "session_id": sid,
                                       "chunk_index": None, "timestamp": timestamp,
                                       "match": "unmatched"})
    else:
        raw = adapter.memory.search(query, filters={"user_id": adapter.user_id}, top_k=k)
        values = raw.get("results", raw) if isinstance(raw, dict) else raw
        for value in values:
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") or {}
            sid = metadata.get("session_id")
            if not sid:
                continue
            sid = str(sid)
            if sid not in returned:
                returned.append(sid)
            label = source_labels.get(sid, "source-unknown")
            timestamp = metadata.get("timestamp", "unknown")
            texts.append(f"[{label} @ {timestamp}] {value.get('memory', value.get('text', ''))}")
            retrieved_rows.append({"source_label": label, "session_id": sid,
                                   "chunk_index": metadata.get("chunk_index"),
                                   "timestamp": timestamp, "match": "adapter-metadata"})
    return "\n".join(texts)[:char_budget], returned[:k], retrieved_rows, source_map


def run_comparison(data: Sequence[Mapping[str, Any]], raw: bytes, adapter_name: str,
                   answer_llm: object, judge_llm: object, *, sample: int = DEFAULT_SAMPLE,
                   k: int = DEFAULT_K, session_char_budget: int = DEFAULT_SESSION_CHAR_BUDGET,
                   chunk_char_budget: int = DEFAULT_CHUNK_CHAR_BUDGET,
                   context_char_budget: int = 9000,
                   embed_model: str = DEFAULT_EMBED_MODEL,
                   base_url: str = DEFAULT_BASE_URL,
                   mem0_config: Mapping[str, Any] | None = None,
                   temp_root: str | None = None, verbose: bool = True,
                   benchmark: str = "LongMemEval-S",
                   progress_path: str | Path | None = None,
                   session_diverse: bool = False,
                   session_overfetch: int = DEFAULT_SESSION_OVERFETCH) -> dict[str, Any]:
    """Run the matched evaluation.

    When ``progress_path`` is provided, a status-``running`` artifact is
    atomically replaced after each selected question, including its errors and
    cleanup record. The caller remains responsible for writing the final
    completed result, which keeps the existing return/API behavior unchanged.
    """
    if sample < 1 or sample > len(data):
        raise ValueError(f"sample must be between 1 and {len(data)}")
    if any(value < 1 for value in (k, session_char_budget, chunk_char_budget,
                                   context_char_budget)):
        raise ValueError("k and all character budgets must be positive")
    if (type(session_overfetch) is not int
            or not 1 <= session_overfetch <= MAX_SESSION_OVERFETCH):
        raise ValueError(
            f"session_overfetch must be an integer between 1 and {MAX_SESSION_OVERFETCH}")
    if embed_model != DEFAULT_EMBED_MODEL:
        raise ValueError(f"matched comparison requires embed model {DEFAULT_EMBED_MODEL!r}")
    if adapter_name == "mem0" and mem0_config is None:
        raise ValueError("mem0 config is required")
    if adapter_name == "mem0" and (session_diverse or session_overfetch != DEFAULT_SESSION_OVERFETCH):
        raise ValueError("session-diverse retrieval options are supported only for Smriti; Mem0 parity is unavailable")
    selected = stratified_answerable_sample(data, sample)
    results: list[dict[str, Any]] = []
    cleanup: list[dict[str, Any]] = []
    started = time.time()
    for index, item in enumerate(selected):
        adapter = None
        rec: dict[str, Any] = {
            "sample_id": item["sample_id"], "question_id": item["question_id"],
            "question_type": item["question_type"], "question": item["question"],
            "gold": item["gold"], "correct": False,
            "unanswerable": bool(item["unanswerable"]),
            "hypothesis": "", "errors": [],
        }
        try:
            source_labels = {str(sid): f"source-{pos:04d}"
                             for pos, sid in enumerate(
                                 dict.fromkeys(str(row["session_id"]) for row in item["rows"]), 1)}
            if adapter_name == "smriti":
                adapter = SmritiAdapter(OllamaEmbedder(model=embed_model, base_url=base_url))
            else:
                root = temp_root or tempfile.gettempdir()
                Path(root).mkdir(parents=True, exist_ok=True)
                adapter = Mem0Adapter(mem0_config or {}, root, base_url)
            ingest_started = time.perf_counter()
            for row in item["rows"]:
                adapter.add(row)
            rec["ingest_s"] = round(time.perf_counter() - ingest_started, 4)
            try:
                context_started = time.perf_counter()
                context, returned, retrieved_rows, source_map = _context(
                    adapter, str(item["question"]), k, context_char_budget,
                    item["rows"], source_labels,
                    session_diverse=session_diverse,
                    session_overfetch=session_overfetch)
                rec["retrieval_s"] = round(time.perf_counter() - context_started, 4)
                rec["returned_session_ids"] = returned
                rec["retrieved_rows"] = retrieved_rows
                rec["source_map"] = source_map
                # This is the exact post-budget context sent to the reader.
                rec["reader_context"] = context
            except Exception as exc:
                rec["errors"].append(_error("retrieval", exc))
                results.append(rec)
                continue
            try:
                today = parse_lme_date(item.get("question_date")) if item.get("question_date") else "unknown"
                answer_started = time.perf_counter()
                rec["hypothesis"] = answer_llm.complete(
                    [{"role": "system", "content": ANSWER_SYSTEM.format(today=(today or "")[:10] or "unknown")},
                     {"role": "user", "content":
                      f"MEMORY CONTEXT:\n{context}\n\nQUESTION: {item['question']}\n"
                      "Answer concisely without showing reasoning."}],
                    max_tokens=256).strip()
                rec["answer_s"] = round(time.perf_counter() - answer_started, 4)
            except Exception as exc:
                rec["errors"].append(_error("answer", exc))
                results.append(rec)
                continue
            try:
                if item["unanswerable"]:
                    rec["correct"] = is_abstention(rec["hypothesis"])
                else:
                    rec["correct"] = judge(judge_llm, str(item["question"]),
                                            str(item["gold"]), rec["hypothesis"],
                                            question_id=str(item["question_id"]))
            except Exception as exc:
                rec["errors"].append(_error("judge", exc))
            results.append(rec)
            if verbose:
                print(f"[{index + 1}/{len(selected)}] {item['question_id']} errors={len(rec['errors'])}", flush=True)
        except Exception as exc:
            rec["errors"].append(_error("ingest", exc))
            results.append(rec)
        except BaseException as exc:
            # Preserve the interrupted question before allowing Ctrl-C or a
            # process-level abort to propagate.  The finally block below then
            # records cleanup and atomically checkpoints this error-inclusive
            # partial result.
            rec["errors"].append(_error("interrupted", exc))
            results.append(rec)
            raise
        finally:
            row = {"sample_id": item["sample_id"], "question_id": item["question_id"],
                   "attempted": adapter is not None, "ok": True}
            try:
                if adapter is not None:
                    try:
                        adapter.close()
                    except Exception as exc:
                        row.update({"ok": False, "error": _error("cleanup", exc)})
            finally:
                cleanup.append(row)
                _write_progress_checkpoint(
                    progress_path, raw=raw, benchmark=benchmark,
                    adapter_name=adapter_name, selected=selected,
                    results=results, cleanup=cleanup,
                    answer_llm=answer_llm, judge_llm=judge_llm,
                    session_diverse=session_diverse,
                    session_overfetch=session_overfetch)
    failures = sum(1 for row in results if row["errors"])
    answerable_rows = [row for row in results if not row["unanswerable"]]
    abstention_rows = [row for row in results if row["unanswerable"]]
    completed_rows = [row for row in results if not row["errors"]]
    completed_answerable_rows = [row for row in answerable_rows if not row["errors"]]
    completed_abstention_rows = [row for row in abstention_rows if not row["errors"]]
    answerable_correct = sum(bool(row["correct"]) for row in answerable_rows)
    abstention_correct = sum(bool(row["correct"]) for row in abstention_rows)
    summary = {
        "benchmark": benchmark,
        "adapter": adapter_name, "requested": len(selected), "completed": len(completed_rows),
        "failures": failures, "cleanup_failures": sum(not row["ok"] for row in cleanup),
        "failure_inclusive_denominator": len(selected),
        "correct": sum(bool(row["correct"]) for row in results),
        "accuracy": round(sum(bool(row["correct"]) for row in results) / max(1, len(selected)), 4),
        "answerable_requested": sum(not item["unanswerable"] for item in selected),
        "abstention_requested": sum(bool(item["unanswerable"]) for item in selected),
        "answerable_completed": len(completed_answerable_rows),
        "abstention_completed": len(completed_abstention_rows),
        "answerable_correct": answerable_correct,
        "abstention_correct": abstention_correct,
        "answerable_accuracy": round(answerable_correct / max(1, len(answerable_rows)), 4),
        "abstention_accuracy": round(abstention_correct / max(1, len(abstention_rows)), 4)
        if abstention_rows else None,
        "source_count": len({str(item.get("sample_id", "")) for item in selected}),
        "question_type_counts": {
            question_type: sum(str(item.get("question_type", "unknown")) == question_type
                               for item in selected)
            for question_type in dict.fromkeys(
                str(item.get("question_type", "unknown")) for item in selected)
        },
        "elapsed_s": round(time.time() - started, 4),
        "usage": {"answer": _usage(answer_llm), "judge": _usage(judge_llm)},
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if failures == 0 and all(row["ok"] for row in cleanup)
        and len(results) == len(selected) else "partial",
        "dataset_sha256": hashlib.sha256(raw).hexdigest(), "summary": summary,
        "provenance": {"platform": platform.platform(), "python": platform.python_version(),
                       "models": {"answer": _llm_meta(answer_llm), "judge": _llm_meta(judge_llm)},
                       "memory": ({"adapter": "Smriti", "mode": "lite",
                                   "embedder": {"class": "OllamaEmbedder",
                                                 "provider": "ollama",
                                                 "model": embed_model,
                                                 "dimensions": 768,
                                                 "base_url": base_url}}
                                  if adapter_name == "smriti" else
                                  {"adapter": "Mem0 OSS", "mode": "infer=False",
                                   "provider_config": _redact_config(mem0_config or {}),
                                   "embedder": {"provider": "ollama",
                                                 "model": embed_model,
                                                 "dimensions": 768,
                                                 "base_url": base_url}}),
                       "embedding": {"provider": "ollama", "model": embed_model,
                                     "dimensions": 768, "base_url": base_url},
                       "retrieval": {"session_diverse": session_diverse,
                                     "session_overfetch": session_overfetch,
                                     "option_scope": "Smriti only; Mem0 rejects non-default options"},
                       "budgets": {"sample": sample, "k": k,
                                   "session_char_budget": session_char_budget,
                                   "chunk_char_budget": chunk_char_budget,
                                   "context_char_budget": context_char_budget,
                                   "answer_max_tokens": 256, "judge_max_tokens": 8},
                       "usage_scope": "Cumulative counters on shared answer/judge objects; not per-question deltas.",
                       "failure_policy": "Every selected question remains in the denominator; raw errors are retained."},
        "selection": {"question_ids": [item["question_id"] for item in selected],
                      "sample_ids": list(dict.fromkeys(str(item.get("sample_id", ""))
                                                       for item in selected)),
                      "answerable_question_ids": [item["question_id"] for item in selected
                                                   if not item["unanswerable"]],
                      "abstention_question_ids": [item["question_id"] for item in selected
                                                   if item["unanswerable"]]},
        "cleanup": cleanup, "results": results,
    }


def judge_sanity_check(judge_llm: object) -> dict[str, Any]:
    """Run two exact yes/no checks and retain raw failures for the artifact."""
    checks: list[dict[str, Any]] = []
    try:
        for gold, response, expected in (("blue", "The answer is blue.", "yes"),
                                         ("blue", "I don't have enough information.", "no")):
            raw_verdict = judge_llm.complete(
                [{"role": "system", "content":
                  "Return exactly yes or no. Do not include reasoning or any other text."},
                 {"role": "user", "content":
                  f"Question: What color?\nGold answer: {gold}\nAssistant response: {response}\nCorrect?"}],
                max_tokens=8)
            checks.append({"expected": expected, "raw": raw_verdict,
                           "ok": raw_verdict.strip().lower() == expected})
            if raw_verdict.strip().lower() != expected:
                raise ValueError(f"expected {expected!r}, got {raw_verdict!r}")
        return {"enabled": True, "status": "passed", "request": getattr(judge_llm, "extra_body", None),
                "checks": checks}
    except Exception as exc:
        return {"enabled": True, "status": "failed", "request": getattr(judge_llm, "extra_body", None),
                "checks": checks, "error": _error("judge_sanity", exc)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Matched answer/judge public QA evaluation")
    parser.add_argument("--dataset", choices=("longmemeval", "locomo"), required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--adapter", choices=("smriti", "mem0"), required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--session-char-budget", type=int, default=DEFAULT_SESSION_CHAR_BUDGET)
    parser.add_argument("--chunk-char-budget", type=int, default=DEFAULT_CHUNK_CHAR_BUDGET)
    parser.add_argument("--context-char-budget", type=int, default=9000)
    parser.add_argument("--answer-model", default=DEFAULT_QWEN_MODEL)
    parser.add_argument("--judge-model", default=DEFAULT_QWEN_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--mem0-config", default=None)
    parser.add_argument("--session-diverse", action="store_true",
                        help="enable Smriti's opt-in session-diverse selector")
    parser.add_argument("--session-overfetch", type=int, default=DEFAULT_SESSION_OVERFETCH,
                        help="bounded Smriti selector overfetch (default: 3)")
    parser.add_argument("--quiet", action="store_true")
    sanity_group = parser.add_mutually_exclusive_group()
    sanity_group.add_argument("--judge-sanity-check", action="store_true",
                              help="run two exact yes/no judge checks before evaluation (default)")
    sanity_group.add_argument("--skip-judge-sanity-check", action="store_true",
                              help="skip the preflight judge checks")
    args = parser.parse_args()
    if args.answer_model != DEFAULT_QWEN_MODEL or args.judge_model != DEFAULT_QWEN_MODEL:
        raise SystemExit("matched QA route requires qwen3:8b for both answer and judge")
    if (type(args.session_overfetch) is not int
            or not 1 <= args.session_overfetch <= MAX_SESSION_OVERFETCH):
        raise SystemExit(
            f"--session-overfetch must be an integer between 1 and {MAX_SESSION_OVERFETCH}")
    if args.adapter == "mem0" and (args.session_diverse or args.session_overfetch != DEFAULT_SESSION_OVERFETCH):
        raise SystemExit("session-diverse retrieval options are supported only for Smriti; Mem0 parity is unavailable")
    path = Path(args.data)
    raw = path.read_bytes()
    if args.dataset == "longmemeval":
        data = load_longmemeval(str(path))
        if path.name.lower().find("oracle") >= 0:
            raise SystemExit("oracle split is not a full-haystack comparison")
        questions = _longmemeval_questions(data, args.session_char_budget, args.chunk_char_budget)
    else:
        questions = _locomo_questions(load_locomo(str(path)), args.session_char_budget, args.chunk_char_budget)
        data = questions
    llm_base_url = args.base_url.rstrip("/")
    if not llm_base_url.endswith("/v1"):
        llm_base_url += "/v1"
    # Request documented no-reasoning behavior; the default preflight below
    # records whether this daemon actually returns exact yes/no judgments.
    ollama_request = {"reasoning_effort": "none", "think": False}
    answer = LLM(model=args.answer_model, provider="ollama", base_url=llm_base_url,
                 extra_body=ollama_request)
    judge_llm = LLM(model=args.judge_model, provider="ollama", base_url=llm_base_url,
                    extra_body=ollama_request)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sanity = {"enabled": not args.skip_judge_sanity_check,
               "request": ollama_request, "checks": []}
    if not args.skip_judge_sanity_check:
        sanity = judge_sanity_check(judge_llm)
        if sanity["status"] == "failed":
            blocked = {
                "schema_version": SCHEMA_VERSION, "status": "blocked_judge_sanity",
                "dataset_sha256": hashlib.sha256(raw).hexdigest(),
                "selection": {"available_questions": len(questions)},
                "provenance": {"models": {"answer": _llm_meta(answer),
                                             "judge": _llm_meta(judge_llm)},
                               "ollama_request": ollama_request},
                "judge_sanity": sanity,
            }
            _atomic_write_json(destination, blocked)
            print(json.dumps(blocked, indent=2))
            raise SystemExit(2)
    else:
        sanity["status"] = "skipped"
    config = _read_mem0_config(args.mem0_config) if args.adapter == "mem0" else None
    result = run_comparison(questions, raw, args.adapter, answer, judge_llm,
                            sample=args.sample, k=args.k,
                            session_char_budget=args.session_char_budget,
                            chunk_char_budget=args.chunk_char_budget,
                            context_char_budget=args.context_char_budget,
                            base_url=args.base_url, mem0_config=config,
                            session_diverse=args.session_diverse,
                            session_overfetch=args.session_overfetch,
                            verbose=not args.quiet,
                            benchmark="LongMemEval-S" if args.dataset == "longmemeval" else "LoCoMo",
                            progress_path=destination)
    result["judge_sanity"] = sanity
    result["provenance"]["ollama_request"] = ollama_request
    _atomic_write_json(destination, result)
    print(json.dumps(result["summary"], indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
