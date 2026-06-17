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
- If a fact has an explicit date/time attached (e.g. "I ran the marathon on 12 March 2024"), set event_date in ISO format (YYYY-MM-DD). Resolve relative dates ("last Tuesday", "next month") against the session timestamp. Otherwise null.
- subject/predicate/object: a normalized triple, subject is usually "user". predicate is a short snake_case relation (e.g. lives_in, works_at, prefers, owns, plans_to).
- entities: proper nouns and key concrete nouns in the fact.
- kind: one of profile | preference | event | knowledge.
- Skip chit-chat, pleasantries, and information with no future value.
- Output ONLY a JSON array. If nothing is worth remembering, output [].

Format:
[{"statement": "...", "subject": "user", "predicate": "lives_in", "object": "Hyderabad", "entities": ["Hyderabad"], "event_date": null, "kind": "profile"}]"""


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
- Output ONLY the summary text, no preamble."""


def build_observation_prompt(label: str, facts: List[Fact]) -> List[dict]:
    lines = [f"Subject: {label}", "Known facts:"]
    for f in facts:
        lines.append(f"- {f.statement}")
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


def parse_facts(raw: str, session_id: Optional[str], session_ts: Optional[str]) -> List[Fact]:
    data = extract_json(raw)
    if not isinstance(data, list):
        return []
    facts = []
    for item in data:
        if not isinstance(item, dict) or not item.get("statement"):
            continue
        facts.append(Fact(
            id=None,
            statement=str(item["statement"]).strip(),
            subject=str(item.get("subject", "user")),
            predicate=str(item.get("predicate", "")),
            object=str(item.get("object", "")),
            kind=str(item.get("kind", "knowledge")),
            entities=[str(e) for e in item.get("entities", []) if e],
            event_date=item.get("event_date") or None,
            valid_from=item.get("event_date") or session_ts,
            session_id=session_id,
        ))
    return facts
