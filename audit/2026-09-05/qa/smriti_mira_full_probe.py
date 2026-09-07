#!/usr/bin/env python3
"""Portable, evidence-preserving full-mode Smriti smoke.

This is an executable audit probe rather than a benchmark.  It uses the
installed Smriti API to ingest three dated Mira updates, then records the
actual extracted facts, retrieval evidence, answer/judge outputs, provider
configuration, model metadata, usage counters, and every failure.  It does
not insert facts directly and does not replace a failed call with a mock.

The probe performs a small YES/NO judge sanity check before the three writes.
If the requested no-thinking configuration does not produce a usable judge
response, it writes the failure artifact and exits without spending the larger
ingestion run.
"""
from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime
import importlib.metadata
import json
import os
import shlex
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import smriti
from smriti import LLM, OllamaEmbedder, Smriti


UPDATES = [
    (
        "2024-01-10T12:00:00Z",
        "On January 10, 2024, Mira worked on the Aurora project in Mumbai and preferred Python.",
    ),
    (
        "2024-06-15T12:00:00Z",
        "On June 15, 2024, Mira moved to Berlin and joined the Atlas project. She still preferred Python.",
    ),
    (
        "2025-02-20T12:00:00Z",
        "On February 20, 2025, Mira switched from Python to Rust for the Atlas project and preferred light mode.",
    ),
]
NOW = "2025-03-01T12:00:00Z"
QUERIES = {
    "current_rust_atlas": "What programming language does Mira currently use for the Atlas project?",
    "history_mumbai_python": "In January 2024, where did Mira work and what programming language did she prefer?",
}
GOLDS = {
    "current_rust_atlas": "Mira currently uses Rust for the Atlas project.",
    "history_mumbai_python": "In January 2024, Mira preferred Python and worked in Mumbai.",
}
HISTORY_POINT = "2024-01-10T12:00:00Z"
SWITCH_POINT = "2025-02-20T12:00:00Z"
ATLAS_SCOPE = "project:Atlas"
MIRA_SUBJECT = "Mira"
LANGUAGE_STATE_PREDICATES = (
    "prefers", "preferred", "preference", "primary_programming_language",
    "preferred_language", "preferred_programming_language", "uses_language",
    "uses_programming_language", "currently_uses_language", "uses_tool",
)


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
    """Keep scheme/host/port/path while removing credentials and queries."""
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    try:
        port = ":" + str(parsed.port) if parsed.port is not None else ""
    except ValueError:
        port = ""
    return (f"{parsed.scheme}://{host}{port}{parsed.path}").rstrip("/")


def runtime_base(url: str) -> str:
    parsed = urllib.parse.urlsplit(url.rstrip("/"))
    path = parsed.path[:-3] if parsed.path.endswith("/v1") else parsed.path
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))


