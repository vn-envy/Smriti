"""Retrieval profiles — *drishti* (दृष्टि, "way of seeing").

One store, many ways of looking at it. A profile is a named, declarative
bundle of channel selection + weights + packing policy, resolvable per query.
This turns the internal per-type router (Build 10) into a first-class,
user- and agent-facing concept:

  * ``facts``     — current-state precision. Lexical + semantic + 1-hop entity
                    over validity-annotated facts. No observation summaries
                    (they launder stale values — the knowledge-update
                    diagnostic, BENCHMARKS.md).
  * ``relations`` — entity-centric. 2-hop *sambandha* traversal + semantic
                    entity linking, entity channels up-weighted.
  * ``timeline``  — *kala*-weighted. Date-anchored episodes emphasized,
                    chronological evidence for when/before/after questions.
  * ``deep``      — high-recall aggregation. All channels + key expansion +
                    observation digests + enumerate-don't-assert packing
                    (the configuration that won +10.3 on multi-session,
                    p=0.046, with no knowledge-update tax).
  * ``precision`` — the legacy default read path, unchanged (all channels,
                    no observations). ``context()`` without a profile still
                    routes aggregation→deep-equivalent / else→precision, so
                    existing behavior and A/B evidence are preserved.
  * ``auto``      — the v2 router: deep → timeline → relations → facts,
                    resolved by zero-token heuristics.

Design rules (NOMENCLATURE.md): code stays English — ``profile="facts"`` —
the Sanskrit lives here in the docs. Profiles are data, not code, so custom
profiles are benchmarkable with the shipped harness exactly like built-ins:
``bench/ab.sh`` A/Bs any profile per question type. Evidence first; the
``auto`` router only changes *opt-in* behavior until a full run gates it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Dict, Optional, Set

from .retrieval import extract_dates, is_aggregation_query, query_entities

# Conceptual channels (user-facing) with Sanskrit aliases. Internal ranking
# keys are expanded in retrieval.expand_channels().
CHANNELS = ("lexical", "semantic", "entity", "temporal")
ALL_CHANNELS: Set[str] = set(CHANNELS)


@dataclass(frozen=True)
class RetrievalProfile:
    """A declarative retrieval policy. Every field maps 1:1 onto a
    ``retrieve()`` / ``pack_context()`` argument, so a profile is nothing more
    than a named, shippable, A/B-able bundle of the knobs that already exist."""
    name: str = "custom"
    channels: Optional[Set[str]] = None          # None = all four
    weights: Optional[Dict[str, float]] = None   # None = retrieval.DEFAULT_WEIGHTS
    k: int = 12
    per_channel: int = 24
    entity_hops: int = 2
    use_key_channel: bool = False
    semantic_entities: bool = False
    include_observations: bool = False
    aggregate_pack: bool = False                 # enumerate-and-count packing
    obs_k: int = 4
    # provenance: the evidence that justified this configuration
    evidence: str = ""

    def with_overrides(self, **kw) -> "RetrievalProfile":
        kw = {k: v for k, v in kw.items() if v is not None}
        return replace(self, **kw) if kw else self


PROFILES: Dict[str, RetrievalProfile] = {
    "facts": RetrievalProfile(
        name="facts",
        channels={"lexical", "semantic", "entity"},
        k=10, entity_hops=1,
        include_observations=False,
        evidence="precision path minus hop-2/temporal noise; observation "
                 "exclusion per knowledge-update diagnostic (-5.1 reversed).",
    ),
    "relations": RetrievalProfile(
        name="relations",
        channels={"lexical", "semantic", "entity"},
        weights={"vec_fact": 1.0, "vec_episode": 0.9, "bm25_fact": 0.9,
                 "bm25_episode": 0.8, "entity": 1.1, "entity_hop2": 0.7,
                 "temporal": 0.0, "key_expansion": 0.0},
        k=14, entity_hops=2, semantic_entities=True,
        include_observations=False,
        evidence="2-hop sambandha + semantic entity linking (mem0-inspired "
                 "lever, Build 12); entity channels up-weighted.",
    ),
    "timeline": RetrievalProfile(
        name="timeline",
        channels={"lexical", "semantic", "temporal"},
        weights={"vec_fact": 1.0, "vec_episode": 1.0, "bm25_fact": 0.9,
                 "bm25_episode": 0.9, "entity": 0.0, "entity_hop2": 0.0,
                 "temporal": 1.2, "key_expansion": 0.0},
        k=14, include_observations=False,
        evidence="kala channel boosted; pack_context orders episodes "
                 "chronologically; validity windows carry as-of semantics.",
    ),
    "deep": RetrievalProfile(
        name="deep",
        channels=None,  # all four
        k=40, per_channel=40,
        use_key_channel=True, semantic_entities=True,
        include_observations=True, aggregate_pack=True,
        evidence="the Build 10 recall configuration: multi-session +10.3 "
                 "(McNemar p=0.046), knowledge-update regression eliminated.",
    ),
    "precision": RetrievalProfile(
        name="precision",
        channels=None,  # all four — the legacy default read path
        k=12, include_observations=False,
        evidence="the unchanged Build 10 precision path (protects "
                 "knowledge-update / single-session).",
    ),
}

_TEMPORAL_RE = re.compile(
    r"\b(when|before|after|since|until|during|first time|last time|"
    r"previous|previously|earlier|ago|timeline|history of|back then|"
    r"at the time|as of)\b", re.IGNORECASE)

_RELATION_RE = re.compile(
    r"\b(who|whom|whose|related to|relationship|connected|connection|"
    r"works? with|work at|colleague|friend of|married|partner|mentor|"
    r"between|know each other|team|reports? to)\b", re.IGNORECASE)


def resolve(query: str, store=None) -> RetrievalProfile:
    """v2 router: zero-token intent classification -> profile.

    Order matters and is deliberate:
      1. aggregation cues -> deep      (exhaustive recall beats precision)
      2. date/tense cues  -> timeline  (kala anchoring)
      3. relation cues or >=2 known entities -> relations
      4. default          -> facts     (current-state precision)

    Heuristics only — same discipline as ``is_aggregation_query`` (Build 9),
    and the same caveat: gate any default-behavior change on an A/B run.
    """
    q = query or ""
    if is_aggregation_query(q):
        return PROFILES["deep"]
    if extract_dates(q) or _TEMPORAL_RE.search(q):
        return PROFILES["timeline"]
    if _RELATION_RE.search(q):
        return PROFILES["relations"]
    if store is not None and len(query_entities(store, q)) >= 2:
        return PROFILES["relations"]
    return PROFILES["facts"]


def get_profile(profile, query: str = "", store=None) -> RetrievalProfile:
    """Accept a profile name, ``"auto"``, or a RetrievalProfile instance."""
    if isinstance(profile, RetrievalProfile):
        return profile
    if not isinstance(profile, str):
        raise ValueError(f"profile must be a name or RetrievalProfile, got {type(profile)}")
    name = profile.lower().strip()
    if name == "auto":
        return resolve(query, store=store)
    if name in PROFILES:
        return PROFILES[name]
    raise ValueError(f"unknown profile {profile!r}; "
                     f"known: {sorted(PROFILES)} or 'auto'")
