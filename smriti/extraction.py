"""Write-time fact extraction — *grahana* (ग्रहण, "grasping").

The stage where raw experience (anubhava) is grasped into durable
impressions (samskara).

Design choice (token efficiency learned from the field): one extraction
call per *session*, not per turn. Facts are atomic, entity-tagged, and
carry explicit event dates where stated, which is what makes the
bi-temporal store and the temporal retrieval channel work.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .llm import extract_json
from .types import Fact

# --- numeric/sum aggregation (Build 8) -------------------------------------
# Enumeration digests fix COUNT questions; SUM questions ("how much total money /
# how many total hours") need actual arithmetic, which LLMs do unreliably. So we
# extract quantities deterministically and let Python add them up, then hand the
# model a trustworthy pre-computed total alongside the components.
_CURRENCY_RE = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")
_UNIT_RE = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*"
    r"(hours?|hrs?|days?|minutes?|mins?|miles?|kilometers?|km|weeks?|months?|years?|dollars?|usd)\b",
    re.IGNORECASE,
)
_UNIT_CANON = {
    "hour": "hours", "hr": "hours", "hrs": "hours", "hours": "hours",
    "day": "days", "days": "days",
    "minute": "minutes", "min": "minutes", "mins": "minutes", "minutes": "minutes",
    "mile": "miles", "miles": "miles", "kilometer": "km", "kilometers": "km", "km": "km",
    "week": "weeks", "weeks": "weeks", "month": "months", "months": "months",
    "year": "years", "years": "years", "dollar": "$", "dollars": "$", "usd": "$",
}


def compute_numeric_totals(facts: List[Fact]) -> str:
    """Sum same-unit quantities across facts; return a verifiable totals string.

    Groups by unit (currency, hours, days, …) so mixed units are never added
    together, and only reports a unit with >= 2 values. Empty string if nothing
    to total."""
    buckets = defaultdict(list)
    for f in facts:
        text = f.statement or ""
        for m in _CURRENCY_RE.finditer(text):
            buckets["$"].append(float(m.group(1).replace(",", "")))
        for m in _UNIT_RE.finditer(text):
            tok = m.group(2).lower()
            unit = _UNIT_CANON.get(tok.rstrip("s")) or _UNIT_CANON.get(tok)
            if unit:
                buckets[unit].append(float(m.group(1).replace(",", "")))
    parts = []
    for unit, vals in buckets.items():
        if len(vals) < 2:
            continue
        total = sum(vals)
        comp = " + ".join(f"{v:g}" for v in vals)
        disp = f"${total:g}" if unit == "$" else f"{total:g} {unit}"
        parts.append(f"{disp} ({comp})")
    return ("Computed totals (verify against facts) — " + "; ".join(parts) + ".") if parts else ""

EXTRACT_SYSTEM = """You are a memory extraction engine for an AI assistant.
Given a conversation session (with its timestamp), extract durable, atomic facts worth remembering long-term about the user, their world, and important things the assistant said or produced.

Rules:
- One fact per item, self-contained ("The user's sister Riya lives in Pune", not "she lives there").
- Include facts stated by the USER and substantive information the ASSISTANT provided that the user may rely on later.
- Capture preferences, profile details, events, plans, relationships, and decisions.
- Preserve the identity of the fact's subject. Use `user` only for a first-person
  self-reference (I/me/my) or an explicitly identified user fact. If the text
  names Mira, a team, or another third party, keep that named entity as the
  subject in both the statement and the structured triple; never rewrite it as
  `user` merely because it came from the user's session.
- For an explicit switch from X to Y in a stated domain/context, emit the
  resulting current-usage state for Y as its own fact and retain the historical
  transition from X as a separate event. This is factual usage, not a
  subjective preference. Preserve the relation and scope stated by the user;
  do not infer a preference merely from "uses" or "switched to", and do not
  assign a scope to an adjacent clause unless that clause is explicitly
  governed by the same context.
- If a fact has an explicit date/time attached (e.g. "I ran the marathon on 12 March 2024"), set event_date in ISO format (YYYY-MM-DD). Resolve relative dates ("last Tuesday", "next month") against the session timestamp. Otherwise null.
- subject/predicate/object: a normalized triple. Keep the named subject when
  the text identifies one; use `user` only under the identity rule above.
  predicate is a short snake_case relation (e.g. lives_in, works_at, prefers,
  owns, plans_to).
- scope: optional explicit applicability context such as "project:Atlas";
  leave it empty when the fact is global or the context is not established.
- Dates and time ranges are temporal fields, not applicability scope: put an
  explicit date in `event_date`/`valid_from` and do not encode it as `scope`.
  Apply a scope only to the clause that explicitly establishes that context;
  an adjacent preference or fact does not inherit a project scope by proximity.
