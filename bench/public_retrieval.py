"""Matched raw-session retrieval on the official LongMemEval-S dataset.

This is deliberately a retrieval-only track. It ingests the complete public
haystack (subject to explicit, shared session/chunk budgets), bypasses
extraction and answer generation, and scores returned session ids against the
dataset's ``answer_session_ids`` labels. The oracle split is rejected because
it contains evidence sessions only and is an easy sanity ceiling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

from smriti import OllamaEmbedder, Smriti

OFFICIAL_DATASET_URL = (
    "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/"
    "resolve/main/longmemeval_s_cleaned.json"
)
SCHEMA_VERSION = 2
DEFAULT_EMBED_MODEL = "nomic-embed-text:v1.5"
DEFAULT_EMBED_DIMS = 768
DEFAULT_BASE_URL = "http://127.0.0.1:11436"
DEFAULT_SAMPLE = 10
DEFAULT_K = 5
DEFAULT_SESSION_CHAR_BUDGET = 16000
# Ollama reports a 2048-token context for the shared nomic model.  Character
# count is only a conservative proxy (CJK/code can approach one token per
# character), so keep the default well below that limit.  Existing 4000-char
# artifacts remain raw exploratory runs and record their explicit budget.
DEFAULT_CHUNK_CHAR_BUDGET = 1000


class DatasetError(ValueError):
    """Raised for malformed or non-comparable input data."""


def percentile(values: Sequence[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(p * len(ordered)) - 1))
    return round(ordered[index], 3)


def stratified_sample(items: Sequence[Mapping[str, Any]], n: int) -> list[Mapping[str, Any]]:
    """Stable round-robin sample over question types."""
    if n < 1:
        raise ValueError("sample must be at least 1")
    if n > len(items):
        raise ValueError(f"sample={n} exceeds dataset size {len(items)}")
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        groups.setdefault(str(item.get("question_type", "unknown")), []).append(item)
    cursors = {key: 0 for key in groups}
    active = list(groups)
    selected: list[Mapping[str, Any]] = []
    while active and len(selected) < n:
        for key in list(active):
            pos = cursors[key]
            group = groups[key]
            if pos >= len(group):
                active.remove(key)
                continue
            selected.append(group[pos])
            cursors[key] = pos + 1
            if len(selected) == n:
                break
    return selected


def validate_item(item: Mapping[str, Any]) -> None:
    """Validate parallel arrays before any zip operation."""
    required = ("question_id", "question", "question_type", "haystack_sessions",
                "haystack_dates", "haystack_session_ids", "answer_session_ids")
    missing = [key for key in required if key not in item]
    if missing:
        raise DatasetError(f"missing required fields: {', '.join(missing)}")
    arrays = [item["haystack_sessions"], item["haystack_dates"], item["haystack_session_ids"]]
    if not all(isinstance(value, list) for value in arrays):
        raise DatasetError("haystack_sessions, haystack_dates, and haystack_session_ids must be lists")
    lengths = [len(value) for value in arrays]
    if len(set(lengths)) != 1:
        raise DatasetError(f"mismatched session/id/date lengths: {lengths}")
    if not isinstance(item["answer_session_ids"], list):
        raise DatasetError("answer_session_ids must be a list")


def load_dataset(path: str) -> tuple[list[dict[str, Any]], bytes]:
    """Load official LongMemEval-S bytes and reject the oracle split."""
    source = Path(path)
    if "oracle" in source.name.lower():
        raise DatasetError("the oracle split is evidence-only and cannot be used for full-haystack results")
    raw = source.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise DatasetError("LongMemEval-S must be a non-empty JSON array")
    for item in data:
        if not isinstance(item, dict):
            raise DatasetError("each LongMemEval item must be an object")
        validate_item(item)
    return data, raw


def render_session(session: Sequence[Mapping[str, Any]]) -> str:
    """Render a session without putting its id or answer label in the text."""
    parts = []
    for turn in session:
        raw_content = turn.get("content", "")
        if raw_content:
            parts.append(f"{turn.get('role', 'user')}: {raw_content}")
    return "\n".join(parts)


def chunk_session(text: str, session_char_budget: int, chunk_char_budget: int) -> tuple[list[str], dict[str, int]]:
    """Apply shared session and chunk limits, returning chunks and counters."""
    if session_char_budget < 1 or chunk_char_budget < 1:
        raise ValueError("session and chunk budgets must be positive")
    original_chars = len(text)
    bounded = text[:session_char_budget]
    chunks = [bounded[start:start + chunk_char_budget]
              for start in range(0, len(bounded), chunk_char_budget)]
    return chunks, {
        "original_chars": original_chars,
        "indexed_chars": len(bounded),
        "truncated_session_chars": max(0, original_chars - len(bounded)),
        "chunk_count": len(chunks),
        "truncated_chunk_chars": 0,
    }


def iter_index_rows(item: Mapping[str, Any], session_char_budget: int,
                    chunk_char_budget: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Create adapter-neutral rows and aggregate truncation counters."""
    validate_item(item)
    rows: list[dict[str, Any]] = []
    totals = {"session_count": 0, "chunk_count": 0, "original_chars": 0,
              "indexed_chars": 0, "truncated_session_chars": 0,
              "truncated_chunk_chars": 0}
    for index in range(len(item["haystack_sessions"])):
        sid = item["haystack_session_ids"][index]
        date = item["haystack_dates"][index]
        session = item["haystack_sessions"][index]
        totals["session_count"] += 1
        chunks, stats = chunk_session(render_session(session), session_char_budget, chunk_char_budget)
        for chunk_index, text in enumerate(chunks):
            # The identifier lives only in adapter metadata/session_id. It is
            # deliberately absent from the embedding payload.
            rows.append({"session_id": str(sid), "timestamp": date,
                         "chunk_index": chunk_index, "text": text})
        for key in ("chunk_count", "original_chars", "indexed_chars",
                    "truncated_session_chars", "truncated_chunk_chars"):
            totals[key] += stats[key]
    return rows, totals


