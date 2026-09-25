"""Named system configurations for lab A/B runs."""
from __future__ import annotations

from .systems import BM25System, DenseSystem, Mem0System, SmritiSystem

SYSTEMS = {
    "bm25": BM25System,
    "dense": DenseSystem,
    "mem0": Mem0System,
    # Default public read path (lite mode): search() + context() as shipped.
    "smriti": lambda: SmritiSystem("smriti"),
    "smriti_stem": lambda: SmritiSystem("smriti_stem", init_kw={"stem": True}),
    "smriti_diverse": lambda: SmritiSystem(
        "smriti_diverse", search_kw={"session_diverse": True},
        context_kw={"session_diverse": True}),
}


def _ev(name, **recall):
    from smriti import RetrievalProfile
    from smriti.recall import RecallConfig
    init = {}
    if "ctx_embed" in recall:
        init["contextual_embeddings"] = recall.pop("ctx_embed")
    prof = RetrievalProfile(name=name, engine="evidence", recall=RecallConfig(**recall))
    return lambda: SmritiSystem(name, init_kw=init, search_kw={"profile": prof},
                                context_kw={"profile": prof})


SYSTEMS.update({
    "evidence": _ev("evidence"),
})


def variant(spec: str):
    """``ev(session_weight=0.5,neighbors=0)`` -> evidence engine with overrides.

    Values are parsed as int, float, bool (true/false) or left as strings."""
    base, _, rest = spec.partition("(")
    rest = rest.rstrip(")")
    kw = {}
    for part in filter(None, (p.strip() for p in rest.split(","))):
        key, _, val = part.partition("=")
        low = val.lower()
        if low in ("true", "false"):
            kw[key] = low == "true"
        else:
            try:
                kw[key] = int(val)
            except ValueError:
                try:
                    kw[key] = float(val)
                except ValueError:
                    kw[key] = val
    if base != "ev":
        raise SystemExit(f"unknown variant base {base!r}")
    return _ev(spec, **kw)()
