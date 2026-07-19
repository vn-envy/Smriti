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
    def invalidate_fact(self, fid: int, superseded_by: int,
                        invalid_at: Optional[str] = None):
        """World time (invalid_at) via core; knowledge time (withdrawn_at)
        stamped here with the real clock. 'On July 1 we still believed X'
        becomes answerable even when the world changed on June 1 and we
        learned it on July 10."""
        super().invalidate_fact(fid, superseded_by, invalid_at=invalid_at)
        self.db.execute(
            "UPDATE facts SET withdrawn_at=? WHERE id=? AND withdrawn_at IS NULL",
            (utcnow(), fid))
