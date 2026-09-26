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
import time
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
        import threading
        self.inner, self.tag = inner, tag
        self.stats = inner.stats
        self._lock = threading.Lock()          # pool_eval.py judges questions in threads
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
        with self._lock:
            for i in range(0, len(keys), 500):
                chunk = keys[i:i + 500]
                marks = ",".join("?" * len(chunk))
                have.update(self.db.execute(f"SELECT k, v FROM judge WHERE k IN ({marks})", chunk))
        todo = [i for i, k in enumerate(keys) if k not in have]
        if todo:
            errors_before = self.stats.errors
            vals = self.inner.rerank(query, [docs[i] for i in todo])
            if self.stats.errors == errors_before:        # never cache a failed batch
                with self._lock:
                    self.db.executemany("INSERT OR REPLACE INTO judge VALUES (?, ?)",
                                        [(keys[i], float(v)) for i, v in zip(todo, vals)])
                    self.db.commit()
            for i, v in zip(todo, vals):
                have[keys[i]] = float(v)
        return [have[k] for k in keys]

    @property
    def cost_usd(self) -> float:
        return getattr(self.inner, "cost_usd", 0.0)


class LearnedHeadReranker:
    """A logistic head trained on labelled (question, candidate) pairs (round 2).

    ``kind`` = ``smriti`` (Smriti's own signals only), ``laya`` (frozen Laya-family
    encoder features) or ``both``. Encoder vectors are cached in SQLite
    (``SMRITI_LAB_FEAT_CACHE``) so repeated budgets reuse them; ``stats`` counts
    only fresh encoder work. Features must match ``round2/extract.py``.
    """

    MAX_TOK, MAX_CHARS = 384, 1500

    def __init__(self, head_path: str, model_dir: Optional[str] = None,
                 feat_cache: Optional[str] = None):
        import numpy as np
        h = np.load(head_path)
        self.np = np
        self.w, self.b = h["w"], float(h["b"])
        self.mu, self.sd = h["mu"], h["sd"]
        self.kind = str(h["kind"])
        self.sm_cols = list(h["sm_cols"])
        self.stats = DecisionStats()
        self.cost_usd = 0.0
        self.enc = self.tok = self.db = None
        if self.kind in ("laya", "both"):
            import torch
            import laya
            torch.set_num_threads(int(os.environ.get("SMRITI_LAB_LAYA_THREADS", "4")))
            agent = laya.load(model_dir, device="cpu")
            self.enc, self.tok, self.torch = agent.model.encoder, agent.tok, torch
            self.enc.eval()
            if feat_cache:
                import sqlite3
                self.db = sqlite3.connect(feat_cache, timeout=60, check_same_thread=False)
                self.db.execute("PRAGMA journal_mode=WAL")
                self.db.execute("CREATE TABLE IF NOT EXISTS feat(k TEXT PRIMARY KEY, v BLOB)")

    def _encode(self, query: str, texts: List[str]):
        import hashlib
        np = self.np
        keys = [hashlib.sha1(f"{query}\x00{t}".encode()).hexdigest() for t in texts]
        out = [None] * len(texts)
        if self.db is not None:
            marks = ",".join("?" * len(keys))
            got = dict(self.db.execute(f"SELECT k, v FROM feat WHERE k IN ({marks})", keys))
            for i, k in enumerate(keys):
                if k in got:
                    out[i] = np.frombuffer(got[k], dtype=np.float16).astype(np.float32)
        todo = [i for i, v in enumerate(out) if v is None]
        if todo:
            t0 = time.perf_counter()
            with self.torch.no_grad():
                batch = self.tok([query] * len(todo), [texts[i][:self.MAX_CHARS] for i in todo],
                                 truncation="only_second", max_length=self.MAX_TOK, padding=True,
                                 return_tensors="pt")
                hid = self.enc(input_ids=batch["input_ids"],
                               attention_mask=batch["attention_mask"]).last_hidden_state
                m = batch["attention_mask"].unsqueeze(-1).float()
                vecs = ((hid * m).sum(1) / m.sum(1)).numpy()
            for j, i in enumerate(todo):
                out[i] = vecs[j].astype(np.float16).astype(np.float32)
            if self.db is not None:
                self.db.executemany("INSERT OR REPLACE INTO feat VALUES (?, ?)",
                                    [(keys[i], vecs[j].astype(np.float16).tobytes())
                                     for j, i in enumerate(todo)])
                self.db.commit()
            self.stats.add(requests=1, docs=len(todo), seconds=time.perf_counter() - t0)
        return np.stack(out)

    def rerank_hits(self, query: str, hits) -> List[float]:
        np = self.np
        top = hits[0].score or 1.0
        parts = []
        if self.kind in ("smriti", "both"):
            sm = np.array([[h.score, h.score / top, i, float(h.episode.role == "assistant"),
                            float(np.log1p(len(h.episode.content))), 0.0]
                           for i, h in enumerate(hits)], dtype=np.float32)
            parts.append(sm[:, self.sm_cols])
        if self.kind in ("laya", "both"):
            parts.append(self._encode(query, [h.episode.content for h in hits]))
        x = (np.concatenate(parts, axis=1) - self.mu) / self.sd
        z = x @ self.w + self.b
        self.stats.add(calls=1)
        return list(1.0 / (1.0 + np.exp(-z)))

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:  # pragma: no cover
        raise TypeError("LearnedHeadReranker needs rerank_hits (Smriti >= 0.4 hit-aware hook)")


class CachedReranker:
    """Memoises the last judgement so search() and context() share one call."""

    def __init__(self, inner):
        self.inner = inner
        self._key = None
        self._val: List[float] = []
        self._mark = inner.stats.as_dict()
        self._cost_mark = getattr(inner, "cost_usd", 0.0)
        if hasattr(inner, "rerank_hits"):
            self.rerank_hits = self._rerank_hits

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        key = (query, tuple(docs))
        if key != self._key:
            self._val = list(self.inner.rerank(query, docs))
            self._key = key
        return list(self._val)

    def _rerank_hits(self, query: str, hits) -> List[float]:
        key = (query, tuple(h.episode.id for h in hits))
        if key != self._key:
            self._val = list(self.inner.rerank_hits(query, hits))
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
    if name.startswith("learned_"):
        head_dir = os.environ.get("SMRITI_LAB_HEAD_DIR", "")
        return LearnedHeadReranker(os.path.join(head_dir, f"head_{name[len('learned_'):]}.npz"),
                                   model_dir=os.environ.get("SMRITI_LAB_LAYA"),
                                   feat_cache=os.environ.get("SMRITI_LAB_FEAT_CACHE"))
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
