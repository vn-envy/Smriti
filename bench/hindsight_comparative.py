#!/usr/bin/env python3
"""Run the real Hindsight REST adapter on the checked-in comparative corpus.

This is a retrieval-evidence protocol, not an answer-quality benchmark.  It
retains all 20 synthetic documents through Hindsight's actual retain pipeline,
recalls all 12 checked-in queries, and stores the unmodified client responses,
source markers, timings, service version, and cumulative API metrics.  The
payload's ``SOURCE_DOCUMENT_ID`` marker and ``document_id`` metadata make raw
evidence traceable without inserting a mock embedder or a scoring layer.

The script never starts Hindsight or Ollama.  Run it only after the documented
Hindsight service is already available, for example:

  /private/tmp/hindsight-bench-venv313/bin/python bench/hindsight_comparative.py

Each run uses a fresh bank by default and attempts to delete that bank in a
finally block.  A service failure is written to the requested output as a
blocker; it is never converted into a score.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = Path(os.environ.get(
    "HINDSIGHT_COMPARATIVE_DATA", str(ROOT / "bench" / "comparative_dataset.json")))
OUTPUT = Path(os.environ.get(
    "HINDSIGHT_COMPARATIVE_OUTPUT",
    str(ROOT / "audit" / "2026-09-05" / "hindsight-comparative-v1.json"),
))
BASE_URL = os.environ.get("HINDSIGHT_COMPARATIVE_BASE_URL", "http://127.0.0.1:8892")
QUERY_TIMESTAMP = os.environ.get(
    "HINDSIGHT_COMPARATIVE_QUERY_TIMESTAMP", "2024-03-05T12:00:00Z")
TIMEOUT = float(os.environ.get("HINDSIGHT_COMPARATIVE_TIMEOUT", "300"))
MARKER_RE = re.compile(r"SOURCE_DOCUMENT_ID=(d\d{2})")

# The bank-config endpoint returns a fully resolved configuration, which may
# include credentials and unrelated implementation details.  Keep this
# allowlist deliberately narrow; absent fields remain unknown.
_OBSERVED_CONFIG_KEYS = frozenset({
    # Flat HindsightConfig fields (v0.9.2); credentials and headers are
    # intentionally absent from this list.
    "llm_provider", "llm_model", "llm_base_url",
    "retain_llm_provider", "retain_llm_model", "retain_llm_base_url",
    "reflect_llm_provider", "reflect_llm_model", "reflect_llm_base_url",
    "consolidation_llm_provider", "consolidation_llm_model",
    "consolidation_llm_base_url", "embeddings_provider", "reranker_provider",
    "embeddings_local_model", "embeddings_onnx_model_id",
    "embeddings_openai_model", "embeddings_openai_base_url",
    "embeddings_cohere_model", "embeddings_cohere_base_url",
    "embeddings_openrouter_model", "embeddings_litellm_model",
    "embeddings_litellm_api_base", "embeddings_litellm_sdk_model",
    "embeddings_litellm_sdk_api_base", "embeddings_gemini_model",
    "embeddings_zeroentropy_model", "embeddings_zeroentropy_base_url",
    "embeddings_tei_url", "reranker_local_model", "reranker_tei_url",
    "reranker_cohere_model", "reranker_cohere_base_url",
    "reranker_openrouter_model", "reranker_openrouter_base_url",
    "reranker_litellm_model", "reranker_litellm_api_base",
    "reranker_litellm_sdk_model", "reranker_litellm_sdk_api_base",
    "retain_extraction_mode", "retain_chunk_size", "retain_structured_chunk_size",
    "enable_observations", "enable_temporal_retrieval", "enable_graph_retrieval",
    "enable_reranking", "enable_auto_consolidation", "enable_observation_history",
    "enable_mental_model_history", "retain_extract_causal_links",
    "retain_batch_enabled", "retain_entity_lookup",
})
_OBSERVED_CONFIG_CONTAINERS = frozenset({"config", "overrides"})
_OBSERVED_CONFIG_URL_KEYS = frozenset({
    "llm_base_url", "retain_llm_base_url", "reflect_llm_base_url",
    "consolidation_llm_base_url", "embeddings_openai_base_url",
    "embeddings_cohere_base_url", "embeddings_litellm_api_base",
    "embeddings_litellm_sdk_api_base", "embeddings_zeroentropy_base_url",
    "embeddings_tei_url", "reranker_tei_url", "reranker_cohere_base_url",
    "reranker_openrouter_base_url", "reranker_litellm_api_base",
    "reranker_litellm_sdk_api_base",
})


def pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    return str(value)


def safe_url(value: str | None) -> str | None:
    """Keep only a credential-free endpoint origin/path in the artifact."""
    if not value:
        return value
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def sanitize_observed_bank_config(value: Any) -> dict[str, Any]:
    """Extract only safe, allowlisted fields from a bank-config response."""
    value = jsonable(value)

    def walk(node: Any) -> Any:
        if not isinstance(node, dict):
            return None
        output: dict[str, Any] = {}
        for raw_key, raw_value in node.items():
            key = str(raw_key)
            normalized = key.casefold().replace("-", "_")
            if normalized in _OBSERVED_CONFIG_KEYS:
                if normalized in _OBSERVED_CONFIG_URL_KEYS:
                    if isinstance(raw_value, str):
                        output[key] = safe_url(raw_value)
                elif isinstance(raw_value, (str, int, float, bool)) or raw_value is None:
                    output[key] = raw_value
            elif normalized in _OBSERVED_CONFIG_CONTAINERS:
                child = walk(raw_value)
                if child:
                    output[key] = child
        return output

    sanitized = walk(value)
    return sanitized if isinstance(sanitized, dict) else {}


def atomic_write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def step(name: str, fn: Callable[[], Any], steps: list[dict[str, Any]],
         *, required: bool = True) -> Any:
    started = time.perf_counter()
    row: dict[str, Any] = {
        "name": name,
        "required": required,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        result = fn()
        row.update({"ok": True, "elapsed_s": round(time.perf_counter() - started, 4),
                    "result": jsonable(result)})
        steps.append(row)
        return result
    except Exception as exc:  # preserve the exact service/client failure
        row.update({"ok": False, "elapsed_s": round(time.perf_counter() - started, 4),
                    "error_type": type(exc).__name__, "error": str(exc),
                    "traceback": traceback.format_exc()})
        steps.append(row)
        return None


def load_dataset() -> dict[str, Any]:
    raw = DATA_PATH.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("documents"), list) \
            or not isinstance(data.get("queries"), list):
        raise ValueError("comparative dataset must contain documents and queries arrays")
    return data


def metrics_snapshot() -> dict[str, Any]:
    response = httpx.get(f"{BASE_URL}/metrics", timeout=30)
    response.raise_for_status()
    prefixes = (
        "hindsight_llm_calls_total",
        "hindsight_llm_duration_seconds_count",
        "hindsight_llm_duration_seconds_sum",
        "hindsight_llm_tokens_input_tokens_total",
        "hindsight_llm_tokens_output_tokens_total",
        "hindsight_operation_operations_total",
        "hindsight_operation_duration_seconds_count",
        "hindsight_operation_duration_seconds_sum",
        "hindsight_retain_documents_total",
    )
    lines = [line for line in response.text.splitlines()
             if line and line.startswith(prefixes)]
    return {"selected_lines": lines, "raw_text": response.text}


def main() -> int:
    started = time.perf_counter()
    steps: list[dict[str, Any]] = []
    # Every run owns a unique bank.  A caller-supplied bank would risk
    # cross-run contamination and could make cleanup destructive.
    bank_id = (
        "hindsight-comparative-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        + "-" + uuid.uuid4().hex[:8]
    )
    report: dict[str, Any] = {
        "probe": "hindsight_real_rest_comparative_retrieval_v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "host": {"platform": platform.platform(), "python": sys.version},
        "service": {"base_url": safe_url(BASE_URL), "bank_id": bank_id},
        "dataset": {"path": str(DATA_PATH), "sha256": None, "name": None,
                     "license": None, "documents": None, "queries": None},
        "packages": {name: pkg(name) for name in
                     ("hindsight-all", "hindsight-all-slim", "hindsight-client",
                      "hindsight-embed")},
        "protocol": {
            "track": "real Hindsight retain plus recall; LLM-backed and distinct from raw-document adapters",
            "retains": "all dataset documents once, with source ID in content and document_id metadata",
            "recalls": "all dataset queries once, no answer model or judge",
            "budget": "high",
            "max_tokens": 1200,
            "query_timestamp": QUERY_TIMESTAMP,
            "include_chunks": True,
            "trace": True,
            "fresh_bank": True,
            "cleanup": "delete_bank attempted in finally",
        },
        "config": {
            "observed_server_configuration": None,
            "configuration_note": "Unknown unless returned by the service; the following are sanitized launcher environment hints only.",
            "environment_hints": {
                "llm_provider": os.environ.get("HINDSIGHT_API_LLM_PROVIDER"),
                "llm_model": os.environ.get("HINDSIGHT_API_LLM_MODEL"),
                "llm_base_url": safe_url(os.environ.get("HINDSIGHT_API_LLM_BASE_URL")),
                "embeddings_provider": os.environ.get("HINDSIGHT_API_EMBEDDINGS_PROVIDER"),
                "embeddings_model": os.environ.get("HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL"),
                "embeddings_base_url": safe_url(os.environ.get("HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL")),
                "reranker_provider": os.environ.get("HINDSIGHT_API_RERANKER_PROVIDER"),
                "database_url": safe_url(os.environ.get("HINDSIGHT_API_DATABASE_URL")),
            },
        },
        "claims": {"quality_score": None, "leaderboard_comparable": False,
                   "note": "Raw service evidence only; source markers are traceability aids, not an answer-quality score."},
        "steps": steps,
        "retains": [],
        "recalls": [],
        "progress": {"retains_attempted": 0, "retains_completed": 0,
                      "recalls_attempted": 0, "recalls_completed": 0},
        "status": "running",
    }

    def persist_progress() -> None:
        atomic_write(OUTPUT, report)

    try:
        raw_dataset = DATA_PATH.read_bytes()
        report["dataset"]["sha256"] = hashlib.sha256(raw_dataset).hexdigest()
        dataset = load_dataset()
        report["dataset"].update({"name": dataset.get("name"), "license": dataset.get("license"),
                                   "documents": len(dataset["documents"]),
                                   "queries": len(dataset["queries"])})
    except Exception as exc:
        report.update({"status": "blocked_dataset", "error_type": type(exc).__name__,
                       "error": str(exc), "elapsed_s": round(time.perf_counter() - started, 4)})
        atomic_write(OUTPUT, report)
        return 2

    health = step("health", lambda: _get_json("/health"), steps)
    version_info = step("version", lambda: _get_json("/version"), steps, required=False)
    report["service"]["version_response"] = jsonable(version_info)
    if version_info is None:
        report.setdefault("warnings", []).append("version endpoint unavailable; service version remains unknown")
    if health is None:
        report.update({"status": "blocked_health",
                       "elapsed_s": round(time.perf_counter() - started, 4)})
        atomic_write(OUTPUT, report)
        return 2

    try:
        from hindsight_client import Hindsight
    except Exception as exc:
        report.update({"status": "blocked_client_dependency", "error_type": type(exc).__name__,
                       "error": str(exc), "elapsed_s": round(time.perf_counter() - started, 4)})
        atomic_write(OUTPUT, report)
        return 2

    try:
        client = Hindsight(base_url=BASE_URL, timeout=TIMEOUT)
    except BaseException as exc:
        report.update({"status": "blocked_client_init", "error_type": type(exc).__name__,
                       "error": str(exc), "elapsed_s": round(time.perf_counter() - started, 4)})
        atomic_write(OUTPUT, report)
        return 2
    created = False
    try:
        report["metrics_before"] = step("metrics_before", metrics_snapshot, steps)
        create_result = step(
            "create_bank",
            lambda: client.create_bank(
                bank_id=bank_id,
                name="SMRITI comparative retrieval v1",
                retain_mission="Extract concrete facts while preserving dates and source details.",
                enable_observations=False,
                enable_temporal_retrieval=True,
                enable_graph_retrieval=True,
                enable_reranking=False,
            ),
            steps,
        )
        if create_result is None:
            report["status"] = "blocked_create_bank"
        else:
            created = True
            def read_bank_config() -> dict[str, Any]:
                getter = getattr(client, "get_bank_config", None)
                if not callable(getter):
                    raise RuntimeError("Hindsight client does not expose get_bank_config")
                # Sanitize before step() records the result: the raw response
                # is never written to steps or any other artifact field.
                return sanitize_observed_bank_config(getter(bank_id))

            observed_config = step("get_bank_config", read_bank_config, steps, required=False)
            if observed_config is None:
                report.setdefault("warnings", []).append(
                    "bank config endpoint unavailable; server configuration remains unknown")
            else:
                report["config"]["observed_server_configuration"] = observed_config
                if not observed_config:
                    report.setdefault("warnings", []).append(
                        "bank config returned no allowlisted fields; server configuration remains partially unknown")
            for document in dataset["documents"]:
                source_id = str(document["id"])
                content = f"[SOURCE_DOCUMENT_ID={source_id}] {document['text']}"
                result = step(
                    f"retain_{source_id}",
                    lambda content=content, document=document, source_id=source_id: client.retain(
                        bank_id=bank_id,
                        content=content,
                        timestamp=datetime.fromisoformat(document["timestamp"].replace("Z", "+00:00")),
                        context="checked-in comparative corpus",
                        document_id=source_id,
                        metadata={"source_id": source_id},
                    ),
                    steps,
                )
                report["retains"].append({"source_id": source_id,
                                          "timestamp": document["timestamp"],
                                          "response": jsonable(result)})
                report["progress"]["retains_attempted"] += 1
                if result is not None:
                    report["progress"]["retains_completed"] += 1
                persist_progress()

            for query in dataset["queries"]:
                result = step(
                    f"recall_{query['id']}",
                    lambda query=query: client.recall(
                        bank_id=bank_id,
                        query=query["query"],
                        budget="high",
                        max_tokens=1200,
                        query_timestamp=QUERY_TIMESTAMP,
                        include_chunks=True,
                        trace=True,
                    ),
                    steps,
                )
                payload = jsonable(result)
                serialized = json.dumps(payload, ensure_ascii=False)
                report["recalls"].append({
                    "query_id": query["id"],
                    "category": query.get("category"),
                    "query": query["query"],
                    "configured_relevant_source_ids": query.get("relevant", []),
                    "response": payload,
                    "diagnostic_source_marker_ids_in_raw_response": sorted(set(MARKER_RE.findall(serialized))),
                    "source_marker_note": "Diagnostic traceability only; never scored as retrieved evidence.",
                })
                report["progress"]["recalls_attempted"] += 1
                if result is not None:
                    report["progress"]["recalls_completed"] += 1
                persist_progress()
    except BaseException as exc:
        report["runner_error"] = {"type": type(exc).__name__, "error": str(exc),
                                   "traceback": traceback.format_exc()}
    finally:
        if created:
            step("delete_bank", lambda: client.delete_bank(bank_id), steps)
            report["cleanup"] = {"attempted": True, "bank_id": bank_id}
        else:
            report["cleanup"] = {"attempted": False, "reason": "bank was not successfully created"}
        try:
            client.close()
        except BaseException as exc:
            report["client_close_error"] = {"type": type(exc).__name__, "error": str(exc),
                                             "traceback": traceback.format_exc()}

    report["metrics_after"] = step("metrics_after", metrics_snapshot, steps)
    expected_retains = len(dataset["documents"])
    expected_recalls = len(dataset["queries"])
    report["completeness"] = {
        "expected_retains": expected_retains,
        "observed_retain_rows": len(report["retains"]),
        "completed_retains": report["progress"]["retains_completed"],
        "expected_recalls": expected_recalls,
        "observed_recall_rows": len(report["recalls"]),
        "completed_recalls": report["progress"]["recalls_completed"],
        "complete": (len(report["retains"]) == expected_retains
                     and report["progress"]["retains_completed"] == expected_retains
                     and len(report["recalls"]) == expected_recalls
                     and report["progress"]["recalls_completed"] == expected_recalls),
    }
    cleanup_failed = any(item.get("name") == "delete_bank" and not item.get("ok")
                         for item in steps)
    failed = [item for item in steps
              if item.get("required", True) and not item.get("ok")]
    blocking_status = report.get("status") if str(report.get("status", "")).startswith("blocked_") else None
    if blocking_status:
        report["status"] = blocking_status
    elif report.get("runner_error") or report.get("client_close_error") \
            or not report["completeness"]["complete"] or cleanup_failed:
        report["status"] = "completed_with_failures"
    else:
        report["status"] = "ok" if not failed else "completed_with_failures"
    incomplete_units = max(expected_retains - report["progress"]["retains_completed"], 0) \
        + max(expected_recalls - report["progress"]["recalls_completed"], 0)
    report["incomplete_units"] = incomplete_units
    report["failure_count"] = (len(failed) + int(bool(report.get("runner_error")))
                                + int(bool(report.get("client_close_error")))
                                + incomplete_units)
    report["elapsed_s"] = round(time.perf_counter() - started, 4)
    atomic_write(OUTPUT, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "ok" else 1


def _get_json(path: str) -> Any:
    response = httpx.get(f"{BASE_URL}{path}", timeout=30)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    raise SystemExit(main())
