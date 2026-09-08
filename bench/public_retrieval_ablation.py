"""Held-out retrieval ablation for the opt-in session-diverse selector.

The driver builds one Smriti raw-session index per question, then queries that
same index with the default selector and ``session_diverse=True``. It never
passes answer labels into the index or query path; labels are read only after
retrieval to compute coverage. This module performs no work at import time.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from smriti import OllamaEmbedder, Smriti
from smriti import retrieval as smriti_retrieval

from .public_retrieval import (
    DEFAULT_BASE_URL,
    DEFAULT_CHUNK_CHAR_BUDGET,
    DEFAULT_EMBED_MODEL,
    DEFAULT_K,
    DEFAULT_SESSION_CHAR_BUDGET,
    iter_index_rows,
    load_dataset,
)

SCHEMA_VERSION = 1
DEFAULT_OVERFETCH = 3
DEFAULT_SAMPLE = 20
DEFAULT_EXCLUDE_FILES = (
    "audit/2026-09-05/public-retrieval-smriti-s50.json",
    "audit/2026-09-05/public-retrieval-mem0-s50.json",
    "audit/2026-09-05/public-qa-smriti-s6.json",
    "audit/2026-09-05/public-qa-mem0-s6.json",
)


def stratified_sample_excluding(items: Sequence[Mapping[str, Any]], n: int,
                                excluded_ids: set[str]) -> list[Mapping[str, Any]]:
    """Stable round-robin sample after removing explicitly held-out ids."""
    eligible = [item for item in items if str(item.get("question_id")) not in excluded_ids]
    if n < 1 or n > len(eligible):
        raise ValueError(f"sample must be between 1 and {len(eligible)} after exclusions")
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in eligible:
        groups.setdefault(str(item.get("question_type", "unknown")), []).append(item)
    cursors = {key: 0 for key in groups}
    active = list(groups)
    selected: list[Mapping[str, Any]] = []
    while active and len(selected) < n:
        for key in list(active):
            if cursors[key] >= len(groups[key]):
                active.remove(key)
                continue
            selected.append(groups[key][cursors[key]])
            cursors[key] += 1
            if len(selected) == n:
                break
    return selected


def load_exclusions(repo_root: Path, files: Sequence[str], explicit: Sequence[str]) -> tuple[set[str], list[str]]:
    """Read prior-run selections and fail closed when a requested file is absent."""
    excluded = {str(value) for value in explicit}
    sources: list[str] = []
    for raw_path in files:
        path = repo_root / raw_path
        if not path.exists():
            raise FileNotFoundError(f"required exclusion artifact is missing: {path}")
        data = json.loads(path.read_text())
        ids = data.get("dataset", {}).get("selected_items") or data.get("selection", {}).get("question_ids")
        if not isinstance(ids, list):
            raise ValueError(f"exclusion artifact has no selected ids: {path}")
        excluded.update(str(value) for value in ids)
        sources.append(str(path))
    return excluded, sources


def _source_snapshot() -> dict[str, Any]:
    imported = {
        "ablation_module": sys.modules[__name__],
        "public_retrieval_module": sys.modules["bench.public_retrieval"],
        "smriti_retrieval_module": smriti_retrieval,
        "smriti_class": Smriti,
        "ollama_embedder_class": OllamaEmbedder,
    }
    files: dict[str, str] = {}
    paths: dict[str, str] = {}
    for label, value in imported.items():
        path = Path(inspect.getfile(value)).resolve()
        paths[label] = str(path)
        files[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    roots = [Path(path).parent for path in paths.values()]
    repo_root = next((candidate for path in roots for candidate in (path, *path.parents)
                      if (candidate / ".git").exists()), None)
    commit = None
    if repo_root is not None:
        try:
            commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_root,
                                             text=True, stderr=subprocess.DEVNULL).strip()
        except (OSError, subprocess.CalledProcessError):
            pass
    return {"captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "commit": commit, "imported_module_paths": paths,
            "imported_file_sha256": files}


def _variant_hits(memory: Smriti, query: str, k: int, *, session_diverse: bool,
                  overfetch: int) -> list[dict[str, Any]]:
    hits = memory.search(query, k=k, session_diverse=session_diverse,
                         session_overfetch=overfetch)
    output = []
    for hit in hits[:k]:
        episode = memory.store.get_episode(hit.id)
        output.append({
            "result_id": hit.id,
            "kind": hit.kind,
            "episode_id": hit.id if episode is not None else None,
            "session_id": str(episode.session_id) if episode is not None and episode.session_id else None,
            "score": round(float(hit.score), 8),
        })
    return output


def _score_hits(hits: Sequence[Mapping[str, Any]], relevant: Sequence[str],
                unanswerable: bool) -> dict[str, Any]:
    returned_episode_ids = [hit["episode_id"] for hit in hits if hit.get("episode_id") is not None]
    returned_session_ids: list[str] = []
    for hit in hits:
        sid = hit.get("session_id")
        if sid and sid not in returned_session_ids:
            returned_session_ids.append(str(sid))
    relevant_ids = [] if unanswerable else list(dict.fromkeys(str(sid) for sid in relevant))
    covered = [sid for sid in relevant_ids if sid in returned_session_ids]
    ranks = [returned_session_ids.index(sid) + 1 for sid in relevant_ids
             if sid in returned_session_ids]
    return {
        "returned_episode_ids": returned_episode_ids,
        "returned_session_ids": returned_session_ids,
        "returned_session_count": len(returned_session_ids),
        "relevant_session_ids": relevant_ids,
        "covered_relevant_session_ids": covered,
        "recall_at_k": (len(covered) / len(relevant_ids) if relevant_ids else None),
        "relevant_coverage": (len(covered) / len(relevant_ids) if relevant_ids else None),
        "reciprocal_rank": (1 / min(ranks) if ranks else (None if unanswerable else 0.0)),
        "empty_retrieval": bool(unanswerable and not returned_session_ids),
    }


def run_ablation(data: Sequence[Mapping[str, Any]], raw: bytes, *, sample: int,
                 k: int, session_char_budget: int, chunk_char_budget: int,
                 overfetch: int, embed_model: str, base_url: str,
                 excluded_ids: set[str], exclusion_sources: Sequence[str],
                 verbose: bool = True) -> dict[str, Any]:
    if embed_model != DEFAULT_EMBED_MODEL:
        raise ValueError(f"matched ablation requires embed model {DEFAULT_EMBED_MODEL!r}")
    if k < 1 or overfetch < 1:
        raise ValueError("k and overfetch must be positive")
    started = time.time()
    selected = stratified_sample_excluding(data, sample, excluded_ids)
    source_snapshot = _source_snapshot()
    embedder = OllamaEmbedder(model=embed_model, base_url=base_url)
    probe_started = time.perf_counter()
    probe = embedder.embed(["dimension probe"])
    probe_elapsed = time.perf_counter() - probe_started
    measured_dimensions = len(probe[0]) if probe and probe[0] else None
    if measured_dimensions != 768:
        raise ValueError(f"expected measured embedding dimension 768, got {measured_dimensions}")
    truncation = {"sessions": 0, "chunks": 0, "original_chars": 0,
                  "indexed_chars": 0, "truncated_session_chars": 0,
                  "truncated_chunk_chars": 0}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    cleanup_failures: list[dict[str, Any]] = []
    for index, item in enumerate(selected):
        memory = None
        stats: dict[str, int] | None = None
        try:
            rows, stats = iter_index_rows(item, session_char_budget, chunk_char_budget)
            for key, value in (("sessions", stats["session_count"]),
                               ("chunks", stats["chunk_count"]),
                               ("original_chars", stats["original_chars"]),
                               ("indexed_chars", stats["indexed_chars"]),
                               ("truncated_session_chars", stats["truncated_session_chars"]),
                               ("truncated_chunk_chars", stats["truncated_chunk_chars"])):
                truncation[key] += value
            memory = Smriti(path=":memory:", mode="lite", embedder=embedder,
                            expand_keys=False,
                aggregate=False, dedupe=False)
            ingest_started = time.perf_counter()
            for row in rows:
                # The row contains only rendered role/content and opaque
                # adapter metadata. Dataset labels never enter this call.
                memory.add([{"role": "user", "content": row["text"]}],
                           session_id=row["session_id"], timestamp=row["timestamp"])
            ingest_s = time.perf_counter() - ingest_started
            query = str(item["question"])
            query_started = time.perf_counter()
            default_hits = _variant_hits(memory, query, k, session_diverse=False,
                                         overfetch=overfetch)
            default_s = time.perf_counter() - query_started
            query_started = time.perf_counter()
            diverse_hits = _variant_hits(memory, query, k, session_diverse=True,
                                         overfetch=overfetch)
            diverse_s = time.perf_counter() - query_started
            unanswerable = str(item["question_id"]).lower().endswith("_abs")
            # Labels are consulted after both retrieval calls, solely for
            # scoring the returned opaque ids.
            relevant = item.get("answer_session_ids", [])
            results.append({
                "question_id": item["question_id"],
                "question_type": item["question_type"],
                "question": item["question"],
                "unanswerable": unanswerable,
                "session_count": stats["session_count"],
                "chunk_count": stats["chunk_count"],
                "ingest_s": round(ingest_s, 4),
                "variants": {
                    "default": {"query_s": round(default_s, 4),
                                **_score_hits(default_hits, relevant, unanswerable),
                                "hits": default_hits},
                    "session_diverse": {"query_s": round(diverse_s, 4),
                                         "session_overfetch": overfetch,
                                         **_score_hits(diverse_hits, relevant, unanswerable),
                                         "hits": diverse_hits},
                },
            })
            if verbose:
                print(f"[{index + 1}/{len(selected)}] {item['question_id']}", flush=True)
        except Exception as exc:
            failures.append({"question_id": item.get("question_id", str(index)),
                             "question_type": item.get("question_type", "unknown"),
                             "error": {"type": type(exc).__name__, "message": str(exc)}})
            if verbose:
                print(f"[{index + 1}/{len(selected)}] ERR {type(exc).__name__}: {exc}", flush=True)
        finally:
            if memory is not None:
                try:
                    memory.close()
                except Exception as exc:
                    cleanup_failures.append({"question_id": item.get("question_id", str(index)),
                                             "question_type": item.get("question_type", "unknown"),
                                             "error": {"type": type(exc).__name__, "message": str(exc)}})
    answerable = [row for row in selected
                  if not str(row["question_id"]).lower().endswith("_abs")]
    completed = [row for row in results if not row["unanswerable"]]
    def aggregate(variant: str) -> dict[str, Any]:
        values = [row["variants"][variant]["recall_at_k"] for row in results
                  if not row["unanswerable"] and row["variants"][variant]["recall_at_k"] is not None]
        mrrs = [row["variants"][variant]["reciprocal_rank"] for row in results
                if not row["unanswerable"] and row["variants"][variant]["reciprocal_rank"] is not None]
        return {"mean_recall_at_k": round(sum(values) / max(1, len(answerable)), 4),
                "mean_reciprocal_rank": round(sum(mrrs) / max(1, len(answerable)), 4),
                "answerable_completed": len(completed),
                "answerable_requested": len(answerable)}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if len(results) == len(selected) and not failures and not cleanup_failures else "partial",
        "track": "held-out LongMemEval-S raw-session retrieval selector ablation",
        "dataset": {"sha256": hashlib.sha256(raw).hexdigest(), "total_items": len(data),
                    "selected_question_ids": [item["question_id"] for item in selected],
                    "excluded_question_ids": sorted(excluded_ids),
                    "exclusion_sources": list(exclusion_sources)},
        "configuration": {"embedding": {"provider": "Ollama", "model": embed_model,
                                         "dimensions": 768, "base_url": base_url},
                          "budgets": {"sample": sample, "k": k,
                                      "session_char_budget": session_char_budget,
                                      "chunk_char_budget": chunk_char_budget},
                          "variants": {"default": {"session_diverse": False},
                                       "session_diverse": {"session_diverse": True,
                                                            "session_overfetch": overfetch}}},
        "run": {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "elapsed_s": round(time.time() - started, 3),
                "platform": platform.platform(), "python": sys.version,
                "input_contract": "answer labels are excluded from index/query inputs; labels are read only after retrieval",
                "latency_policy": "query timings are diagnostic only; default is always queried first and no latency ranking is performed",
                "source_snapshot": source_snapshot,
                "embedding_dimension_probe": {
                    "input_chars": len("dimension probe"),
                    "measured_dimensions": measured_dimensions,
                    "elapsed_ms": round(probe_elapsed * 1000, 3),
                    "outside_timed_question_runs": True,
                }},
        "summary": {"requested": len(selected), "completed": len(results),
                    "failures": len(failures), "cleanup_failures": len(cleanup_failures),
                    "failure_inclusive_denominator": len(selected),
                    "unanswerable_requested": len(selected) - len(answerable),
                    "default": aggregate("default"),
                    "session_diverse": aggregate("session_diverse"),
                    "truncation": truncation},
        "results": results,
        "failure_records": failures,
        "cleanup_failure_records": cleanup_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Held-out default/session-diverse retrieval ablation")
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--session-char-budget", type=int, default=DEFAULT_SESSION_CHAR_BUDGET)
    parser.add_argument("--chunk-char-budget", type=int, default=DEFAULT_CHUNK_CHAR_BUDGET)
    parser.add_argument("--session-overfetch", type=int, default=DEFAULT_OVERFETCH)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--exclude-file", action="append", default=list(DEFAULT_EXCLUDE_FILES))
    parser.add_argument("--exclude-id", action="append", default=[])
    parser.add_argument("--exclusion-root", default=None,
                        help="root for relative exclusion files (required outside the checkout)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    path = Path(args.data)
    data, raw = load_dataset(str(path))
    exclusion_root = Path(args.exclusion_root).expanduser() if args.exclusion_root else Path.cwd()
    excluded, sources = load_exclusions(exclusion_root, args.exclude_file, args.exclude_id)
    result = run_ablation(data, raw, sample=args.sample, k=args.k,
                          session_char_budget=args.session_char_budget,
                          chunk_char_budget=args.chunk_char_budget,
                          overfetch=args.session_overfetch,
                          embed_model=args.embed_model, base_url=args.base_url,
                          excluded_ids=excluded, exclusion_sources=sources,
                          verbose=not args.quiet)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result["summary"], indent=2))
    if result["status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
