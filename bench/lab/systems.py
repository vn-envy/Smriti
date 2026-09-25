"""System adapters for the lab. Every adapter sees the same turns, the same
vectors (shared cache), the same question date and the same character budget.

Adapter contract::

    sys.build(case)                       # ingest every session of the case
    ranked, context = sys.query(q, budget) # ranked turn ids + packed context

``ranked`` is scored for retrieval recall; ``context`` is what a reader model
would receive, scored for evidence *survival* (does the supporting utterance
appear, complete, in the text the reader actually gets?).
"""
from __future__ import annotations

import re
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

from .data import Case, Question
from .embed import lab_embedder

RANK_DEPTH = 50

_TOKEN = re.compile(r"\w+", re.UNICODE)
STOP = set("""a an the and or but if of at by for with about against between into through
during before after above below to from up down in out on off over under again further then
once here there when where why how all any both each few more most other some such no nor not
only own same so than too very s t can will just don should now i me my myself we our ours
ourselves you your yours yourself yourselves he him his himself she her hers herself it its
itself they them their theirs themselves what which who whom this that these those am is are
was were be been being have has had having do does did doing would could ought i'm you're he's
she's it's we're they're i've you've we've they've i'd you'd he'd she'd we'd they'd i'll you'll
he'll she'll we'll they'll isn't aren't wasn't weren't hasn't haven't hadn't doesn't don't
didn't won't wouldn't shan't shouldn't can't cannot couldn't mustn't let's that's who's what's
here's there's when's where's why's how's""".split())


def tokenize(text: str, stop: bool = True) -> List[str]:
    toks = [t.lower() for t in _TOKEN.findall(text)]
    return [t for t in toks if not (stop and t in STOP)]


def render_turn(ts: Optional[str], role: str, content: str) -> str:
    return f"- [{(ts or '?')[:10]}] {role}: {content}"


def pack_ranked(turns: List[Tuple[str, Optional[str], str, str]], budget: int) -> str:
    """Generic packer for baselines: rank order, full turns, hard budget."""
    lines, used = ["RAW CONVERSATION EVIDENCE (ranked):"], 0
    for _tid, ts, role, content in turns:
        line = render_turn(ts, role, content)
        if used + len(line) + 1 > budget:
            room = budget - used - 1
            if room > 80:
                lines.append(line[:room])
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


class _TurnCorpus:
    def build(self, case: Case) -> None:
        self.case = case
        self.ids, self.meta = [], []
        for s in case.sessions:
            for t in s.turns:
                self.ids.append(t.turn_id)
                self.meta.append((t.turn_id, s.ts, t.role, t.content))


class BM25System(_TurnCorpus):
    name = "bm25"

    def build(self, case: Case) -> None:
        from rank_bm25 import BM25Okapi
        super().build(case)
        self.bm25 = BM25Okapi([tokenize(m[3]) or ["_"] for m in self.meta])

    def query(self, q: Question, budget: int):
        scores = self.bm25.get_scores(tokenize(q.question) or ["_"])
        order = np.argsort(-scores)
        ranked = [self.ids[i] for i in order[:RANK_DEPTH]]
        return ranked, pack_ranked([self.meta[i] for i in order[:200]], budget)


class DenseSystem(_TurnCorpus):
    name = "dense"

    def build(self, case: Case) -> None:
        super().build(case)
        self.emb = lab_embedder()
        self.mat = self.emb.embed_np([m[3] for m in self.meta])

    def query(self, q: Question, budget: int):
        qv = self.emb.embed_np([q.question])[0]
        order = np.argsort(-(self.mat @ qv))
        ranked = [self.ids[i] for i in order[:RANK_DEPTH]]
        return ranked, pack_ranked([self.meta[i] for i in order[:200]], budget)