def get_json(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def provider_snapshot(base_url: str, model_names: Iterable[str]) -> Dict[str, Any]:
    """Capture best-effort Ollama version/tags without issuing model calls."""
    root = runtime_base(base_url)
    snapshot: Dict[str, Any] = {
        "endpoint": safe_url(base_url),
        "runtime_endpoint": safe_url(root),
        "version": None,
        "tags": None,
        "models": {},
        "errors": [],
    }
    for name, path in (("version", "/api/version"), ("tags", "/api/tags")):
        try:
            data = get_json(root + path)
            snapshot[name] = data
        except Exception as exc:  # retain service/config failures in artifact
            snapshot["errors"].append({
                "endpoint": safe_url(root + path),
                "type": type(exc).__name__,
                "error": str(exc),
            })
    tags = snapshot.get("tags") or {}
    available = tags.get("models", []) if isinstance(tags, dict) else []
    for requested in model_names:
        matches = [m for m in available if isinstance(m, dict) and
                   (m.get("name") == requested or str(m.get("name", "")).split(":", 1)[0] == requested.split(":", 1)[0])]
        snapshot["models"][requested] = matches
    return snapshot


def usage_snapshot(llm: LLM) -> Dict[str, Any]:
    return {name: getattr(llm, name, None) for name in (
        "attempts", "http_attempts", "calls", "tokens_in", "tokens_out", "usage_missing")}


def usage_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for key, value in after.items():
        old = before.get(key)
        out[key] = value - old if isinstance(value, (int, float)) and isinstance(old, (int, float)) else value
    return out


def run_step(name: str, fn, steps: List[Dict[str, Any]]) -> Any:
    started = time.monotonic()
    row: Dict[str, Any] = {"name": name, "started_at_monotonic": started}
    try:
        value = fn()
        row.update({"ok": True, "elapsed_s": round(time.monotonic() - started, 4),
                    "result": jsonable(value)})
        return value
    except Exception as exc:
        row.update({
            "ok": False,
            "elapsed_s": round(time.monotonic() - started, 4),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })
        return None
    finally:
        row.pop("started_at_monotonic", None)
        steps.append(row)


def attach_usage(steps: List[Dict[str, Any]], before: Dict[str, Any], llm: LLM) -> None:
    if steps:
        after = usage_snapshot(llm)
        steps[-1]["usage_delta"] = usage_delta(before, after)
        steps[-1]["usage_after"] = after


def result_dicts(results: Iterable[Any]) -> List[Dict[str, Any]]:
    return [jsonable(result) for result in results]


def read_facts(memory: Smriti) -> List[Dict[str, Any]]:
    columns = (
        "id", "statement", "subject", "predicate", "object", "kind",
        "event_date", "ingested_at", "valid_from", "invalid_at",
        "superseded_by", "episode_id", "session_id", "scope",
    )
    cursor = memory.store.db.execute("SELECT " + ", ".join(columns) + " FROM facts ORDER BY id")
    names = [description[0] for description in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def text_of_evidence(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(text_of_evidence(item) for item in value)
    if isinstance(value, dict):
        return " ".join(text_of_evidence(item) for item in value.values())
    return str(value)


def has_terms(value: Any, terms: Iterable[str]) -> bool:
    haystack = text_of_evidence(value).lower()
    return all(term.lower() in haystack for term in terms)


def interval_contains(fact: Dict[str, Any], point: str) -> bool:
    """Evaluate a fact's structured validity interval at an ISO timestamp."""
    start = fact.get("valid_from")
    end = fact.get("invalid_at")
    return (start is None or str(start) <= point) and (end is None or point < str(end))


def same_calendar_day(left: Any, right: str) -> bool:
    def parse(value: Any):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    try:
        return parse(left) == parse(right)
    except (TypeError, ValueError):
        return False


def structured_fact_matches(fact: Dict[str, Any], terms: Iterable[str], point: Optional[str] = None) -> bool:
    structured = " ".join(str(fact.get(key, "")) for key in ("subject", "predicate", "object"))
    searchable = structured + " " + str(fact.get("statement", ""))
    if not has_terms(searchable, terms):
        return False
    return point is None or interval_contains(fact, point)


def active_preference_facts(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [fact for fact in facts if fact.get("invalid_at") is None and
            "prefer" in (str(fact.get("predicate", "")) + " " + str(fact.get("statement", ""))).lower()]


def active_language_preference_facts(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Limit ambiguity checking to the programming-language preference."""
    return [fact for fact in facts if fact.get("invalid_at") is None and
            str(fact.get("predicate", "")).strip().lower() in
            LANGUAGE_STATE_PREDICATES and
            any(language in str(fact.get("object", "")).lower()
                for language in ("python", "rust"))]


def language_preference_value(fact: Dict[str, Any]) -> Optional[str]:
    value = str(fact.get("object", "")).strip().lower()
    return value or None


def language_preference_matches(fact: Dict[str, Any], language: str,
                                point: Optional[str] = None,
                                scope: Optional[str] = None,
                                subject: Optional[str] = None) -> bool:
    predicate = str(fact.get("predicate", "")).strip().lower()
    value = language_preference_value(fact)
    return (predicate in LANGUAGE_STATE_PREDICATES and
            value is not None and language.lower() in value and
            (scope is None or str(fact.get("scope", "")) == scope) and
            (subject is None or str(fact.get("subject", "")).strip().casefold() == subject.casefold()) and
            (point is None or interval_contains(fact, point)))


def raw_fact_matches(fact: Dict[str, Any], *, predicate: Optional[str] = None,
                     object_terms: Iterable[str] = (), scope: Optional[str] = None,
                     event_date: Optional[str] = None,
                     subject: Optional[str] = MIRA_SUBJECT) -> bool:
    """Match audit-critical structured fields without statement substring inference."""
    if subject is not None and str(fact.get("subject", "")).strip().casefold() != subject.casefold():
        return False
    if predicate is not None and str(fact.get("predicate", "")).strip().casefold() != predicate.casefold():
        return False
    value = str(fact.get("object", "")).casefold()
    if any(str(term).casefold() not in value for term in object_terms):
        return False
    if scope is not None and str(fact.get("scope", "")) != scope:
        return False
    return event_date is None or str(fact.get("event_date", "")) == event_date


def scope_is_not_date(fact: Dict[str, Any]) -> bool:
    """Dates belong in event/validity fields, not applicability scope."""
    return not str(fact.get("scope", "")).strip().casefold().startswith("date:")


def is_project_membership_predicate(value: Any) -> bool:
    predicate = str(value or "").strip().casefold()
    return predicate in {"joined", "joined_project", "works_on", "worked_on",
                         "participates_in", "member_of"} or predicate.startswith("joined_")


def judge_verdict(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    normalized = text.strip().upper()
    return normalized if normalized in ("YES", "NO") else None


def relation_review(facts: List[Dict[str, Any]]) -> Dict[str, Any]:
    relation_words = ("work", "join", "project", "moved", "live", "prefer", "switch")
    candidates = [fact for fact in facts if any(
        word in (str(fact.get("statement", "")) + " " + str(fact.get("predicate", ""))).lower()
        for word in relation_words)]
    return {
        "candidate_relation_facts": candidates,
        "note": "Candidate relation facts and parser aliases are reported for review; no relation or alias correction was applied post hoc.",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="JSON artifact path")
    parser.add_argument("--llm-base-url", default=os.environ.get("SMRITI_MIRA_LLM_URL", "http://127.0.0.1:11436/v1"))
    parser.add_argument("--embed-base-url", default=os.environ.get("SMRITI_MIRA_EMBED_URL", "http://127.0.0.1:11436"))
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--embed-model", default="nomic-embed-text:v1.5")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    steps: List[Dict[str, Any]] = []
    report: Dict[str, Any] = {
        "track": "Smriti installed full-mode synthetic Mira quality smoke; not a comparative benchmark",
        "status": "started",
        "command": shlex.join([sys.executable, str(Path(sys.argv[0]).resolve())] + sys.argv[1:]),
        "provenance": {
            "smriti_version": getattr(smriti, "__version__", None),
            "smriti_module": str(Path(smriti.__file__).resolve()),
            "distribution_version": None,
            "python": os.sys.version,
        },
        "config": {
            "mode": "full",
            "model": args.model,
            "embed_model": args.embed_model,
            "llm_endpoint": safe_url(args.llm_base_url),
            "embed_endpoint": safe_url(args.embed_base_url),
            "extra_body": {"reasoning_effort": "none", "think": False},
            "extract_max_tokens": 2048,
            "answer_max_tokens": 256,
            "judge_max_tokens": 64,
            "now": NOW,
            "database": ":memory:",
        },
        "updates": [{"timestamp": timestamp, "content": content} for timestamp, content in UPDATES],
        "steps": steps,
        "assertions": {},
        "failures": [],
        "usage": {},
        "metrics_scope": "This artifact reports this probe's object-local counters; failed-call usage is unknown and not counted as successful usage.",
    }

    try:
        report["provenance"]["distribution_version"] = importlib.metadata.version("smriti-agents")
    except importlib.metadata.PackageNotFoundError:
        report["provenance"]["distribution_version"] = "not-installed-as-smriti-agents"

    report["provider"] = run_step(
        "provider_snapshot", lambda: provider_snapshot(args.llm_base_url, (args.model, args.embed_model)), steps)
    write_report(out, report)

    body = {"reasoning_effort": "none", "think": False}
    extract_llm = LLM(model=args.model, base_url=args.llm_base_url, provider="ollama", extra_body=body, max_tokens=2048)
    answer_llm = LLM(model=args.model, base_url=args.llm_base_url, provider="ollama", extra_body=body, max_tokens=256)
    judge_llm = LLM(model=args.model, base_url=args.llm_base_url, provider="ollama", extra_body=body, max_tokens=64)

    before = usage_snapshot(judge_llm)
    sanity = run_step(
        "judge_sanity",
        lambda: judge_llm.complete([
            {"role": "system", "content": "Answer exactly YES or NO. Do not explain."},
            {"role": "user", "content": "Does Rust appear in this text? Text: Mira uses Rust."},
        ], max_tokens=32),
        steps,
    )
    attach_usage(steps, before, judge_llm)
    report["judge_sanity"] = {"raw": sanity, "verdict": judge_verdict(sanity)}
    write_report(out, report)
    before = usage_snapshot(judge_llm)
    negative_sanity = run_step(
        "judge_sanity_negative_control",
        lambda: judge_llm.complete([
            {"role": "system", "content": "Answer exactly YES or NO. Do not explain."},
            {"role": "user", "content": "Does Python appear in this text? Text: Mira uses Rust."},
        ], max_tokens=32),
        steps,
    )
    attach_usage(steps, before, judge_llm)
    report["judge_sanity_negative_control"] = {
        "raw": negative_sanity, "verdict": judge_verdict(negative_sanity),
    }
    write_report(out, report)
    if judge_verdict(sanity) != "YES" or judge_verdict(negative_sanity) != "NO":
        report["status"] = "judge_sanity_failed"
        report["failures"].append({
            "step": "judge_sanity", "reason": "positive/negative no-thinking judge controls did not return YES/NO",
            "positive_verdict": judge_verdict(sanity), "negative_verdict": judge_verdict(negative_sanity),
        })
        report["usage"] = {"extract": usage_snapshot(extract_llm), "answer": usage_snapshot(answer_llm), "judge": usage_snapshot(judge_llm)}
        write_report(out, report)
        return 2

    embedder = OllamaEmbedder(model=args.embed_model, base_url=args.embed_base_url)
    before_embedding = time.monotonic()
    embedding_probe = run_step("embedding_probe", lambda: embedder.embed(["Smriti dimension probe"]), steps)
    if embedding_probe is not None:
        report["config"]["embedding_dimensions_observed"] = len(embedding_probe[0]) if embedding_probe else None
        steps[-1]["result"] = {"vectors": len(embedding_probe), "dimensions": report["config"]["embedding_dimensions_observed"]}
    steps[-1]["elapsed_s"] = round(time.monotonic() - before_embedding, 4)
    write_report(out, report)

    memory: Optional[Smriti] = None
    try:
        memory = run_step("construct_full_memory", lambda: Smriti(
            path=":memory:", mode="full", llm=extract_llm, embedder=embedder), steps)
        if memory is None:
            report["status"] = "construct_failed"
            write_report(out, report)
            return 2

        for index, (timestamp, content) in enumerate(UPDATES):
            def ingest(timestamp=timestamp, content=content, index=index):
                result = memory.add([{"role": "user", "content": content}],
                                    session_id="mira-update-%d" % (index + 1), timestamp=timestamp)
                return {"add_result": result,
                        "extraction_diagnostics": jsonable(memory.last_extraction_diagnostics),
                        "stats": jsonable(memory.stats())}
            before = usage_snapshot(extract_llm)
            run_step("ingest_update_%d" % (index + 1), ingest, steps)
            attach_usage(steps, before, extract_llm)
            write_report(out, report)

        facts = run_step("read_actual_facts", lambda: read_facts(memory), steps) or []
        report["facts"] = facts
        report["extraction_audit"] = {
            "normalized_predicates": [
                fact for fact in facts if fact.get("predicate") in ("lives_in", "moved_to", "relocated_to")
            ],
            "relation_review": relation_review(facts),
        }

        evidence: Dict[str, Any] = {}
        contexts: Dict[str, str] = {}
        for label, question in QUERIES.items():
            found = run_step("retrieve_%s" % label, lambda question=question: memory.search(question, k=12, now=NOW), steps) or []
            context = run_step("context_%s" % label, lambda question=question: memory.context(question, k=12, now=NOW, char_budget=9000), steps) or ""
            evidence[label] = {"question": question, "search": result_dicts(found), "context": context}
            contexts[label] = context
        report["evidence"] = evidence

        for label, question in QUERIES.items():
            source = contexts[label]
            prompt = "Question: %s\n\nEvidence:\n%s" % (question, source)
            before = usage_snapshot(answer_llm)
            answer = run_step("answer_%s" % label, lambda prompt=prompt: answer_llm.complete([
                {"role": "system", "content": "Answer only from the supplied evidence. Be concise."},
                {"role": "user", "content": prompt},
            ], max_tokens=256), steps)
            attach_usage(steps, before, answer_llm)
            report.setdefault("answers", {})[label] = {"question": question, "gold": GOLDS[label], "context": source, "answer": answer}
            judge_prompt = "Question: %s\nGold answer: %s\nHypothesis: %s\nEvidence:\n%s\nAnswer YES only if the hypothesis matches the gold answer and is supported by the evidence; otherwise answer NO. Output only YES or NO." % (question, GOLDS[label], answer or "", source)
            before = usage_snapshot(judge_llm)
            verdict_raw = run_step("judge_%s" % label, lambda judge_prompt=judge_prompt: judge_llm.complete([
                {"role": "system", "content": "Evaluate the hypothesis against the gold answer. Output exactly YES or NO."},
                {"role": "user", "content": judge_prompt},
            ], max_tokens=64), steps)
            attach_usage(steps, before, judge_llm)
            report["answers"][label]["judge_raw"] = verdict_raw
            report["answers"][label]["judge_verdict"] = judge_verdict(verdict_raw)

        current_source = evidence.get("current_rust_atlas", {})
        history_source = evidence.get("history_mumbai_python", {})
        active_preferences = active_preference_facts(facts)
        active_language_preferences = active_language_preference_facts(facts)
        current_rust_state_facts = [fact for fact in facts if language_preference_matches(
            fact, "rust", NOW, ATLAS_SCOPE, subject=MIRA_SUBJECT)]
        january_python_facts = [fact for fact in facts if language_preference_matches(
            fact, "python", HISTORY_POINT, subject=MIRA_SUBJECT)]
        atlas_python_preference_facts = [fact for fact in facts if language_preference_matches(
            fact, "python", scope=ATLAS_SCOPE, subject=MIRA_SUBJECT)]
        inferred_primary_python_facts = [fact for fact in facts if
                                         str(fact.get("subject", "")).strip().casefold() == MIRA_SUBJECT.casefold()
                                         and str(fact.get("predicate", "")).strip().casefold() == "primary_programming_language"
                                         and str(fact.get("object", "")).strip().casefold() == "python"]
        current_atlas_facts = [fact for fact in facts if structured_fact_matches(
            fact, ("atlas",), NOW) and str(fact.get("subject", "")).strip().casefold() == MIRA_SUBJECT.casefold()]
        current_berlin_facts = [fact for fact in facts if structured_fact_matches(fact, ("berlin",), NOW)
                                and str(fact.get("predicate", "")).lower() in ("lives_in", "located_in", "current_city")
                                and str(fact.get("subject", "")).strip().casefold() == MIRA_SUBJECT.casefold()]
        latest_python = max(atlas_python_preference_facts,
                            key=lambda fact: str(fact.get("valid_from") or ""),
                            default=None)
        prior_python_ended = not atlas_python_preference_facts or (
            not any(interval_contains(fact, NOW) for fact in atlas_python_preference_facts)
            and latest_python.get("invalid_at") is not None
            and same_calendar_day(latest_python["invalid_at"], SWITCH_POINT)
        )
        identity_scope_assertions = {
            "aurora_event_keeps_mira_subject": any(raw_fact_matches(
                fact, predicate="worked_on", object_terms=("aurora",),
                event_date="2024-01-10") and scope_is_not_date(fact)
                for fact in facts),
            "aurora_date_is_not_applicability_scope": any(raw_fact_matches(
                fact, predicate="worked_on", object_terms=("aurora",),
                event_date="2024-01-10") and scope_is_not_date(fact)
                for fact in facts),
            "berlin_event_keeps_mira_subject": any(raw_fact_matches(
                fact, predicate="lives_in", object_terms=("berlin",), scope="", event_date="2024-06-15")
                for fact in facts),
            "atlas_project_event_keeps_mira_subject": any(
                raw_fact_matches(fact, object_terms=("atlas",), scope="", event_date="2024-06-15")
                and is_project_membership_predicate(fact.get("predicate"))
                for fact in facts),
            "atlas_language_state_keeps_mira_subject": bool(current_rust_state_facts),
            "atlas_transition_keeps_mira_subject": any(raw_fact_matches(
                fact, predicate="switched_from", object_terms=("python",), scope=ATLAS_SCOPE)
                for fact in facts),
            "adjacent_theme_does_not_inherit_atlas_scope": any(
                raw_fact_matches(fact, object_terms=("light",), scope="")
                and str(fact.get("predicate", "")).strip().lower() in ("prefers", "prefers_theme")
                for fact in facts),
        }
        report["temporal_fact_review"] = {
            "current_rust_state_facts": current_rust_state_facts,
            "current_atlas_facts": current_atlas_facts,
            "current_berlin_facts": current_berlin_facts,
            "january_python_facts": january_python_facts,
            "atlas_python_preference_facts": atlas_python_preference_facts,
            "inferred_primary_python_facts": inferred_primary_python_facts,
            "prior_python_preference_ended_before_now": prior_python_ended,
            "python_preference_end_dates": [fact.get("invalid_at") for fact in atlas_python_preference_facts],
            "latest_python_preference": latest_python,
            "active_preference_facts": active_preferences,
            "active_language_preference_facts": active_language_preferences,
            "competing_active_preference_objects": sorted({value for value in (language_preference_value(fact) for fact in active_language_preferences if str(fact.get("scope", "")) == ATLAS_SCOPE) if value}),
            "ambiguity_note": "Preference replacement is evaluated only within the explicit project:Atlas scope. Global Python may remain valid alongside Atlas-scoped Rust; competing values within that scope remain unresolved and prevent an OK status.",
        }
        report["identity_scope_review"] = {
            "expected_named_subject": MIRA_SUBJECT,
            "observed_subjects": sorted({str(fact.get("subject", "")) for fact in facts}),
            "assertions": identity_scope_assertions,
        }
        judge_verdicts = {
            label: report.get("answers", {}).get(label, {}).get("judge_verdict")
            for label in QUERIES
        }
        report["assertions"] = {
            "current_fact_contains_rust": bool(current_rust_state_facts),
            "current_fact_contains_atlas": bool(current_atlas_facts),
            "history_fact_contains_mumbai": has_terms(facts, ("mumbai",)),
            "history_fact_contains_python": has_terms(facts, ("python",)),
            "current_rust_preference_object_interval": bool(current_rust_state_facts),
            "prior_python_preference_ended_before_now": prior_python_ended,
            "current_rust_atlas_structured_interval": bool(current_rust_state_facts and current_atlas_facts),
            "january_python_structured_interval": bool(january_python_facts),
            "current_berlin_structured_interval": bool(current_berlin_facts),
            "no_competing_active_preferences": len(report["temporal_fact_review"]["competing_active_preference_objects"]) <= 1,
            "current_source_contains_rust": has_terms(current_source, ("rust",)),
            "current_source_contains_atlas": has_terms(current_source, ("atlas",)),
            "history_source_contains_mumbai": has_terms(history_source, ("mumbai",)),
            "history_source_contains_python": has_terms(history_source, ("python",)),
            "judge_sanity_yes": report["judge_sanity"]["verdict"] == "YES",
            "judge_sanity_negative_no": report["judge_sanity_negative_control"]["verdict"] == "NO",
            "current_answer_judge_yes": judge_verdicts.get("current_rust_atlas") == "YES",
            "history_answer_judge_yes": judge_verdicts.get("history_mumbai_python") == "YES",
            "no_primary_language_inferred_from_preference": not inferred_primary_python_facts,
            **identity_scope_assertions,
        }
    except Exception as exc:
        report["failures"].append({"step": "workflow", "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()})
    finally:
        if memory is not None:
            run_step("cleanup_close", memory.close, steps)
        report["usage"] = {"extract": usage_snapshot(extract_llm), "answer": usage_snapshot(answer_llm), "judge": usage_snapshot(judge_llm)}
        report["failures"].extend({
            "step": step.get("name"), "error_type": step.get("error_type"),
            "error": step.get("error"), "traceback": step.get("traceback")
        } for step in steps if not step.get("ok"))
        expected = report["assertions"]
        report["status"] = "ok" if expected and all(expected.values()) and not report["failures"] else "completed_with_failures"
        write_report(out, report)
    return 0 if report["status"] == "ok" else 2


def write_report(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(jsonable(report), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
