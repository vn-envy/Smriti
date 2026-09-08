"""Write-time consolidation — supersession as *badha* (बाध, "sublation").

In Vedanta, badha is the precise technical event where a later cognition
invalidates an earlier one — the rope is seen, the snake is sublated — yet
the earlier cognition is not erased from having occurred. That is exactly
what SMRITI does: invalid_at is set, superseded_by points forward, and the
old fact remains queryable history. ADD / SUPERSEDE / SKIP.

The knowledge-update failure mode in flat-store systems is that "I moved
to Bengaluru" and "I live in Hyderabad" coexist and confuse retrieval.
SMRITI resolves conflicts at write time via *supersession*: the old fact
gets an invalid_at timestamp and a pointer to its successor. Nothing is
deleted, so "where did I live before?" still answers correctly.

Two tiers, cheapest first:
  1. Heuristic: exact (subject, predicate) collision on single-valued
     predicates -> supersede the older fact. Zero LLM tokens.
  2. LLM arbitration (full mode only): when the new fact is semantically
     close to existing valid facts but not an exact key match, one small
     call decides ADD / SUPERSEDE(id) / SKIP-duplicate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Tuple

from .llm import extract_json
from .store import Store, normalize_scope
from .types import Fact

# predicates where only one value can be true at a time
SINGLE_VALUED = {
    "lives_in", "works_at", "employed_by", "married_to", "named", "aged",
    "weighs", "earns", "studies_at", "drives", "located_in", "job_title",
    "favorite", "favourite", "uses_phone", "current_city", "current_job",
    "primary_programming_language", "preferred_theme",
}

# Semantic arbitration can bridge the two explicitly equivalent employer
# labels, but it must not let a high-similarity event invalidate an unrelated
# relation. Exact-key consolidation remains authoritative; these groups only
# constrain the optional semantic tier.
SEMANTIC_PREDICATE_GROUPS = (
    # These two labels describe the same employer relation in the extraction
    # schema. Keep role/title separate: a person can have a job title and an
    # employer at the same time.
    frozenset({"employed_by", "works_at"}),
)


def _predicates_semantically_compatible(left: str, right: str) -> bool:
    left = left.lower().strip()
    right = right.lower().strip()
    if not left or not right:
        return False
    # ``prefers`` is intentionally multi-valued across domains (language,
    # theme, food, and so on); an embedding match cannot safely decide which
    # preference a new fact replaces.
    if left == "prefers" or right == "prefers":
        return False
    if left == right:
        return True
    return any(left in group and right in group for group in SEMANTIC_PREDICATE_GROUPS)

ARBITER_SYSTEM = """You manage a long-term memory store. Given a NEW fact and a list of EXISTING valid facts, decide the action:
- "add": the new fact is genuinely new information.
- "supersede": the new fact replaces/updates an existing fact (the old one is no longer current). Include "target_id".
- "skip": the new fact is a duplicate of an existing fact.
Output ONLY JSON: {"action": "add"|"supersede"|"skip", "target_id": <int or null>}"""


def heuristic_conflicts(store: Store, fact: Fact) -> List[Fact]:
    if not fact.subject or not fact.predicate:
        return []
    pred = fact.predicate.lower().strip()
    if pred not in SINGLE_VALUED and not pred.startswith("favorite"):
        return []
    existing = store.similar_valid_facts(fact.subject, fact.predicate, fact.scope)
    return [e for e in existing if e.object.strip().lower() != fact.object.strip().lower()]


def llm_arbitrate(llm, fact: Fact, candidates: List[Fact]) -> Tuple[str, Optional[int]]:
    lines = [f"NEW FACT: {fact.statement} (subject={fact.subject}; predicate={fact.predicate}; object={fact.object}; scope={fact.scope})"]
    lines.append("EXISTING FACTS:")
    for c in candidates:
        lines.append(f"  id={c.id}: {c.statement} (subject={c.subject}; predicate={c.predicate}; object={c.object}; scope={c.scope}; since {c.valid_from})")
    raw = llm.complete(
        [{"role": "system", "content": ARBITER_SYSTEM},
         {"role": "user", "content": "\n".join(lines)}],
        json_mode=True, max_tokens=128,
    )
    data = extract_json(raw) or {}
    action = data.get("action", "add")
    target = data.get("target_id")
    if action not in {"add", "supersede", "skip"}:
        return "add", None
    if action == "supersede":
        if isinstance(target, bool):
            return "add", None
        try:
            target = int(target)
        except (TypeError, ValueError):
            return "add", None
        if target not in {candidate.id for candidate in candidates}:
            return "add", None
    return action, target


def _time_key(value: Optional[str]):
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (0, parsed.timestamp())
    except (TypeError, ValueError):
        return (1, value or "")


def consolidate(store: Store, fact: Fact, emb, embedder=None, llm=None,
                sim_threshold: float = 0.72) -> Optional[int]:
    """Insert a fact with conflict resolution. Returns new fact id (or None if skipped)."""
    fact.scope = normalize_scope(fact.scope)
    # Resolve the effective event time once. This is also what Store.add_fact
    # persists, and comparing it prevents late-arriving history from replacing
    # a fact that became true later.
    fact.valid_from = fact.valid_from or fact.event_date or fact.ingested_at
    pred = fact.predicate.lower().strip()
    if fact.subject and (pred in SINGLE_VALUED or pred.startswith("favorite")):
        history = store.facts_for_key(fact.subject, fact.predicate, fact.scope)
        effective = fact.valid_from or fact.event_date or fact.ingested_at
        for old in history:
            if (old.statement.strip().lower() == fact.statement.strip().lower()
                    and (effective is None or old.valid_from == effective)):
                return None
        if history:
            new_id = store.add_fact(fact, emb)
            history.append(store.get_fact(new_id))

            history.sort(key=lambda item: (*_time_key(item.valid_from), item.id))
            for current, successor in zip(history, history[1:]):
                # Route through the store hook so EnterpriseStore can maintain
                # its independent knowledge-time withdrawal axis too.
                store.invalidate_fact(current.id, successor.id,
                                      invalid_at=successor.valid_from)
            store.set_fact_successor(history[-1].id, None)
            return new_id

    # tier 1: key collision, free
    conflicts = heuristic_conflicts(store, fact)
    if conflicts:
        new_id = store.add_fact(fact, emb)
        for old in conflicts:
            store.invalidate_fact(old.id, new_id, invalid_at=fact.valid_from)
        return new_id

    # exact duplicate guard
    for e in store.similar_valid_facts(fact.subject, fact.predicate, fact.scope):
        if e.statement.strip().lower() == fact.statement.strip().lower():
            return None

    # tier 2: semantic collision -> LLM arbitration (full mode only)
    if llm is not None and emb is not None:
        near = store.vector_search(emb, "fact", limit=3)
        candidates = []
        for fid, sim in near:
            if sim < sim_threshold:
                continue
            f = store.get_fact(fid)
            if (f and f.invalid_at is None and fact.subject.strip() and f.subject.strip()
                    and f.subject.strip().lower() == fact.subject.strip().lower()
                    and (f.scope or "") == (fact.scope or "")
                    and _predicates_semantically_compatible(f.predicate, fact.predicate)):
                candidates.append(f)
        if candidates:
            action, target = llm_arbitrate(llm, fact, candidates)
            if action == "skip":
                return None
            if action == "supersede":
                new_id = store.add_fact(fact, emb)
                old = store.get_fact(int(target)) if target else None
                if old and old.invalid_at is None:
                    new = store.get_fact(new_id)
                    if _time_key(old.valid_from) > _time_key(new.valid_from):
                        store.invalidate_fact(new_id, old.id, invalid_at=old.valid_from)
                    else:
                        store.invalidate_fact(old.id, new_id, invalid_at=new.valid_from)
                return new_id

    return store.add_fact(fact, emb)
