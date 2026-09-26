"""Decision-model ("System One") rerankers — *nirnaya* (निर्णय, a decision).

A System One model answers typed questions (``noul`` = P(true), ``choice``,
``score``) about a state in one forward pass instead of generating text.
Asked "does this memory help answer the question?", it becomes a relevance
judge that can re-examine the head of Smriti's ranked evidence.

Three backends speak the same TypeSafe wire protocol
(``POST {base_url}/v1/systemone`` with ``{state, model, questions}``):

* hosted **Jev** (``https://api.typesafe.ai``, ``Authorization: Bearer <key>``),
* a local **Laya** server (``laya-serve``, Apache-2.0, ModernBERT encoders),
* a local **CLM** server (``clm-serve``, Contrastive-LM heads on Qwen3-8B).

:class:`SystemOneReranker` talks to any of them over stdlib HTTP.
:class:`LayaReranker` runs Laya in-process when the optional ``laya``
package is installed. Both keep :class:`DecisionStats` (calls, tokens,
seconds, errors) so latency and cost can be reported next to quality.

Everything here is optional: the core never imports it, and nothing leaves
the process unless the caller points a reranker at a remote endpoint.
Enterprise egress checks see ``base_url`` like any other adapter.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Sequence

from .embedder import _post_json

RELEVANCE_INSTRUCTIONS = ("Does the memory contain information that helps answer the "
                          "question? Answer true only if it states a fact, event, date, "
                          "preference or detail the question asks about.")
CHOICE_INSTRUCTIONS = "Which memory best helps answer the question?"


class DecisionStats:
    """Thread-safe usage counters for one reranker instance."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with getattr(self, "_lock", threading.Lock()):
            self.calls = 0          # rerank() invocations
            self.requests = 0       # model requests (HTTP calls or forward batches)
            self.docs = 0           # candidates judged
            self.input_tokens = 0   # as reported by the backend (0 if unreported)
            self.seconds = 0.0      # wall time inside rerank()
            self.errors = 0

    def add(self, **kw) -> None:
        with self._lock:
            for k, v in kw.items():
                setattr(self, k, getattr(self, k) + v)

    def as_dict(self) -> Dict[str, float]:
        with self._lock:
            return {"calls": self.calls, "requests": self.requests, "docs": self.docs,
                    "input_tokens": self.input_tokens, "seconds": round(self.seconds, 4),
                    "errors": self.errors}


def _clip(text: str, n: int) -> str:
    text = text or ""
    return text if len(text) <= n else text[:n] + " ..."