def is_unanswerable_item(item: Mapping[str, Any]) -> bool:
    """LongMemEval marks abstention questions with a ``_abs`` id suffix."""
    return str(item.get("question_id", "")).lower().endswith("_abs")


def score_retrieval(returned: Sequence[str], relevant: Sequence[str], k: int,
                    unanswerable: bool = False) -> dict[str, Any]:
    """Score unique returned session ids against dataset-derived labels."""
    returned_unique = []
    for sid in returned[:k]:
        sid = str(sid)
        if sid and sid not in returned_unique:
            returned_unique.append(sid)
    relevant_set = set() if unanswerable else {str(sid) for sid in relevant}
    ranks = [returned_unique.index(sid) + 1 for sid in relevant_set if sid in returned_unique]
    return {
        "returned": returned_unique,
        "relevant": sorted(relevant_set),
        "recall_at_k": len(ranks) / len(relevant_set) if relevant_set else None,
        "reciprocal_rank": 1 / min(ranks) if ranks else (None if unanswerable else 0.0),
        "unanswerable": unanswerable,
        "empty_retrieval_success": bool(unanswerable and not returned_unique),
    }


class SmritiAdapter:
    label = "Smriti lite / raw episodes / Ollama nomic-embed-text:v1.5"

    def __init__(self, embedder: OllamaEmbedder):
        self.memory = Smriti(path=":memory:", mode="lite", embedder=embedder,
                             expand_keys=False, aggregate=False, dedupe=False)

    def add(self, row: Mapping[str, Any]) -> None:
        self.memory.add([{"role": "user", "content": row["text"]}],
                        session_id=row["session_id"], timestamp=row["timestamp"])

    def search(self, query: str, k: int) -> list[str]:
        ids = []
        for hit in self.memory.search(query, k=k):
            episode = self.memory.store.get_episode(hit.id)
            if episode and episode.session_id not in ids:
                ids.append(episode.session_id)
        return ids[:k]

    def close(self) -> None:
        self.memory.close()


