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
from .extraction import build_extraction_prompt, parse_facts
from .llm import LLM
from .retrieval import pack_context, retrieve
from .store import Store, utcnow
from .types import Episode, Fact, RetrievalResult

# Sanskrit aliases: laghu (लघु, "light") and purna (पूर्ण, "complete")
MODE_ALIASES = {"laghu": "lite", "purna": "full"}


class Smriti:
    def __init__(self, path: str = ":memory:", embedder=None, llm: Optional[LLM] = None,
                 mode: str = "auto", embed_episodes: bool = True):
        """mode: "full"/"purna" (LLM extraction+consolidation), "lite"/"laghu"
        (episodic only), or "auto" (full if an llm is provided, else lite)."""
        self.store = Store(path)
        self.embedder = embedder or HashEmbedder()
        self.llm = llm
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
        return retrieve(self.store, self.embedder, query, now=now, k=k)

    def context(self, query: str, k: int = 12, now: Optional[str] = None,
                char_budget: int = 9000) -> str:
        return pack_context(self.search(query, k=k, now=now), now=now, char_budget=char_budget)

    # ---------------------------------------------------------------- misc
    def stats(self) -> dict:
        s = self.store.stats()
        s["mode"] = self.mode
        return s
