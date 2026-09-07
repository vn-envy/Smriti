"""Bounded growing-corpus cost/speed measurements.

The run is a corpus-growth simulation, not longitudinal calendar evidence. A
checkpoint records incremental ingestion, a labelled cold boundary (gbrain
uses a process restart; Smriti and mem0 use a same-process client/database
reopen), warm p50/p95, result validity, and on-disk bytes. Local model cache
files and hardware/electricity are reported separately and are not counted as
zero-cost infrastructure.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

from bench.comparative import Mem0, pct
from smriti import HashEmbedder, OllamaEmbedder, Smriti


QUERIES = [
    "passport renewal appointment",
    "doctor knee recommendation",
    "project launch date",
    "invoice due date",
    "emergency contact",
]
NOMIC_MODEL = "nomic-embed-text:v1.5"
NOMIC_EMBEDDING_DIMS = 768


def doc(i: int) -> dict[str, str]:
    return {
        "id": f"n{i:07d}",
        "timestamp": f"2024-{i % 12 + 1:02d}-{i % 28 + 1:02d}T09:00:00Z",
        "text": f"Synthetic record {i}: {QUERIES[i % len(QUERIES)]}; reference code {i * 7919}.",
    }


def size_tree(path: str) -> int:
    return sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(path) for f in fs)


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _safe_endpoint(value: object) -> str | None:
    """Keep host/port provenance while excluding URL credentials and queries."""
    if value is None:
        return None
    raw = str(value).rstrip("/")
    try:
        parsed = urlsplit(raw)
        if parsed.scheme and parsed.hostname:
            host = parsed.hostname
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return f"{parsed.scheme}://{host}"
    except ValueError:
        pass
    return "<invalid-or-redacted-endpoint>"


class SmritiOllama:
    label = "Smriti lite / Ollama nomic-embed-text:v1.5"

    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="smriti-growth-nomic-")
        self.path = os.path.join(self.root, "memory.db")
        self.model = os.environ.get("GROWTH_EMBED_MODEL", "nomic-embed-text:v1.5")
        self.base_url = os.environ.get("GROWTH_OLLAMA_URL", "http://127.0.0.1:11436")
        self.effective_embedder = {
            "provider": "ollama",
            "model": self.model,
            "embedding_dims": NOMIC_EMBEDDING_DIMS if self.model == NOMIC_MODEL else None,
            "endpoint": _safe_endpoint(self.base_url),
        }
        if self.model != NOMIC_MODEL:
            raise RuntimeError(f"smriti-nomic requires {NOMIC_MODEL}; effective model was {self.model}")
        probe = OllamaEmbedder(model=self.model, base_url=self.base_url).embed(["dimension probe"])
        measured_dims = len(probe[0]) if probe and probe[0] else None
        self.effective_embedder["measured_embedding_dims"] = measured_dims
        if measured_dims != NOMIC_EMBEDDING_DIMS:
            raise RuntimeError(f"{NOMIC_MODEL} returned {measured_dims} dimensions; expected {NOMIC_EMBEDDING_DIMS}")
        self._open()

    def _open(self) -> None:
        self.m = Smriti(path=self.path, mode="lite", embedder=OllamaEmbedder(model=self.model, base_url=self.base_url))

    def add(self, d: dict[str, str]) -> None:
        self.m.add([{"role": "user", "content": f"[DOC:{d['id']}] {d['text']}"}], session_id=d["id"], timestamp=d["timestamp"])

    def search(self, q: str, k: int) -> list[tuple[str, float]]:
        import re
        out = []
        for result in self.m.search(q, k=k):
            match = re.search(r"\[DOC:([^\]]+)\]", result.text)
            if match:
                out.append((match.group(1), float(result.score)))
        return out

    def storage(self) -> int:
        return size_tree(self.root)

    def storage_paths(self) -> list[str]:
        return [self.path]

    def restart(self) -> None:
        started = time.perf_counter_ns()
        self.m.store.db.close()
        self._open()
        self.last_restart_startup_ms = (time.perf_counter_ns() - started) / 1e6

    def close(self) -> None:
        self.m.store.db.close()


class SmritiHash:
    label = "Smriti lite / raw episodes / HashEmbedder"

    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="smriti-growth-hash-")
        self.path = os.path.join(self.root, "memory.db")
        self._open()

    def _open(self) -> None:
        self.m = Smriti(path=self.path, mode="lite", embedder=HashEmbedder())

    def add(self, d: dict[str, str]) -> None:
        self.m.add([{"role": "user", "content": f"[DOC:{d['id']}] {d['text']}"}], session_id=d["id"], timestamp=d["timestamp"])

    def search(self, q: str, k: int) -> list[tuple[str, float]]:
        import re
        out = []
        for result in self.m.search(q, k=k):
            match = re.search(r"\[DOC:([^\]]+)\]", result.text)
            if match:
                out.append((match.group(1), float(result.score)))
        return out

    def storage(self) -> int:
        return size_tree(self.root)

    def storage_paths(self) -> list[str]:
        return [self.path]

    def restart(self) -> None:
        started = time.perf_counter_ns()
        self.m.store.db.close()
        self._open()
        self.last_restart_startup_ms = (time.perf_counter_ns() - started) / 1e6

    def close(self) -> None:
        self.m.store.db.close()


class Mem0Growth(Mem0):
    """mem0 OSS adapter with effective embedder provenance in its artifact."""

    def __init__(self) -> None:
        super().__init__()
        self.root_paths = [p for p in (self.cfg.get("history_db_path"), self.cfg.get("vector_store", {}).get("config", {}).get("path")) if p]
        cfg = getattr(self.m, "config", None)
        embedder = _field(cfg, "embedder", {})
        embed_cfg = _field(embedder, "config", {})
        self.effective_embedder = {
            "provider": _field(embedder, "provider", self.cfg.get("embedder", {}).get("provider")),
            "model": _field(embed_cfg, "model", self.cfg.get("embedder", {}).get("config", {}).get("model")),
            "embedding_dims": _field(embed_cfg, "embedding_dims", self.cfg.get("embedder", {}).get("config", {}).get("embedding_dims")),
            "endpoint": _safe_endpoint(_field(embed_cfg, "ollama_base_url", self.cfg.get("embedder", {}).get("config", {}).get("ollama_base_url"))),
        }
        self.effective_embedder["configured_embedding_dims"] = self.effective_embedder["embedding_dims"]
        if self.effective_embedder["model"] == NOMIC_MODEL and self.effective_embedder["embedding_dims"] != NOMIC_EMBEDDING_DIMS:
            raise RuntimeError("mem0 nomic configuration must declare 768 embedding dimensions")
        measured_dims = None
        if self.effective_embedder["provider"] in {"fastembed", "ollama"}:
            embedding_model = getattr(self.m, "embedding_model", None)
            embed = getattr(embedding_model, "embed", None)
            if callable(embed):
                try:
                    probe = embed("dimension probe", "search")
                except TypeError:
                    probe = embed("dimension probe")
                measured_dims = len(probe) if probe else None
        self.effective_embedder["measured_embedding_dims"] = measured_dims
        if self.effective_embedder["model"] == NOMIC_MODEL and self.effective_embedder["measured_embedding_dims"] != NOMIC_EMBEDDING_DIMS:
            raise RuntimeError("mem0 effective nomic embedder dimensions are not 768")
        vector = _field(cfg, "vector_store", {})
        self.effective_vector_store = {"provider": _field(vector, "provider", self.cfg.get("vector_store", {}).get("provider"))}
        self.local_cost_verified = self.effective_embedder["provider"] in {"fastembed", "ollama"} and self.effective_vector_store["provider"] in {"qdrant", "sqlite", "chroma"}
        e = self.effective_embedder
        self.label = f"mem0 OSS / infer=False / embedder={e['provider']}:{e['model']} dims={e['embedding_dims']} endpoint={e['endpoint']} / vector_store={self.effective_vector_store['provider']}"

    def storage_paths(self) -> list[str]:
        return self.root_paths

    def restart(self) -> None:
        started = time.perf_counter_ns()
        self.close()
        from mem0 import Memory
        self.m = Memory.from_config(self.cfg)
        self.last_restart_startup_ms = (time.perf_counter_ns() - started) / 1e6

    def close(self) -> None:
        # mem0 has no Memory.close() in this pinned OSS release. Release the
        # local Qdrant/SQLite handles explicitly before reopening the same
        # persisted paths, then let the object be collected.
        for name in ("vector_store", "_telemetry_vector_store"):
            store = getattr(getattr(self, "m", None), name, None)
            client = getattr(store, "client", None)
            if client is not None and hasattr(client, "close"):
                client.close()
        db = getattr(getattr(self, "m", None), "db", None)
        if db is not None and hasattr(db, "close"):
            db.close()


class GbrainPersistent:
    """Pinned gbrain public engine/import pipeline, one Bun process per run."""

    label = "gbrain PGLite / persistent public engine / lexical keyword track (no embedding)"

    def __init__(self) -> None:
        self.root = tempfile.mkdtemp(prefix="gbrain-growth-")
        self.db_path = os.path.join(self.root, "db")
        self.worker = str(Path(__file__).with_name("gbrain_growth_worker.ts"))
        self.gbrain_root = os.environ.get("GBRAIN_ROOT")
        if not self.gbrain_root:
            raise RuntimeError("GBRAIN_ROOT must point to the pinned gbrain checkout for the gbrain growth adapter")
        self.startup_ms = self._start()

    def _start(self) -> float:
        started = time.perf_counter_ns()
        env = {**os.environ, "GBRAIN_ROOT": self.gbrain_root, "GBRAIN_DB_PATH": self.db_path}
        self.proc = subprocess.Popen([os.environ.get("BUN_BIN", "bun"), self.worker], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, bufsize=1)
        self._request({"op": "ready"})
        return (time.perf_counter_ns() - started) / 1e6

    def _request(self, message: dict[str, object]) -> dict[str, object]:
        if self.proc.stdin is None or self.proc.stdout is None:
            raise RuntimeError("gbrain worker pipes are unavailable")
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            error = self.proc.stderr.read()[-1000:] if self.proc.stderr else ""
            raise RuntimeError(f"gbrain worker exited without a response: {error}")
        result = json.loads(line)
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "gbrain worker failure")))
        return result

    def add_many(self, docs: list[dict[str, str]], expected_count: int | None = None) -> None:
        result = self._request({"op": "put_many", "documents": docs})
        self.last_batch_result = result
        if int(result.get("imported", 0)) + int(result.get("skipped", 0)) != len(docs):
            raise RuntimeError(f"gbrain batch accounting mismatch: {result}")
        if expected_count is not None and int(result.get("page_count", -1)) != expected_count:
            raise RuntimeError(f"gbrain checkpoint page count mismatch: expected {expected_count}, got {result}")

    def add(self, d: dict[str, str]) -> None:
        self.add_many([d])

    def analyze(self) -> float:
        result = self._request({"op": "analyze"})
        self.last_analyze_result = result
        return float(result["maintenance_ms"])

    def search(self, q: str, k: int) -> list[tuple[str, float]]:
        result = self._request({"op": "search", "query": q, "limit": k})
        return [(str(row["slug"]).split("/")[-1], float(row.get("score", 0))) for row in result["results"]]

    def storage(self) -> int:
        return size_tree(self.root)

    def storage_paths(self) -> list[str]:
        return [self.db_path]

    def restart(self) -> None:
        self._stop()
        self.last_restart_startup_ms = self._start()

    def _stop(self) -> None:
        if self.proc.poll() is None:
            try:
                self._request({"op": "close"})
            except Exception:
                self.proc.terminate()
        self.proc.wait(timeout=15)

    def close(self) -> None:
        self._stop()


def _relevant_ids(query: str, hits: list[tuple[str, float]]) -> list[str]:
    topic_index = QUERIES.index(query)
    out = []
    for identifier, _ in hits:
        digits = "".join(ch for ch in identifier if ch.isdigit())
        if digits and int(digits) % len(QUERIES) == topic_index:
            out.append(identifier)
    return out


def _meta(adapter: object) -> dict[str, object]:
    local_model = isinstance(adapter, (SmritiOllama, Mem0Growth))
    return {
        "model_calls": {
            "successful_calls": None if local_model else 0,
            "successful_tokens": None if local_model else 0,
            "failed_attempts": "unknown" if local_model else 0,
            "note": "Embedding client counters are not exposed; failed/retried attempts may be unobserved." if local_model else "No model call in this lexical track.",
        },
        "storage_scope": {
            "paths": adapter.storage_paths() if hasattr(adapter, "storage_paths") else [],
            "shared_model_cache_included": False,
            "shared_model_cache_paths": [],
            "shared_model_cache_note": "Model cache location/size was not measured and is excluded from storage_bytes.",
            "hardware_and_electricity_measured": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", choices=["smriti", "smriti-nomic", "mem0", "gbrain"], required=True)
    parser.add_argument("--checkpoints", nargs="+", type=int, default=[100, 1000, 5000])
    parser.add_argument("--out", required=True)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--gbrain-analyze", action="store_true", help="run executeRaw('ANALYZE') after each gbrain checkpoint as a maintained variant")
    args = parser.parse_args()
    if not args.checkpoints or any(x <= 0 for x in args.checkpoints) or args.checkpoints != sorted(set(args.checkpoints)):
        parser.error("checkpoints must be unique, positive, and increasing")
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    if args.gbrain_analyze and args.adapter != "gbrain":
        parser.error("--gbrain-analyze is only valid with --adapter gbrain")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    adapter: object | None = None
    rows: list[dict[str, object]] = []
    added = 0
    succeeded = False

    def write_result(status: str, error: dict[str, str] | None = None) -> None:
        result: dict[str, object] = {
            "schema_version": 2,
            "status": status,
            "adapter": args.adapter,
            "configuration": getattr(adapter, "label", args.adapter),
            "measurement": "growing-corpus simulation in one run; checkpoints are not elapsed-day longitudinal observations",
            "timing_scope": "persistent gbrain engine process; process-restart cold query; keyword-only, no embedding" if args.adapter == "gbrain" else "in-process operations; cold query follows same-process client/database reopen (not a new OS process)",
            "model_cost": {"observed_paid_api_usd": 0 if not isinstance(adapter, Mem0Growth) or adapter.local_cost_verified else None, "hardware_electricity_cost_usd": None, "note": "Local/API charge is $0 only for the verified local route; otherwise paid API cost is unknown. Electricity, hardware purchase/rental, and depreciation were not measured. Shared model cache is excluded."},
            "verification": {"synthetic_queries": QUERIES, "nonempty_and_relevant_definition": "A result is relevant when its synthetic document bucket matches the query topic."},
            "checkpoints": rows,
            "gbrain_analyze": bool(args.gbrain_analyze),
        }
        if args.gbrain_analyze:
            result["timing_scope"] = "persistent gbrain engine process; executeRaw('ANALYZE') after each checkpoint; process-restart cold query; keyword-only, no embedding"
        if error is not None:
            result["error"] = error
        if adapter is not None:
            result.update(_meta(adapter))
            if isinstance(adapter, GbrainPersistent):
                result["process_startup_ms"] = round(adapter.startup_ms, 3)
            if isinstance(adapter, (SmritiOllama, Mem0Growth)):
                result["effective_embedder"] = adapter.effective_embedder
            if isinstance(adapter, Mem0Growth):
                result["effective_vector_store"] = adapter.effective_vector_store
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n")

    try:
        if args.adapter == "gbrain":
            adapter = GbrainPersistent()
        elif args.adapter == "mem0":
            adapter = Mem0Growth()
        elif args.adapter == "smriti-nomic":
            adapter = SmritiOllama()
        else:
            adapter = SmritiHash()

        for target in args.checkpoints:
            pending = [doc(i) for i in range(added, target)]
            started = time.perf_counter_ns()
            if isinstance(adapter, GbrainPersistent):
                adapter.add_many(pending, expected_count=target)
            else:
                for item in pending:
                    adapter.add(item)
            ingest_ms = (time.perf_counter_ns() - started) / 1e6
            ingest_batch = getattr(adapter, "last_batch_result", None)
            added = target
            # Measure the adapter's idempotent re-submit/update path separately
            # from first-time ingestion. The payload is unchanged so this
            # does not introduce a new synthetic fact into the query set.
            update_started = time.perf_counter_ns()
            last = doc(target - 1)
            if isinstance(adapter, GbrainPersistent):
                adapter.add_many([last], expected_count=target)
            else:
                adapter.add(last)
            update_ms = (time.perf_counter_ns() - update_started) / 1e6
            update_batch = getattr(adapter, "last_batch_result", None)
            maintenance_ms = None
            if args.gbrain_analyze:
                maintenance_ms = adapter.analyze()
            started = time.perf_counter_ns()
            first_hits = adapter.search(QUERIES[0], 5)
            first_ms = (time.perf_counter_ns() - started) / 1e6
            if not first_hits:
                raise RuntimeError(f"{args.adapter} returned no results at {target} documents after ingest")
            if hasattr(adapter, "restart"):
                adapter.restart()
            started = time.perf_counter_ns()
            cold_hits = adapter.search(QUERIES[0], 5)
            cold_ms = (time.perf_counter_ns() - started) / 1e6
            if not cold_hits:
                raise RuntimeError(f"{args.adapter} returned no results at {target} documents after restart")

            samples: list[float] = []
            nonempty = 0
            relevant = 0
            timed_queries: list[dict[str, object]] = []
            for index in range(args.repeats):
                query = QUERIES[index % len(QUERIES)]
                started = time.perf_counter_ns()
                hits = adapter.search(query, 5)
                samples.append((time.perf_counter_ns() - started) / 1e6)
                nonempty += bool(hits)
                relevant_ids = _relevant_ids(query, hits)
                relevant += bool(relevant_ids)
                timed_queries.append({
                    "query": query,
                    "returned_ids": [identifier for identifier, _ in hits],
                    "per_hit_relevance": [identifier in relevant_ids for identifier, _ in hits],
                    "relevant_ids": relevant_ids,
                    "latency_ms": round(samples[-1], 3),
                })
            cold_relevant = _relevant_ids(QUERIES[0], cold_hits)
            storage = adapter.storage()
            rows.append({
                "documents": target,
                "incremental_ingest_ms": round(ingest_ms, 3),
                "same_payload_update_ms": round(update_ms, 3),
                "update_definition": "idempotent re-submit of the final record unchanged; adapter dedup/update semantics apply",
                "gbrain_analyze_maintenance_ms": round(maintenance_ms, 3) if maintenance_ms is not None else None,
                "gbrain_ingest_statuses": (ingest_batch or {}).get("statuses") if isinstance(ingest_batch, dict) else None,
                "gbrain_update_statuses": (update_batch or {}).get("statuses") if isinstance(update_batch, dict) else None,
                "first_query_after_ingest_ms": round(first_ms, 3),
                "first_query_after_ingest_returned_ids": [identifier for identifier, _ in first_hits],
                "first_query_after_ingest_per_hit_relevance": [identifier in _relevant_ids(QUERIES[0], first_hits) for identifier, _ in first_hits],
                "first_query_after_ingest_returned": len(first_hits),
                "first_query_after_ingest_relevant_ids": _relevant_ids(QUERIES[0], first_hits),
                "first_query_after_ingest_relevant": len(_relevant_ids(QUERIES[0], first_hits)),
                "cold_query_after_restart_ms": round(cold_ms, 3),
                "cold_query_boundary": "process_restart" if isinstance(adapter, GbrainPersistent) else "same_process_client_reopen",
                "process_restart_startup_ms": round(getattr(adapter, "last_restart_startup_ms", 0), 3),
                "cold_query_returned_ids": [identifier for identifier, _ in cold_hits],
                "cold_query_per_hit_relevance": [identifier in cold_relevant for identifier, _ in cold_hits],
                "cold_query_returned": len(cold_hits),
                "cold_query_relevant": len(cold_relevant),
                "warm_query_ms_p50": pct(samples, 0.5),
                "warm_query_ms_p95": pct(samples, 0.95),
                "timed_query_samples": len(samples),
                "warm_nonempty_results": nonempty,
                "warm_queries_with_relevant_result": relevant,
                "timed_queries": timed_queries,
                "storage_bytes": storage,
                "storage_mb": round(storage / 1_000_000, 3),
            })
            print(rows[-1], flush=True)
            # Flush each successful checkpoint so an interrupted long run is
            # reviewable and cannot be mistaken for a complete experiment.
            write_result("partial")
        succeeded = True
    except Exception as exc:
        write_result("partial" if rows else "blocked", {"type": type(exc).__name__, "message": str(exc)})
        raise
    finally:
        if adapter is not None:
            adapter.close()
    if succeeded:
        write_result("complete")


if __name__ == "__main__":
    main()
