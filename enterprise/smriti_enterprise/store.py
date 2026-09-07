"""EnterpriseStore — the core Store plus enterprise semantics, no core edits.

Adds:
  * read-only opening (verified packs mount immutable; DDL/pragma writes skipped)
  * knowledge-time stamping: invalidate_fact() also sets withdrawn_at to the
    ACTUAL clock — core's invalid_at carries *world* time (fact.valid_from of
    the successor); withdrawn_at carries *when this store learned it*. That
    separation is what makes late-arriving corrections reconstructable.
  * enterprise migration on open (writable stores only).
"""
from __future__ import annotations

import sqlite3
from typing import Dict, Optional

from smriti.store import Store, utcnow

from .migrations import migrate, schema_version, store_id


class EnterpriseStore(Store):
    def __init__(self, path: str = ":memory:", stem: bool = False,
                 read_only: bool = False):
        if read_only:
            # Bypass Store.__init__ (it applies pragmas + DDL, which write).
            # Mirror only the fields core code touches; verified in tests
            # against the core version pin.
            self.db = sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                                      isolation_level=None)
            self.db.execute("PRAGMA query_only=ON")
            self.stem = stem
            self._vec_cache: Dict = {}
            self._dirty = {"episode": True, "fact": True, "entity": True}
            self._pending = {"episode": [], "fact": []}
            self.read_only = True
        else:
            super().__init__(path, stem=stem)
            migrate(self.db)
            self.read_only = False
        self._knowledge_time: Optional[str] = None

    # ---- identity / versions -------------------------------------------
    @property
    def store_id(self) -> str:
        try:
            return store_id(self.db)
        except sqlite3.OperationalError:
            return ""

    @property
    def enterprise_schema_version(self) -> int:
        return schema_version(self.db)

    # ---- knowledge-time stamping ---------------------------------------
    def _now_known(self) -> str:
        return self._knowledge_time or utcnow()

    def _record_validity(self, fid: int, known_at: Optional[str] = None) -> None:
        row = self.db.execute(
            "SELECT valid_from, invalid_at, superseded_by FROM facts WHERE id=?",
            (fid,)).fetchone()
        if row:
            self.db.execute(
                "INSERT INTO fact_validity_history("
                "fact_id, valid_from, invalid_at, superseded_by, known_at) "
                "VALUES(?,?,?,?,?)", (fid, row[0], row[1], row[2],
                                      known_at or self._now_known()))

    def invalidate_fact(self, fid: int, superseded_by: int,
                        invalid_at: Optional[str] = None):
        """World time (invalid_at) via core; knowledge time (withdrawn_at)
        stamped here with the real clock. 'On July 1 we still believed X'
        becomes answerable even when the world changed on June 1 and we
        learned it on July 10."""
        known_at = self._now_known()
        super().invalidate_fact(fid, superseded_by, invalid_at=invalid_at)
        self.db.execute(
            "UPDATE facts SET withdrawn_at=? WHERE id=? AND withdrawn_at IS NULL",
            (known_at, fid))
        self._record_validity(fid, known_at)

    def set_fact_successor(self, fid: int, successor) -> None:
        """Record chain rewrites made by core's event-time rebuilding."""
        super().set_fact_successor(fid, successor)
        known_at = self._now_known()
        if successor is not None:
            self.db.execute(
                "UPDATE facts SET withdrawn_at=COALESCE(withdrawn_at, ?) WHERE id=?",
                (known_at, fid))
        self._record_validity(fid, known_at)

    def _erase_facts(self, fids) -> int:
        """Keep governance history within the same erasure boundary as facts."""
        ids = list(fids)
        if ids:
            marks = ",".join("?" for _ in ids)
            self.db.execute(
                f"DELETE FROM fact_validity_history WHERE fact_id IN ({marks})",
                ids)
        return super()._erase_facts(ids)