- Do not upgrade a generic preference or usage fact into a primary-state fact:
  use `primary_programming_language` only when the source explicitly says
  primary, main, or default. Use `preferred_programming_language` when the
  source explicitly states a preference, and use a factual usage predicate
  such as `uses_language` or `uses_tool` for actual usage. Apply the same
  rule to other categories: `preferred_theme` requires an explicit theme
  preference. For an explicit switch, emit the factual destination usage with
  its stated scope and retain the historical transition; do not label it a
  primary state or preference unless the source does so.
- entities: proper nouns and key concrete nouns in the fact.
- search_keys: 2-5 alternate search terms a person might use to find this fact that are NOT already in the statement — category words, synonyms, or hypernyms (e.g. for "lime" include "citrus", "fruit"; for "gallery opening" include "art", "event"; for a doctor visit include "doctor", "appointment", "health"). This widens recall for aggregation/category questions.
- kind: one of profile | preference | event | knowledge.
- Skip chit-chat, pleasantries, and information with no future value.
- Output ONLY a JSON array. If nothing is worth remembering, output [].

Format (for a source transition such as "The Redwood team switched from ToolA to ToolB for project Cedar"):
[
  {
    "statement": "The Redwood team currently uses ToolB for project Cedar",
    "subject": "Redwood team", "predicate": "uses_tool", "object": "ToolB",
    "scope": "project:Cedar", "entities": ["Redwood", "Cedar", "ToolB"],
    "search_keys": ["tool", "current"], "event_date": null, "kind": "knowledge"
  },
  {
    "statement": "The Redwood team switched from ToolA to ToolB for project Cedar",
    "subject": "Redwood team", "predicate": "switched_from", "object": "ToolA",
    "scope": "project:Cedar", "entities": ["Redwood", "Cedar", "ToolA", "ToolB"],
    "search_keys": ["transition", "previous tool"], "event_date": null, "kind": "event"
  }
]"""


def build_extraction_prompt(turns: List[dict], session_ts: Optional[str]) -> List[dict]:
    lines = [f"Session timestamp: {session_ts or 'unknown'}", "---"]
    for t in turns:
        lines.append(f"{t.get('role', 'user').upper()}: {t.get('content', '')}")
    return [
        {"role": "system", "content": EXTRACT_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


_SCOPE_KIND_MARKERS = {
    "project": ("project",),
    "workspace": ("workspace",),
    "team": ("team",),
    "account": ("account",),
    "organization": ("organization", "organisation", "org"),
    # Location scopes are often expressed with a preposition rather than the
    # literal word "location" ("worked in Mumbai", "based at Pune").
    "location": ("location", "city", "in", "at", "from"),
}


def _scope_text(value: Any) -> str:
    """Normalize only presentation differences for scope evidence matching."""
    text = " ".join(str(value or "").casefold().split())
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'“”‘’":
        text = text[1:-1].strip()
    return text


def _scope_value_pattern(value: str) -> re.Pattern[str]:
    # Word boundaries prevent Ceder from matching Cedar and Cedar from
    # matching Cedarwood while still supporting quoted/multiword values.
    return re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", re.IGNORECASE)


def _scope_kind_markers(kind: str) -> Tuple[str, ...]:
    normalized = _scope_text(kind).replace("_", " ")
    markers = _SCOPE_KIND_MARKERS.get(normalized)
    if markers:
        return markers
    return (normalized,) if normalized else ()


def _scope_evidenced(scope: str, source: str, statement: str) -> Tuple[bool, str]:
    """Check an explicitly formatted scope against source and fact text.

    This intentionally uses bounded lexical evidence rather than a general NER
    or fuzzy spelling pipeline.  The identifier value must occur in both the
    source and returned statement; an applicability marker must occur near the
    value on both sides when the scope is nonempty.
    """
    if not isinstance(scope, str) or not scope.strip():
        return True, ""
    raw = scope.strip()
    if ":" not in raw:
        return False, "scope must use kind:value form"
    kind, value = raw.split(":", 1)
    kind = _scope_text(kind)
    value = _scope_text(value)
    if not kind or not value:
        return False, "scope kind and value must be non-empty"
    if kind == "date":
        return False, "dates belong in event_date/validity fields, not scope"
    value_pattern = _scope_value_pattern(value)
    marker_patterns = [_scope_value_pattern(marker) for marker in _scope_kind_markers(kind)]

    def text_supports(text: str) -> Tuple[bool, bool]:
        normalized = _scope_text(text)
        value_match = value_pattern.search(normalized)
        if value_match is None:
            return False, False
        # Keep the relation bounded to local proximity. This supports "for
        # project Cedar" and "Cedar project" without claiming to solve full
        # clause semantics or coreference.
        value_matches = value_pattern.finditer(normalized)
        for candidate_value in value_matches:
            for marker_pattern in marker_patterns:
                for marker_match in marker_pattern.finditer(normalized):
                    if abs(marker_match.start() - candidate_value.start()) <= 80:
                        return True, True
        return True, False

    source_has_value, source_has_marker = text_supports(source)
    statement_has_value, statement_has_marker = text_supports(statement)
    if not source_has_value:
        return False, "scope kind/value is not evidenced by the source turns"
    if not statement_has_value:
        return False, "scope kind/value is not evidenced by the fact statement"
    if not source_has_marker or not statement_has_marker:
        return False, "scope kind marker is not evidenced in both source and fact statement"
    return True, ""


def validate_fact_scopes(facts: List[Fact], turns: List[dict]) -> Tuple[List[Fact], List[Dict[str, Any]]]:
    """Return facts with source-grounded scopes and diagnostics for rejects."""
    source = "\n".join(str(turn.get("content", "")) for turn in turns)
    valid: List[Fact] = []
    invalid: List[Dict[str, Any]] = []
    for fact in facts:
        ok, reason = _scope_evidenced(fact.scope, source, fact.statement)
        if ok:
            valid.append(fact)
        else:
            invalid.append({"statement": fact.statement, "scope": fact.scope,
                            "subject": fact.subject, "predicate": fact.predicate,
                            "object": fact.object, "reason": reason})
    return valid, invalid


def reject_scope_erasure_retry(facts: List[Fact], rejected: List[Dict[str, Any]]) -> Tuple[List[Fact], List[Dict[str, Any]]]:
    """Block a correction that silently turns a rejected scope into global."""
    rejected_keys = {
        (str(item.get("subject", "")).casefold().strip(),
         str(item.get("predicate", "")).casefold().strip(),
         str(item.get("object", "")).casefold().strip())
        for item in rejected if str(item.get("scope", "")).strip()
    }
    valid: List[Fact] = []
    blocked: List[Dict[str, Any]] = []
    for fact in facts:
        key = (fact.subject.casefold().strip(), fact.predicate.casefold().strip(),
               fact.object.casefold().strip())
        if not fact.scope.strip() and key in rejected_keys:
            blocked.append({"statement": fact.statement, "scope": fact.scope,
                            "subject": fact.subject, "predicate": fact.predicate,
                            "object": fact.object,
                            "reason": "retry erased scope from an originally rejected candidate; refusing to globalize it"})
        else:
            valid.append(fact)
    return valid, blocked


def merge_scope_valid_facts(first: List[Fact], replacement: List[Fact]) -> List[Fact]:
    """Retain validated first facts that a corrective response omitted.

    Only an exact fact identity is deduplicated. Distinct objects in a
    multivalued relation (for example Python and tea preferences) remain
    available if a corrective response omits one. Invalid scoped facts never
    enter this merge.
    """
    replacement_keys = {
        (fact.subject.casefold().strip(), fact.predicate.casefold().strip(),
         fact.object.casefold().strip(), fact.scope.strip(),
         fact.statement.casefold().strip(), fact.event_date or "")
        for fact in replacement
    }
    retained = [fact for fact in first if (
        fact.subject.casefold().strip(), fact.predicate.casefold().strip(),
        fact.object.casefold().strip(), fact.scope.strip(),
        fact.statement.casefold().strip(), fact.event_date or ""
    ) not in replacement_keys]
    return retained + replacement


def build_scope_correction_prompt(turns: List[dict], session_ts: Optional[str],
                                  invalid: List[Dict[str, Any]]) -> List[dict]:
    """Ask for one complete replacement extraction after scope validation."""
    prompts = build_extraction_prompt(turns, session_ts)
    rejected = "\n".join(
        f"- scope={item.get('scope')!r}; statement={item.get('statement')!r}; reason={item.get('reason')}"
        for item in invalid
    )
    prompts[1]["content"] += (
        "\n\nSCOPE VALIDATION FEEDBACK:\n"
        "The previous JSON contained applicability scopes that were not copied "
        "exactly from the source clause and fact statement. Return a complete "
        "replacement JSON array. Preserve valid facts, use only explicitly "
        "evidenced kind:value scopes, keep dates in event_date/validity fields, "
        "and leave scope empty when applicability is not explicit. Do not guess, "
        "spell-correct, or move a scope to a neighboring fact.\n"
        + rejected
    )
    return prompts


OBSERVATION_SYSTEM = """You synthesize a concise, objective profile of an entity from a list of known facts about it.

