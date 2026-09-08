#!/usr/bin/env python3
"""Full-mode Mem0 2.0.20 smoke on three dated Mira updates.

This probe is deliberately separate from the matched infer=False retrieval
track. It records Mem0's actual add/update events, full stored memories, raw
retrieval results, timings, and errors. It does not synthesize post-hoc answers.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import inspect
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


UPDATES = [
    ("2024-01-10T12:00:00Z", "On January 10, 2024, Mira worked on the Aurora project in Mumbai and preferred Python."),
    ("2024-06-15T12:00:00Z", "On June 15, 2024, Mira moved to Berlin and joined the Atlas project. She still preferred Python."),
    ("2025-02-20T12:00:00Z", "On February 20, 2025, Mira switched from Python to Rust for the Atlas project and preferred light mode."),
]
QUERIES = {
    "current_rust_atlas": "What programming language does Mira currently prefer for the Atlas project?",
    "history_mumbai_python": "In January 2024, where did Mira work and what programming language did she prefer?",
}


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def safe_url(url: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    try:
        port = ":" + str(parsed.port) if parsed.port is not None else ""
    except ValueError:
        port = ""
    return f"{parsed.scheme}://{host}{port}{parsed.path.rstrip('/')}"


def sanitize_for_report(value: Any, key: str = "") -> Any:
    """Redact credentials/query strings from nested provider configuration."""
    if isinstance(value, dict):
        return {str(k): sanitize_for_report(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_for_report(item, key) for item in value]
    if isinstance(value, str) and ("url" in key.lower() or "endpoint" in key.lower()):
        return safe_url(value)
    return value


def get_json(url: str) -> Any:
    with urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def provider_snapshot(base_url: str) -> dict[str, Any]:
    root = safe_url(base_url).removesuffix("/v1")
    out: dict[str, Any] = {"endpoint": safe_url(base_url), "runtime_endpoint": root,
                           "version": None, "tags": None, "processes": None, "errors": []}
    for field, suffix in (("version", "/api/version"), ("tags", "/api/tags"), ("processes", "/api/ps")):
        try:
            out[field] = get_json(root + suffix)
        except Exception as exc:  # retain service metadata failure
            out["errors"].append({"endpoint": safe_url(root + suffix), "type": type(exc).__name__, "error": str(exc)})
    return out


def usage_snapshot(llm: Any) -> dict[str, Any]:
    return {"calls": getattr(llm, "calls", None),
            "tokens_in": getattr(llm, "tokens_in", None),
            "tokens_out": getattr(llm, "tokens_out", None),
            "usage_missing": getattr(llm, "usage_missing", None),
            "usage_observable": bool(getattr(llm, "usage_observable", False))}


class ThinkingOffOllamaLLM:
    """Mem0-compatible wrapper using official Client.chat with ``think=False``.

    Mem0 calls ``generate_response`` with optional response-format and tool
    arguments.  The wrapper forwards response format and tools, while retaining
    the Ollama native ``tool_choice`` default because Client.chat does not have
    a portable tool-choice contract across installed Ollama versions.
    """

    def __init__(self, config: dict[str, Any], timeout_s: float = 120.0,
                 num_ctx: int = 16384):
        from mem0.llms.ollama import OllamaConfig
        from ollama import Client
        self.config = OllamaConfig(**config)
        self.model = self.config.model
        self.timeout_s = timeout_s
        self.num_ctx = num_ctx
        self.client = Client(host=self.config.ollama_base_url, timeout=timeout_s)
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self.usage_missing = 0
        self.usage_observable = False
        self.call_timings: list[dict[str, Any]] = []
        self.thinking_control = {"parameter": "think", "value": False,
                                 "route": "ollama.Client.chat", "official": True,
                                 "signature": str(inspect.signature(Client.chat)),
                                 "timeout_s": timeout_s, "num_ctx": num_ctx}
        self.wrapper_contract = {
            "method": "generate_response",
            "response_format_forwarded": True,
            "tools_forwarded": True,
            "tool_choice": "accepted but left at Ollama Client.chat default",
            "think_false_forwarded": True,
        }

    def generate_response(self, messages, response_format=None, tools=None,
                          tool_choice="auto", **kwargs):
        started = time.perf_counter()
        params: dict[str, Any] = {"model": self.config.model, "messages": messages,
                                  "think": False,
                                  "options": {"temperature": self.config.temperature,
                                               "num_predict": self.config.max_tokens,
                                               "top_p": self.config.top_p}}
        params["options"]["num_ctx"] = self.num_ctx
        if response_format and response_format.get("type") == "json_object":
            params["format"] = "json"
        if tools:
            params["tools"] = tools
        self.calls += 1
        try:
            response = self.client.chat(**params)
            content = response["message"]["content"] if isinstance(response, dict) else response.message.content
            def response_field(name: str):
                if isinstance(response, dict):
                    return response.get(name)
                return getattr(response, name, None)
            prompt_tokens = response_field("prompt_eval_count")
            output_tokens = response_field("eval_count")
            if prompt_tokens is None or output_tokens is None:
                self.usage_missing += 1
            else:
                self.usage_observable = True
                self.tokens_in += int(prompt_tokens)
                self.tokens_out += int(output_tokens)
            message_chars = sum(len(str(message.get("content", ""))) for message in messages if isinstance(message, dict))
            message_sha256 = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            self.call_timings.append({"call": self.calls, "elapsed_s": round(time.perf_counter() - started, 4), "ok": True,
                                      "message_chars": message_chars, "message_sha256": message_sha256,
                                      "effective_num_ctx": self.num_ctx,
                                      "prompt_eval_count": prompt_tokens, "eval_count": output_tokens})
            return content
        except Exception as exc:
            message_chars = sum(len(str(message.get("content", ""))) for message in messages if isinstance(message, dict))
            message_sha256 = hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            self.call_timings.append({"call": self.calls, "elapsed_s": round(time.perf_counter() - started, 4),
                                      "message_chars": message_chars, "message_sha256": message_sha256,
                                      "effective_num_ctx": self.num_ctx,
                                      "ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})
            raise


def run_step(name: str, fn: Callable[[], Any], steps: list[dict[str, Any]]) -> Any:
    started = time.perf_counter()
    row: dict[str, Any] = {"name": name}
    try:
        result = fn()
        row.update({"ok": True, "elapsed_s": round(time.perf_counter() - started, 4),
                    "result": jsonable(result)})
        return result
    except Exception as exc:
        row.update({"ok": False, "elapsed_s": round(time.perf_counter() - started, 4),
                    "error": {"type": type(exc).__name__, "message": str(exc),
                              "traceback": traceback.format_exc()}})
        return None
    finally:
        steps.append(row)


def accepts_top_k(method: Any) -> bool:
    """Only claim top_k was applied when the installed method exposes it."""
    try:
        return "top_k" in inspect.signature(method).parameters
    except (TypeError, ValueError):
        return False


def get_all_bounded(memory: Any, filters: dict[str, Any], top_k: int) -> Any:
    if accepts_top_k(memory.get_all):
        return memory.get_all(filters=filters, top_k=top_k)
    return memory.get_all(filters=filters)


def search_bounded(memory: Any, query: str, filters: dict[str, Any], top_k: int) -> Any:
    if accepts_top_k(memory.search):
        return memory.search(query, filters=filters, top_k=top_k)
    return memory.search(query, filters=filters)


def text_of(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(text_of(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(text_of(item) for item in value)
    return str(value)


def has_terms(value: Any, terms: tuple[str, ...]) -> bool:
    haystack = text_of(value).lower()
    return all(term.lower() in haystack for term in terms)


def response_items(value: Any) -> list[Any]:
    """Unwrap Mem0's ``{"results": [...]}`` and list response shapes."""
    if isinstance(value, dict):
        for key in ("results", "memories", "data"):
            if isinstance(value.get(key), list):
                return value[key]
    return value if isinstance(value, list) else []


