"""Separate semantic/hybrid GBrain track for public raw-session retrieval.

This worker is intentionally separate from the lexical GBrain track. It uses
the pinned GBrain public import + ``hybridSearch`` APIs with the real local
Ollama nomic embedding model. Opaque document ids are mapped to session ids in
memory; session ids and answer labels never enter imported document text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import select
import shutil
import subprocess
import time
import tempfile
import threading
from pathlib import Path
from typing import Any, Mapping, Sequence

from .public_retrieval import (
    DEFAULT_CHUNK_CHAR_BUDGET,
    DEFAULT_K,
    DEFAULT_SESSION_CHAR_BUDGET,
    iter_index_rows,
    load_dataset,
)
from .public_retrieval_ablation import (
    DEFAULT_EXCLUDE_FILES,
    stratified_sample_excluding,
    load_exclusions,
)

SCHEMA_VERSION = 1
DEFAULT_EMBED_MODEL = "ollama:nomic-embed-text:v1.5"
DEFAULT_EMBED_DIMENSIONS = 768
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11436/v1"
REQUEST_TIMEOUT_S = 300.0
STDERR_TAIL_BYTES = 64 * 1024
SEMANTIC_DEGRADED_STAGES = frozenset({
    "embed_timeout", "embed_unavailable", "vector_arm_failed", "rescore_skipped",
    "expansion_partial",
})


def _score_hits(hits: Sequence[Mapping[str, Any]], relevant: Sequence[str],
                unanswerable: bool) -> dict[str, Any]:
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
        "returned_session_ids": returned_session_ids,
        "returned_session_count": len(returned_session_ids),
        "relevant_session_ids": relevant_ids,
        "covered_relevant_session_ids": covered,
        "recall_at_k": len(covered) / len(relevant_ids) if relevant_ids else None,
        "reciprocal_rank": 1 / min(ranks) if ranks else (None if unanswerable else 0.0),
        "empty_retrieval": bool(unanswerable and not returned_session_ids),
    }


class GbrainSemanticPersistent:
    """One persistent Bun process using GBrain's real semantic pipeline."""

    label = "GBrain persistent PGLite / hybrid semantic + keyword / Ollama nomic 768d"

    def __init__(self, *, embed_model: str = DEFAULT_EMBED_MODEL,
                 embed_dimensions: int = DEFAULT_EMBED_DIMENSIONS,
                 ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
                 _worker_path: str | None = None,
                 _request_timeout_s: float = REQUEST_TIMEOUT_S):
        if embed_model != DEFAULT_EMBED_MODEL:
            raise ValueError(f"semantic track requires embed model {DEFAULT_EMBED_MODEL!r}")
        if embed_dimensions != DEFAULT_EMBED_DIMENSIONS:
            raise ValueError("semantic track requires 768 embedding dimensions")
        if not ollama_base_url.startswith("http"):
            raise ValueError("Ollama base URL must be an absolute http(s) URL")
        self.gbrain_root = os.environ.get("GBRAIN_ROOT")
        if not self.gbrain_root:
            raise RuntimeError("GBRAIN_ROOT must point to the pinned gbrain checkout")
        self.root = tempfile.mkdtemp(prefix="gbrain-semantic-")
        self.db_path = str(Path(self.root) / "db")
        self.worker = _worker_path or str(Path(__file__).with_name("gbrain_public_semantic_worker.ts"))
        self.request_timeout_s = _request_timeout_s
        self._stdout_buffer = b""
        self._stderr_tail = bytearray()
        self._stderr_lock = threading.Lock()
        self._stderr_thread: threading.Thread | None = None
        self.embed_model = embed_model
        self.embed_dimensions = embed_dimensions
        self.ollama_base_url = ollama_base_url
        try:
            self.startup_ms = self._start()
        except Exception:
            try:
                self._stop()
            except Exception:
                proc = getattr(self, "proc", None)
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        proc.kill()
            try:
                self.stderr_handle.close()
            except Exception:
                pass
            shutil.rmtree(self.root, ignore_errors=True)
            raise

    def _start(self) -> float:
        started = time.perf_counter_ns()
        env = {
            **os.environ,
            "GBRAIN_ROOT": self.gbrain_root,
            "GBRAIN_DB_PATH": self.db_path,
            "GBRAIN_EMBEDDING_MODEL": self.embed_model,
            "GBRAIN_EMBEDDING_DIMENSIONS": str(self.embed_dimensions),
            "GBRAIN_OLLAMA_BASE_URL": self.ollama_base_url,
        }
        self.proc = subprocess.Popen(
            [os.environ.get("BUN_BIN", "bun"), self.worker], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, env=env,
            bufsize=0,
        )
        os.set_blocking(self.proc.stdout.fileno(), False)
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr, args=(self.proc.stderr,), daemon=True,
        )
        self._stderr_thread.start()
        ready = self._request({"op": "ready"})
        measured = int(ready.get("measured_embedding_dimensions", -1))
        if measured != self.embed_dimensions:
            self._stop()
            raise RuntimeError(f"semantic worker measured {measured} dimensions, expected {self.embed_dimensions}")
        self.ready_metadata = ready
        return (time.perf_counter_ns() - started) / 1e6

    def _request(self, message: dict[str, object]) -> dict[str, object]:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("semantic worker pipes are unavailable")
        self.proc.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        deadline = time.monotonic() + self.request_timeout_s
        while True:
            newline = self._stdout_buffer.find(b"\n")
            if newline >= 0:
                line = self._stdout_buffer[:newline]
                self._stdout_buffer = self._stdout_buffer[newline + 1:]
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._terminate_process()
                raise TimeoutError(
                    f"semantic worker request timed out after {self.request_timeout_s:.3f}s: {message.get('op')}"
                )
            ready, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not ready:
                self._terminate_process()
                raise TimeoutError(
                    f"semantic worker request timed out after {self.request_timeout_s:.3f}s: {message.get('op')}"
                )
            try:
                chunk = os.read(self.proc.stdout.fileno(), 4096)
            except BlockingIOError:
                continue
            if not chunk:
                error = self._stderr_tail_text()
                raise RuntimeError(f"semantic worker exited without a response: {error}")
            self._stdout_buffer += chunk
        result = json.loads(line.decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "semantic worker failure")))
        return result

    def _drain_stderr(self, stream: Any) -> None:
        if stream is None:
            return
        while True:
            chunk = stream.read(4096)
            if not chunk:
                return
            with self._stderr_lock:
                self._stderr_tail.extend(chunk)
                if len(self._stderr_tail) > STDERR_TAIL_BYTES:
                    del self._stderr_tail[:-STDERR_TAIL_BYTES]

    def _stderr_tail_text(self) -> str:
        with self._stderr_lock:
            tail = bytes(self._stderr_tail)
        return tail.decode("utf-8", errors="replace")[-1000:]

    def _terminate_process(self) -> None:
        proc = getattr(self, "proc", None)
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def add(self, doc: Mapping[str, Any]) -> None:
        result = self._request({"op": "put_many", "documents": [dict(doc)]})
        self.last_import_stats = result.get("vector_stats")
        if int(result.get("imported", 0)) + int(result.get("skipped", 0)) != 1:
            raise RuntimeError(f"semantic import accounting mismatch: {result}")

    def search(self, query: str, k: int) -> dict[str, Any]:
        return self._request({"op": "search", "query": query, "limit": k})

    def _stop(self) -> None:
        if getattr(self, "proc", None) is None:
            return
        proc = self.proc
        try:
            if proc.poll() is None:
                try:
                    self._request({"op": "close"})
                except Exception:
                    pass
        finally:
            # Closing is best effort, but cleanup is a hard invariant: never
            # remove the temp root while a worker still owns its database.
            self._terminate_process()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def close(self) -> None:
        error = None
        try:
            self._stop()
        except Exception as exc:  # noqa: BLE001
            error = exc
        finally:
            shutil.rmtree(self.root, ignore_errors=True)
        if error is not None:
            raise error


