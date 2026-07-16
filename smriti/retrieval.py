"""Read-time reflective retrieval — *smarana* (स्मरण, the act of recollection).

Four channels — shabda (शब्द, word: BM25), artha (अर्थ, meaning: vectors),
sambandha (सम्बन्ध, relation: entity hop), kala (काल, time: date proximity) —
meet in *sangama* (संगम, confluence: RRF fusion) and are packed into
*prasanga* (प्रसंग, context) for the answering model.

Single-strategy retrieval is the documented weakness of first-generation
memory layers. SMRITI fuses four cheap channels with Reciprocal Rank
Fusion (RRF), then applies temporal validity filtering:

  1. lexical   - BM25 (SQLite FTS5) over facts AND raw episodes
  2. semantic  - vector similarity over facts AND raw episodes
  3. entity    - graph-lite hop: facts linked to entities in the query
  4. temporal  - episodes nearest to dates referenced in the query

Facts and episodes are both first-class: facts give precise, consolidated
answers (knowledge updates, preferences); raw episodes are the safety net
for details extraction missed. Validity windows are surfaced so the
answering model can reason about "as of <date>" questions and supersession.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .store import Store
from .types import RetrievalResult

MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"])}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items())})

_DATE_PATTERNS = [
    re.compile(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
    re.compile(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})"),
    re.compile(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"),
    re.compile(r"([A-Za-z]+)\s+(\d{4})"),
]


_AGG_RE = re.compile(
    r"\b(how many|how much|number of|count of|total|in total|"
    r"combined|altogether|sum of|on average)\b|\bhow many different\b",
    re.IGNORECASE,
)
# NOTE: "how often" and bare "different" were dropped — they fired on
# knowledge-update / current-state questions ("how often do I attend yoga"),
# routing them to the high-recall path and surfacing superseded facts
# (the knowledge-update regression in the n=300 run).


def is_aggregation_query(query: str) -> bool:
    """True for counting/summing/averaging questions — the queries that need
    exhaustive recall of every instance rather than top-k precision (Build 9)."""
    return bool(_AGG_RE.search(query or ""))


def extract_dates(text: str) -> List[str]:
    """Pull explicit dates out of free text -> ISO strings (best effort)."""
    found = []
    for pat in _DATE_PATTERNS:
        for m in pat.finditer(text):
            g = m.groups()
            try:
                if pat is _DATE_PATTERNS[0]:
                    found.append(f"{int(g[0]):04d}-{int(g[1]):02d}-{int(g[2]):02d}")
                elif pat is _DATE_PATTERNS[1] and g[1].lower() in MONTHS:
                    found.append(f"{int(g[2]):04d}-{MONTHS[g[1].lower()]:02d}-{int(g[0]):02d}")
                elif pat is _DATE_PATTERNS[2] and g[0].lower() in MONTHS:
                    found.append(f"{int(g[2]):04d}-{MONTHS[g[0].lower()]:02d}-{int(g[1]):02d}")
                elif pat is _DATE_PATTERNS[3] and g[0].lower() in MONTHS:
                    found.append(f"{int(g[1]):04d}-{MONTHS[g[0].lower()]:02d}-15")
            except (ValueError, KeyError):
                continue
    return list(dict.fromkeys(found))


def query_entities(store: Store, query: str) -> List[str]:
    """Match query tokens against the known entity vocabulary, then against
    registered aliases ("rachel smith" in the query reaches the canonical
    "rachel" entity — the read-time half of alias handling, 0.3.0)."""
    tokens = set(re.findall(r"[A-Za-z][A-Za-z0-9'-]+", query.lower()))
    known = store.all_entities()
    hits = []
    for ent in known:
        ent_tokens = set(ent.split())
        if ent in tokens or (ent_tokens and ent_tokens <= tokens):
            hits.append(ent)
    for canonical in store.match_aliases(tokens):
        if canonical not in hits:
            hits.append(canonical)
    return hits[:10]


def _rrf(rankings: Dict[str, List[Tuple[str, int]]], weights: Dict[str, float],
         k: int = 60) -> Dict[Tuple[str, int], Tuple[float, List[str]]]:
    fused: Dict[Tuple[str, int], Tuple[float, List[str]]] = {}
    for channel, ranked in rankings.items():
        w = weights.get(channel, 1.0)
        for rank, key in enumerate(ranked):
            score, chans = fused.get(key, (0.0, []))
            fused[key] = (score + w / (k + rank + 1), chans + [channel])
    return fused


DEFAULT_WEIGHTS = {
    "vec_fact": 1.0, "vec_episode": 1.0,
    "bm25_fact": 0.9, "bm25_episode": 0.9,
    "entity": 0.6, "entity_hop2": 0.4, "temporal": 0.6,
    "key_expansion": 0.7,
}

# Conceptual channels -> internal ranking keys. User-facing names are the
# four channels of the read path; Sanskrit aliases accepted (NOMENCLATURE.md).
CHANNEL_GROUPS = {
    "lexical": ("bm25_fact", "bm25_episode", "key_expansion"),   # shabda शब्द
    "semantic": ("vec_fact", "vec_episode"),                     # artha अर्थ
    "entity": ("entity", "entity_hop2"),                         # sambandha सम्बन्ध
    "temporal": ("temporal",),                                   # kala काल
}
CHANNEL_ALIASES = {"shabda": "lexical", "artha": "semantic",
                   "sambandha": "entity", "kala": "temporal"}


def expand_channels(channels) -> Optional[set]:
    """Normalize a user-facing channel selection into internal ranking keys.

    Accepts conceptual names ("lexical"), Sanskrit aliases ("shabda"), or raw
    internal keys ("bm25_fact"). None means all channels (default)."""
    if channels is None:
        return None
    internal: set = set()
    valid_internal = {k for grp in CHANNEL_GROUPS.values() for k in grp}
    for c in channels:
        c = str(c).lower().strip()
        c = CHANNEL_ALIASES.get(c, c)
        if c in CHANNEL_GROUPS:
            internal.update(CHANNEL_GROUPS[c])
        elif c in valid_internal:
            internal.add(c)
        else:
            raise ValueError(
                f"unknown channel {c!r}; known: {sorted(CHANNEL_GROUPS)} "
                f"(aliases: {sorted(CHANNEL_ALIASES)})")
    return internal


def retrieve(store: Store, embedder, query: str, now: Optional[str] = None,
             k: int = 12, weights: Optional[Dict[str, float]] = None,
             per_channel: int = 24, entity_hops: int = 2,
             reranker=None, rerank_top: int = 48, obs_k: int = 4,
             semantic_entities: bool = False,
             semantic_threshold: float = 0.3,
             use_key_channel: bool = False,
             include_observations: bool = True,
             channels=None) -> List[RetrievalResult]:
    weights = weights or DEFAULT_WEIGHTS
    # channel gating (drishti): each ranking block below is independent, so a
    # disabled channel is simply never built — and never billed (a lexical-only
    # call skips the query embedding entirely).
    chset = expand_channels(channels)

    def _on(name: str) -> bool:
        return chset is None or name in chset

    need_vec = _on("vec_fact") or _on("vec_episode") or (semantic_entities and _on("entity"))
    qvec = embedder.embed([query])[0] if (embedder and need_vec) else None

    rankings: Dict[str, List[Tuple[str, int]]] = {}
    if _on("bm25_fact"):
        rankings["bm25_fact"] = [("fact", i) for i, _ in store.fts_search(query, "fact", per_channel)]
    if _on("bm25_episode"):
        rankings["bm25_episode"] = [("episode", i) for i, _ in store.fts_search(query, "episode", per_channel)]
    # key-expansion channel — only on the recall profile (aggregation queries),
    # so category/synonym keys widen recall without touching precision queries.
    if use_key_channel and _on("key_expansion"):
        rankings["key_expansion"] = [("fact", i) for i, _ in store.key_fts_search(query, per_channel)]
    if qvec is not None and _on("vec_fact"):
        rankings["vec_fact"] = [("fact", i) for i, _ in store.vector_search(qvec, "fact", per_channel)]
    if qvec is not None and _on("vec_episode"):
        rankings["vec_episode"] = [("episode", i) for i, _ in store.vector_search(qvec, "episode", per_channel)]
    ents = query_entities(store, query) if _on("entity") else []
    # Semantic entity linking (mem0-inspired, zero-dep): reach entities the
    # lexical token match misses by cosine-matching query -> entity-name
    # embeddings. Strictly additive — lexical hits stay first, the rest are
    # appended deduped, then the existing entity-hop logic runs unchanged.
    if semantic_entities and qvec is not None:
        for n, _s in store.semantic_entities(embedder, qvec,
                                             threshold=semantic_threshold, limit=8):
            if n not in ents:
                ents.append(n)
        ents = ents[:12]
    if ents:
        hop1 = store.entity_facts(ents, per_channel)
        rankings["entity"] = [("fact", i) for i, _ in hop1]
        # graph-lite multi-hop: facts one entity-link away from the hop-1 facts.
        # "Rachel works at Acme" + "Acme is in Berlin" -> reach Berlin from Rachel.
        # Bounded (one extra hop, deduped, down-weighted) — no graph DB.
        if entity_hops >= 2 and hop1 and _on("entity_hop2"):
            hop1_ids = [i for i, _ in hop1]
            seen = set(hop1_ids)
            hop2_ents = [e for e in store.entities_of_facts(hop1_ids)
                         if e not in set(ents)][:20]
            if hop2_ents:
                rankings["entity_hop2"] = [
                    ("fact", i) for i, _ in store.entity_facts(hop2_ents, per_channel)
                    if i not in seen
                ]
    if _on("temporal"):
        for d in extract_dates(query)[:2]:
            rankings.setdefault("temporal", [])
            rankings["temporal"] += [("episode", i) for i, _ in store.episodes_near(d, per_channel // 2)]

    fused = _rrf(rankings, weights)
    ordered = sorted(fused.items(), key=lambda kv: -kv[1][0])

    # Materialize a larger pool when a reranker will re-sort it, else just k.
    pool = max(k, rerank_top) if reranker is not None else k
    results: List[RetrievalResult] = []
    observations: List[RetrievalResult] = []
    seen_sessions_text = set()
    for (kind, rid), (score, chans) in ordered:
        if len(results) >= pool and len(observations) >= obs_k:
            break
        if kind == "fact":
            f = store.get_fact(rid)
            if not f:
                continue
            if f.kind == "observation":
                # observation summaries are a RECALL-profile feature (Build 12):
                # they help aggregation but launder stale/superseded values on
                # current-state queries, so the precision path excludes them and
                # relies on raw, CURRENT/SUPERSEDED-annotated facts instead.
                if not include_observations or len(observations) >= obs_k:
                    continue
                observations.append(RetrievalResult(
                    kind="observation", id=rid, text=f.statement, score=score,
                    valid_from=f.valid_from, invalid_at=f.invalid_at, channels=chans))
                continue
            if len(results) >= pool:
                continue
            results.append(RetrievalResult(
                kind="fact", id=rid, text=f.statement, score=score,
                valid_from=f.valid_from, invalid_at=f.invalid_at, channels=chans))
        else:
            if len(results) >= pool:
                continue
            e = store.get_episode(rid)
            if not e:
                continue
            key = (e.session_id, e.content[:80])
            if key in seen_sessions_text:
                continue
            seen_sessions_text.add(key)
            results.append(RetrievalResult(
                kind="episode", id=rid, text=e.content, score=score,
                ts=e.ts, role=e.role, channels=chans))

    # cross-encoder re-examination of the raw pool, then trim to k
    if reranker is not None and results:
        scores = reranker.rerank(query, [r.text for r in results])
        for r, sc in zip(results, scores):
            r.score = float(sc)
            if "rerank" not in r.channels:
                r.channels = r.channels + ["rerank"]
        results.sort(key=lambda r: -r.score)
        results = results[:k]
    return observations + results


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return "?"
    return iso[:10]


def pack_context(results: List[RetrievalResult], now: Optional[str] = None,
                 char_budget: int = 9000, aggregate: bool = False) -> str:
    """Render retrieval into an answer-ready context block with provenance.

    When aggregate=True (counting/aggregation query), prepend an instruction to
    enumerate-and-count every relevant item and give a best-effort total rather
    than abstaining — directly countering the abstention failure mode."""
    observations, facts, episodes = [], [], []
    for r in results:
        (observations if r.kind == "observation" else
         facts if r.kind == "fact" else episodes).append(r)

    # Validity-first ordering (0.3.1): CURRENT facts precede SUPERSEDED ones in
    # the packed block (stable — fused-score order preserved within each group).
    # Annotation tells the model which is which; ordering stops a superseded
    # value from being the first thing it reads on current-state questions.
    facts.sort(key=lambda r: r.invalid_at is not None)

    lines: List[str] = []
    if aggregate:
        lines.append("COUNTING / AGGREGATION QUESTION — go through the FACTS, SUMMARIES and "
                     "EVIDENCE below, enumerate every item relevant to the question, and give "
                     "your best count or total from what is shown. Do NOT reply that you lack "
                     "information if relevant items are present; count them.")
        lines.append("")
    if observations:
        lines.append("ENTITY SUMMARIES (synthesized overviews of what's known about key "
                      "entities; useful for spotting counts/totals, but confirm the specifics "
                      "against the FACTS and EVIDENCE below):")
        for r in observations:
            lines.append(f"- {r.text}")
        lines.append("")
    if facts:
        lines.append("KNOWN FACTS (each with validity window; CURRENT means still true, "
                      "SUPERSEDED means it was true then but later changed):")
        for r in facts:
            status = "CURRENT" if r.invalid_at is None else f"SUPERSEDED on {_fmt_date(r.invalid_at)}"
            lines.append(f"- [{_fmt_date(r.valid_from)} | {status}] {r.text}")
        lines.append("")
    if episodes:
        lines.append("RAW CONVERSATION EVIDENCE (timestamped):")
        episodes.sort(key=lambda r: r.ts or "")
        for r in episodes:
            snippet = r.text if len(r.text) <= 700 else r.text[:700] + " ..."
            lines.append(f"- [{_fmt_date(r.ts)}] {r.role or 'user'}: {snippet}")

    out = "\n".join(lines)
    if len(out) > char_budget:
        out = out[:char_budget] + "\n[truncated]"
    return out
