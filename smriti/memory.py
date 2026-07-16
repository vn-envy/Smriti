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

import hashlib
import json as _json
import re as _re
import uuid
from typing import List, Optional

# Secret redaction (opt-in, hardening 0.3.0): scrub common credential shapes
# BEFORE anything is persisted or sent to an extraction model. Conservative
# patterns — high precision over recall; this is a seatbelt, not a DLP system.
_REDACT_PATTERNS = [
    _re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),                      # OpenAI-style
    _re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),                 # GitHub tokens
    _re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                           # AWS access key
    _re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),               # Slack tokens
    _re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*"),        # bearer headers
    _re.compile(r"(?i)\b(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*\S{6,}"),
]


def redact_secrets(text: str) -> str:
    for pat in _REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text

from .consolidation import consolidate, heuristic_conflicts
from .embedder import HashEmbedder
from .extraction import (build_extraction_prompt, build_followup_prompt,
                         build_observation_prompt, compute_numeric_totals, parse_facts)
from .llm import LLM
from .profiles import RetrievalProfile, get_profile
from .retrieval import is_aggregation_query, pack_context, retrieve
from .store import Store, utcnow
from .types import Episode, Fact, RetrievalResult

# Sanskrit aliases: laghu (लघु, "light") and purna (पूर्ण, "complete")
MODE_ALIASES = {"laghu": "lite", "purna": "full"}