class GBrainPublicAdapter(GbrainSemanticPersistent):
    """Semantic GBrain adapter with opaque document-to-session mapping."""

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._document_sessions: dict[str, str] = {}

    def add(self, row: Mapping[str, Any]) -> None:
        # Do not derive the document id from session_id. The worker requires an
        # id in frontmatter, so use an opaque id and retain the mapping here.
        document_id = f"public-{len(self._document_sessions):08d}"
        slug = f"bench/{document_id}"
        self._document_sessions[slug] = str(row["session_id"])
        document = {"id": document_id, "timestamp": str(row["timestamp"]),
                    "text": str(row["text"])}
        try:
            super().add(document)
        except Exception:
            self._document_sessions.pop(slug, None)
            raise

    def search(self, query: str, k: int) -> list[dict[str, Any]]:
        result = super().search(query, k)
        self.last_search_meta = result.get("search_meta")
        hits = []
        for row in result["results"]:
            slug = str(row["slug"])
            session_id = self._document_sessions.get(slug)
            if session_id is None:
                # Keep the failure explicit if the engine returns an unknown
                # document rather than guessing a session id from its slug.
                raise RuntimeError(f"GBrain returned unmapped document slug {slug!r}")
            hits.append({"document_slug": slug, "session_id": session_id,
                         "score": float(row.get("score", 0.0))})
        return hits[:k]