class SmritiSystem:
    """Smriti through its public API (lite mode: no LLM at write time).

    ``search_kw`` / ``context_kw`` / ``init_kw`` select the configuration
    under test, so baseline and variants differ only in declared options.
    """

    def __init__(self, name: str = "smriti", init_kw: Optional[dict] = None,
                 search_kw: Optional[dict] = None, context_kw: Optional[dict] = None,
                 pass_now: bool = True):
        self.name = name
        self.init_kw = init_kw or {}
        self.search_kw = search_kw or {}
        self.context_kw = context_kw or {}
        self.pass_now = pass_now

    def build(self, case: Case) -> None:
        from smriti import Smriti
        self.mem = Smriti(path=":memory:", embedder=lab_embedder(), mode="lite",
                          **self.init_kw)
        order: List[str] = []
        for s in case.sessions:
            msgs = [{"role": t.role, "content": t.content} for t in s.turns]
            self.mem.add(msgs, session_id=s.session_id, timestamp=s.ts)
            order.extend(t.turn_id for t in s.turns)
        rows = [r[0] for r in self.mem.store.db.execute("SELECT id FROM episodes ORDER BY id")]
        assert len(rows) == len(order), (len(rows), len(order))
        self.ep2turn: Dict[int, str] = dict(zip(rows, order))

    def query(self, q: Question, budget: int):
        now = q.question_date if self.pass_now else None
        res = self.mem.search(q.question, k=RANK_DEPTH, now=now, **self.search_kw)
        ranked = []
        for r in res:
            if r.kind == "episode" and r.id in self.ep2turn:
                ranked.append(self.ep2turn[r.id])
        ctx = self.mem.context(q.question, now=now, char_budget=budget, **self.context_kw)
        return ranked, ctx

    def close(self):
        self.mem.close()


class Mem0System:
    """Mem0 OSS (``mem0ai``) with ``infer=False``: every turn is stored as a
    memory (session timestamp as ``created_at``), searched with Mem0's own
    hybrid scoring (semantic + spaCy-lemmatized BM25 + entity boosts). No LLM
    is called. Vectors come from the same shared ONNX embedder as every other
    arm. Mem0 has no context packer, so results are listed in its ranked
    order with timestamps up to the shared character budget."""

    name = "mem0"

    def build(self, case: Case) -> None:
        import logging
        import os
        import tempfile
        import uuid
        os.environ.setdefault("MEM0_TELEMETRY", "False")
        os.environ.setdefault("OPENAI_API_KEY", "unused-infer-false")
        logging.getLogger("mem0").setLevel(logging.ERROR)
        from mem0 import Memory
        self.root = tempfile.mkdtemp(prefix="lab-mem0-")
        emb = lab_embedder()
        dims = len(emb.embed(["dimension probe"])[0])
        cfg = {
            "vector_store": {"provider": "qdrant", "config": {
                "path": os.path.join(self.root, "qdrant"),
                "collection_name": "lab_" + uuid.uuid4().hex[:12],
                "embedding_model_dims": dims}},
            "history_db_path": os.path.join(self.root, "history.db"),
        }
        self.memory = Memory.from_config(cfg)
        # Mem0's hybrid BM25 half needs fastembed's "Qdrant/bm25" sparse encoder,
        # normally fetched from Hugging Face. It is a Snowball stemmer plus a
        # stopword list, so it is built from a local directory holding
        # english.txt (SMRITI_LAB_QDRANT_BM25) when the hub is unreachable.
        bm25_dir = os.environ.get("SMRITI_LAB_QDRANT_BM25", "/home/user/data/qdrant_bm25")
        if os.path.isdir(bm25_dir):
            from fastembed import SparseTextEmbedding
            self.memory.vector_store._bm25_encoder = SparseTextEmbedding(
                model_name="Qdrant/bm25", specific_model_path=bm25_dir)

        class _Shim:
            def embed(self, text, memory_action=None):
                return emb.embed([text])[0]
        self.memory.embedding_model = _Shim()
        self.user = "u" + uuid.uuid4().hex[:8]
        self.meta: Dict[str, Tuple[Optional[str], str, str]] = {}
        for s in case.sessions:
            for t in s.turns:
                self.meta[t.turn_id] = (s.ts, t.role, t.content)
                self.memory.add([{"role": t.role, "content": t.content}], user_id=self.user,
                                infer=False, metadata={"turn_id": t.turn_id,
                                                       "session_id": s.session_id,
                                                       "created_at": s.ts})

    def query(self, q: Question, budget: int):
        raw = self.memory.search(q.question, top_k=100, filters={"user_id": self.user})
        rows = raw.get("results", raw) if isinstance(raw, dict) else raw
        ranked = []
        for row in rows:
            tid = (row.get("metadata") or {}).get("turn_id")
            if tid and tid not in ranked:
                ranked.append(tid)
        turns = [(tid, *self.meta[tid]) for tid in ranked if tid in self.meta]
        return ranked[:RANK_DEPTH], pack_ranked(turns, budget)

    def close(self):
        import shutil
        for res in (getattr(self.memory, "db", None), getattr(self.memory, "vector_store", None)):
            close = getattr(res, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        shutil.rmtree(self.root, ignore_errors=True)