class Smriti:
    def __init__(self, path: str = ":memory:", embedder=None, llm: Optional[LLM] = None,
                 mode: str = "auto", embed_episodes: bool = True, reranker=None,
                 expand_keys: bool = True, aggregate: bool = True, k_agg: int = 40,
                 stem: bool = False, semantic_entities: bool = False,
                 semantic_threshold: float = 0.3,
                 redact: bool = False, dedupe: bool = True):
        """mode: "full"/"purna" (LLM extraction+consolidation), "lite"/"laghu"
        (episodic only), or "auto" (full if an llm is provided, else lite).
        reranker: optional cross-encoder (any .rerank(query, docs)->scores) applied
        to fused candidates at read time.
        expand_keys: index fact-augmented search keys for recall (Build 9 Part A).
        aggregate: use a high-recall, enumerate-and-count read path on aggregation
        queries (Build 9 Part B); non-aggregation queries are unaffected.
        k_agg: retrieval depth for the aggregation path.
        stem: FTS5 Porter stemmer so conjugation variants match
        ('attend' <-> 'attending') — the keyword-normalization lever mem0
        credits. Zero-dependency (built into SQLite). Default off (A/B-able).
        semantic_entities: cosine-match query embeddings against entity-NAME
        embeddings to reach entities lexical token matching misses (mem0's
        'entity linking' lever). Zero-dependency; uses the existing embedder.
        semantic_threshold: cosine cutoff for the semantic-entity channel."""
        self.store = Store(path, stem=stem)
        self.embedder = embedder or HashEmbedder()
        self.llm = llm
        self.reranker = reranker
        self.expand_keys = expand_keys
        self.aggregate = aggregate
        self.k_agg = k_agg
        self.stem = stem
        self.semantic_entities = semantic_entities
        self.semantic_threshold = semantic_threshold
        # hardening (0.3.0): redact scrubs credential-shaped strings before
        # persistence/extraction (opt-in); dedupe makes ingestion idempotent —
        # replaying an identical (messages, timestamp, session) is a no-op.
        self.redact = redact
        self.dedupe = dedupe
        mode = MODE_ALIASES.get(mode, mode)
        if mode == "auto":
            mode = "full" if llm is not None else "lite"
        if mode == "full" and llm is None:
            raise ValueError("full mode requires an llm")
        self.mode = mode
        self.embed_episodes = embed_episodes

    # ------------------------------------------------------------------ add
    def add(self, messages: List[dict], session_id: Optional[str] = None,
            timestamp: Optional[str] = None, dedupe: Optional[bool] = None) -> dict:
        """Ingest one session (a list of {role, content} turns).

        Idempotent by default: the (messages, timestamp, session_id) triple is
        hashed and a replay returns {"deduped": True} without writing — the
        protection against double-ingested sessions. Pass dedupe=False to
        force a re-ingest."""
        session_id = session_id or uuid.uuid4().hex[:12]
        timestamp = timestamp or utcnow()

        if self.redact:
            messages = [{**m, "content": redact_secrets(m.get("content", ""))}
                        for m in messages]

        dedupe = self.dedupe if dedupe is None else dedupe
        ihash = hashlib.sha256(_json.dumps(
            [[m.get("role", "user"), m.get("content", "")] for m in messages]
            + [timestamp, session_id], ensure_ascii=False).encode()).hexdigest()
        if dedupe:
            prior = self.store.seen_ingest(ihash)
            if prior is not None:  # cheap fast path before any embedding cost
                return {"session_id": prior, "episodes": 0, "facts": 0, "deduped": True}

        # -- expensive, side-effect-free work happens BEFORE the transaction --
        contents = [m.get("content", "")[:4000] for m in messages]
        embs = self.embedder.embed(contents) if (self.embed_episodes and contents) else [None] * len(contents)
        facts, fembs = [], []
        if self.mode == "full":
            raw = self.llm.complete(
                build_extraction_prompt(messages, timestamp), json_mode=False
            )
            facts = parse_facts(raw, session_id, timestamp)
            if facts:
                if not self.expand_keys:
                    for f in facts:
                        f.search_keys = []
                # embed the clean statement only; expansion keys live in the
                # separate key index (Build 10) so they can't dilute precision.
                fembs = self.embedder.embed([f.statement for f in facts])

        # -- atomic ingest: hash claim + all writes commit or roll back as one.
        # Two concurrent ingests serialize on BEGIN IMMEDIATE; the loser's
        # claim fails and it exits as deduped. A crash before COMMIT leaves
        # nothing — no partial session, and the retry re-ingests cleanly.
        # (Tier-2 semantic arbitration can still call the LLM inside the
        # transaction; it's rare and the single-writer lock makes it safe.)
        self.store.begin()
        try:
            if dedupe and not self.store.log_ingest_claim(ihash, session_id):
                self.store.rollback()
                prior = self.store.seen_ingest(ihash)
                return {"session_id": prior or session_id, "episodes": 0,
                        "facts": 0, "deduped": True}
            episode_ids = []
            for m, emb in zip(messages, embs):
                eid = self.store.add_episode(
                    Episode(id=None, session_id=session_id, role=m.get("role", "user"),
                            content=m.get("content", ""), ts=m.get("timestamp", timestamp)),
                    emb=emb,
                )
                episode_ids.append(eid)
            facts_added = 0
            for f, femb in zip(facts, fembs):
                f.episode_id = episode_ids[0] if episode_ids else None
                if consolidate(self.store, f, femb, self.embedder, self.llm) is not None:
                    facts_added += 1
            self.store.commit()
        except BaseException:
            self.store.rollback()
            raise
        return {"session_id": session_id, "episodes": len(episode_ids), "facts": facts_added}

    @staticmethod
    def _index_text(fact: Fact) -> str:
        """Text used for embedding/FTS: statement plus expansion keys (Build 9 A)."""
        if fact.search_keys:
            return fact.statement + " " + " ".join(fact.search_keys)
        return fact.statement

    def add_fact(self, fact: Fact, resolve_conflicts: bool = True) -> Optional[int]:
        """Directly insert a fact (e.g. from an agent's own observations)."""
        if not self.expand_keys:
            fact.search_keys = []
        emb = self.embedder.embed([fact.statement])[0]
        if resolve_conflicts:
            return consolidate(self.store, fact, emb, self.embedder,
                               self.llm if self.mode == "full" else None)
        return self.store.add_fact(fact, emb)

    # --------------------------------------------------------------- search
    def _profiled(self, query: str, profile, k: Optional[int], now: Optional[str],
                  channels=None) -> tuple:
        """Resolve a profile (name / 'auto' / RetrievalProfile) and run
        retrieval with its policy. Returns (profile, results). Explicit k and
        channels args override the profile — knobs beat presets."""
        p = get_profile(profile, query=query, store=self.store)
        results = retrieve(
            self.store, self.embedder, query, now=now,
            k=k or p.k, weights=p.weights,
            per_channel=p.per_channel, entity_hops=p.entity_hops,
            reranker=self.reranker, obs_k=p.obs_k,
            semantic_entities=p.semantic_entities,
            semantic_threshold=self.semantic_threshold,
            use_key_channel=p.use_key_channel and self.expand_keys,
            include_observations=p.include_observations,
            channels=channels if channels is not None else p.channels)
        return p, results

    def search(self, query: str, k: Optional[int] = None, now: Optional[str] = None,
               profile=None, channels=None) -> List[RetrievalResult]:
        """profile: None (legacy default), a name ("facts" / "relations" /
        "timeline" / "deep" / "precision"), "auto" (v2 router), or a custom
        RetrievalProfile. channels: optional mask — {"lexical","semantic",
        "entity","temporal"} or Sanskrit aliases — orthogonal to profiles."""
        if profile is not None:
            return self._profiled(query, profile, k, now, channels=channels)[1]
        return retrieve(self.store, self.embedder, query, now=now, k=k or 12,
                        reranker=self.reranker,
                        semantic_entities=self.semantic_entities,
                        semantic_threshold=self.semantic_threshold,
                        channels=channels)

    def context(self, query: str, k: Optional[int] = None, now: Optional[str] = None,
                char_budget: int = 9000, profile=None, channels=None) -> str:
        # Explicit profile (drishti): named policy, evidence attached. The
        # legacy path below stays byte-identical when profile is None, so the
        # Build 10 A/B evidence keeps describing the default behavior.
        if profile is not None:
            p, results = self._profiled(query, profile, k, now, channels=channels)
            return pack_context(results, now=now, char_budget=char_budget,
                                aggregate=p.aggregate_pack)
        # Build 10 — per-type router. Each query class uses the config that
        # tested best for it (agile: adjust a profile as new A/B evidence lands):
        #   * aggregation  -> RECALL profile: high-k + key-expansion channel +
        #                     semantic-entity linking (won +18.5 on multi-session)
        #   * everything else -> PRECISION profile: the clean, unchanged path
        #                     (protects knowledge-update / single-session, which
        #                      regressed under global recall expansion in n=300)
        if self.aggregate and is_aggregation_query(query):
            results = retrieve(self.store, self.embedder, query, now=now, k=self.k_agg,
                               reranker=self.reranker, per_channel=max(24, self.k_agg),
                               use_key_channel=self.expand_keys,
                               semantic_entities=True,
                               semantic_threshold=self.semantic_threshold,
                               include_observations=True,
                               channels=channels)
            return pack_context(results, now=now, char_budget=char_budget, aggregate=True)
        # precision path: exclude observation summaries — they launder stale
        # values on current-state questions (knowledge-update diagnostic, -5.1pts).
        results = retrieve(self.store, self.embedder, query, now=now, k=k or 12,
                           reranker=self.reranker, include_observations=False,
                           channels=channels)
        return pack_context(results, now=now, char_budget=char_budget)

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
                              reranker=self.reranker,
                              semantic_entities=self.semantic_entities,
                              semantic_threshold=self.semantic_threshold):
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
        # Build 8: append Python-computed totals for sum-type aggregation, so the
        # answering model gets a trustworthy total instead of doing the arithmetic.
        totals = compute_numeric_totals(facts)
        if totals:
            summary = (summary + " " + totals).strip()
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

    # ------------------------------------------------- ownership & hygiene
    # Deliberately NOT exposed via the MCP server: destructive and identity-
    # shaping operations are owner-API-only, so untrusted conversation content
    # can never talk an agent into erasing or rewiring its own memory.
    def add_alias(self, alias: str, canonical: str) -> str:
        """Register an entity alias ("Rachel Smith" -> "Rachel"): future facts
        consolidate under the canonical entity, and queries mentioning the
        alias reach it. Conservative by design — nothing merges automatically."""
        return self.store.add_alias(alias, canonical)

    def erase_session(self, session_id: str) -> dict:
        """Owner-initiated erasure (data ownership) — distinct from supersession
        (knowledge update). Cascades: episodes, extracted facts, FTS rows,
        entity links, embeddings, ingest log."""
        return self.store.erase_session(session_id)

    def erase_entity(self, name: str) -> dict:
        """Erase every fact linked to an entity. Raw episodes are untouched;
        use erase_session for transcript-level erasure."""
        return self.store.erase_entity(name)

    def export_json(self, path: str) -> dict:
        """Lossless backup: episodes, facts (with supersession chains),
        entities, aliases, embeddings (base64). Restore with import_json."""
        data = self.store.export_data()
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(data, fh, ensure_ascii=False)
        return {"episodes": len(data["episodes"]), "facts": len(data["facts"]),
                "path": path}

    def import_json(self, path: str) -> dict:
        """Restore an export into this (empty) store. IDs are preserved, so
        supersession chains and episode links survive the round trip."""
        with open(path, encoding="utf-8") as fh:
            self.store.import_data(_json.load(fh))
        return self.stats()

    # ---------------------------------------------------------------- misc
    def stats(self) -> dict:
        s = self.store.stats()
        s["mode"] = self.mode
        return s