def memory_ids(value: Any) -> list[str]:
    ids = []
    for item in response_items(value):
        if isinstance(item, dict) and item.get("id"):
            ids.append(str(item["id"]))
    return ids


def memory_history_ids(memory: Any, ids: list[str]) -> dict[str, Any]:
    """Capture native Memory.history for every stored/add-result memory id."""
    records: list[dict[str, Any]] = []
    for memory_id in ids:
        try:
            records.append({"id": memory_id, "ok": True,
                            "history": jsonable(memory.history(memory_id))})
        except Exception as exc:
            records.append({"id": memory_id, "ok": False,
                            "error": {"type": type(exc).__name__, "message": str(exc),
                                      "traceback": traceback.format_exc()}})
    return {"requested_memory_ids": ids, "records": records}


def build_config(root: Path, base_url: str) -> dict[str, Any]:
    return {
        "vector_store": {"provider": "qdrant", "config": {
            "path": str(root / "qdrant"), "collection_name": "mira_full_probe",
            "embedding_model_dims": 768}},
        "embedder": {"provider": "ollama", "config": {
            "model": "nomic-embed-text:v1.5", "embedding_dims": 768,
            "ollama_base_url": base_url}},
        "llm": {"provider": "ollama", "config": {
            "model": "qwen3:8b", "temperature": 0.0, "max_tokens": 2048,
            "top_p": 0.1, "ollama_base_url": base_url}},
        "history_db_path": str(root / "history.db"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11436")
    parser.add_argument("--timeout-s", type=float, default=120.0,
                        help="bounded Ollama client timeout in seconds (1..300)")
    args = parser.parse_args()
    if not 1.0 <= args.timeout_s <= 300.0:
        parser.error("--timeout-s must be between 1 and 300 seconds")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    root = Path(tempfile.mkdtemp(prefix="mem0-mira-full-"))
    config = build_config(root, args.base_url)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "started",
        "track": "Mem0 OSS 2.0.20 full-mode three-update Mira smoke; no post-hoc answers",
        "config": {"mem0": sanitize_for_report(config), "mode": "infer=True", "database_scope": str(root),
                   "embedding_model": "nomic-embed-text:v1.5", "embedding_dimensions_configured": 768,
                   "llm_model": "qwen3:8b", "base_url": safe_url(args.base_url),
                   "client_timeout_s": args.timeout_s,
                   "llm_effective_options": {"num_ctx": 16384, "num_predict": 2048,
                                             "temperature": 0.0, "top_p": 0.1, "think": False},
                   "thinking_control": {"parameter": "think", "value": False,
                                        "mechanism": "explicit ThinkingOffOllamaLLM -> official ollama.Client.chat(think=False)",
                                        "Mem0_OllamaConfig_field": "unsupported; omitted from config"}},
        "updates": [{"timestamp": ts, "content": content} for ts, content in UPDATES],
        "queries": QUERIES, "steps": [], "retain_effects": [], "recall": {},
        "full_memory_facts": None, "errors": [], "usage": {},
        "metrics_scope": "Object-local call/timing counters and native Ollama prompt_eval_count/eval_count are recorded when returned; failed-call usage remains unknown.",
    }
    memory = None
    llm = None
    try:
        report["provenance"] = {"python": sys.version, "platform": platform.platform(),
                                "mem0_version": importlib.metadata.version("mem0ai"),
                                "source_snapshot": {"script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
        report["provider"] = run_step("provider_snapshot", lambda: provider_snapshot(args.base_url), report["steps"])
        from mem0 import Memory
        memory = run_step("construct_memory", lambda: Memory.from_config(config), report["steps"])
        if memory is None:
            raise RuntimeError("Memory.from_config failed")
        report["provenance"]["memory_method_contract"] = {
            "search_signature": str(inspect.signature(memory.search)),
            "get_all_signature": str(inspect.signature(memory.get_all)),
            "history_signature": str(inspect.signature(memory.history)),
            "search_top_k_parameter": accepts_top_k(memory.search),
            "get_all_top_k_parameter": accepts_top_k(memory.get_all),
        }
        llm = ThinkingOffOllamaLLM(config["llm"]["config"], timeout_s=args.timeout_s, num_ctx=16384)
        memory.llm = llm
        report["provenance"]["thinking_control_runtime"] = llm.thinking_control
        report["provenance"]["wrapper_contract"] = llm.wrapper_contract
        user_id = "mira-full-probe"
        for index, (timestamp, content) in enumerate(UPDATES, 1):
            before = usage_snapshot(llm)
            step: dict[str, Any] = {"index": index, "timestamp": timestamp}
            step_started = time.perf_counter()
            try:
                add_result = memory.add([{"role": "user", "content": content}],
                                        user_id=user_id, infer=True,
                                        metadata={"source": "mira-full-probe", "event_timestamp": timestamp})
                step["add_result"] = jsonable(add_result)
                step["stored_after_add"] = jsonable(get_all_bounded(memory, {"user_id": user_id}, 1000))
                step["stored_read_top_k_requested"] = 1000
                step["stored_read_top_k_applied"] = accepts_top_k(memory.get_all)
                step["ok"] = True
            except Exception as exc:
                step["ok"] = False
                step["error"] = {"type": type(exc).__name__, "message": str(exc),
                                  "traceback": traceback.format_exc()}
                report["errors"].append({"stage": f"retain_update_{index}", **step["error"]})
            step["elapsed_s"] = round(time.perf_counter() - step_started, 4)
            step["usage_before"] = before
            step["usage_after"] = usage_snapshot(llm)
            report["retain_effects"].append(step)
            if index == 1:
                report["provider_after_first_llm"] = run_step(
                    "provider_snapshot_after_first_llm", lambda: provider_snapshot(args.base_url), report["steps"])
        full_memory = run_step(
            "read_full_memory", lambda: get_all_bounded(memory, {"user_id": user_id}, 1000), report["steps"])
        report["full_memory_facts"] = full_memory
        report["full_memory_read_contract"] = {
            "top_k_requested": 1000,
            "top_k_applied": accepts_top_k(memory.get_all),
            "returned_count": len(response_items(full_memory)),
        }
        history_ids = []
        for source in [full_memory] + [step.get("add_result") for step in report["retain_effects"]]:
            for memory_id in memory_ids(source):
                if memory_id not in history_ids:
                    history_ids.append(memory_id)
        report["history"] = memory_history_ids(memory, history_ids)
        for history_record in report["history"]["records"]:
            if not history_record.get("ok"):
                report["errors"].append({
                    "stage": "history", "memory_id": history_record.get("id"),
                    "error": history_record.get("error"),
                })
        for label, query in QUERIES.items():
            row: dict[str, Any] = {"question": query}
            row["top_k_requested"] = 12
            row["top_k_applied"] = accepts_top_k(memory.search)
            row_started = time.perf_counter()
            try:
                row["results"] = jsonable(search_bounded(memory, query, {"user_id": user_id}, 12))
                row["ok"] = True
                if label == "history_mumbai_python":
                    row["history"] = report["history"]
            except Exception as exc:
                row["ok"] = False
                row["error"] = {"type": type(exc).__name__, "message": str(exc),
                                 "traceback": traceback.format_exc()}
                report["errors"].append({"stage": f"recall_{label}", **row["error"]})
            row["elapsed_s"] = round(time.perf_counter() - row_started, 4)
            report["recall"][label] = row
        report["quality_assertions"] = {
            "current_rust_atlas_evidence": bool(
                report["recall"].get("current_rust_atlas", {}).get("ok") and
                has_terms(report["recall"]["current_rust_atlas"].get("results"), ("rust", "atlas"))),
            "history_mumbai_python_search_evidence": bool(
                report["recall"].get("history_mumbai_python", {}).get("ok") and
                has_terms(report["recall"]["history_mumbai_python"].get("results"), ("mumbai", "python"))),
        }
        report["operational_assertions"] = {
            "history_calls_completed": bool(history_ids) and all(record.get("ok") for record in report["history"]["records"]),
        }
    except Exception as exc:
        report["errors"].append({"stage": "workflow", "type": type(exc).__name__,
                                 "message": str(exc), "traceback": traceback.format_exc()})
    finally:
        if memory is not None:
            try:
                memory.vector_store.client.close()
            except Exception as exc:
                report["errors"].append({"stage": "cleanup_vector_store", "type": type(exc).__name__, "message": str(exc)})
            try:
                memory.db.close()
            except Exception as exc:
                report["errors"].append({"stage": "cleanup_db", "type": type(exc).__name__, "message": str(exc)})
        if llm is not None:
            report["usage"] = {"llm": usage_snapshot(llm), "call_timings": llm.call_timings}
        shutil.rmtree(root, ignore_errors=True)
        report["elapsed_s"] = round(time.time() - started, 4)
        report["status"] = "ok" if (report.get("quality_assertions") and all(report["quality_assertions"].values())
                                     and report.get("operational_assertions")
                                     and all(report["operational_assertions"].values())
                                     and not report["errors"]) else "completed_with_failures"
        out.write_text(json.dumps(jsonable(report), indent=2, ensure_ascii=False) + "\n")
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
