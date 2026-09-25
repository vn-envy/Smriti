"""Evidence-first recall — *smarana* v2 (स्मरण, recollection).

Diagnosis that motivated this module (lab benchmark, ``bench/lab``): the
legacy read path ranks evidence well — recall@10 on par with or above BM25 —
yet only ~40% of supporting turns reached the reader *complete*. Two packing
rules caused it: a fixed ``k=12`` (LoCoMo contexts used ~2k of a 9k budget)
and a hard 700-character cut per turn (answers inside long turns were cut
off). Retrieval quality was being thrown away at the last step.

This path keeps everything that was good (hybrid lexical + semantic, facts
first-class, validity annotations) and changes how evidence is chosen and
delivered:

1. **Score-level hybrid fusion.** BM25 (stopword-stripped query) and cosine
   scores are normalized per query and combined convexly instead of by rank
   only, so a strong lexical hit is not flattened into the same reciprocal
   rank as a weak one (Bruch et al., TOIS 2023).
2. **Turn → session roll-up.** A turn inherits part of its session's best
   score, so turns from the conversation that is actually about the topic rise
   together (turn-isolation retrieval / NDCG-of-turns in the literature).
3. **Priors that need no model.** Assistant turns are softened unless the
   question addresses the assistant ("what did you recommend…"); a question
   that names a period ("last weekend", "in March", "past two months") gives
   a soft boost to turns dated in, or talking about, that window.
4. **Budget-adaptive, evidence-first packing.** Hits are packed whole while
   they fit; long turns are reduced to query-focused excerpts rather than a
   prefix; neighbouring turns are added only after the evidence itself.
5. **Reader-friendly rendering.** Evidence is grouped by session, sessions in
   chronological order under dated headers, and relative time phrases carry
   resolved absolute dates (``yesterday [2023-05-07]``, see
   :mod:`smriti.temporal`).

Everything is deterministic, zero-token and stdlib + numpy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

try:  # numpy is a core dependency; mirror store.py's import style
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from .temporal import annotate, find_mentions, parse_anchor, query_window
from .types import Episode, RetrievalResult

# Function words plus conversational filler common in memory questions
# ("can you remind me what …", "in our previous chat …"). Removing them keeps
# FTS5's OR-query from matching every turn that says "you" or "previous".
STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been
before being below between both but by can could did do does doing down during
each few for from further had has have having he her here hers herself him
himself his how i if in into is it its itself just me more most my myself no nor
not now of off on once only or other our ours ourselves out over own same she
should so some such than that the their theirs them themselves then there these
they this those through to too under until up very was we were what when where
which while who whom why will with would you your yours yourself yourselves
im ive id ill youre youve dont didnt doesnt isnt wasnt cant couldnt wont
also get got really thing things something anything much many one
remind recall remember previous previously earlier conversation chat talked
talk discussed mentioned tell told know wondering wonder asked ask
please thanks thank hey hi okay ok yes yeah sure like
""".split())

_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'_-]*|\w+", re.UNICODE)

_ASSISTANT_REF = re.compile(
    r"\byou\s+(?:\w+\s+){0,3}?(?:said|told|mentioned|suggested|recommended|recommend|"
    r"gave|give|provided|listed|shared|described|explained|wrote|write|created|"
    r"came up|named|called|proposed|offered|advised|helped|generated|drafted|"
    r"showed|answered|responded|included)\b"
    r"|\byour\s+(?:suggestion|recommendation|advice|answer|response|list|"
    r"explanation|previous|earlier|last|reply|idea|tip)s?\b"
    r"|\byou\s+(?:made|played|used|picked|chose)\b"
    r"|\bremind me\b|\bwe\s+(?:talked|discussed|chatted|spoke|went over)\b"
    r"|\b(?:our|the)\s+(?:previous|last|earlier)\s+(?:\w+\s+)?"
    r"(?:chat|conversation|discussion|game|session)\b",
    re.IGNORECASE)

_AGG = re.compile(
    r"\b(how many|how much|number of|count of|total|in total|combined|"
    r"altogether|sum of|on average|all the|list all|every|each of|different)\b",
    re.IGNORECASE)