def _patch_mem0_config(config: Mapping[str, Any], root: str, base_url: str) -> dict[str, Any]:
    """Clone a mem0 config into a fresh per-question local store."""
    cfg = json.loads(json.dumps(config))
    cfg["history_db_path"] = os.path.join(root, "history.db")
    vector = cfg.get("vector_store", {})
    vector_cfg = vector.get("config", {}) if isinstance(vector, dict) else {}
    if isinstance(vector_cfg, dict):
        vector_cfg["path"] = os.path.join(root, "qdrant")
        vector_cfg["collection_name"] = "lme_" + uuid.uuid4().hex
        # mem0's Qdrant config defaults to 1536, while nomic-embed-text:v1.5
        # returns 768 dimensions. Keep the vector-store shape matched too.
        if vector.get("provider") == "qdrant":
            vector_cfg["embedding_model_dims"] = DEFAULT_EMBED_DIMS
    embedder = cfg.get("embedder", {})
    embedder_cfg = embedder.get("config", {}) if isinstance(embedder, dict) else {}
    if isinstance(embedder_cfg, dict):
        embedder_cfg["ollama_base_url"] = base_url
    return cfg


class Mem0Adapter:
    label = "mem0 OSS / infer=False / configured Ollama nomic-embed-text:v1.5"

    def __init__(self, config: Mapping[str, Any], root: str, base_url: str):
        from mem0 import Memory
        self.root = tempfile.mkdtemp(prefix="smriti-public-mem0-", dir=root)
        self.memory = Memory.from_config(_patch_mem0_config(config, self.root, base_url))
        self.user_id = "lme-" + uuid.uuid4().hex

    def add(self, row: Mapping[str, Any]) -> None:
        self.memory.add(row["text"], user_id=self.user_id, infer=False,
                        metadata={"session_id": row["session_id"],
                                  "chunk_index": row["chunk_index"],
                                  "timestamp": row["timestamp"]})

    def search(self, query: str, k: int) -> list[str]:
        raw = self.memory.search(query, filters={"user_id": self.user_id}, top_k=k)
        rows = raw.get("results", raw) if isinstance(raw, dict) else raw
        ids = []
        for row in rows:
            sid = (row.get("metadata") or {}).get("session_id") if isinstance(row, dict) else None
            if sid and sid not in ids:
                ids.append(str(sid))
        return ids[:k]

    def close(self) -> None:
        db = getattr(self.memory, "db", None)
        errors = []
        for resource in (db, getattr(self.memory, "vector_store", None)):
            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{type(exc).__name__}: {exc}")
        shutil.rmtree(self.root, ignore_errors=True)
        if errors:
            raise RuntimeError("; ".join(errors))


