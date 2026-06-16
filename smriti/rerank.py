"""Optional cross-encoder reranking — *punarvichara* (पुनर्विचार, re-examination).

Reciprocal Rank Fusion is cheap and order-robust, but it scores a candidate by
its *ranks* across channels, not by a joint reading of (query, document). A
cross-encoder re-examines the top fused candidates by scoring each query/doc
pair directly, which is the lever the strongest systems (e.g. Hindsight) add
on top of RRF.

Model-agnostic by design: any object exposing ``rerank(query, docs) -> list[float]``
(higher = more relevant) plugs in. Stdlib HTTP only, consistent with the rest
of SMRITI — no torch, no sentence-transformers required in the core.
"""
from __future__ import annotations

from typing import List, Sequence

from .embedder import _post_json


class MockReranker:
    """Deterministic, dependency-free reranker for tests and offline use.

    Scores by query/document token overlap. Not semantically smart, but stable
    and good enough to exercise the rerank plumbing without a model server.
    """

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        q = set(query.lower().split())
        return [len(q & set(d.lower().split())) for d in docs]


class HTTPReranker:
    """Calls a TEI / Jina / Cohere-style ``/rerank`` endpoint.

    Accepts the common response shapes: ``{"results": [{"index", "relevance_score"}]}``
    or a bare list of ``{"index", "score"}``. Missing scores default to 0.
    """

    def __init__(self, model: str, base_url: str, api_key: str = ""):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def rerank(self, query: str, docs: Sequence[str]) -> List[float]:
        docs = list(docs)
        if not docs:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = _post_json(
            f"{self.base_url}/rerank",
            {"model": self.model, "query": query, "documents": docs},
            headers,
        )
        rows = resp.get("results", resp) if isinstance(resp, dict) else resp
        scores = [0.0] * len(docs)
        for r in rows or []:
            idx = r.get("index")
            if idx is not None and 0 <= idx < len(docs):
                scores[idx] = float(r.get("relevance_score", r.get("score", 0.0)))
        return scores