def query_terms(query: str) -> List[str]:
    """Lower-cased content terms of a query (stopwords and 1-char tokens out).

    Falls back to all tokens when a query is made only of stopwords."""
    toks = [t.lower().strip("'_-") for t in _WORD.findall(query or "")]
    toks = [t.replace("'", "") for t in toks if t]
    kept = [t for t in toks if len(t) > 1 and t not in STOPWORDS]
    return list(dict.fromkeys(kept or [t for t in toks if len(t) > 1]))


def addresses_assistant(query: str) -> bool:
    """True when the question asks about something the assistant said."""
    return bool(_ASSISTANT_REF.search(query or ""))


_WHEN_Q = re.compile(
    r"^\s*(?:when\b|what (?:date|day|year|month|time)\b|which (?:date|day|year|month)\b)"
    r"|\bhow long ago\b|\bhow many (?:days|weeks|months|years)\b",
    re.IGNORECASE)
_DATEISH = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b|"
    r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|weekend|yesterday|"
    r"tomorrow|tonight|today|ago|last (?:week|month|year|night))\b", re.IGNORECASE)
_ORDER_Q = re.compile(r"\b(first|before|after|earlier|later|order|sooner|most recently)\b",
                      re.IGNORECASE)


_GENERIC_ROLES = frozenset({"user", "assistant", "system", "tool", "human", "ai", "bot"})
_SPEAKER_PREFIX = re.compile(r"^\s*([A-Z][\w'.-]{0,30}(?: [A-Z][\w'.-]{0,30}){0,2}):\s")


@lru_cache(maxsize=16384)
def _content_terms(text: str) -> int:
    """Number of content words in a turn, ignoring a leading "Name:" prefix."""
    m = _SPEAKER_PREFIX.match(text or "")
    body = text[m.end():] if m else (text or "")
    return sum(1 for t in _WORD.findall(body) if len(t) > 2 and t.lower() not in STOPWORDS)


def speaker_of(ep: Episode) -> Optional[str]:
    """Named participant of a turn: a non-generic role, else a leading
    "Name: " prefix (the common transcript convention). None if unknown."""
    role = (ep.role or "").strip()
    if role and role.lower() not in _GENERIC_ROLES:
        return role.lower()
    m = _SPEAKER_PREFIX.match(ep.content or "")
    return m.group(1).lower() if m else None


@lru_cache(maxsize=16384)
def _has_dateish(text: str) -> bool:
    return bool(_DATEISH.search(text))


def asks_when(query: str) -> bool:
    return bool(_WHEN_Q.search(query or ""))


def alternatives(query: str) -> List[str]:
    """Sub-queries for ordering questions naming alternatives:
    "Which did I do first, the pottery class or the yoga retreat?" ->
    ["the pottery class", "the yoga retreat"]. Empty when not applicable."""
    q = query or ""
    if " or " not in q.lower() or not _ORDER_Q.search(q):
        return []
    body = re.split(r"[,:?]", q)
    parts: List[str] = []
    for seg in body:
        if re.search(r"\bor\b", seg, re.IGNORECASE):
            parts.extend(p.strip() for p in re.split(r"\bor\b", seg, flags=re.IGNORECASE))
    parts = [p for p in parts if len(query_terms(p)) >= 1]
    return parts if len(parts) >= 2 else []


