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
from typing import List, Optional

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
- For an explicitly singular state, use the category predicate when the text
  establishes it: `primary_programming_language` for a stated primary language
  and `preferred_theme` for a stated theme. Do not infer either category from
  vague liking or from an unrelated transition; retain the stated generic
  predicate/event instead. When an explicit switch states a resulting state
  and its applicability context, emit that resulting state with the category
  predicate and scope, and retain a separate transition event when useful.
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
