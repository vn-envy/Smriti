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

from typing import List, Optional, Tuple

from .llm import extract_json
from .store import Store
from .types import Fact

# predicates where only one value can be true at a time
SINGLE_VALUED = {
    "lives_in", "works_at", "employed_by", "married_to", "named", "aged",
    "weighs", "earns", "studies_at", "drives", "located_in", "job_title",
    "favorite", "favourite", "uses_phone", "current_city", "current_job",
}

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
    existing = store.similar_valid_facts(fact.subject, fact.predicate)
    return [e for e in existing if e.object.strip().lower() != fact.object.strip().lower()]


def llm_arbitrate(llm, fact: Fact, candidates: List[Fact]) -> Tuple[str, Optional[int]]:
    lines = [f"NEW FACT: {fact.statement}"]
    lines.append("EXISTING FACTS:")
    for c in candidates:
        lines.append(f"  id={c.id}: {c.statement} (since {c.valid_from})")
    raw = llm.complete(
        [{"role": "system", "content": ARBITER_SYSTEM},
         {"role": "user", "content": "\n".join(lines)}],
        json_mode=True, max_tokens=128,
    )
    data = extract_json(raw) or {}
    action = data.get("action", "add")
    target = data.get("target_id")
    if action == "supersede" and target is None:
        action = "add"
    return action, target


def consolidate(store: Store, fact: Fact, emb, embedder=None, llm=None,
                sim_threshold: float = 0.72) -> Optional[int]:
    """Insert a fact with conflict resolution. Returns new fact id (or None if skipped)."""
    # tier 1: key collision, free
    conflicts = heuristic_conflicts(store, fact)
    if conflicts:
        new_id = store.add_fact(fact, emb)
        for old in conflicts:
            store.invalidate_fact(old.id, new_id, invalid_at=fact.valid_from)
        return new_id

    # exact duplicate guard
    for e in store.similar_valid_facts(fact.subject, fact.predicate):
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
            if f and f.invalid_at is None:
                candidates.append(f)
        if candidates:
            action, target = llm_arbitrate(llm, fact, candidates)
            if action == "skip":
                return None
            if action == "supersede":
                new_id = store.add_fact(fact, emb)
                old = store.get_fact(int(target)) if target else None
                if old and old.invalid_at is None:
                    store.invalidate_fact(old.id, new_id, invalid_at=fact.valid_from)
                return new_id

    return store.add_fact(fact, emb)
