"""SMRITI public API.

    from smriti import Smriti
    mem = Smriti(path="memory.db")          # lite mode: no LLM needed
    mem.add([{"role": "user", "content": "I moved to Bengaluru last week"}],
            timestamp="2026-06-01T10:00:00Z")
    results = mem.search("where do I live?")
    ctx = mem.context("where do I live?")    # answer-ready packed context

Modes:
  * lite (laghu, लघु)  - episodic-only ingest + 4-channel hybrid retrieval.
            No LLM at write time, near-zero cost; surprisingly strong recall.
  * full (purna, पूर्ण) - adds single-pass fact extraction + write-time
            consolidation (supersession) using any OpenAI-compatible LLM.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from .consolidation import consolidate, heuristic_conflicts
from .embedder import HashEmbedder
from .extraction import (build_extraction_prompt, build_followup_prompt,
                         build_observation_prompt, parse_facts)
from .llm import LLM
from .retrieval import pack_context, retrieve
from .store import Store, utcnow
from .types import Episode, Fact, RetrievalResult

# Sanskrit aliases: laghu (लघु, "light") and purna (पूर्ण, "complete")
MODE_ALIASES = {"laghu": "lite", "purna": "full"}


class Smriti:
    def __init__(self, path: str = ":memory:", embedder=None, llm: Optional[LLM] = None,
                 mode: str = "auto", embed_episodes: bool = True, reranker=None):
        """mode: "full"/"purna" (LLM extraction+consolidation), "lite"/"laghu"
        (episodic only), or "auto" (full if an llm is provided, else lite).
        reranker: optional cross-encoder (any .rerank(query, docs)->scores) applied
        to fused candidates at read time."""
        self.store = Store(path)
        self.embedder = embedder or HashEmbedder()
        self.llm = llm
        self.reranker = reranker
        mode = MODE_ALIASES.get(mode, mode)
        if mode == "auto":
            mode = "full" if llm is not None else "lite"
        if mode == "full" and llm is None:
            raise ValueError("full mode requires an llm")
        self.mode = mode
        self.embed_episodes = embed_episodes

    # ------------------------------------------------------------------ add
    def add(self, messages: List[dict], session_id: Optional[str] = None,
            timestamp: Optional[str] = None) -> dict:
        """Ingest one session (a list of {role, content} turns)."""
        session_id = session_id or uuid.uuid4().hex[:12]
        timestamp = timestamp or utcnow()

        contents = [m.get("content", "")[:4000] for m in messages]
        embs = self.embedder.embed(contents) if (self.embed_episodes and contents) else [None] * len(contents)

        episode_ids = []
        for m, emb in zip(messages, embs):
            eid = self.store.add_episode(
                Episode(id=None, session_id=session_id, role=m.get("role", "user"),
                        content=m.get("content", ""), ts=m.get("timestamp", timestamp)),
                emb=emb,
            )
            episode_ids.append(eid)

        facts_added = 0
        if self.mode == "full":
            raw = self.llm.complete(
                build_extraction_prompt(messages, timestamp), json_mode=False
            )
            facts = parse_facts(raw, session_id, timestamp)
            if facts:
                fembs = self.embedder.embed([f.statement for f in facts])
                for f, femb in zip(facts, fembs):
                    f.episode_id = episode_ids[0] if episode_ids else None
                    if consolidate(self.store, f, femb, self.embedder, self.llm) is not None:
                        facts_added += 1

        return {"session_id": session_id, "episodes": len(episode_ids), "facts": facts_added}

    def add_fact(self, fact: Fact, resolve_conflicts: bool = True) -> Optional[int]:
        """Directly insert a fact (e.g. from an agent's own observations)."""
        emb = self.embedder.embed([fact.statement])[0]
        if resolve_conflicts:
            return consolidate(self.store, fact, emb, self.embedder,
                               self.llm if self.mode == "full" else None)
        return self.store.add_fact(fact, emb)

    # --------------------------------------------------------------- search
    def search(self, query: str, k: int = 12, now: Optional[str] = None) -> List[RetrievalResult]:
        return retrieve(self.store, self.embedder, query, now=now, k=k, reranker=self.reranker)

    def context(self, query: str, k: int = 12, now: Optional[str] = None,
                char_budget: int = 9000) -> str:
        return pack_context(self.search(query, k=k, now=now), now=now, char_budget=char_budget)

    def search_iterative(self, query: str, k: int = 12, now: Optional[str] = None,
                         rounds: int = 2) -> List[RetrievalResult]:
        """Multi-step retrieval for multi-hop questions (DualRAG-style).

        After the first pass, ask the LLM what's still missing, issue a
        follow-up retrieval seeded by that, and merge — so chains the single
        pass can't resolve in one shot ("my mentor's research field" needs the
        mentor, then the mentor's field) get a second look. Full mode only;
        with no llm or rounds<2 it degrades to a normal single-pass search.
        """
        results = self.search(query, k=k, now=now)
        if self.llm is None or rounds < 2:
            return results
        seen = {(r.kind, r.id) for r in results}
        for _ in range(rounds - 1):
            notes = pack_context(results, now=now)
            follow = self.llm.complete(
                build_followup_prompt(query, notes), max_tokens=64
            ).strip()
            if not follow or follow.upper().startswith("NONE"):
                break
            for r in retrieve(self.store, self.embedder, follow, now=now, k=k,
                              reranker=self.reranker):
                if (r.kind, r.id) not in seen:
                    seen.add((r.kind, r.id))
                    results.append(r)
        return results

    def context_iterative(self, query: str, k: int = 12, now: Optional[str] = None,
                          char_budget: int = 9000, rounds: int = 2) -> str:
        return pack_context(self.search_iterative(query, k=k, now=now, rounds=rounds),
                            now=now, char_budget=char_budget)

    # -------------------------------------------------------- observations
    def _write_observation(self, subject: str, predicate: str, label: str,
                           facts: List[Fact]) -> bool:
        """Synthesize one observation/digest fact from `facts`, superseding any
        prior one with the same (subject, predicate). Returns True if written."""
        summary = self.llm.complete(
            build_observation_prompt(label, facts), max_tokens=256
        ).strip()
        if not summary:
            return False
        ents = self.store.entities_of_facts([f.id for f in facts if f.id])[:10]
        obs = Fact(id=None, statement=summary, subject=subject, predicate=predicate,
                   object="", kind="observation", entities=ents, valid_from=utcnow())
        emb = self.embedder.embed([summary])[0]
        prior = self.store.similar_valid_facts(subject, predicate)
        new_id = self.store.add_fact(obs, emb)
        for p in prior:
            self.store.invalidate_fact(p.id, new_id)
        return True

    def refresh_observations(self, min_facts: int = 2,
                             entities: Optional[List[str]] = None,
                             granularity=("entity", "predicate")) -> dict:
        """Synthesize 'observation' summary facts at multiple granularities — the
        Hindsight observation paradigm plus MemGAS-style multi-granularity.

        Two granularities, because aggregation questions span two units:
          * entity    — "tell me about Acme" → one summary per entity.
          * predicate — "how many events did I attend / doctors did I see" →
                        one digest per (subject, predicate) that ENUMERATES every
                        object across all entities/sessions. This is the cross-
                        entity aggregation per-entity summaries structurally miss.

        Summaries sit on top of raw facts (kind='observation'), ride the existing
        channels, and supersede their prior version (full audit trail). Opt-in
        and idempotent; keeps write latency and the zero-cost default intact.
        Requires an llm.
        """
        if self.llm is None:
            raise ValueError("refresh_observations requires an llm (full mode)")
        made = {"entity": 0, "predicate": 0}

        if "entity" in granularity:
            targets = ([e.lower().strip() for e in entities]
                       if entities is not None else self.store.all_entities())
            for ent in targets:
                facts = self.store.facts_for_entity(ent, valid_only=True)
                if len(facts) >= min_facts and self._write_observation(ent, "observation", ent, facts):
                    made["entity"] += 1

        # predicate digests are global; skip when caller targets specific entities
        if "predicate" in granularity and entities is None:
            for subj, pred, _c in self.store.predicate_groups(min_facts=min_facts):
                facts = [f for f in self.store.similar_valid_facts(subj, pred)
                         if f.kind != "observation"]
                if len(facts) < min_facts:
                    continue
                label = f"{subj} — {pred.replace('_', ' ')}"
                if self._write_observation(subj, f"digest:{pred}", label, facts):
                    made["predicate"] += 1

        made["observations"] = made["entity"] + made["predicate"]
        return made

    # ---------------------------------------------------------------- misc
    def stats(self) -> dict:
        s = self.store.stats()
        s["mode"] = self.mode
        return s
