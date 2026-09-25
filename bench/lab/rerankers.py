"""Rerankers for lab arms: decision models, an oracle ceiling and a lexical floor.

``ev(rerank=NAME,...)`` in ``configs.variant`` builds one of:

* ``oracle`` — knows the gold evidence turns of the current question and
  scores them 1.0, everything else 0.0 (stable sort keeps fused order). It is
  the most any reranker can add at a given ``rerank_depth``.
* ``overlap`` — query/turn token overlap; a dumb judge used as a floor.
* ``laya`` — Laya in-process (``pip install laya``). ``SMRITI_LAB_LAYA`` names a
  hub id or local checkpoint dir (default ``convaiinnovations/laya``),
  ``SMRITI_LAB_LAYA_SUBFOLDER`` an optional bundle subfolder.
* ``laya_http`` — a ``laya-serve`` endpoint (``SMRITI_LAB_LAYA_URL``,
  default ``http://127.0.0.1:8000``).
* ``jev`` — hosted TypeSafe Jev (``api.typesafe.ai``). The key comes from
  ``TYPESAFE_API_KEY`` or the file named by ``SMRITI_LAB_JEV_KEY_FILE``; it is
  never logged. Priced at ``SMRITI_LAB_JEV_PRICE`` USD per 1M input tokens
  (default 0.042, the published list price).
* ``clm`` — a ``clm-serve`` endpoint (``CLM_BASE_URL``, default
  ``http://127.0.0.1:8700``), scored with a ``choice`` over the candidates.

``rerank_mode`` (``noul`` / ``fanout`` / ``choice``) overrides the HTTP mode.
Every reranker is wrapped in :class:`CachedReranker`, so the lab's
``search()`` + ``context()`` pair pays for one judgement per question.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Set

from smriti.decision import DecisionStats, LayaReranker, SystemOneReranker


class OracleReranker:
    def __init__(self):
        self.gold: Set[str] = set()
        self.stats = DecisionStats()
        self.cost_usd = 0.0

    def set_gold(self, texts: Set[str]) -> None:
        self.gold = set(texts)

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        self.stats.add(calls=1, docs=len(docs))
        return [1.0 if d in self.gold else 0.0 for d in docs]


class OverlapReranker:
    def __init__(self):
        self.stats = DecisionStats()
        self.cost_usd = 0.0

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        q = {w.strip("?.,!'\"").lower() for w in query.split() if len(w) > 3}
        self.stats.add(calls=1, docs=len(docs))
        return [len(q & {w.strip("?.,!'\"").lower() for w in d.split()}) / max(1, len(q))
                for d in docs]


class DryRunReranker:
    """Sends nothing: counts the input tokens (about 4 characters per token)
    that a System One request in ``mode`` would carry, to project hosted cost."""

    def __init__(self, mode: str = "noul", price_per_mtok: float = 0.042):
        import json
        from smriti.decision import RELEVANCE_INSTRUCTIONS, _clip
        self._json, self._inst, self._clip = json, RELEVANCE_INSTRUCTIONS, _clip
        self.mode, self.price_per_mtok = mode, price_per_mtok
        self.stats = DecisionStats()

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        q = {"type": "noul", "instructions": self._inst}
        if self.mode == "fanout":
            n, chars = 0, 0
            for i in range(0, len(docs), 12):
                group = docs[i:i + 12]
                state = {"question": query,
                         "memories": {f"m{j}": self._clip(d, 1500) for j, d in enumerate(group)}}
                chars += len(self._json.dumps(state)) + len(group) * (len(self._inst) + 20)
                n += 1
        else:
            n = len(docs)
            chars = sum(len(self._json.dumps({"question": query, "memory": self._clip(d, 1500)}))
                        + len(self._json.dumps(q)) for d in docs)
        self.stats.add(calls=1, requests=n, docs=len(docs), input_tokens=chars // 4)
        return [0.0] * len(docs)

    @property
    def cost_usd(self) -> float:
        return self.stats.input_tokens / 1e6 * self.price_per_mtok


class DiskCachedJudge:
    """Persists each (judge, question, memory) score in SQLite so budgets and
    blend weights reuse one judgement. Only uncached candidates reach the
    model, so ``stats`` (and latency) describe real model work alone."""

    def __init__(self, inner, path: str, tag: str):
        import sqlite3
        self.inner, self.tag = inner, tag
        self.stats = inner.stats
        self.db = sqlite3.connect(path, timeout=60, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS judge(k TEXT PRIMARY KEY, v REAL)")
        self.db.commit()

    def _key(self, query: str, doc: str) -> str:
        import hashlib
        return hashlib.sha1(f"{self.tag}\x00{query}\x00{doc}".encode()).hexdigest()

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        keys = [self._key(query, d) for d in docs]
        have = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            marks = ",".join("?" * len(chunk))
            have.update(self.db.execute(f"SELECT k, v FROM judge WHERE k IN ({marks})", chunk))
        todo = [i for i, k in enumerate(keys) if k not in have]
        if todo:
            errors_before = self.stats.errors
            vals = self.inner.rerank(query, [docs[i] for i in todo])
            if self.stats.errors == errors_before:        # never cache a failed batch
                self.db.executemany("INSERT OR REPLACE INTO judge VALUES (?, ?)",
                                    [(keys[i], float(v)) for i, v in zip(todo, vals)])
                self.db.commit()
            for i, v in zip(todo, vals):
                have[keys[i]] = float(v)
        return [have[k] for k in keys]

    @property
    def cost_usd(self) -> float:
        return getattr(self.inner, "cost_usd", 0.0)


class CachedReranker:
    """Memoises the last judgement so search() and context() share one call."""

    def __init__(self, inner):
        self.inner = inner
        self._key = None
        self._val: List[float] = []
        self._mark = inner.stats.as_dict()
        self._cost_mark = getattr(inner, "cost_usd", 0.0)

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        key = (query, tuple(docs))
        if key != self._key:
            self._val = list(self.inner.rerank(query, docs))
            self._key = key
        return list(self._val)

    def usage_delta(self) -> Dict[str, float]:
        now = self.inner.stats.as_dict()
        cost = getattr(self.inner, "cost_usd", 0.0)
        out = {"rerank_ms": round(1000 * (now["seconds"] - self._mark["seconds"]), 2),
               "rerank_requests": now["requests"] - self._mark["requests"],
               "rerank_docs": now["docs"] - self._mark["docs"],
               "rerank_tokens": now["input_tokens"] - self._mark["input_tokens"],
               "rerank_errors": now["errors"] - self._mark["errors"],
               "rerank_usd": round(cost - self._cost_mark, 8)}
        self._mark, self._cost_mark = now, cost
        return out


def _jev_key() -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    path = os.environ.get("SMRITI_LAB_JEV_KEY_FILE", "")
    if not key and path:
        with open(path) as f:
            key = f.read().strip()
    if not key:
        raise SystemExit("jev arm needs TYPESAFE_API_KEY or SMRITI_LAB_JEV_KEY_FILE")
    return key


_MODELS: Dict[tuple, object] = {}


def make_reranker(name: str, mode: Optional[str] = None):
    """One instance per (name, mode) per process: model weights load once.

    With ``SMRITI_LAB_JUDGE_CACHE`` set, model judges persist their scores
    there (keyed by judge, mode and model id)."""
    key = (name, mode)
    if key not in _MODELS:
        judge = _build(name, mode)
        path = os.environ.get("SMRITI_LAB_JUDGE_CACHE")
        if path and name in ("laya", "laya_http", "jev", "clm"):
            model = os.environ.get("SMRITI_LAB_LAYA", "") if name == "laya" else ""
            judge = DiskCachedJudge(judge, path, f"{name}:{mode}:{model}")
        _MODELS[key] = judge
    return _MODELS[key]


def _build(name: str, mode: Optional[str]):
    if name == "oracle":
        return OracleReranker()
    if name == "overlap":
        return OverlapReranker()
    if name == "dryrun":
        return DryRunReranker(mode=mode or "noul",
                              price_per_mtok=float(os.environ.get("SMRITI_LAB_JEV_PRICE", "0.042")))
    if name == "laya":
        return LayaReranker(model=os.environ.get("SMRITI_LAB_LAYA", "convaiinnovations/laya"),
                            subfolder=os.environ.get("SMRITI_LAB_LAYA_SUBFOLDER") or None,
                            device=os.environ.get("SMRITI_LAB_LAYA_DEVICE", "cpu"),
                            threads=int(os.environ.get("SMRITI_LAB_LAYA_THREADS", "0")) or None)
    if name == "laya_http":
        return SystemOneReranker(base_url=os.environ.get("SMRITI_LAB_LAYA_URL",
                                                         "http://127.0.0.1:8000"),
                                 model=None, mode=mode or "noul")
    if name == "jev":
        return SystemOneReranker(base_url=os.environ.get("TYPESAFE_BASE_URL",
                                                         "https://api.typesafe.ai"),
                                 api_key=_jev_key(), model="jev-latest", mode=mode or "noul",
                                 workers=int(os.environ.get("SMRITI_LAB_JEV_WORKERS", "8")),
                                 price_per_mtok=float(os.environ.get("SMRITI_LAB_JEV_PRICE",
                                                                     "0.042")))
    if name == "clm":
        return SystemOneReranker(base_url=os.environ.get("CLM_BASE_URL", "http://127.0.0.1:8700"),
                                 api_key=os.environ.get("CLM_API_KEY", ""), model=None,
                                 mode=mode or "choice")
    raise SystemExit(f"unknown reranker {name!r}")