class SystemOneReranker:
    """Relevance reranking through any TypeSafe-compatible ``/v1/systemone``.

    ``mode``:

    * ``"noul"`` (default) — one request per candidate: the state holds the
      question and one memory, the answer is P(the memory helps). Calibrated
      and independent per candidate; requests run on ``workers`` threads.
    * ``"fanout"`` — one request per group of candidates: the state holds the
      question and up to ``fanout_size`` memories, with one ``noul`` question
      per memory. The shared state is read once, so hosted input tokens drop.
    * ``"choice"`` — one request: a ``choice`` over the candidates, scored by
      their softmax probabilities; the state holds the question and a fixed
      instruction asks which memory helps (options must fit the backend's
      option budget).
    * ``"rank"`` — as ``choice``, but the user's question itself is the
      instruction over an empty state: the layout contrastive System One
      models such as CLM are trained on (question last, each candidate
      embedded verbatim), i.e. CLM's ``/v1/rank`` primitive.

    A failed request scores its candidates 0.0 and is counted in
    ``stats.errors``; the rest of the ranking is kept.
    """

    def __init__(self, base_url: str = "https://api.typesafe.ai", api_key: str = "",
                 model: Optional[str] = "jev-latest", mode: str = "noul",
                 instructions: str = RELEVANCE_INSTRUCTIONS, workers: int = 8,
                 timeout: int = 60, max_doc_chars: int = 1500, fanout_size: int = 12,
                 price_per_mtok: float = 0.0, extra_question: Optional[dict] = None):
        if mode not in ("noul", "fanout", "choice", "rank"):
            raise ValueError("mode must be 'noul', 'fanout', 'choice' or 'rank'")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.mode = mode
        self.instructions = instructions
        self.workers = max(1, int(workers))
        self.timeout = int(timeout)
        self.max_doc_chars = int(max_doc_chars)
        self.fanout_size = max(1, int(fanout_size))
        self.price_per_mtok = float(price_per_mtok)
        self.extra_question = dict(extra_question or {})
        self.stats = DecisionStats()
        self._local = threading.local()     # per-thread result of the last call

    # ---------------------------------------------------------------- wire
    def _post(self, state, questions: dict) -> dict:
        body = {"state": state, "questions": questions}
        if self.model:
            body["model"] = self.model
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        out = _post_json(f"{self.base_url}/v1/systemone", body, headers,
                         timeout=self.timeout, retries=2)
        usage = out.get("usage") or {}
        self.stats.add(requests=1, input_tokens=int(usage.get("input_tokens") or 0))
        return out

    def _noul_q(self) -> dict:
        q = {"type": "noul", "instructions": self.instructions}
        q.update(self.extra_question)
        return q

    # ------------------------------------------------------------- scoring
    def _score_one(self, query: str, doc: str) -> float:
        out = self._post({"question": query, "memory": _clip(doc, self.max_doc_chars)},
                         {"rel": self._noul_q()})
        return float(out["answers"]["rel"]["noul"])

    def _score_group(self, query: str, docs: Sequence[str]) -> List[float]:
        state = {"question": query,
                 "memories": {f"m{i}": _clip(d, self.max_doc_chars) for i, d in enumerate(docs)}}
        qs = {}
        for i in range(len(docs)):
            q = self._noul_q()
            q["instructions"] = f"Memory m{i}: {self.instructions}"
            qs[f"m{i}"] = q
        out = self._post(state, qs)
        return [float(out["answers"][f"m{i}"]["noul"]) for i in range(len(docs))]

    def _score_choice(self, query: str, docs: Sequence[str]) -> List[float]:
        criteria = {str(i): _clip(d, self.max_doc_chars) for i, d in enumerate(docs)}
        if self.mode == "rank":
            state, q = "", {"type": "choice", "instructions": query, "criteria": criteria}
        else:
            state = {"question": query}
            q = {"type": "choice", "instructions": CHOICE_INSTRUCTIONS, "criteria": criteria}
        out = self._post(state, {"best": q})
        probs = out["answers"]["best"].get("probabilities") or {}
        return [float(probs.get(str(i), 0.0)) for i in range(len(docs))]

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        docs = list(docs)
        self._local.errors = 0
        if not docs:
            return []
        t0 = time.perf_counter()
        scores = [0.0] * len(docs)
        errors = 0
        if self.mode in ("choice", "rank"):
            try:
                scores = self._score_choice(query, docs)
            except Exception:
                errors += 1
        else:
            if self.mode == "noul":
                jobs = [(i, [d]) for i, d in enumerate(docs)]
            else:
                jobs = [(i, docs[i:i + self.fanout_size])
                        for i in range(0, len(docs), self.fanout_size)]

            def run(job):
                start, group = job
                try:
                    vals = ([self._score_one(query, group[0])] if self.mode == "noul"
                            else self._score_group(query, group))
                    return start, vals, 0
                except Exception:
                    return start, [0.0] * len(group), 1

            with ThreadPoolExecutor(max_workers=min(self.workers, len(jobs))) as pool:
                for start, vals, err in pool.map(run, jobs):
                    scores[start:start + len(vals)] = vals
                    errors += err
        self.stats.add(calls=1, docs=len(docs), errors=errors,
                       seconds=time.perf_counter() - t0)
        self._local.errors = errors
        return scores

    @property
    def last_errors(self) -> int:
        """Failed requests in the calling thread's most recent ``rerank()``.

        ``stats`` is shared by every thread; this is not, so concurrent callers
        can tell their own failures apart."""
        return getattr(self._local, "errors", 0)

    @property
    def cost_usd(self) -> float:
        return self.stats.input_tokens / 1e6 * self.price_per_mtok


class LayaReranker:
    """Laya in-process (``pip install laya``; weights from the Hugging Face Hub
    or a local checkpoint directory). Candidates are judged with one ``noul``
    question each, batched through ``predict_batch``.

    ``labels`` defaults to neutral ``A``/``B`` slot names because the English
    checkpoint's ``noul`` can follow the default ``false``/``true`` labels
    instead of the state (Laya issue #156).
    """

    def __init__(self, model: str = "convaiinnovations/laya", subfolder: Optional[str] = None,
                 device: str = "cpu", batch_size: int = 16,
                 instructions: str = RELEVANCE_INSTRUCTIONS, max_doc_chars: int = 1500,
                 labels: Optional[Dict[str, str]] = None, threads: Optional[int] = None):
        import laya  # optional dependency
        if threads:
            try:
                import torch
                torch.set_num_threads(int(threads))
            except Exception:  # pragma: no cover - torch is laya's dependency
                pass
        kw = {"device": device}
        if subfolder:
            kw["subfolder"] = subfolder
        self.agent = laya.load(model, **kw)
        self.batch_size = max(1, int(batch_size))
        self.max_doc_chars = int(max_doc_chars)
        self.question = {"type": "noul", "instructions": instructions,
                         "criteria": {"true": "yes, the memory helps answer the question",
                                      "false": "no, the memory is unrelated to the question"},
                         "labels": labels or {"true": "A", "false": "B"}}
        self.stats = DecisionStats()
        self._local = threading.local()     # per-thread result of the last call
        self.price_per_mtok = 0.0

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        docs = list(docs)
        self._local.errors = 0
        if not docs:
            return []
        t0 = time.perf_counter()
        states = [{"question": query, "memory": _clip(d, self.max_doc_chars)} for d in docs]
        try:
            res = self.agent.predict_batch(states, {"rel": self.question},
                                           batch_size=self.batch_size)
            scores = [float(r["answers"]["rel"]["noul"]) for r in res]
            errors = 0
        except Exception:
            scores, errors = [0.0] * len(docs), 1
        self.stats.add(calls=1, requests=(len(docs) + self.batch_size - 1) // self.batch_size,
                       docs=len(docs), errors=errors, seconds=time.perf_counter() - t0)
        self._local.errors = errors
        return scores

    @property
    def last_errors(self) -> int:
        """Failed batches in the calling thread's most recent ``rerank()``."""
        return getattr(self._local, "errors", 0)

    @property
    def cost_usd(self) -> float:
        return 0.0
