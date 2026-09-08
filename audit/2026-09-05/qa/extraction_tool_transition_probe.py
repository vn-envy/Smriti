#!/usr/bin/env python3
"""Two-step installed-model probe for a scoped tool transition.

This is a bounded diagnostic fixture, not a benchmark.  It first states that
Leila uses Sketch for project Cedar and then states an explicit switch to
Figma.  The report retains the persisted facts after each step, derives
read-only as-of views from their validity intervals, and records cumulative
extraction/arbitration-provider counters.  It does not normalize or delete a
prior ``uses_tool`` fact.  If both tools remain active after the explicit
switch, ``quality_failures`` is non-empty so that the behavior is visible as
an observed contract result rather than silently scored as success.

Run only when an Ollama endpoint and the installed Smriti package are ready;
this file deliberately performs no model calls on import or with ``--help``.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Reuse only the existing probe's evidence and provider helpers.  The sibling
# probe is intentionally left unchanged: its four-update fixture and
# assertions must remain comparable with its preserved v6 artifacts.  These
# imports stay lazy so ``--help`` remains offline even on a source checkout
# without the installed runtime package.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _load_runtime_imports() -> None:
    global fact_matches, interval_contains, is_transition_predicate
    global is_usage_predicate, jsonable, provider_snapshot, safe_url
    global usage_delta, usage_snapshot, LLM, OllamaEmbedder, Smriti, smriti
    from extraction_generalization_probe import (  # noqa: E402
        fact_matches,
        interval_contains,
        is_transition_predicate,
        is_usage_predicate,
        jsonable,
        provider_snapshot,
        safe_url,
        usage_delta,
        usage_snapshot,
    )
    from smriti import LLM, OllamaEmbedder, Smriti  # noqa: E402
    import smriti  # noqa: E402


UPDATES = [
    (
        "2025-01-10T12:00:00Z",
        "Leila currently uses Sketch for project Cedar.",
    ),
    (
        "2025-03-10T12:00:00Z",
        "Leila switched from Sketch to Figma for project Cedar.",
    ),
]
ASOF_POINTS = {
    "before_switch": "2025-02-01T12:00:00Z",
    "after_switch": "2025-04-01T12:00:00Z",
}
NOW = ASOF_POINTS["after_switch"]
SCOPE = "project:Cedar"


def file_sha256(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def read_facts(memory: Smriti) -> List[Dict[str, Any]]:
    """Read persisted facts without asking the model or applying post-hoc fixes."""
    columns = {row[1] for row in memory.store.db.execute("PRAGMA table_info(facts)")}
    scope = "scope" if "scope" in columns else "'' AS scope"
    selected = (
        "id, statement, subject, predicate, object, kind, event_date, "
        "ingested_at, valid_from, invalid_at, superseded_by, episode_id, "
        f"session_id, {scope}"
    )
    cursor = memory.store.db.execute("SELECT " + selected + " FROM facts ORDER BY id")
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def facts_asof(facts: Iterable[Dict[str, Any]], point: str) -> List[Dict[str, Any]]:
    """Project persisted validity intervals at *point*; do not mutate facts."""
    return [
        fact for fact in facts
        if interval_contains(fact, point)
    ]


def _active_tool_facts(facts: Iterable[Dict[str, Any]], tool: str,
                       point: str = NOW) -> List[Dict[str, Any]]:
    return [
        fact for fact in facts
        if fact_matches(fact, subject="Leila", object_terms=(tool,), scope=SCOPE)
        and is_usage_predicate(fact.get("predicate"))
        and interval_contains(fact, point)
    ]


def _transition_facts(facts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        fact for fact in facts
        if fact_matches(fact, subject="Leila", object_terms=("Sketch",), scope=SCOPE)
        and is_transition_predicate(fact.get("predicate"))
    ]


def evaluate_transition(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    sketch_before = _active_tool_facts(
        facts_asof(facts, ASOF_POINTS["before_switch"]), "Sketch",
        ASOF_POINTS["before_switch"])
    figma_after = _active_tool_facts(
        facts_asof(facts, ASOF_POINTS["after_switch"]), "Figma",
        ASOF_POINTS["after_switch"])
    sketch_after = _active_tool_facts(
        facts_asof(facts, ASOF_POINTS["after_switch"]), "Sketch",
        ASOF_POINTS["after_switch"])
    transitions = _transition_facts(facts)
    return {
        "sketch_active_before_switch": bool(sketch_before),
        "figma_active_after_switch": bool(figma_after),
        "sketch_active_after_switch": bool(sketch_after),
        "historical_transition_present": bool(transitions),
        "sketch_before_facts": sketch_before,
        "figma_after_facts": figma_after,
        "sketch_after_facts": sketch_after,
        "transition_facts": transitions,
        "asof_fact_counts": {
            name: len(facts_asof(facts, point)) for name, point in ASOF_POINTS.items()
        },
    }


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
    _load_runtime_imports()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    report: Dict[str, Any] = {
        "track": "installed Smriti scoped uses_tool transition diagnostic; not a benchmark",
        "status": "started",
        "fixture": {
            "updates": [{"timestamp": ts, "content": text} for ts, text in UPDATES],
            "scope": SCOPE,
            "asof_points": ASOF_POINTS,
            "expected_prior": {"subject": "Leila", "predicate": "uses_tool",
                                "object": "Sketch", "scope": SCOPE},
            "expected_destination": {"subject": "Leila", "predicate": "uses_tool",
                                      "object": "Figma", "scope": SCOPE},
            "expected_transition": {"subject": "Leila", "predicate": "switched_from",
                                     "object": "Sketch", "scope": SCOPE},
        },
        "config": {
            "mode": "full", "model": args.model, "embed_model": args.embed_model,
            "llm_endpoint": safe_url(args.llm_base_url),
            "embed_endpoint": safe_url(args.embed_base_url),
            "extra_body": {"reasoning_effort": "none", "think": False},
            "extract_max_tokens": 2048, "session_ids": ["tool-transition-update-1",
                                                            "tool-transition-update-2"],
            "database": ":memory:",
        },
        "facts": [], "asof": {}, "steps": [], "failures": [],
        "quality_failures": [], "assertions": {}, "usage": {},
        "metrics_scope": "Cumulative counters on this probe's extraction LLM object; failed-call usage is unknown.",
        "provenance": {
            "script": str(Path(__file__).resolve()),
            "script_sha256_at_start": file_sha256(Path(__file__).resolve()),
            "reused_helper": str(_HERE / "extraction_generalization_probe.py"),
            "reused_helper_sha256_at_start": file_sha256(
                _HERE / "extraction_generalization_probe.py"),
            "smriti_version": getattr(smriti, "__version__", None),
            "smriti_module": str(Path(smriti.__file__).resolve()),
            "smriti_module_sha256": file_sha256(Path(smriti.__file__).resolve()),
            "python": sys.version,
        },
        "interpretation": {
            "retirement_contract": "diagnostic only: uses_tool is not assumed single-valued by this fixture",
            "quality_failure_meaning": "old Sketch remaining active alongside explicit scoped Figma destination",
            "quality_failure_is_proof": False,
            "unobserved_runtime_behavior": "same-predicate semantic arbitration may be conditional on similarity, scope, and arbiter response",
        },
    }
    try:
        report["provenance"]["distribution_version"] = importlib.metadata.version("smriti-agents")
    except importlib.metadata.PackageNotFoundError:
        report["provenance"]["distribution_version"] = "not-installed-as-smriti-agents"

    report["provider"] = provider_snapshot(args.llm_base_url, (args.model, args.embed_model))
    write_report(out, report)

    memory: Optional[Smriti] = None
    extract_llm = LLM(model=args.model, provider="ollama", base_url=args.llm_base_url,
                       extra_body={"reasoning_effort": "none", "think": False}, max_tokens=2048)
    try:
        memory = Smriti(path=":memory:", mode="full", llm=extract_llm,
                        embedder=OllamaEmbedder(model=args.embed_model,
                                                base_url=args.embed_base_url))
        for index, (timestamp, content) in enumerate(UPDATES, 1):
            started = time.perf_counter()
            before = usage_snapshot(extract_llm)
            step: Dict[str, Any] = {
                "name": f"ingest_update_{index}", "timestamp": timestamp,
                "content": content, "session_id": f"tool-transition-update-{index}",
            }
            try:
                added = memory.add([{"role": "user", "content": content}],
                                   session_id=step["session_id"], timestamp=timestamp)
                step.update({
                    "ok": True,
                    "add_result": jsonable(added),
                    "extraction_diagnostics": jsonable(
                        getattr(memory, "last_extraction_diagnostics", None)),
                })
            except Exception as exc:
                step.update({"ok": False, "error_type": type(exc).__name__,
                             "error": str(exc), "traceback": traceback.format_exc()})
                report["failures"].append({"step": step["name"], "error_type": type(exc).__name__,
                                           "error": str(exc)})
            after = usage_snapshot(extract_llm)
            step["usage_before"] = before
            step["usage_after"] = after
            step["usage_delta"] = usage_delta(before, after)
            step["elapsed_s"] = round(time.perf_counter() - started, 4)
            report["steps"].append(step)
            report["facts"] = read_facts(memory)
            report["asof"] = {
                name: facts_asof(report["facts"], point)
                for name, point in ASOF_POINTS.items()
            }
            write_report(out, report)

        report["assertions"] = evaluate_transition(report["facts"])
        # A destination and explicit switch are enough to make an active prior
        # tool a visible quality failure; absence of either is a contract/
        # extraction failure, not a retirement result.
        if (report["assertions"]["figma_active_after_switch"] and
                report["assertions"]["sketch_active_after_switch"]):
            report["quality_failures"].append({
                "kind": "prior_tool_remains_active_after_explicit_switch",
                "prior": "Sketch", "destination": "Figma", "scope": SCOPE,
                "asof": ASOF_POINTS["after_switch"],
                "message": "Explicit Figma switch coexists with active scoped Sketch fact; retirement behavior requires review.",
            })
        for key in ("sketch_active_before_switch", "figma_active_after_switch"):
            if not report["assertions"].get(key, False):
                report["failures"].append({"step": "contract", "error_type": "MissingExpectedFact",
                                           "error": key})
    except Exception as exc:
        report["failures"].append({"step": "workflow", "error_type": type(exc).__name__,
                                   "error": str(exc), "traceback": traceback.format_exc()})
    finally:
        if memory is not None:
            try:
                report["facts"] = read_facts(memory)
                report["asof"] = {
                    name: facts_asof(report["facts"], point)
                    for name, point in ASOF_POINTS.items()
                }
            except Exception as exc:
                report["failures"].append({"step": "read_facts", "error_type": type(exc).__name__,
                                           "error": str(exc)})
            try:
                memory.close()
            except Exception as exc:
                report["failures"].append({"step": "cleanup", "error_type": type(exc).__name__,
                                           "error": str(exc), "traceback": traceback.format_exc()})
        report["usage"] = {"extract": usage_snapshot(extract_llm)}
        report["status"] = (
            "completed_with_quality_failures" if report["quality_failures"] else
            "completed_with_failures" if report["failures"] else "ok"
        )
        write_report(out, report)
    return 2 if report["failures"] or report["quality_failures"] else 0


def write_report(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(jsonable(report), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