def _stem(t: str) -> str:
    for suf in ("ings", "ing", "edly", "ed", "ies", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


@dataclass(frozen=True)
class RecallConfig:
    """Knobs of the evidence-first path. Every field is A/B-able in bench/lab."""
    depth: int = 200                 # candidates taken from each channel
    w_lexical: float = 0.5           # convex weight of normalized BM25
    w_semantic: float = 0.5          # convex weight of normalized cosine
    fusion: str = "convex"           # "convex" | "rrf" | "blend" (mean of both, each max-scaled)
    session_weight: float = 0.25     # share of the session's best score inherited
    assistant_prior: float = 0.55    # multiplier on assistant turns (unless addressed)
    time_boost: float = 0.25         # additive boost inside a query's time window
    neighbors: int = 1               # +/- turns attached to packed hits
    neighbor_chars: int = 360        # excerpt size for neighbour turns
    max_turn_chars: int = 1400       # longer hits are reduced to a query-focused excerpt
    top_hits: int = 5                # the best N hits get ``top_turn_chars`` instead
    top_turn_chars: int = 2000
    neighbor_top: int = 0            # neighbours of the best N hits are packed right after them
    min_turn_chars: int = 220        # smallest excerpt worth packing
    per_session_cap: int = 0         # max hits per session in the first pass (0 = off)
    agg_session_cap: int = 0         # cap applied automatically to aggregation questions
    min_relative: float = 0.0        # stop packing hits scoring below this share of the best
    annotate_time: bool = True       # resolve relative dates when rendering
    fact_share: float = 0.35         # max share of the budget spent on the facts block
    layout: str = "chrono"           # "chrono" | "relevance" | "top" (ranked head + chronological rest)
    top_section: int = 5             # hits shown in the ranked head of the "top" layout
    # levers added after the first sweeps (bench/lab dev split); prf stays off
    when_boost: float = 0.15         # "when …?" questions: boost turns that carry time expressions
    split_alternatives: bool = True  # "X or Y" ordering questions: also retrieve each alternative
    prf: float = 0.0                 # dense pseudo-relevance feedback weight (top-3 turns)
    speaker_prior: float = 0.75      # multiplier on turns by participants the question does not name
    speaker_terms: bool = False      # keep named speakers' names as lexical terms
    min_content_terms: int = 0       # turns with fewer content words get ``short_turn_prior``
    short_turn_prior: float = 1.0
    stem_prefix: bool = True         # lexical: match light stems as FTS5 prefixes
    # optional reranker (Smriti(reranker=...)): how many head turns it judges,
    # and how its score mixes with the fused score (1.0 = replace, the 0.3.x
    # contract; 0.5 = equal blend of max-normalised fused score and reranker score)
    rerank_depth: int = 48
    rerank_weight: float = 1.0

    def with_overrides(self, **kw) -> "RecallConfig":
        kw = {k: v for k, v in kw.items() if v is not None}
        return replace(self, **kw) if kw else self


DEFAULT_RECALL = RecallConfig()


@dataclass
class Hit:
    episode: Episode
    score: float
    channels: List[str] = field(default_factory=list)


def _normalize(scores: Dict[int, float], min_spread: float = 0.0,
               ratio: bool = False) -> Dict[int, float]:
    """Scale a channel's scores to [0, 1] per query.

    ``ratio`` divides by the maximum (for non-negative BM25 scores), keeping
    relative magnitudes. Otherwise min-max, with the range widened to at least
    ``min_spread`` so that near-identical scores (a tiny store, a handful of
    candidates) are not stretched into a 0-vs-1 difference."""
    if not scores:
        return {}
    hi = max(scores.values())
    if ratio:
        return {k: (v / hi if hi > 0 else 1.0) for k, v in scores.items()}
    lo = min(min(scores.values()), hi - min_spread)
    if hi <= lo:
        return {k: 1.0 for k in scores}
    return {k: (v - lo) / (hi - lo) for k, v in scores.items()}


def _in_window(ts: Optional[str], window: Tuple[date, date]) -> bool:
    d = parse_anchor(ts)
    return d is not None and window[0] <= d <= window[1]


def _mentions_window(text: str, ts: Optional[str], window: Tuple[date, date]) -> bool:
    for m in find_mentions(text, ts):
        if m.first <= window[1] and m.last >= window[0]:
            return True
    return False


def rank_episodes(store, embedder, query: str, now: Optional[str] = None,
                  config: RecallConfig = DEFAULT_RECALL,
                  qvec=None) -> List[Hit]:
    """Rank raw episodes for ``query`` with fused, session-aware scoring."""
    cfg = config
    if cfg.split_alternatives:
        alts = alternatives(query)
        base = cfg.with_overrides(split_alternatives=False)
        main = rank_episodes(store, embedder, query, now=now, config=base, qvec=qvec)
        if not alts:
            return main
        merged: Dict[int, Hit] = {h.episode.id: h for h in main}
        for alt in alts:
            for h in rank_episodes(store, embedder, alt, now=now, config=base):
                cur = merged.get(h.episode.id)
                if cur is None or h.score > cur.score:
                    merged[h.episode.id] = Hit(h.episode, h.score, list(h.channels))
        return sorted(merged.values(), key=lambda h: (-h.score, h.episode.id))
    terms = query_terms(query)

    def lexical_search(words: List[str]) -> Dict[int, float]:
        if not words or cfg.w_lexical <= 0:
            return {}
        if cfg.stem_prefix:
            expr = " OR ".join(
                (f'"{_stem(t)}"*' if len(_stem(t)) >= 4 and _stem(t) != t else f'"{t}"')
                for t in words if '"' not in t)
            found = store.fts_match(expr, "episode", cfg.depth)
        else:
            found = store.fts_search(" ".join(words), "episode", cfg.depth)
        return {rid: sc for rid, sc in found}

    lexical = lexical_search(terms)
    semantic: Dict[int, float] = {}
    all_ids: List[int] = []
    all_sims = None
    if cfg.w_semantic > 0 and embedder is not None:
        if qvec is None:
            qvec = embedder.embed([query])[0]
        all_ids, all_sims = store.vector_all(qvec, "episode")
        if all_ids and cfg.prf > 0:
            _ids, mat = store._vectors("episode")
            seed = np.argpartition(-all_sims, 3)[:3] if len(all_sims) > 3 else np.arange(len(all_sims))
            q = np.asarray(qvec, dtype="float32")
            q = q / (np.linalg.norm(q) or 1.0)
            q2 = q + cfg.prf * mat[seed].mean(axis=0)
            all_sims = mat @ (q2 / (np.linalg.norm(q2) or 1.0))
        if all_ids:
            # top-`depth` in O(N) instead of a full O(N log N) sort
            if len(all_ids) > cfg.depth:
                top = np.argpartition(-all_sims, cfg.depth)[:cfg.depth]
            else:
                top = np.arange(len(all_ids))
            semantic = {all_ids[i]: float(all_sims[i]) for i in top}
    window = query_window(query, now) if cfg.time_boost > 0 else None
    windowed: set = set()
    if window is not None:
        windowed = set(store.episodes_in_range(window[0].isoformat(),
                                               window[1].isoformat() + "T23:59:59Z",
                                               limit=cfg.depth * 2))
    cand = set(lexical) | set(semantic) | windowed
    if not cand:
        return []
    # cosine for windowed candidates that the semantic top-k missed
    if windowed and all_ids:
        pos = {rid: i for i, rid in enumerate(all_ids)}
        for rid in windowed - set(semantic):
            if rid in pos:
                semantic[rid] = float(all_sims[pos[rid]])
    eps = store.episodes_by_ids(cand)

    fused: Dict[int, float] = {}
    chans: Dict[int, List[str]] = {rid: [] for rid in cand}
    rrf: Dict[int, float] = {}
    convex: Dict[int, float] = {}
    # channel labels use the fusion engine's internal names (CHANNEL_GROUPS)
    for name, table in (("bm25_episode", lexical), ("vec_episode", semantic)):
        w = cfg.w_lexical if name == "bm25_episode" else cfg.w_semantic
        for rank, rid in enumerate(sorted(table, key=lambda r: -table[r])):
            rrf[rid] = rrf.get(rid, 0.0) + w * 61.0 / (60 + rank + 1)
            chans[rid].append(name)
    nlex = _normalize(lexical, ratio=True)
    nsem = _normalize(semantic, min_spread=0.25)
    for rid in cand:
        convex[rid] = cfg.w_lexical * nlex.get(rid, 0.0) + cfg.w_semantic * nsem.get(rid, 0.0)
    if cfg.fusion == "rrf":
        fused = {rid: rrf.get(rid, 0.0) for rid in cand}
    elif cfg.fusion == "blend":
        top_r = max(rrf.values(), default=1.0) or 1.0
        top_c = max(convex.values(), default=1.0) or 1.0
        fused = {rid: 0.5 * rrf.get(rid, 0.0) / top_r + 0.5 * convex[rid] / top_c for rid in cand}
    else:
        fused = dict(convex)

    to_assistant = addresses_assistant(query)
    when_q = cfg.when_boost > 0 and asks_when(query)
    named: set = set()
    if cfg.speaker_prior != 1.0:
        qtok = {t.lower() for t in _WORD.findall(query or "")}
        counts: Dict[str, int] = {}
        for e in eps.values():
            sp = speaker_of(e)
            if sp:
                counts[sp] = counts.get(sp, 0) + 1
        # a "speaker" must recur; a stray "Note: …" prefix is not a participant
        speakers = {sp for sp, n in counts.items() if n >= 3}
        mentioned = {sp for sp in speakers if sp and (sp in qtok or sp.split()[0] in qtok)}
        named = set() if mentioned == speakers else mentioned
        if not cfg.speaker_terms and mentioned:
            # A participant's name sits in the "Name:" prefix of every one of
            # their turns: as a lexical term it matches them all and BM25's
            # length normalization then favours their emptiest turns. The
            # speaker prior carries that signal; search on the content terms.
            names = {w for sp in mentioned for w in sp.split()}
            rest = [t for t in terms if t not in names]
            if rest and len(rest) < len(terms):
                new_lex = lexical_search(rest)
                missing = set(new_lex) - set(eps)
                if missing:
                    eps.update(store.episodes_by_ids(missing))
                    for rid in missing:
                        chans[rid] = []
                        if rid in semantic:
                            chans[rid].append("vec_episode")
                        cand.add(rid)
                lexical = new_lex
                for rid in cand:
                    chans[rid] = [c for c in chans[rid] if c != "bm25_episode"]
                    if rid in lexical:
                        chans[rid].insert(0, "bm25_episode")
                nlex = _normalize(lexical, ratio=True)
                for rid in cand:
                    fused[rid] = (cfg.w_lexical * nlex.get(rid, 0.0)
                                  + cfg.w_semantic * nsem.get(rid, 0.0))
    for rid in cand:
        ep = eps.get(rid)
        if ep is None:
            fused.pop(rid, None)
            continue
        if (ep.role or "").lower() == "assistant" and not to_assistant:
            fused[rid] *= cfg.assistant_prior
        if window is not None and (rid in windowed or _in_window(ep.ts, window)
                                   or _mentions_window(ep.content, ep.ts, window)):
            fused[rid] += cfg.time_boost
            chans[rid].append("temporal")
        if when_q and _has_dateish(ep.content):
            fused[rid] += cfg.when_boost
        if named and speaker_of(ep) not in named:
            fused[rid] *= cfg.speaker_prior
        if cfg.min_content_terms and _content_terms(ep.content) < cfg.min_content_terms:
            fused[rid] *= cfg.short_turn_prior

    session_weight = cfg.session_weight
    if session_weight > 0:
        best: Dict[str, float] = {}
        for rid, v in fused.items():
            sid = eps[rid].session_id or f"#{rid}"
            best[sid] = max(best.get(sid, 0.0), v)
        for rid in fused:
            sid = eps[rid].session_id or f"#{rid}"
            fused[rid] += session_weight * best[sid]

    ranked = sorted(fused, key=lambda r: (-fused[r], r))
    return [Hit(eps[r], fused[r], chans[r]) for r in ranked]


# ------------------------------------------------------------------ packing
_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def excerpt(text: str, query: str, limit: int) -> str:
    """Query-focused excerpt: keep the sentences sharing most terms with the
    query (plus the opening sentence for context), in original order."""
    if len(text) <= limit:
        return text
    sents = [s.strip() for s in _SENT.split(text) if s and s.strip()]
    if len(sents) <= 1:
        return text[:limit].rstrip() + " …"
    qs = {_stem(t) for t in query_terms(query)}
    scored = []
    for i, s in enumerate(sents):
        toks = {_stem(t) for t in query_terms(s)}
        overlap = len(qs & toks)
        scored.append((overlap + (0.5 if i == 0 else 0.0), -i, i))
    keep: List[int] = []
    used = 0
    for _score, _neg, i in sorted(scored, reverse=True):
        cost = len(sents[i]) + 3
        if used + cost > limit:
            if not keep and limit > 40:
                keep.append(i)
                sents[i] = sents[i][:limit - 3].rstrip()
                used = limit
            continue
        keep.append(i)
        used += cost
    keep.sort()
    out, prev = [], None
    for i in keep:
        if prev is not None and i != prev + 1:
            out.append("…")
        out.append(sents[i])
        prev = i
    if keep and keep[0] != 0:
        out.insert(0, "…")
    if keep and keep[-1] != len(sents) - 1:
        out.append("…")
    return " ".join(out)


def _weekday(ts: Optional[str]) -> str:
    d = parse_anchor(ts)
    return d.strftime("%a") if d else ""


def _render_turn(ep: Episode, text: str, annotate_time: bool) -> str:
    body = annotate(text, ep.ts) if annotate_time else text
    role = ep.role or "user"
    if role.lower() in _GENERIC_ROLES and _SPEAKER_PREFIX.match(body):
        return body  # "Caroline: …" already names the speaker
    return f"{role}: {body}"


def _stamp(ts: Optional[str]) -> str:
    d = parse_anchor(ts)
    return f"{d.isoformat()} {d.strftime('%a')}" if d else "undated"


def is_aggregation(query: str) -> bool:
    return bool(_AGG.search(query or ""))


def pack_evidence(store, hits: Sequence[Hit], query: str, char_budget: int = 9000,
                  now: Optional[str] = None, config: RecallConfig = DEFAULT_RECALL,
                  facts: Sequence[RetrievalResult] = (),
                  aggregate: Optional[bool] = None) -> str:
    """Render facts + episode evidence into an answer-ready context block."""
    cfg = config
    if aggregate is None:
        from .retrieval import is_aggregation_query
        aggregate = is_aggregation_query(query)
    header: List[str] = []
    if now:
        d = parse_anchor(now)
        if d:
            header.append(f"(Current date: {d.isoformat()} {d.strftime('%a')})")
    if aggregate:
        header.append("COUNTING / AGGREGATION QUESTION — enumerate every relevant item "
                      "in the evidence below (they may be spread across sessions), then "
                      "give the count or total.")
    head = "\n".join(header)
    used = len(head) + (1 if head else 0)

    fact_lines: List[str] = []
    observations = [r for r in facts if r.kind == "observation"]
    facts = [r for r in facts if r.kind != "observation"]
    if observations:
        ol = ["ENTITY SUMMARIES (synthesized overviews; confirm specifics against the "
              "facts and evidence below):"]
        for r in observations:
            scope = f" [scope={r.scope}]" if r.scope else ""
            ol.append(f"- {r.text}{scope}")
        fact_lines.extend(ol + [""])
        used += sum(len(x) + 1 for x in ol) + 1
    if facts:
        cap = int(char_budget * cfg.fact_share)
        fl = ["KNOWN FACTS (validity window; CURRENT = still true, SUPERSEDED = "
              "true then, later changed):"]
        fused = len(fl[0]) + 1
        ordered = sorted(facts, key=lambda r: r.invalid_at is not None)
        for r in ordered:
            status = "CURRENT" if r.invalid_at is None else f"SUPERSEDED on {(r.invalid_at or '?')[:10]}"
            scope = f" | scope={r.scope}" if r.scope else ""
            line = f"- [{(r.valid_from or '?')[:10]} | {status}{scope}] {r.text}"
            if fused + len(line) + 1 > cap:
                break
            fl.append(line)
            fused += len(line) + 1
        if len(fl) > 1:
            fact_lines.extend(fl)
            used += fused + 1

    titles = {
        "chrono": "CONVERSATION EVIDENCE (grouped by session, oldest first; for current-state "
                  "questions the most recent statement wins):",
        "relevance": "CONVERSATION EVIDENCE (grouped by session, most relevant session first; "
                     "check the session dates for time order):",
        "top": "OTHER CONVERSATION EVIDENCE (grouped by session, oldest first; for "
               "current-state questions the most recent statement wins):",
    }
    layout = cfg.layout if cfg.layout in titles else "chrono"
    title = titles[layout]
    head_title = "MOST RELEVANT EXCERPTS (best match first):"
    used += len(title) + 1 + (len(head_title) + 2 if layout == "top" else 0)
    budget = char_budget - used

    top = hits[0].score if hits else 0.0
    selected: Dict[int, Tuple[Episode, str, bool]] = {}   # id -> (episode, text, is_hit)
    order: Dict[int, int] = {}                            # id -> rank of the hit it serves
    sessions_open: set = set()
    per_session: Dict[str, int] = {}
    cap = cfg.per_session_cap or (cfg.agg_session_cap if aggregate else 0)
    deferred: List[Hit] = []
    header_cost = len("[Session 2023-05-08 Mon]") + 1

    def try_add(ep: Episode, limit: int, is_hit: bool, rank: int) -> bool:
        nonlocal budget
        if ep.id in selected:
            return True
        sid = ep.session_id or f"#{ep.id}"
        overhead = (0 if sid in sessions_open else header_cost) + 4  # line break + possible gap
        room = budget - overhead - len(ep.role or "user") - 4
        if room < min(cfg.min_turn_chars, len(ep.content)):
            return False
        text = excerpt(ep.content, query, min(limit, room))
        line = "  " + _render_turn(ep, text, cfg.annotate_time)
        if overhead + len(line) > budget:  # resolved-date annotations can add a little
            text = excerpt(ep.content, query, max(40, min(limit, room) - (overhead + len(line) - budget)))
            line = "  " + _render_turn(ep, text, cfg.annotate_time)
            if overhead + len(line) > budget:
                return False
        selected[ep.id] = (ep, text, is_hit)
        order[ep.id] = rank
        sessions_open.add(sid)
        budget -= overhead + len(line)
        return True

    for rank, h in enumerate(hits):
        if budget <= 40:
            break
        if cfg.min_relative > 0 and top > 0 and h.score < cfg.min_relative * top:
            break
        sid = h.episode.session_id or f"#{h.episode.id}"
        if cap and per_session.get(sid, 0) >= cap:
            deferred.append(h)
            continue
        limit = cfg.top_turn_chars if rank < cfg.top_hits else cfg.max_turn_chars
        if try_add(h.episode, limit, True, rank):
            per_session[sid] = per_session.get(sid, 0) + 1
            if rank < cfg.neighbor_top and cfg.neighbors > 0:
                for nb in store.episode_neighbors(h.episode, cfg.neighbors):
                    if nb.id not in selected:
                        try_add(nb, cfg.neighbor_chars, False, rank)
    for h in deferred:
        if budget <= 40:
            break
        try_add(h.episode, cfg.max_turn_chars, True, len(hits))
    if cfg.neighbors > 0:
        for rank, h in enumerate(hits):
            if budget <= cfg.min_turn_chars:
                break
            if h.episode.id not in selected:
                continue
            for nb in store.episode_neighbors(h.episode, cfg.neighbors):
                if nb.id not in selected:
                    try_add(nb, cfg.neighbor_chars, False, rank)

    lines: List[str] = []
    if head:
        lines.append(head)
    lines.extend(fact_lines)
    if fact_lines:
        lines.append("")
    head_ids: List[int] = []
    if layout == "top":
        head_ids = sorted((eid for eid, (_e, _t, is_hit) in selected.items() if is_hit),
                          key=lambda eid: order[eid])[:cfg.top_section]
        if head_ids:
            lines.append(head_title)
            for eid in head_ids:
                ep, text, _ = selected[eid]
                lines.append(f"- [{_stamp(ep.ts)}] " + _render_turn(ep, text, cfg.annotate_time))
            lines.append("")
    by_session: Dict[str, List[Tuple[Episode, str, bool]]] = {}
    for eid, (ep, text, is_hit) in selected.items():
        if eid in head_ids:
            continue
        by_session.setdefault(ep.session_id or f"#{ep.id}", []).append((ep, text, is_hit))

    def s_key(item):
        eps = item[1]
        if layout == "relevance":
            return (min(order[e.id] for e, _, _ in eps), min(e.id for e, _, _ in eps))
        return (min((e.ts or "") for e, _, _ in eps), min(e.id for e, _, _ in eps))
    if by_session:
        lines.append(title)
    for _sid, items in sorted(by_session.items(), key=s_key):
        items.sort(key=lambda x: x[0].id)
        lines.append(f"[Session {_stamp(items[0][0].ts)}]")
        prev_id = None
        for ep, text, _is_hit in items:
            if prev_id is not None and ep.id != prev_id + 1:
                lines.append("  …")
            lines.append("  " + _render_turn(ep, text, cfg.annotate_time))
            prev_id = ep.id
    out = "\n".join(lines)
    if len(out) > char_budget:  # annotations can add a little; never exceed
        out = out[:char_budget - 12].rstrip() + "\n[truncated]"
    return out