def _gbrain_snapshot(gbrain_root: str) -> dict[str, Any]:
    """Capture the actual pinned checkout and worker inputs before starting."""
    root = Path(gbrain_root).expanduser().resolve()
    worker = Path(__file__).with_name("gbrain_public_semantic_worker.ts").resolve()
    imported = [root / "src/core/engine-factory.ts", root / "src/core/import-file.ts",
                root / "src/core/search/hybrid.ts", root / "src/core/ai/gateway.ts",
                root / "src/core/ai/recipes/ollama.ts"]
    paths = [worker, *imported]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in paths if path.exists()}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                         text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        commit = None
    return {"captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "gbrain_root": str(root), "commit": commit,
            "worker_path": str(worker), "imported_module_paths": [str(path) for path in imported],
            "file_sha256": hashes}


def run(data: Sequence[Mapping[str, Any]], raw: bytes, *, sample: int,
        k: int = DEFAULT_K, session_char_budget: int = DEFAULT_SESSION_CHAR_BUDGET,
        chunk_char_budget: int = DEFAULT_CHUNK_CHAR_BUDGET,
        excluded_ids: set[str] | None = None,
        exclusion_sources: Sequence[str] = (), verbose: bool = True) -> dict[str, Any]:
    excluded_ids = excluded_ids or set()
    if k < 1 or session_char_budget < 1 or chunk_char_budget < 1:
        raise ValueError("k and session/chunk budgets must be positive")
    gbrain_root = os.environ.get("GBRAIN_ROOT")
    if not gbrain_root:
        raise RuntimeError("GBRAIN_ROOT must point to the pinned gbrain checkout")
    source_snapshot = _gbrain_snapshot(gbrain_root)
    selected = stratified_sample_excluding(data, sample, excluded_ids)
    started = time.time()
    truncation = {"sessions": 0, "chunks": 0, "original_chars": 0,
                  "indexed_chars": 0, "truncated_session_chars": 0,
                  "truncated_chunk_chars": 0}
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    cleanup_failures: list[dict[str, Any]] = []
    worker_metadata: dict[str, Any] | None = None
    worker_startup_ms: float | None = None
    for index, item in enumerate(selected):
        adapter = None
        try:
            rows, stats = iter_index_rows(item, session_char_budget, chunk_char_budget)
            for key, value in (("sessions", stats["session_count"]),
                               ("chunks", stats["chunk_count"]),
                               ("original_chars", stats["original_chars"]),
                               ("indexed_chars", stats["indexed_chars"]),
                               ("truncated_session_chars", stats["truncated_session_chars"]),
                               ("truncated_chunk_chars", stats["truncated_chunk_chars"])):
                truncation[key] += value
            adapter = GBrainPublicAdapter()
            if worker_metadata is None:
                worker_metadata = dict(adapter.ready_metadata)
                worker_startup_ms = round(float(adapter.startup_ms), 4)
            ingest_started = time.perf_counter()
            for row in rows:
                adapter.add(row)
            ingest_s = time.perf_counter() - ingest_started
            query_started = time.perf_counter()
            hits = adapter.search(str(item["question"]), k)
            query_s = time.perf_counter() - query_started
            unanswerable = str(item["question_id"]).lower().endswith("_abs")
            results.append({
                "question_id": item["question_id"],
                "question_type": item["question_type"],
                "question": item["question"],
                "unanswerable": unanswerable,
                "session_count": stats["session_count"],
                "chunk_count": stats["chunk_count"],
                "ingest_s": round(ingest_s, 4),
                "query_s": round(query_s, 4),
                "hits": hits,
                "vector_stats": getattr(adapter, "last_import_stats", None),
                "search_meta": getattr(adapter, "last_search_meta", None),
                "relevance": _score_hits(hits, item.get("answer_session_ids", []), unanswerable),
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
            if adapter is not None:
                try:
                    adapter.close()
                except Exception as exc:
                    cleanup_failures.append({"question_id": item.get("question_id", str(index)),
                                             "question_type": item.get("question_type", "unknown"),
                                             "error": {"type": type(exc).__name__, "message": str(exc)}})
    answerable = [item for item in selected
                  if not str(item["question_id"]).lower().endswith("_abs")]
    scored = [row for row in results if not row["unanswerable"]]
    def aggregate(key: str) -> dict[str, Any]:
        recalls = [row["relevance"]["recall_at_k"] for row in scored]
        mrrs = [row["relevance"]["reciprocal_rank"] for row in scored]
        return {"mean_recall_at_k": round(sum(recalls) / max(1, len(answerable)), 4),
                "mean_reciprocal_rank": round(sum(mrrs) / max(1, len(answerable)), 4),
                "answerable_requested": len(answerable), "answerable_completed": len(scored)}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "complete" if len(results) == len(selected) and not failures and not cleanup_failures else "partial",
        "track": "official LongMemEval-S full-haystack raw-session retrieval; GBrain semantic/hybrid separate track",
        "dataset": {"source": "official LongMemEval-S input", "sha256": hashlib.sha256(raw).hexdigest(),
                    "total_items": len(data), "selected_question_ids": [item["question_id"] for item in selected],
                    "excluded_question_ids": sorted(excluded_ids), "exclusion_sources": list(exclusion_sources)},
        "configuration": {"engine": GBrainPublicAdapter.label,
                          "embedding": {"provider": DEFAULT_EMBED_MODEL,
                                        "dimensions": DEFAULT_EMBED_DIMENSIONS,
                                        "ollama_base_url": DEFAULT_OLLAMA_BASE_URL,
                                        "measured_dimensions": (worker_metadata or {}).get(
                                            "measured_embedding_dimensions")},
                          "budgets": {"sample": sample, "k": k,
                                      "session_char_budget": session_char_budget,
                                      "chunk_char_budget": chunk_char_budget},
                          "worker_startup_ms": worker_startup_ms,
                          "semantic_fail_closed": True,
                          "input_contract": "rendered role/content only; opaque document mapping; labels read after retrieval",
                          "latency_policy": "timings are diagnostic only and are not ranked against semantic adapters"},
        "run": {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
                "elapsed_s": round(time.time() - started, 3),
                "gbrain_source_snapshot": source_snapshot},
        "summary": {"requested": len(selected), "completed": len(results),
                    "failures": len(failures), "cleanup_failures": len(cleanup_failures),
                    "failure_inclusive_denominator": len(selected),
                    "unanswerable_requested": len(selected) - len(answerable),
                    "gbrain": aggregate("gbrain"), "truncation": truncation},
        "results": results, "failure_records": failures,
        "cleanup_failure_records": cleanup_failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="GBrain semantic/hybrid public retrieval track")
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", type=int, default=2)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--session-char-budget", type=int, default=DEFAULT_SESSION_CHAR_BUDGET)
    parser.add_argument("--chunk-char-budget", type=int, default=DEFAULT_CHUNK_CHAR_BUDGET)
    parser.add_argument("--exclude-file", action="append", default=list(DEFAULT_EXCLUDE_FILES))
    parser.add_argument("--exclude-id", action="append", default=[])
    parser.add_argument("--exclusion-root", default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    path = Path(args.data)
    data, raw = load_dataset(str(path))
    root = Path(args.exclusion_root).expanduser() if args.exclusion_root else Path.cwd()
    excluded, sources = load_exclusions(root, args.exclude_file, args.exclude_id)
    result = run(data, raw, sample=args.sample, k=args.k,
                 session_char_budget=args.session_char_budget,
                 chunk_char_budget=args.chunk_char_budget,
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
