#!/usr/bin/env python3
"""Small installed-model probe for named subjects and applicability scope.

This is an evidence-preserving extraction probe, not a quality benchmark.  It
uses the installed full-mode Smriti API to ingest unrelated named people, a
project-scoped tool transition, a separate global preference, and an explicit
self-reference.  The raw facts and cumulative provider counters are retained
so a failed contract assertion cannot be hidden by a post-hoc normalization.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import smriti
from smriti import LLM, OllamaEmbedder, Smriti


UPDATES = [
    ("2025-01-10T12:00:00Z",
     "Leila lives in Kyoto and works on the Juniper project."),
    ("2025-02-10T12:00:00Z",
     "Omar lives in Nairobi and works on the Kestrel project."),
    ("2025-03-10T12:00:00Z",
     "Leila switched from Sketch to Figma for project Cedar. Separately, Leila prefers dark mode globally."),
    ("2025-04-10T12:00:00Z",
     "I prefer concise answers."),
]
NOW = "2025-05-01T12:00:00Z"
CLEAR_SCOPE = "project:Cedar"
SWITCH_DATE = "2025-03-10"
USAGE_PREDICATES = frozenset({
    "uses", "uses_tool", "uses_software", "uses_application", "uses_editor",
    "currently_uses", "currently_uses_tool", "current_tool", "adopted_tool",
    "selected_tool",
})
TRANSITION_PREDICATES = frozenset({
    "switched_from", "switched_to", "changed_from", "changed_to",
    "migrated_from", "migrated_to", "replaced",
})


def jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return jsonable(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def safe_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url))
    host = parsed.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    try:
        port = ":" + str(parsed.port) if parsed.port is not None else ""
    except ValueError:
        port = ""
    return (f"{parsed.scheme}://{host}{port}{parsed.path}").rstrip("/")


def runtime_base(url: str) -> str:
    parsed = urllib.parse.urlsplit(str(url).rstrip("/"))
    path = parsed.path[:-3] if parsed.path.endswith("/v1") else parsed.path
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def provider_snapshot(base_url: str, models: Iterable[str]) -> Dict[str, Any]:
    root = runtime_base(base_url)
    result: Dict[str, Any] = {"endpoint": safe_url(base_url), "runtime_endpoint": safe_url(root),
                              "version": None, "tags": None, "models": {}, "errors": []}
    for key, path in (("version", "/api/version"), ("tags", "/api/tags")):
        try:
            request = urllib.request.Request(root + path, method="GET")
            with urllib.request.urlopen(request, timeout=5) as response:
                result[key] = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            result["errors"].append({"endpoint": safe_url(root + path),
                                      "type": type(exc).__name__, "error": str(exc)})
    available = (result.get("tags") or {}).get("models", [])
    for requested in models:
        result["models"][requested] = [model for model in available
                                         if isinstance(model, dict) and
                                         (model.get("name") == requested or
                                          str(model.get("name", "")).split(":", 1)[0] == requested.split(":", 1)[0])]
    return result


def usage_snapshot(llm: LLM) -> Dict[str, Any]:
    return {name: getattr(llm, name, None) for name in (
        "calls", "attempts", "http_attempts", "tokens_in", "tokens_out", "usage_missing")}


def usage_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in after.items():
        old = before.get(key)
        result[key] = value - old if isinstance(value, (int, float)) and isinstance(old, (int, float)) else value
    return result


def read_facts(memory: Smriti) -> List[Dict[str, Any]]:
    columns = {row[1] for row in memory.store.db.execute("PRAGMA table_info(facts)")}
    scope = "scope" if "scope" in columns else "'' AS scope"
    selected = ("id, statement, subject, predicate, object, kind, event_date, "
                "ingested_at, valid_from, invalid_at, superseded_by, "
                f"episode_id, session_id, {scope}")
    cursor = memory.store.db.execute("SELECT " + selected + " FROM facts ORDER BY id")
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _fold(value: Any) -> str:
    return str(value or "").strip().casefold()


def interval_contains(fact: Dict[str, Any], point: str) -> bool:
    start = fact.get("valid_from")
    end = fact.get("invalid_at")
    return ((start is None or str(start) <= point) and
            (end is None or point < str(end)))


def is_usage_predicate(value: Any) -> bool:
    predicate = _fold(value)
    return predicate in USAGE_PREDICATES or predicate.startswith(("use_", "uses_", "currently_uses_"))


def is_transition_predicate(value: Any) -> bool:
    return _fold(value) in TRANSITION_PREDICATES


def fact_matches(fact: Dict[str, Any], *, subject: str, object_terms: Iterable[str],
                 scope: Optional[str] = None, active: bool = False,
                 valid_from_date: Optional[str] = None) -> bool:
    if _fold(fact.get("subject")) != _fold(subject):
        return False
    if any(_fold(term) not in _fold(fact.get("object")) for term in object_terms):
        return False
    if scope is not None and str(fact.get("scope", "")) != scope:
        return False
    if valid_from_date is not None and not _fold(fact.get("valid_from")).startswith(_fold(valid_from_date)):
        return False
    return not active or fact.get("invalid_at") is None


def evaluate_contract(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    leila_kyoto = [fact for fact in facts if fact_matches(
        fact, subject="Leila", object_terms=("Kyoto",), scope="", active=True)]
    omar_nairobi = [fact for fact in facts if fact_matches(
        fact, subject="Omar", object_terms=("Nairobi",), scope="", active=True)]
    destination = [fact for fact in facts if fact_matches(
        fact, subject="Leila", object_terms=("Figma",), scope=CLEAR_SCOPE, active=True)
        and is_usage_predicate(fact.get("predicate"))
        and interval_contains(fact, NOW)]
    transition = [fact for fact in facts if fact_matches(
        fact, subject="Leila", object_terms=("Sketch",), scope=CLEAR_SCOPE,
        valid_from_date=SWITCH_DATE)
        and is_transition_predicate(fact.get("predicate"))]
    global_theme = [fact for fact in facts if fact_matches(
        fact, subject="Leila", object_terms=("dark",), scope="", active=True)]
    scoped_theme = [fact for fact in facts if fact_matches(
        fact, subject="Leila", object_terms=("dark",), scope=CLEAR_SCOPE, active=True)]
    self_reference = [fact for fact in facts if fact_matches(
        fact, subject="user", object_terms=("concise",), scope="", active=True)]
    return {
        "leila_kyoto_active": bool(leila_kyoto),
        "omar_nairobi_active": bool(omar_nairobi),
        "distinct_named_subjects": bool(leila_kyoto and omar_nairobi),
        "no_crossperson_city_invalidation": bool(leila_kyoto and omar_nairobi),
        "scoped_destination_state": bool(destination),
        "historical_scoped_transition_retained": bool(transition),
        "global_preference_is_unscoped": bool(global_theme) and not scoped_theme,
        "self_reference_is_user_scoped_empty": bool(self_reference),
        "leila_city_facts": leila_kyoto,
        "omar_city_facts": omar_nairobi,
        "scoped_destination_facts": destination,
        "scoped_transition_facts": transition,
        "global_preference_facts": global_theme,
        "scoped_preference_facts": scoped_theme,
        "self_reference_facts": self_reference,
        "observed_subjects": sorted({_fold(fact.get("subject")) for fact in facts}),
    }


def offline_adversarial_checks() -> Dict[str, bool]:
    """Ensure audit assertions reject plausible but incorrect extractions."""
    base = [
        {"subject": "Leila", "predicate": "uses_tool", "object": "Figma",
         "scope": CLEAR_SCOPE, "valid_from": "2025-03-10T12:00:00Z", "invalid_at": None},
        {"subject": "Leila", "predicate": "switched_from", "object": "Sketch",
         "scope": CLEAR_SCOPE, "valid_from": "2025-03-10T12:00:00Z", "invalid_at": None},
    ]
    wrong_relation = [dict(fact) for fact in base]
    wrong_relation[0]["predicate"] = "dislikes_tool"
    future_state = [dict(fact) for fact in base]
    future_state[0]["valid_from"] = "2025-06-01T12:00:00Z"
    current_sketch = [dict(fact) for fact in base]
    current_sketch[0]["object"] = "Sketch"
    wrong_transition_relation = [dict(fact) for fact in base]
    wrong_transition_relation[1]["predicate"] = "mentions_tool"
    wrong_transition_date = [dict(fact) for fact in base]
    wrong_transition_date[1]["valid_from"] = "2025-04-10T12:00:00Z"
    return {
        "wrong_destination_relation_rejected": not evaluate_contract(wrong_relation)["scoped_destination_state"],
        "future_destination_state_rejected": not evaluate_contract(future_state)["scoped_destination_state"],
        "current_sketch_not_destination_state": not evaluate_contract(current_sketch)["scoped_destination_state"],
        "wrong_transition_relation_rejected": not evaluate_contract(wrong_transition_relation)["historical_scoped_transition_retained"],
        "wrong_transition_date_rejected": not evaluate_contract(wrong_transition_date)["historical_scoped_transition_retained"],
    }


def write_report(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(jsonable(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="JSON artifact path")
    parser.add_argument("--llm-base-url", default=os.environ.get(
        "SMRITI_GENERALIZATION_LLM_URL", "http://127.0.0.1:11436/v1"))
    parser.add_argument("--embed-base-url", default=os.environ.get(
        "SMRITI_GENERALIZATION_EMBED_URL", "http://127.0.0.1:11436"))
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--embed-model", default="nomic-embed-text:v1.5")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "track": "installed Smriti extraction generalization probe; not a benchmark",
        "status": "started",
        "config": {
            "mode": "full", "model": args.model, "embed_model": args.embed_model,
            "llm_endpoint": safe_url(args.llm_base_url),
            "embed_endpoint": safe_url(args.embed_base_url),
            "extra_body": {"reasoning_effort": "none", "think": False},
            "extract_max_tokens": 2048, "now": NOW, "database": ":memory:",
        },
        "updates": [{"timestamp": timestamp, "content": content} for timestamp, content in UPDATES],
        "facts": [], "steps": [], "failures": [], "assertions": {}, "usage": {},
        "metrics_scope": "Cumulative counters on this probe's extraction LLM object; failed-call usage is unknown.",
        "provenance": {
            "smriti_version": getattr(smriti, "__version__", None),
            "smriti_module": str(Path(smriti.__file__).resolve()),
            "python": os.sys.version,
        },
    }
    try:
        report["provenance"]["distribution_version"] = importlib.metadata.version("smriti-agents")
    except importlib.metadata.PackageNotFoundError:
        report["provenance"]["distribution_version"] = "not-installed-as-smriti-agents"
    report["offline_contract_checks"] = offline_adversarial_checks()
    if not all(report["offline_contract_checks"].values()):
        report["status"] = "probe_contract_failure"
        report["failures"].append({"step": "offline_contract_checks",
                                   "error": "an adversarial negative was accepted by the audit assertions"})
        write_report(out, report)
        return 2
    report["provider"] = provider_snapshot(args.llm_base_url, (args.model, args.embed_model))
    write_report(out, report)

    memory: Optional[Smriti] = None
    extract_llm = LLM(model=args.model, provider="ollama", base_url=args.llm_base_url,
                       extra_body={"reasoning_effort": "none", "think": False}, max_tokens=2048)
    try:
        memory = Smriti(path=":memory:", mode="full", llm=extract_llm,
                        embedder=OllamaEmbedder(model=args.embed_model, base_url=args.embed_base_url))
        for index, (timestamp, content) in enumerate(UPDATES, 1):
            started = time.perf_counter()
            before = usage_snapshot(extract_llm)
            step: Dict[str, Any] = {"name": f"ingest_update_{index}", "timestamp": timestamp}
            try:
                added = memory.add([{"role": "user", "content": content}],
                                   session_id=f"generalization-update-{index}", timestamp=timestamp)
                step.update({"ok": True, "add_result": jsonable(added),
                             "extraction_diagnostics": jsonable(memory.last_extraction_diagnostics),
                             "elapsed_s": round(time.perf_counter() - started, 4)})
            except Exception as exc:
                step.update({"ok": False, "error_type": type(exc).__name__, "error": str(exc),
                             "traceback": traceback.format_exc(),
                             "elapsed_s": round(time.perf_counter() - started, 4)})
                report["failures"].append({"step": step["name"], "error": str(exc),
                                           "error_type": type(exc).__name__})
            after = usage_snapshot(extract_llm)
            step["usage_delta"] = usage_delta(before, after)
            step["usage_after"] = after
            report["steps"].append(step)
            report["facts"] = read_facts(memory)
            write_report(out, report)
        report["assertions"] = evaluate_contract(report["facts"])
    except Exception as exc:
        report["failures"].append({"step": "workflow", "error_type": type(exc).__name__,
                                   "error": str(exc), "traceback": traceback.format_exc()})
    finally:
        if memory is not None:
            try:
                report["facts"] = read_facts(memory)
            except Exception as exc:
                report["failures"].append({"step": "read_facts", "error_type": type(exc).__name__,
                                           "error": str(exc), "traceback": traceback.format_exc()})
            try:
                memory.close()
            except Exception as exc:
                report["failures"].append({"step": "cleanup", "error_type": type(exc).__name__,
                                           "error": str(exc), "traceback": traceback.format_exc()})
        report["usage"] = {"extract": usage_snapshot(extract_llm)}
        report["status"] = "ok" if report["assertions"] and all(report["assertions"].get(key, False)
                                                                  for key in (
                                                                      "leila_kyoto_active", "omar_nairobi_active",
                                                                      "distinct_named_subjects",
                                                                      "no_crossperson_city_invalidation",
                                                                      "scoped_destination_state",
                                                                      "historical_scoped_transition_retained",
                                                                      "global_preference_is_unscoped",
                                                                      "self_reference_is_user_scoped_empty",
                                                                  )) and not report["failures"] else "completed_with_failures"
        write_report(out, report)
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