def _read_mem0_config(value: str | None) -> dict[str, Any]:
    source = value or os.environ.get("MEM0_BENCH_CONFIG")
    if not source:
        raise RuntimeError("MEM0_BENCH_CONFIG or --mem0-config is required")
    path = Path(source)
    try:
        config = json.loads(path.read_text()) if path.exists() else json.loads(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid mem0 config: {exc}") from exc
    if not isinstance(config, dict):
        raise RuntimeError("mem0 config must be a JSON object")
    embedder = config.get("embedder", {})
    provider = embedder.get("provider") if isinstance(embedder, dict) else None
    model = (embedder.get("config") or {}).get("model") if isinstance(embedder, dict) else None
    if provider != "ollama" or model != DEFAULT_EMBED_MODEL:
        raise RuntimeError("mem0 config must use embedder.provider=ollama and model=nomic-embed-text:v1.5")
    return config


def run(data: Sequence[Mapping[str, Any]], raw: bytes, adapter_name: str, *, sample: int,
        k: int, embed_model: str, base_url: str, session_char_budget: int,
        chunk_char_budget: int, mem0_config: Mapping[str, Any] | None = None,
        temp_root: str | None = None, verbose: bool = True) -> dict[str, Any]:
    if embed_model != DEFAULT_EMBED_MODEL:
        raise ValueError(f"matched public run requires embed model {DEFAULT_EMBED_MODEL!r}")
    if k < 1:
        raise ValueError("k must be at least 1")
    items = stratified_sample(data, sample)
    started = time.time()
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    cleanup_failures: list[dict[str, Any]] = []
    latency: list[float] = []
    truncation = {"sessions": 0, "chunks": 0, "original_chars": 0,
                  "indexed_chars": 0, "truncated_session_chars": 0,
                  "truncated_chunk_chars": 0}
    owns_root = temp_root is None
    root = temp_root or tempfile.mkdtemp(prefix="smriti-public-")
    os.makedirs(root, exist_ok=True)
    for index, item in enumerate(items):
        adapter = None
        active_row: dict[str, Any] | None = None
        try:
            rows, stats = iter_index_rows(item, session_char_budget, chunk_char_budget)
            for key, value in (("sessions", stats["session_count"]),
                               ("chunks", stats["chunk_count"]),
                               ("original_chars", stats["original_chars"]),
                               ("indexed_chars", stats["indexed_chars"]),
                               ("truncated_session_chars", stats["truncated_session_chars"]),
                               ("truncated_chunk_chars", stats["truncated_chunk_chars"])):
                truncation[key] += value
            if adapter_name == "smriti":
                adapter = SmritiAdapter(OllamaEmbedder(model=embed_model, base_url=base_url))
            else:
                if mem0_config is None:
                    raise RuntimeError("mem0 config is required")
                adapter = Mem0Adapter(mem0_config, root, base_url)
            ingest_started = time.perf_counter_ns()
            for row in rows:
                active_row = row
                adapter.add(row)
            active_row = None
            ingest_ms = (time.perf_counter_ns() - ingest_started) / 1e6
            query_started = time.perf_counter_ns()
            returned = adapter.search(str(item["question"]), k)
            query_ms = (time.perf_counter_ns() - query_started) / 1e6
            latency.append(query_ms)
            score = score_retrieval(returned, item["answer_session_ids"], k,
                                    unanswerable=is_unanswerable_item(item))
            results.append({"question_id": item["question_id"],
                            "question_type": item["question_type"],
                            "session_count": stats["session_count"],
                            "chunk_count": stats["chunk_count"],
                            "ingest_ms": round(ingest_ms, 3),
                            "latency_ms": round(query_ms, 3), **score})
            if verbose:
                print(f"[{index + 1}/{len(items)}] {item['question_id']} {item['question_type']} latency={query_ms:.1f}ms", flush=True)
        except Exception as exc:
            failure: dict[str, Any] = {
                "question_id": item.get("question_id", str(index)),
                "question_type": item.get("question_type", "unknown"),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
            # Preserve the exact adapter-neutral row that failed. This makes
            # context-limit failures diagnosable without parsing ids from text.
            if active_row is not None:
                failure["failed_row"] = {
                    "session_id": active_row["session_id"],
                    "chunk_index": active_row["chunk_index"],
                    "text_chars": len(active_row["text"]),
                }
            failures.append(failure)
            if verbose:
                print(f"[{index + 1}/{len(items)}] ERR {type(exc).__name__}: {exc}", flush=True)
        finally:
            if adapter is not None:
                try:
                    adapter.close()
                except Exception as exc:
                    cleanup_failures.append({"question_id": item.get("question_id", str(index)),
                                             "question_type": item.get("question_type", "unknown"),
                                     "error": {"type": type(exc).__name__, "message": f"cleanup: {exc}"}})
    if owns_root:
        shutil.rmtree(root, ignore_errors=True)
    denominator = len(items)
    answerable_items = [item for item in items if not is_unanswerable_item(item)]
    answerable_denominator = len(answerable_items)
    scored = [row for row in results if row["relevant"] and not row["unanswerable"]]
    abstention_rows = [row for row in results if row["unanswerable"]]
    abstention_requested = len(items) - answerable_denominator
    type_denominators: dict[str, int] = {}
    type_recall: dict[str, float] = {}
    type_mrr: dict[str, float] = {}
    type_failures: dict[str, int] = {}
    for item in items:
        qtype = str(item.get("question_type", "unknown"))
        type_denominators[qtype] = type_denominators.get(qtype, 0) + 1
    for row in results:
        qtype = str(row["question_type"])
        type_recall[qtype] = type_recall.get(qtype, 0.0) + (row["recall_at_k"] or 0.0)
        type_mrr[qtype] = type_mrr.get(qtype, 0.0) + (row["reciprocal_rank"] or 0.0)
    for failure in failures:
        qtype = str(failure.get("question_type", "unknown"))
        type_failures[qtype] = type_failures.get(qtype, 0) + 1
    per_type = {
        qtype: {
            "requested": count,
            "completed": count - type_failures.get(qtype, 0),
            "failures": type_failures.get(qtype, 0),
            "answerable_requested": sum(1 for item in items
                                          if str(item.get("question_type", "unknown")) == qtype
                                          and not is_unanswerable_item(item)),
            "unanswerable_requested": sum(1 for item in items
                                            if str(item.get("question_type", "unknown")) == qtype
                                            and is_unanswerable_item(item)),
            "mean_recall_at_k": round(type_recall.get(qtype, 0.0) /
                                       max(1, sum(1 for item in items
                                                  if str(item.get("question_type", "unknown")) == qtype
                                                  and not is_unanswerable_item(item))), 4),
            "mrr": round(type_mrr.get(qtype, 0.0) /
                          max(1, sum(1 for item in items
                                     if str(item.get("question_type", "unknown")) == qtype
                                     and not is_unanswerable_item(item))), 4),
        }
        for qtype, count in sorted(type_denominators.items())
    }
    summary = {
        "requested": denominator,
        "completed": len(results),
        "failures": len(failures),
        "cleanup_failures": len(cleanup_failures),
        "failure_inclusive_denominator": denominator,
        "answerable_requested": answerable_denominator,
        "answerable_completed": sum(1 for row in results if not row["unanswerable"]),
        "mean_recall_at_k": round(sum(row["recall_at_k"] or 0 for row in results
                                       if not row["unanswerable"]) /
                                   max(1, answerable_denominator), 4),
        "mrr": round(sum(row["reciprocal_rank"] or 0 for row in results
                         if not row["unanswerable"]) /
                     max(1, answerable_denominator), 4),
        "empty_retrieval_requested": abstention_requested,
        "empty_retrieval_completed": len(abstention_rows),
        "empty_retrieval_successes": sum(1 for row in abstention_rows if row["empty_retrieval_success"]),
        "empty_retrieval_rate": (round(sum(1 for row in abstention_rows
                                             if row["empty_retrieval_success"]) /
                                        abstention_requested, 4)
                                 if abstention_requested else None),
        "latency_ms_p50": percentile(latency, 0.50),
        "latency_ms_p95": percentile(latency, 0.95),
        "truncation": truncation,
        "per_question_type": per_type,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if len(results) == denominator and not failures and not cleanup_failures else "partial",
        "track": "official LongMemEval-S full-haystack raw-session retrieval; extraction bypassed",
        "adapter": adapter_name,
        "configuration": "Smriti lite / raw episodes / Ollama nomic-embed-text:v1.5" if adapter_name == "smriti" else Mem0Adapter.label,
        "dataset": {"source": OFFICIAL_DATASET_URL,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "total_items": len(data),
                    "selected_items": [item["question_id"] for item in items]},
        "embedding": {"provider": "Ollama", "model": embed_model,
                       "dimensions": DEFAULT_EMBED_DIMS, "base_url": base_url},
        "budgets": {"sample": sample, "k": k,
                    "session_char_budget": session_char_budget,
                    "chunk_char_budget": chunk_char_budget},
        "run": {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "platform": platform.platform(), "python": sys.version,
                "clock": "time.perf_counter_ns",
                "failure_policy": "raw failures remain in denominator as zero"},
        "summary": summary, "results": results, "failure_records": failures,
        "cleanup_failure_records": cleanup_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Matched full-haystack LongMemEval-S retrieval")
    parser.add_argument("--adapter", choices=("smriti", "mem0"), required=True)
    parser.add_argument("--data", required=True, help="official longmemeval_s_cleaned.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE,
                        help="stable stratified question count (10 pilot; use 50 for bounded run)")
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--session-char-budget", type=int, default=DEFAULT_SESSION_CHAR_BUDGET)
    parser.add_argument("--chunk-char-budget", type=int, default=DEFAULT_CHUNK_CHAR_BUDGET)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--mem0-config", default=None, help="JSON path or inline JSON; required for mem0")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    data, raw = load_dataset(args.data)
    mem0_config = _read_mem0_config(args.mem0_config) if args.adapter == "mem0" else None
    result = run(data, raw, args.adapter, sample=args.sample, k=args.k,
                 embed_model=args.embed_model, base_url=args.base_url,
                 session_char_budget=args.session_char_budget,
                 chunk_char_budget=args.chunk_char_budget, mem0_config=mem0_config,
                 verbose=not args.quiet)
    destination = Path(args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
