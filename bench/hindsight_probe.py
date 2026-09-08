#!/usr/bin/env python3
"""Bounded real Hindsight retain/recall smoke probe.

The probe talks to a separately started Hindsight API and records raw client
responses, timings, installed package versions, and provider configuration.
It intentionally makes no quality claim or leaderboard score.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx

from hindsight_client import Hindsight


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "audit" / "2026-09-05" / "hindsight-smoke.json"
OUTPUT = Path(os.environ.get("HINDSIGHT_SMOKE_OUTPUT", str(OUT)))
BASE_URL = os.environ.get("HINDSIGHT_SMOKE_BASE_URL", "http://127.0.0.1:8892")
BANK_ID = os.environ.get("HINDSIGHT_SMOKE_BANK", "smriti-hindsight-smoke-20260907")


def pkg(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        return jsonable(value.model_dump(mode="json"))
    if hasattr(value, "to_dict"):
        return jsonable(value.to_dict())
    return str(value)


def safe_url(value: str | None) -> str | None:
    """Persist provider endpoints without credentials, query strings, or fragments."""
    if not value:
        return value
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def run_step(name: str, fn: Callable[[], Any], steps: list[dict[str, Any]]) -> Any:
    started = time.perf_counter()
    row: dict[str, Any] = {"name": name, "started_at": datetime.now(timezone.utc).isoformat()}
    try:
        result = fn()
        row.update({"ok": True, "elapsed_s": round(time.perf_counter() - started, 4), "result": jsonable(result)})
        steps.append(row)
        return result
    except Exception as exc:  # retain exact errors for auditability
        row.update(
            {
                "ok": False,
                "elapsed_s": round(time.perf_counter() - started, 4),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        steps.append(row)
        return None


def metrics_snapshot() -> list[str]:
    """Keep the counters needed to audit model calls/tokens and operation time."""
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
    return [line for line in response.text.splitlines() if line and line.startswith(prefixes)]


def ollama_snapshot() -> dict[str, Any]:
    """Capture the local Ollama runtime and model inventory used by the service."""
    result: dict[str, Any] = {}
    ollama_url = os.environ.get("HINDSIGHT_SMOKE_OLLAMA_URL", "http://127.0.0.1:11434")
    for name, path in (("version", "/api/version"), ("models", "/api/tags")):
        try:
            response = httpx.get(f"{ollama_url}{path}", timeout=30)
            response.raise_for_status()
            result[name] = response.json()
        except Exception as exc:
            result[name] = {"error_type": type(exc).__name__, "error": str(exc)}
    return result


def main() -> int:
    started = time.perf_counter()
    steps: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "probe": "hindsight_real_local_retain_recall_smoke",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "host": {"platform": platform.platform(), "python": sys.version},
        "base_url": BASE_URL,
        "bank_id": BANK_ID,
        "workflow_mode": "metrics_only" if os.environ.get("HINDSIGHT_SMOKE_SKIP_RETAIN") == "1" else "full",
        "packages": {name: pkg(name) for name in ("hindsight-all", "hindsight-all-slim", "hindsight-api-slim", "hindsight-client", "hindsight-embed")},
        "config": {
            "llm_provider": os.environ.get("HINDSIGHT_API_LLM_PROVIDER"),
            "llm_model": os.environ.get("HINDSIGHT_API_LLM_MODEL"),
            "llm_base_url": safe_url(os.environ.get("HINDSIGHT_API_LLM_BASE_URL")),
            "embeddings_provider": os.environ.get("HINDSIGHT_API_EMBEDDINGS_PROVIDER"),
            "embeddings_model": os.environ.get("HINDSIGHT_API_EMBEDDINGS_OPENAI_MODEL"),
            "embeddings_base_url": safe_url(os.environ.get("HINDSIGHT_API_EMBEDDINGS_OPENAI_BASE_URL")),
            "reranker_provider": os.environ.get("HINDSIGHT_API_RERANKER_PROVIDER"),
            "database_url": safe_url(os.environ.get("HINDSIGHT_API_DATABASE_URL")),
        },
        "steps": steps,
        "claims": {
            "quality_score": None,
            "leaderboard_comparable": False,
            "note": "Synthetic three-update smoke only; no accuracy score or cross-system comparison.",
        },
        "metrics_scope": "API process cumulative; not a per-run delta (shared service may include prior smoke attempts).",
    }

    def get(path: str) -> Any:
        response = httpx.get(f"{BASE_URL}{path}", timeout=30)
        response.raise_for_status()
        return response.json()

    health = run_step("health", lambda: get("/health"), steps)
    version_info = run_step("version", lambda: get("/version"), steps)
    if health is None:
        report["status"] = "blocked_health"
        report["elapsed_s"] = round(time.perf_counter() - started, 4)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
        return 2

    client = Hindsight(base_url=BASE_URL, timeout=300)
    try:
        report["ollama"] = run_step("ollama_snapshot", ollama_snapshot, steps)
        current_recall = run_step(
            "create_bank",
            lambda: client.create_bank(
                bank_id=BANK_ID,
                name="Smriti Hindsight smoke",
                retain_mission="Extract concise, concrete facts and preserve event dates.",
                enable_observations=False,
                enable_temporal_retrieval=True,
                enable_graph_retrieval=True,
                enable_reranking=False,
            ),
            steps,
        )

        updates = [
            {
                "timestamp": "2024-01-10T12:00:00Z",
                "content": "On January 10, 2024, Mira worked on the Aurora project in Mumbai and preferred Python.",
                "context": "initial profile",
            },
            {
                "timestamp": "2024-06-15T12:00:00Z",
                "content": "On June 15, 2024, Mira moved to Berlin and joined the Atlas project. She still preferred Python.",
                "context": "mid-year update",
            },
            {
                "timestamp": "2025-02-20T12:00:00Z",
                "content": "On February 20, 2025, Mira switched from Python to Rust for the Atlas project and preferred light mode.",
                "context": "current update",
            },
        ]
        if os.environ.get("HINDSIGHT_SMOKE_SKIP_RETAIN") != "1":
            for index, item in enumerate(updates, start=1):
                run_step(
                    f"retain_update_{index}",
                    lambda item=item: client.retain(
                        bank_id=BANK_ID,
                        content=item["content"],
                        timestamp=datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")),
                        context=item["context"],
                    ),
                    steps,
                )

        current_recall = run_step(
            "recall_current",
            lambda: client.recall(
                bank_id=BANK_ID,
                query="What programming language does Mira currently prefer for the Atlas project?",
                budget="high",
                max_tokens=1200,
                query_timestamp="2025-03-01T12:00:00Z",
                include_chunks=True,
                trace=True,
            ),
            steps,
        )
        history_recall = run_step(
            "recall_history",
            lambda: client.recall(
                bank_id=BANK_ID,
                query="What programming language did Mira prefer before switching to Rust?",
                budget="high",
                max_tokens=1200,
                query_timestamp="2025-03-01T12:00:00Z",
                include_chunks=True,
                trace=True,
            ),
            steps,
        )
        run_step(
            "list_memories",
            lambda: client.list_memories(bank_id=BANK_ID, limit=50),
            steps,
        )
    finally:
        client.close()

    report["metrics"] = run_step("metrics_snapshot", metrics_snapshot, steps)
    current_payload = jsonable(current_recall) if current_recall is not None else {}
    history_payload = jsonable(history_recall) if history_recall is not None else {}
    current_texts = [item.get("text", "") for item in current_payload.get("results", [])]
    history_texts = [item.get("text", "") for item in history_payload.get("results", [])]
    report["assertions"] = {
        "current_recall_contains_rust": any("switched from Python to Rust" in text for text in current_texts),
        "current_recall_contains_atlas": any("Atlas project" in text for text in current_texts),
        "history_recall_contains_mumbai": any("Mumbai" in text for text in history_texts),
        "history_recall_contains_prior_python": any("preferred Python" in text for text in history_texts),
        "current_result_count": len(current_texts),
        "history_result_count": len(history_texts),
    }
    expected = (
        "current_recall_contains_rust",
        "current_recall_contains_atlas",
        "history_recall_contains_mumbai",
        "history_recall_contains_prior_python",
    )
    steps_ok = all(step.get("ok") for step in steps)
    assertions_ok = all(report["assertions"].get(key) is True for key in expected)
    report["status"] = "ok" if steps_ok and assertions_ok else "completed_with_failures"
    report["elapsed_s"] = round(time.perf_counter() - started, 4)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
