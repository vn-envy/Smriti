"""Dataset loaders producing one uniform shape for every lab benchmark.

A *case* is one memory store plus the questions asked against it:

    Case(case_id, sessions=[Session(session_id, ts, turns=[Turn(...)])],
         questions=[Question(...)])

``Turn.turn_id`` is globally unique inside a case and is the unit evidence is
labelled at, so retrieval can be scored at turn level (did the supporting
utterance come back?) rather than only at session level.

Datasets
--------
* ``locomo``  — the full LoCoMo10 release (10 conversations, 1,986 QA). Each
  conversation is one case. Evidence = the QA ``evidence`` dialog ids.
* ``lmex``    — LongMemEval with a *cross-question distractor haystack*. The
  full LongMemEval-S file is not reachable from every environment, so this
  builds a harder-than-oracle haystack from the evidence-session release: each
  question keeps its own evidence sessions (true dates) and receives
  ``distractors`` sessions drawn from other questions' evidence sessions,
  re-dated uniformly before the question date. Evidence = ``has_answer``
  turns. This is NOT the official LongMemEval-S haystack and results must be
  labelled ``LME-X`` rather than compared with published LongMemEval-S scores.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

LOCOMO_CATEGORIES = {1: "multi-hop", 2: "temporal", 3: "open-domain",
                     4: "single-hop", 5: "adversarial"}


@dataclass
class Turn:
    turn_id: str
    role: str
    content: str
    ts: Optional[str] = None


@dataclass
class Session:
    session_id: str
    ts: Optional[str]
    turns: List[Turn]


@dataclass
class Question:
    qid: str
    question: str
    answer: str
    category: str
    question_date: Optional[str]
    evidence_turns: List[str] = field(default_factory=list)
    evidence_sessions: List[str] = field(default_factory=list)
    abstention: bool = False


@dataclass
class Case:
    case_id: str
    sessions: List[Session]
    questions: List[Question]

    def turn_index(self) -> Dict[str, Turn]:
        return {t.turn_id: t for s in self.sessions for t in s.turns}

    def turn_session(self) -> Dict[str, str]:
        return {t.turn_id: s.session_id for s in self.sessions for t in s.turns}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- LoCoMo
def parse_locomo_date(s: Optional[str]) -> Optional[str]:
    """'1:56 pm on 8 May, 2023' -> '2023-05-08T13:56:00Z' (time kept)."""
    if not s:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", s, re.I)
    months = {mo.lower()[:3]: i + 1 for i, mo in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
    if m:
        hh, mm, ap, d, mon, y = m.groups()
        hh = int(hh) % 12 + (12 if ap.lower() == "pm" else 0)
        mo = months.get(mon.lower()[:3])
        if mo:
            return datetime(int(y), mo, int(d), hh, int(mm)).strftime("%Y-%m-%dT%H:%M:%SZ")
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})", s)
    if m and months.get(m.group(2).lower()[:3]):
        return datetime(int(m.group(3)), months[m.group(2).lower()[:3]],
                        int(m.group(1))).strftime("%Y-%m-%dT%H:%M:%SZ")
    return None


def load_locomo(path: str, categories: Iterable[int] = (1, 2, 3, 4, 5)) -> List[Case]:
    data = json.load(open(path))
    cats = set(categories)
    cases = []
    for ci, item in enumerate(data):
        conv = item["conversation"]
        cid = str(item.get("sample_id") or f"conv-{ci}")
        keys = sorted((k for k in conv if re.fullmatch(r"session_\d+", k)),
                      key=lambda k: int(k.split("_")[1]))
        sessions = []
        for key in keys:
            ts = parse_locomo_date(conv.get(f"{key}_date_time"))
            turns = []
            for t in conv.get(key) or []:
                text = t.get("text") or t.get("clean_text") or ""
                if t.get("blip_caption"):
                    text = f"{text} [shared an image: {t['blip_caption']}]".strip()
                if not text:
                    continue
                turns.append(Turn(turn_id=f"{cid}:{t['dia_id']}", role="user",
                                  content=f"{t.get('speaker', 'user')}: {text}", ts=ts))
            if turns:
                sessions.append(Session(f"{cid}:{key}", ts, turns))
        known = {t.turn_id for s in sessions for t in s.turns}
        tsess = {t.turn_id: s.session_id for s in sessions for t in s.turns}
        questions = []
        for qi, q in enumerate(item.get("qa", [])):
            cat = int(q.get("category", 0))
            if cat not in cats:
                continue
            ev = []
            for e in q.get("evidence", []) or []:
                # a few labels pack several ids into one string ("D8:6; D9:17")
                for part in re.split(r"[;,\s]+", str(e)):
                    part = part.strip()
                    if re.fullmatch(r"D\d+:\d+", part) and f"{cid}:{part}" in known:
                        ev.append(f"{cid}:{part}")
            ev = list(dict.fromkeys(ev))
            last_ts = sessions[-1].ts if sessions else None
            questions.append(Question(
                qid=f"{cid}-q{qi}", question=q.get("question", ""),
                answer=str(q.get("answer", q.get("adversarial_answer", ""))),
                category=LOCOMO_CATEGORIES.get(cat, str(cat)),
                question_date=last_ts, evidence_turns=ev,
                evidence_sessions=list(dict.fromkeys(tsess[e] for e in ev)),
                abstention=(cat == 5)))
        cases.append(Case(cid, sessions, questions))
    return cases


# ------------------------------------------------------------ LongMemEval
def parse_lme_date(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})(?:.*?(\d{1,2}):(\d{2}))?", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return datetime(y, mo, d, int(m.group(4) or 0), int(m.group(5) or 0)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:8], "big")


def load_lmex(path: str, distractors: int = 48, seed: str = "lmex-v1",
              limit: Optional[int] = None, qtypes: Optional[Sequence[str]] = None,
              include_abstention: bool = True) -> List[Case]:
    """LongMemEval evidence sessions + cross-question distractor haystack."""
    data = json.load(open(path))
    pool: Dict[str, dict] = {}
    owner: Dict[str, set] = {}
    for item in data:
        for sid, date, sess in zip(item["haystack_session_ids"], item["haystack_dates"],
                                   item["haystack_sessions"]):
            pool.setdefault(sid, {"date": date, "turns": sess})
            owner.setdefault(sid, set()).add(item["question_id"])
    pool_ids = sorted(pool)
    # Questions that share any evidence session are "related": never use one's
    # sessions as the other's distractors (they may carry competing answers).
    related: Dict[str, set] = {}
    for sid, qs in owner.items():
        for q in qs:
            related.setdefault(q, set()).update(qs)

    def base_qid(qid: str) -> str:
        return qid[:-4] if qid.endswith("_abs") else qid

    cases = []
    for item in data:
        qid = item["question_id"]
        abstention = qid.endswith("_abs")
        if abstention and not include_abstention:
            continue
        if qtypes and item["question_type"] not in qtypes:
            continue
        qdate = parse_lme_date(item["question_date"])
        own = list(zip(item["haystack_session_ids"], item["haystack_dates"], item["haystack_sessions"]))
        own_dates = [parse_lme_date(d) for _, d, _ in own]
        start = min(d for d in own_dates if d)
        lo = datetime.strptime(start[:10], "%Y-%m-%d") - timedelta(days=180)
        hi = datetime.strptime(qdate[:16], "%Y-%m-%dT%H:%M")
        rng = random.Random(_seed(seed, qid))
        banned = set(item["haystack_session_ids"])
        rel = related.get(qid, set()) | related.get(base_qid(qid), set()) | {qid, base_qid(qid), base_qid(qid) + "_abs"}
        candidates = [sid for sid in pool_ids
                      if sid not in banned and not (owner[sid] & rel)]
        picks = rng.sample(candidates, min(distractors, len(candidates)))
        sessions: List[tuple] = []
        for sid, d, sess in own:
            sessions.append((parse_lme_date(d), sid, sess, True))
        span = max(60, int((hi - lo).total_seconds()))
        for sid in picks:
            ts = (lo + timedelta(seconds=rng.randrange(span))).strftime("%Y-%m-%dT%H:%M:00Z")
            sessions.append((ts, sid, pool[sid]["turns"], False))
        sessions.sort(key=lambda x: (x[0] or "", x[1]))
        out_sessions, ev_turns, ev_sessions = [], [], []
        for ts, sid, sess, is_own in sessions:
            turns = []
            for ti, t in enumerate(sess):
                if not t.get("content"):
                    continue
                tid = f"{sid}#{ti}"
                turns.append(Turn(tid, t.get("role", "user"), t["content"], ts))
                if is_own and t.get("has_answer"):
                    ev_turns.append(tid)
            if is_own and sid in item["answer_session_ids"]:
                ev_sessions.append(sid)
            out_sessions.append(Session(sid, ts, turns))
        q = Question(qid=qid, question=item["question"], answer=str(item["answer"]),
                     category=item["question_type"], question_date=qdate,
                     evidence_turns=ev_turns, evidence_sessions=ev_sessions,
                     abstention=abstention)
        cases.append(Case(qid, out_sessions, [q]))
        if limit and len(cases) >= limit:
            break
    return cases


def stratified(cases: List[Case], n: int, key=lambda c: c.questions[0].category,
               seed: str = "strat-v1") -> List[Case]:
    """Deterministic round-robin sample over categories (seeded shuffle)."""
    groups: Dict[str, List[Case]] = {}
    for c in cases:
        groups.setdefault(key(c), []).append(c)
    for k in groups:
        groups[k].sort(key=lambda c: _seed(seed, c.case_id))
    out, i = [], 0
    names = sorted(groups)
    while len(out) < n and any(i < len(groups[g]) for g in names):
        for g in names:
            if i < len(groups[g]) and len(out) < n:
                out.append(groups[g][i])
        i += 1
    return out