Rules:
- Produce a short overview capturing the salient, durable properties: roles, attributes, and relationships.
- If the facts describe several instances of the same kind of thing (e.g. multiple trips, purchases, or events), ENUMERATE every instance explicitly so a reader can count them — e.g. "events: A, B, C" — rather than only asserting a total. State a number only alongside the explicit list, and only if you are listing every instance.
- Do not guess or round. If you are unsure whether the list is complete, list what is supported and do not assert a total.
- Be objective and preference-neutral. Use ONLY what the facts support; invent nothing.
- Applicability scope is part of each fact's meaning. Preserve a scoped fact's
  scope in the summary (for example, say "for project:Atlas"), and never
  rewrite it as a global or unscoped property.
- Keep otherwise similar facts with different scopes distinct. Treat an
  explicitly unscoped fact as global only when the fact itself supports that
  interpretation; never infer a scope for a neighboring fact.
- Output ONLY the summary text, no preamble."""


def build_observation_prompt(label: str, facts: List[Fact]) -> List[dict]:
    lines = [f"Subject: {label}", "Known facts:"]
    for f in facts:
        scope = f.scope.strip() if isinstance(f.scope, str) and f.scope.strip() else "<unscoped/global>"
        valid_from = f.valid_from or "unknown"
        invalid_at = f.invalid_at or "present"
        lines.append(
            f"- {f.statement} [scope={scope}; subject={f.subject}; "
            f"predicate={f.predicate}; object={f.object}; "
            f"valid_from={valid_from}; invalid_at={invalid_at}]"
        )
    return [
        {"role": "system", "content": OBSERVATION_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
    ]


FOLLOWUP_SYSTEM = """You help a memory system answer a multi-hop question by deciding what to look up next.
Given the QUESTION and the NOTES retrieved so far:
- If the notes already contain everything needed to answer, reply with exactly: NONE
- Otherwise reply with a SINGLE short search query (no explanation, no quotes) for the missing piece — typically a bridging entity, date, or fact the question still needs."""


def build_followup_prompt(question: str, notes: str) -> List[dict]:
    return [
        {"role": "system", "content": FOLLOWUP_SYSTEM},
        {"role": "user",
         "content": f"QUESTION: {question}\n\nNOTES:\n{notes}\n\nNext search query or NONE:"},
    ]


_PREDICATE_ALIASES = {
    "moved_to": "lives_in",
    "relocated_to": "lives_in",
    # LLMs sometimes emit the inflected adjective/verb for the same
    # preference relation. Keep single-valued preference consolidation on one
    # canonical key instead of allowing ``preferred`` and ``prefers`` to
    # coexist as independent current values.
    "preferred": "prefers",
    "prefer": "prefers",
}


def parse_facts(raw: str, session_id: Optional[str], session_ts: Optional[str],
                diagnostics: Optional[dict] = None) -> List[Fact]:
    data = extract_json(raw)
    if diagnostics is not None:
        diagnostics.update(raw_chars=len(raw or ""), status="ok", items=0,
                           accepted=0, skipped=0, normalized_predicates=0)
    if not isinstance(data, list):
        if diagnostics is not None:
            diagnostics["status"] = "malformed" if data is None else "wrong_shape"
        return []
    if diagnostics is not None:
        diagnostics["items"] = len(data)
    facts = []
    for item in data:
        if not isinstance(item, dict) or not item.get("statement"):
            if diagnostics is not None:
                diagnostics["skipped"] += 1
            continue
        entities = item.get("entities") or []
        keys = item.get("search_keys") or []
        if not isinstance(entities, list) or not isinstance(keys, list):
            if diagnostics is not None:
                diagnostics["skipped"] += 1
            continue
        raw_scope = item.get("scope", "")
        if raw_scope is None:
            raw_scope = ""
        if not isinstance(raw_scope, str):
            if diagnostics is not None:
                diagnostics["skipped"] += 1
            continue
        predicate = str(item.get("predicate", "")).lower().strip()
        normalized = _PREDICATE_ALIASES.get(predicate, predicate)
        if diagnostics is not None and normalized != predicate:
            diagnostics["normalized_predicates"] += 1
        facts.append(Fact(
            id=None,
            statement=str(item["statement"]).strip(),
            subject=str(item.get("subject", "user")),
            predicate=normalized,
            object=str(item.get("object", "")),
            kind=str(item.get("kind", "knowledge")),
            entities=[str(e) for e in entities if e],
            search_keys=[str(k) for k in keys if k],
            event_date=item.get("event_date") or None,
            valid_from=item.get("event_date") or session_ts,
            session_id=session_id,
            scope=raw_scope.strip(),
        ))
    if diagnostics is not None:
        diagnostics["accepted"] = len(facts)
        if data and not facts:
            diagnostics["status"] = "all_items_rejected"
    return facts
