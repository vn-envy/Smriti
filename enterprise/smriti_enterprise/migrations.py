"""Enterprise schema migrations — `PRAGMA user_version`-driven, transactional,
idempotent, backfilled.

Migration 1 (the E1A substrate) adds, without touching any core column:

  facts:    uuid, recorded_at, withdrawn_at, origin, quarantined,
            retain_until, hold_id
  episodes: uuid, recorded_at, origin, retain_until, hold_id
  tables:   derivations (exact lineage edges), holds, store_meta

Tri-temporal model (the three concepts are never one reused column):
  * world validity     valid_from / invalid_at        (core, unchanged)
  * system knowledge   recorded_at / withdrawn_at     (added here)
  * storage lifecycle  retain_until / deleted-by-erasure / hold_id (added here)

Backfill rule: recorded_at defaults to ingested_at (facts) / ts (episodes) —
the best available approximation of "when this store learned it" for rows
that predate the enterprise schema. Documented as approximate in ASSURANCE.md.
"""
from __future__ import annotations

import sqlite3
import uuid as _uuid

from smriti.store import utcnow

ENTERPRISE_SCHEMA_VERSION = 1

_M1_COLUMNS = {
    "facts": [
        ("uuid", "TEXT"),
        ("recorded_at", "TEXT"),
        ("withdrawn_at", "TEXT"),
        ("origin", "TEXT DEFAULT 'owner'"),
        ("quarantined", "INTEGER DEFAULT 0"),
        ("retain_until", "TEXT"),
        ("hold_id", "TEXT"),
    ],
    "episodes": [
        ("uuid", "TEXT"),
        ("recorded_at", "TEXT"),
        ("origin", "TEXT DEFAULT 'owner'"),
        ("retain_until", "TEXT"),
        ("hold_id", "TEXT"),
    ],
}

# individual statements (executescript() would implicitly COMMIT our txn)
_M1_TABLES = [
    "CREATE TABLE IF NOT EXISTS derivations("
    " child_kind TEXT NOT NULL, child_id INTEGER NOT NULL,"
    " parent_kind TEXT NOT NULL, parent_id INTEGER NOT NULL,"
    " transform TEXT NOT NULL, transform_version TEXT, created_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_deriv_child ON derivations(child_kind, child_id)",
    "CREATE INDEX IF NOT EXISTS idx_deriv_parent ON derivations(parent_kind, parent_id)",
    "CREATE TABLE IF NOT EXISTS holds("
    " id TEXT PRIMARY KEY, scope_kind TEXT NOT NULL, scope_value TEXT NOT NULL,"
    " reason TEXT, authority TEXT, created_at TEXT NOT NULL,"
    " expires_at TEXT, released_at TEXT)",
    "CREATE TABLE IF NOT EXISTS store_meta(key TEXT PRIMARY KEY, value TEXT)",
]


def _existing_columns(db: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def schema_version(db: sqlite3.Connection) -> int:
    return db.execute("PRAGMA user_version").fetchone()[0]


def store_id(db: sqlite3.Connection) -> str:
    row = db.execute("SELECT value FROM store_meta WHERE key='store_id'").fetchone()
    return row[0] if row else ""


def migrate(db: sqlite3.Connection) -> dict:
    """Bring a core SMRITI database to the current enterprise schema.
    Transactional and idempotent: safe to call on every open."""
    start = schema_version(db)
    if start >= ENTERPRISE_SCHEMA_VERSION:
        return {"from": start, "to": start, "applied": False}

    if db.in_transaction:  # pragma: no cover - defensive
        raise RuntimeError("migrate() must not run inside an open transaction")
    db.execute("BEGIN IMMEDIATE")
    try:
        # ---- migration 1 ----
        for table, cols in _M1_COLUMNS.items():
            have = _existing_columns(db, table)
            for name, decl in cols:
                if name not in have:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
        for stmt in _M1_TABLES:
            db.execute(stmt)
        # store identity + provenance metadata
        db.execute(
            "INSERT OR IGNORE INTO store_meta(key, value) VALUES('store_id', ?)",
            (_uuid.uuid4().hex,))
        db.execute(
            "INSERT OR REPLACE INTO store_meta(key, value) VALUES('enterprise_migrated_at', ?)",
            (utcnow(),))
        # backfill stable ids + approximate knowledge time for pre-existing rows
        for (fid,) in db.execute("SELECT id FROM facts WHERE uuid IS NULL").fetchall():
            db.execute("UPDATE facts SET uuid=? WHERE id=?", (_uuid.uuid4().hex, fid))
        db.execute("UPDATE facts SET recorded_at=COALESCE(recorded_at, ingested_at)")
        for (eid,) in db.execute("SELECT id FROM episodes WHERE uuid IS NULL").fetchall():
            db.execute("UPDATE episodes SET uuid=? WHERE id=?", (_uuid.uuid4().hex, eid))
        db.execute("UPDATE episodes SET recorded_at=COALESCE(recorded_at, ts)")
        db.execute(f"PRAGMA user_version={ENTERPRISE_SCHEMA_VERSION}")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return {"from": start, "to": ENTERPRISE_SCHEMA_VERSION, "applied": True}
