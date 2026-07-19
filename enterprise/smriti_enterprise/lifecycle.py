"""Storage lifecycle — retention classes, legal holds, sweeps.

Distinct verbs, never conflated (the tri-temporal rule):
  * retention  — `retain_until` on rows; `sweep()` erases what has expired
  * legal hold — a structured record (scope, reason, authority, expiry), not
    a Boolean; held rows are immune to BOTH sweeps and owner erasure until
    released
Erasure here follows exact derivation lineage (E1A edges) and cleans its own
edges — replacing the heuristic overlap purge for enterprise stores.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Optional

from smriti.store import utcnow

from .lineage import descendants_of, drop_edges_for


class HeldError(RuntimeError):
    """Raised when erasure or sweep touches records under an active hold."""


def _active_holds(store, scope_kind: str, scope_value: str):
    now = utcnow()
    return store.db.execute(
        "SELECT id FROM holds WHERE scope_kind=? AND scope_value=? "
        "AND released_at IS NULL AND (expires_at IS NULL OR expires_at > ?)",
        (scope_kind, scope_value, now)).fetchall()


def place_hold(store, scope_kind: str, scope_value: str, reason: str,
               authority: str, expires_at: Optional[str] = None) -> str:
    """scope_kind: 'session' | 'entity'. Marks matching rows and records the
    hold with its authority — releasable, expirable, receipted by the caller."""
    hid = _uuid.uuid4().hex
    store.db.execute("BEGIN IMMEDIATE")
    try:
        store.db.execute(
            "INSERT INTO holds(id, scope_kind, scope_value, reason, authority,"
            " created_at, expires_at) VALUES(?,?,?,?,?,?,?)",
            (hid, scope_kind, scope_value, reason, authority, utcnow(), expires_at))
        if scope_kind == "session":
            store.db.execute("UPDATE episodes SET hold_id=? WHERE session_id=?",
                             (hid, scope_value))
            store.db.execute("UPDATE facts SET hold_id=? WHERE session_id=?",
                             (hid, scope_value))
        elif scope_kind == "entity":
            canonical = store.resolve_entity(scope_value)
            store.db.execute(
                "UPDATE facts SET hold_id=? WHERE id IN "
                "(SELECT DISTINCT fact_id FROM entities WHERE name=?)",
                (hid, canonical))
        else:
            raise ValueError(f"unknown hold scope {scope_kind!r}")
        store.db.execute("COMMIT")
    except BaseException:
        store.db.execute("ROLLBACK")
        raise
    return hid


def release_hold(store, hold_id: str) -> bool:
    store.db.execute("BEGIN IMMEDIATE")
    try:
        cur = store.db.execute(
            "UPDATE holds SET released_at=? WHERE id=? AND released_at IS NULL",
            (utcnow(), hold_id))
        store.db.execute("UPDATE episodes SET hold_id=NULL WHERE hold_id=?", (hold_id,))
        store.db.execute("UPDATE facts SET hold_id=NULL WHERE hold_id=?", (hold_id,))
        store.db.execute("COMMIT")
    except BaseException:
        store.db.execute("ROLLBACK")
        raise
    return cur.rowcount == 1


def set_retention(store, session_id: str, retain_until: str) -> int:
    cur = store.db.execute(
        "UPDATE episodes SET retain_until=? WHERE session_id=?",
        (retain_until, session_id))
    store.db.execute("UPDATE facts SET retain_until=? WHERE session_id=?",
                     (retain_until, session_id))
    return cur.rowcount


def erase_session(store, session_id: str) -> dict:
    """Transactional, hold-aware, lineage-exact erasure. Refuses (raises
    HeldError) if any row in scope is under an active hold. Derived
    observations are found via derivation edges, not heuristics."""
    if _active_holds(store, "session", session_id):
        raise HeldError(f"session {session_id!r} is under an active legal hold")
    held = store.db.execute(
        "SELECT COUNT(*) FROM facts WHERE session_id=? AND hold_id IS NOT NULL",
        (session_id,)).fetchone()[0]
    if held:
        raise HeldError(f"{held} fact(s) in session {session_id!r} carry a hold")

    store.db.execute("BEGIN IMMEDIATE")
    try:
        fids = [r[0] for r in store.db.execute(
            "SELECT id FROM facts WHERE session_id=?", (session_id,)).fetchall()]
        derived = []
        for fid in fids:
            derived += [(k, i) for k, i in descendants_of(store, "fact", fid)
                        if k == "fact"]
        derived_ids = sorted({i for _k, i in derived} - set(fids))

        eps = store.db.execute(
            "SELECT id, content FROM episodes WHERE session_id=?",
            (session_id,)).fetchall()
        for eid, content in eps:
            store.db.execute(
                "INSERT INTO episodes_fts(episodes_fts, rowid, content) "
                "VALUES('delete',?,?)", (eid, content))
        store.db.execute("DELETE FROM episodes WHERE session_id=?", (session_id,))
        facts_gone = store._erase_facts(fids)
        obs_gone = store._erase_facts(derived_ids)
        drop_edges_for(store, [("fact", i) for i in fids + derived_ids]
                              + [("episode", e) for e, _c in eps])
        store.db.execute("DELETE FROM ingest_log WHERE session_id=?", (session_id,))
        store.db.execute("COMMIT")
    except BaseException:
        store.db.execute("ROLLBACK")
        raise
    return {"episodes": len(eps), "facts": facts_gone,
            "derived": obs_gone, "lineage_exact": True}


def sweep(store, now: Optional[str] = None) -> dict:
    """Erase everything whose retention expired — except held rows."""
    now = now or utcnow()
    # Select every EXPIRED session, held or not — the hold check inside
    # erase_session then rejects held ones, so they are reported as
    # skipped_held rather than silently omitted from the sweep report.
    sessions = [r[0] for r in store.db.execute(
        "SELECT DISTINCT session_id FROM episodes WHERE retain_until IS NOT NULL "
        "AND retain_until <= ? AND session_id IS NOT NULL",
        (now,)).fetchall()]
    out = {"sessions": 0, "episodes": 0, "facts": 0, "skipped_held": 0}
    for sid in sessions:
        try:
            r = erase_session(store, sid)
            out["sessions"] += 1
            out["episodes"] += r["episodes"]
            out["facts"] += r["facts"] + r["derived"]
        except HeldError:
            out["skipped_held"] += 1
    return out
