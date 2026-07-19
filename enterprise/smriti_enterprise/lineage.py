"""Exact derivation lineage — evidence-grade parent/child edges.

Core links a fact to only the FIRST episode of its session, and observations
carry no parents at all. Enterprise records the full edges:

    episode --extract--> fact --observe--> observation

so every derived record reaches its exact parents (and erasure can follow
derivation instead of heuristic overlap).
"""
from __future__ import annotations

from typing import List, Tuple

from smriti.store import utcnow


def add_edges(store, child_kind: str, child_id: int,
              parents: List[Tuple[str, int]], transform: str,
              transform_version: str = "") -> int:
    n = 0
    for pkind, pid in parents:
        store.db.execute(
            "INSERT INTO derivations(child_kind, child_id, parent_kind, parent_id,"
            " transform, transform_version, created_at) VALUES(?,?,?,?,?,?,?)",
            (child_kind, child_id, pkind, pid, transform, transform_version, utcnow()))
        n += 1
    return n


def parents_of(store, kind: str, rid: int) -> List[Tuple[str, int, str]]:
    return [(r[0], r[1], r[2]) for r in store.db.execute(
        "SELECT parent_kind, parent_id, transform FROM derivations "
        "WHERE child_kind=? AND child_id=?", (kind, rid))]


def children_of(store, kind: str, rid: int) -> List[Tuple[str, int, str]]:
    return [(r[0], r[1], r[2]) for r in store.db.execute(
        "SELECT child_kind, child_id, transform FROM derivations "
        "WHERE parent_kind=? AND parent_id=?", (kind, rid))]


def descendants_of(store, kind: str, rid: int, max_depth: int = 5) -> List[Tuple[str, int]]:
    """Transitive closure (bounded) — the erase-by-derivation frontier."""
    seen, frontier = set(), [(kind, rid)]
    for _ in range(max_depth):
        nxt = []
        for k, i in frontier:
            for ck, ci, _t in children_of(store, k, i):
                if (ck, ci) not in seen:
                    seen.add((ck, ci))
                    nxt.append((ck, ci))
        if not nxt:
            break
        frontier = nxt
    return sorted(seen)


def drop_edges_for(store, pairs: List[Tuple[str, int]]) -> int:
    n = 0
    for kind, rid in pairs:
        cur = store.db.execute(
            "DELETE FROM derivations WHERE (child_kind=? AND child_id=?) "
            "OR (parent_kind=? AND parent_id=?)", (kind, rid, kind, rid))
        n += cur.rowcount
    return n
