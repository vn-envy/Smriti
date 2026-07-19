"""Multi-store read federation — personal writable store + verified read-only
packs, fused with the same RRF math the four channels already use.

Writes go to YOUR store only. Every result carries store provenance (a
`store:<name>` channel tag). Precedence is declared, not hidden: on identical
fused scores the earlier-listed store wins (personal-first by convention).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from smriti.retrieval import retrieve
from smriti.types import RetrievalResult


def retrieve_multi(stores: List[Tuple[str, object]], embedder, query: str,
                   k: int = 12, weights: Optional[Dict[str, float]] = None,
                   per_store_k: Optional[int] = None, rrf_k: int = 60,
                   **retrieve_kw) -> List[RetrievalResult]:
    """stores: ordered [(name, Store)] — order is declared precedence.
    Runs core retrieval per store, then reciprocal-rank-fuses across stores.
    Fusing ranked lists across stores is the same operation as fusing
    channels; no new math, no server."""
    per_store_k = per_store_k or max(k, 12)
    ranked: Dict[Tuple[str, str, int], Tuple[float, RetrievalResult, int]] = {}
    for order, (name, store) in enumerate(stores):
        hits = retrieve(store, embedder, query, k=per_store_k, weights=weights,
                        **retrieve_kw)
        for rank, r in enumerate(hits):
            key = (name, r.kind, r.id)
            score = 1.0 / (rrf_k + rank + 1)
            r.channels = list(r.channels) + [f"store:{name}"]
            ranked[key] = (score, r, order)
    fused = sorted(ranked.values(), key=lambda t: (-t[0], t[2]))
    out = []
    for score, r, _order in fused[:k]:
        r.score = float(score)
        out.append(r)
    return out
