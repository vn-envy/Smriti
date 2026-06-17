"""Zero-infrastructure storage layer.

Nomenclature: episodes are *anubhava* (अनुभव, direct experience); facts are
*samskara* (संस्कार, the impressions experience leaves behind); the entity
table is *padartha* (पदार्थ, the Nyaya term for entities/categories); a
fact's validity window [valid_from, invalid_at) is its *avadhi* (अवधि, term).

One SQLite file holds everything:
  * episodes      - append-only raw turns
  * facts         - bi-temporal atomic facts (supersession, never deletion)
  * entities      - lightweight entity -> fact links (graph-lite, no Neo4j)
  * FTS5 indexes  - lexical/BM25 search over both tables
  * embeddings    - float32 blobs, searched in-memory via numpy

This is a deliberate design bet learned from the field: Zep/Graphiti's
temporal model is the right idea but Neo4j is the wrong tax; mem0's
flat store is cheap but loses time. SMRITI keeps the temporal model
and drops the infrastructure.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

from .types import Episode, Fact

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes(
    id INTEGER PRIMARY KEY,
    session_id TEXT, role TEXT, content TEXT, ts TEXT, emb BLOB
);
CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    content, content='episodes', content_rowid='id'
);
CREATE TABLE IF NOT EXISTS facts(
    id INTEGER PRIMARY KEY,
    statement TEXT, subject TEXT, predicate TEXT, object TEXT, kind TEXT,
    event_date TEXT, ingested_at TEXT, valid_from TEXT, invalid_at TEXT,
    superseded_by INTEGER, episode_id INTEGER, session_id TEXT, emb BLOB
);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(
    statement, content='facts', content_rowid='id'
);
CREATE TABLE IF NOT EXISTS entities(
    name TEXT, fact_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_facts_subj_pred ON facts(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fts_query(text: str) -> str:
    """Sanitize free text into an OR-joined FTS5 query (recall-oriented)."""
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    tokens = [t for t in tokens if len(t) > 1][:32]
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"' for t in tokens)


def _to_blob(vec) -> Optional[bytes]:
    if vec is None:
        return None
    if np is not None:
        return np.asarray(vec, dtype="float32").tobytes()
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


class Store:
    def __init__(self, path: str = ":memory:"):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript(_SCHEMA)
        self._vec_cache: Dict[str, Tuple[list, object]] = {}
        self._dirty = {"episode": True, "fact": True}
        self._pending: Dict[str, list] = {"episode": [], "fact": []}

    # ------------------------------------------------------------- episodes
    def add_episode(self, ep: Episode, emb=None) -> int:
        cur = self.db.execute(
            "INSERT INTO episodes(session_id, role, content, ts, emb) VALUES(?,?,?,?,?)",
            (ep.session_id, ep.role, ep.content, ep.ts, _to_blob(emb)),
        )
        rowid = cur.lastrowid
        self.db.execute(
            "INSERT INTO episodes_fts(rowid, content) VALUES(?,?)", (rowid, ep.content)
        )
        if emb is not None:
            self._note_vec("episode", rowid, emb)
        return rowid

    def get_episode(self, eid: int) -> Optional[Episode]:
        row = self.db.execute(
            "SELECT id, session_id, role, content, ts FROM episodes WHERE id=?", (eid,)
        ).fetchone()
        return Episode(*row) if row else None

    # ---------------------------------------------------------------- facts
    def add_fact(self, f: Fact, emb=None) -> int:
        cur = self.db.execute(
            """INSERT INTO facts(statement, subject, predicate, object, kind,
               event_date, ingested_at, valid_from, invalid_at, superseded_by,
               episode_id, session_id)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f.statement, f.subject.lower().strip(), f.predicate.lower().strip(),
                f.object, f.kind, f.event_date,
                f.ingested_at or utcnow(),
                f.valid_from or f.event_date or f.ingested_at or utcnow(),
                f.invalid_at, f.superseded_by, f.episode_id, f.session_id,
            ),
        )
        rowid = cur.lastrowid
        # index statement + expansion keys (Build 9 Part A) for lexical recall;
        # the stored statement (display/provenance) stays clean.
        fts_text = f.statement
        if getattr(f, "search_keys", None):
            fts_text = f.statement + " " + " ".join(f.search_keys)
        self.db.execute(
            "INSERT INTO facts_fts(rowid, statement) VALUES(?,?)", (rowid, fts_text)
        )
        if emb is not None:
            self.db.execute("UPDATE facts SET emb=? WHERE id=?", (_to_blob(emb), rowid))
        for ent in {e.lower().strip() for e in f.entities if e and e.strip()}:
            self.db.execute("INSERT INTO entities(name, fact_id) VALUES(?,?)", (ent, rowid))
        if emb is not None:
            self._note_vec("fact", rowid, emb)
        return rowid

    def get_fact(self, fid: int) -> Optional[Fact]:
        row = self.db.execute(
            """SELECT id, statement, subject, predicate, object, kind, event_date,
               ingested_at, valid_from, invalid_at, superseded_by, episode_id, session_id
               FROM facts WHERE id=?""",
            (fid,),
        ).fetchone()
        if not row:
            return None
        return Fact(
            id=row[0], statement=row[1], subject=row[2], predicate=row[3],
            object=row[4], kind=row[5], event_date=row[6], ingested_at=row[7],
            valid_from=row[8], invalid_at=row[9], superseded_by=row[10],
            episode_id=row[11], session_id=row[12],
        )

    def invalidate_fact(self, fid: int, superseded_by: int, invalid_at: Optional[str] = None):
        """Supersession, not deletion: the old fact stays queryable as history."""
        self.db.execute(
            "UPDATE facts SET invalid_at=?, superseded_by=? WHERE id=?",
            (invalid_at or utcnow(), superseded_by, fid),
        )  # embeddings unchanged; vector cache stays valid

    def similar_valid_facts(self, subject: str, predicate: str) -> List[Fact]:
        rows = self.db.execute(
            "SELECT id FROM facts WHERE subject=? AND predicate=? AND invalid_at IS NULL",
            (subject.lower().strip(), predicate.lower().strip()),
        ).fetchall()
        return [self.get_fact(r[0]) for r in rows]

    def facts_for_entity(self, name: str, valid_only: bool = True,
                         include_observations: bool = False) -> List[Fact]:
        """All facts linked to an entity. By default only currently-valid facts,
        and excluding observation summaries (so we summarize raw facts, not
        prior summaries)."""
        rows = self.db.execute(
            "SELECT DISTINCT fact_id FROM entities WHERE name=?", (name.lower().strip(),)
        ).fetchall()
        out = []
        for (fid,) in rows:
            f = self.get_fact(fid)
            if not f:
                continue
            if valid_only and f.invalid_at is not None:
                continue
            if not include_observations and f.kind == "observation":
                continue
            out.append(f)
        return out

    def predicate_groups(self, min_facts: int = 2, valid_only: bool = True) -> List[Tuple[str, str, int]]:
        """(subject, predicate) groups with >= min_facts valid facts — the unit
        for cross-entity aggregation ("user/attended" spans many event entities).
        Excludes observation/digest rows so digests aren't summarized again."""
        cond = "AND invalid_at IS NULL" if valid_only else ""
        rows = self.db.execute(
            f"SELECT subject, predicate, COUNT(*) c FROM facts "
            f"WHERE kind != 'observation' AND subject != '' AND predicate != '' {cond} "
            f"GROUP BY subject, predicate HAVING COUNT(*) >= ?",
            (min_facts,),
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    def entities_of_facts(self, fact_ids: Sequence[int]) -> List[str]:
        """Entities mentioned by the given facts (for graph-lite multi-hop)."""
        if not fact_ids:
            return []
        marks = ",".join("?" for _ in fact_ids)
        rows = self.db.execute(
            f"SELECT DISTINCT name FROM entities WHERE fact_id IN ({marks})", list(fact_ids)
        ).fetchall()
        return [r[0] for r in rows]

    # --------------------------------------------------------------- search
    def fts_search(self, query: str, table: str, limit: int = 20) -> List[Tuple[int, float]]:
        q = _fts_query(query)
        if not q:
            return []
        fts = "episodes_fts" if table == "episode" else "facts_fts"
        try:
            rows = self.db.execute(
                f"SELECT rowid, bm25({fts}) FROM {fts} WHERE {fts} MATCH ? "
                f"ORDER BY bm25({fts}) LIMIT ?",
                (q, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        # bm25(): lower is better -> negate so higher is better
        return [(r[0], -r[1]) for r in rows]

    def _note_vec(self, kind: str, rowid: int, emb):
        """Queue a new embedding for incremental cache append (no rebuild)."""
        if not self._dirty[kind] and kind in self._vec_cache and np is not None:
            v = np.asarray(emb, dtype="float32")
            n = np.linalg.norm(v)
            self._pending[kind].append((rowid, v / n if n else v))
        else:
            self._dirty[kind] = True

    def _vectors(self, kind: str):
        if not self._dirty[kind] and kind in self._vec_cache:
            if self._pending[kind] and np is not None:
                ids, mat = self._vec_cache[kind]
                new_ids = [r for r, _ in self._pending[kind]]
                new_rows = np.stack([v for _, v in self._pending[kind]])
                mat = new_rows if mat is None else np.vstack([mat, new_rows])
                self._vec_cache[kind] = (ids + new_ids, mat)
                self._pending[kind] = []
            return self._vec_cache[kind]
        table = "episodes" if kind == "episode" else "facts"
        rows = self.db.execute(
            f"SELECT id, emb FROM {table} WHERE emb IS NOT NULL"
        ).fetchall()
        ids = [r[0] for r in rows]
        if np is None or not rows:
            self._vec_cache[kind] = (ids, None if not rows else [r[1] for r in rows])
        else:
            mat = np.stack([np.frombuffer(r[1], dtype="float32") for r in rows])
            norm = np.linalg.norm(mat, axis=1, keepdims=True)
            norm[norm == 0] = 1.0
            self._vec_cache[kind] = (ids, mat / norm)
        self._dirty[kind] = False
        self._pending[kind] = []
        return self._vec_cache[kind]

    def vector_search(self, query_vec, kind: str, limit: int = 20) -> List[Tuple[int, float]]:
        if query_vec is None or np is None:
            return []
        ids, mat = self._vectors(kind)
        if not ids or mat is None:
            return []
        q = np.asarray(query_vec, dtype="float32")
        n = np.linalg.norm(q)
        if n == 0:
            return []
        sims = mat @ (q / n)
        order = np.argsort(-sims)[:limit]
        return [(ids[i], float(sims[i])) for i in order]

    def entity_facts(self, entities: Sequence[str], limit: int = 20) -> List[Tuple[int, float]]:
        """Graph-lite channel: facts linked to entities mentioned in the query."""
        if not entities:
            return []
        marks = ",".join("?" for _ in entities)
        rows = self.db.execute(
            f"""SELECT fact_id, COUNT(*) c FROM entities WHERE name IN ({marks})
                GROUP BY fact_id ORDER BY c DESC LIMIT ?""",
            [e.lower().strip() for e in entities] + [limit],
        ).fetchall()
        return [(r[0], float(r[1])) for r in rows]

    def all_entities(self) -> List[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT name FROM entities")]

    def episodes_near(self, iso_date: str, limit: int = 20) -> List[Tuple[int, float]]:
        """Temporal channel: episodes closest in time to a referenced date.

        ISO-8601 strings sort chronologically, so two indexed range probes
        (nearest below, nearest above) replace a full-table date scan:
        O(log N + k) instead of O(N)."""
        half = limit // 2 + 2
        below = self.db.execute(
            "SELECT id, ts FROM episodes WHERE ts IS NOT NULL AND ts <= ? "
            "ORDER BY ts DESC LIMIT ?", (iso_date, half)).fetchall()
        above = self.db.execute(
            "SELECT id, ts FROM episodes WHERE ts IS NOT NULL AND ts > ? "
            "ORDER BY ts ASC LIMIT ?", (iso_date, half)).fetchall()

        def _ord(iso):
            try:
                return datetime.strptime(iso[:10], "%Y-%m-%d").toordinal()
            except (ValueError, TypeError):
                return None
        target = _ord(iso_date)
        if target is None:
            return []
        scored = []
        for rid, ts in below + above:
            o = _ord(ts)
            if o is not None:
                scored.append((rid, 1.0 / (1.0 + abs(o - target))))
        scored.sort(key=lambda x: -x[1])
        return scored[:limit]

    def stats(self) -> dict:
        e = self.db.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
        f = self.db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        v = self.db.execute("SELECT COUNT(*) FROM facts WHERE invalid_at IS NULL").fetchone()[0]
        n = self.db.execute("SELECT COUNT(DISTINCT name) FROM entities").fetchone()[0]
        return {"episodes": e, "facts": f, "valid_facts": v, "entities": n}
