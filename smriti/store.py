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

# Base schema (FTS5 tables are created per-instance so the tokenizer can be
# chosen at open time — see Store.__init__'s `stem` flag).
_SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS episodes(
    id INTEGER PRIMARY KEY,
    session_id TEXT, role TEXT, content TEXT, ts TEXT, emb BLOB
);
CREATE TABLE IF NOT EXISTS facts(
    id INTEGER PRIMARY KEY,
    statement TEXT, subject TEXT, predicate TEXT, object TEXT, kind TEXT,
    event_date TEXT, ingested_at TEXT, valid_from TEXT, invalid_at TEXT,
    superseded_by INTEGER, episode_id INTEGER, session_id TEXT, emb BLOB
);
CREATE TABLE IF NOT EXISTS entities(
    name TEXT, fact_id INTEGER
);
CREATE TABLE IF NOT EXISTS entity_aliases(
    alias TEXT PRIMARY KEY, canonical TEXT
);
CREATE TABLE IF NOT EXISTS ingest_log(
    hash TEXT PRIMARY KEY, session_id TEXT, ingested_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_facts_subj_pred ON facts(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
CREATE INDEX IF NOT EXISTS idx_episodes_session ON episodes(session_id);
CREATE INDEX IF NOT EXISTS idx_facts_session ON facts(session_id);
"""


def _fts_ddl(stem: bool) -> str:
    """FTS5 tables over episodes/facts. With `stem`, the built-in Porter
    stemmer is applied so conjugation variants match ('attend' <-> 'attending')
    — the keyword-normalization lever mem0 credits with measurable gains.
    Pure SQLite; no new dependency."""
    tok = ", tokenize='porter'" if stem else ""
    return (
        f"CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5("
        f"content, content='episodes', content_rowid='id'{tok});\n"
        f"CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5("
        f"statement, content='facts', content_rowid='id'{tok});\n"
        f"CREATE VIRTUAL TABLE IF NOT EXISTS fact_keys_fts USING fts5(keys{tok});\n"
    )


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fts_query(text: str) -> str:
    """Sanitize free text into an OR-joined FTS5 query (recall-oriented).

    \\w+ (unicode) instead of [A-Za-z0-9]+ so non-Latin scripts — Devanagari,
    CJK, Cyrillic — reach FTS5's unicode61 tokenizer instead of being stripped
    before the search even runs (hardening pass, 0.3.0)."""
    tokens = re.findall(r"\w+", text, re.UNICODE)
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
    def __init__(self, path: str = ":memory:", stem: bool = False):
        self.db = sqlite3.connect(path, isolation_level=None)
        # Hardening (0.3.0): WAL lets readers proceed during a write and
        # survives crashes cleanly; NORMAL sync is the standard WAL pairing;
        # busy_timeout waits instead of throwing when another connection
        # holds the write lock. No-ops harmlessly on :memory: databases.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.executescript(_SCHEMA_BASE)
        self.db.executescript(_fts_ddl(stem))
        self.stem = stem
        self._vec_cache: Dict[str, Tuple[list, object]] = {}
        # 'entity' holds entity-NAME embeddings (semantic entity linking),
        # cached the same way as episode/fact vectors and invalidated on write.
        self._dirty = {"episode": True, "fact": True, "entity": True}
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
        # Statement FTS stays CLEAN (precision path for all queries). Expansion
        # keys go to a SEPARATE index consulted only on the aggregation/recall
        # profile (Build 10 router) — so key expansion can't pollute precision-
        # sensitive queries (the knowledge-update regression in the n=300 run).
        self.db.execute(
            "INSERT INTO facts_fts(rowid, statement) VALUES(?,?)", (rowid, f.statement)
        )
        if getattr(f, "search_keys", None):
            self.db.execute(
                "INSERT INTO fact_keys_fts(rowid, keys) VALUES(?,?)",
                (rowid, " ".join(f.search_keys)),
            )
        if emb is not None:
            self.db.execute("UPDATE facts SET emb=? WHERE id=?", (_to_blob(emb), rowid))
        # write-time canonicalization: aliases collapse to their canonical
        # entity so "Rachel Smith" and "Rachel" accumulate under one node.
        for ent in {self.resolve_entity(e) for e in f.entities if e and e.strip()}:
            self.db.execute("INSERT INTO entities(name, fact_id) VALUES(?,?)", (ent, rowid))
        if f.entities:
            self._dirty["entity"] = True  # invalidate semantic-entity cache
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

    def key_fts_search(self, query: str, limit: int = 20) -> List[Tuple[int, float]]:
        """Lexical search over fact expansion keys (separate index). Consulted
        only on the aggregation/recall profile so it never affects precision
        queries. Returns [(fact_id, score)]."""
        q = _fts_query(query)
        if not q:
            return []
        try:
            rows = self.db.execute(
                "SELECT rowid, bm25(fact_keys_fts) FROM fact_keys_fts WHERE fact_keys_fts MATCH ? "
                "ORDER BY bm25(fact_keys_fts) LIMIT ?", (q, limit)).fetchall()
        except sqlite3.OperationalError:
            return []
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

    # ------------------------------------------------- semantic entity link
    def _entity_vecs(self, embedder):
        """Cached (names, L2-normalized matrix) of entity-NAME embeddings.

        Mirrors the episode/fact vector cache: built lazily on first query,
        invalidated whenever add_fact writes new entities. One batched embed
        call covers every known entity, so the cost is amortized across a
        run. This is the mem0 'entity linking' lever done with the embedder
        SMRITI already has — no Qdrant, no separate index service."""
        if not self._dirty.get("entity") and "entity" in self._vec_cache:
            return self._vec_cache["entity"]
        names = self.all_entities()
        if not names or np is None or embedder is None:
            self._vec_cache["entity"] = (names, None)
            self._dirty["entity"] = False
            return self._vec_cache["entity"]
        embs = embedder.embed(names)
        mat = np.stack([np.asarray(v, dtype="float32") for v in embs])
        norm = np.linalg.norm(mat, axis=1, keepdims=True)
        norm[norm == 0] = 1.0
        self._vec_cache["entity"] = (names, mat / norm)
        self._dirty["entity"] = False
        return self._vec_cache["entity"]

    def semantic_entities(self, embedder, query_vec, threshold: float = 0.3,
                          limit: int = 8) -> List[Tuple[str, float]]:
        """Entity names whose name-embedding is close to the query vector.

        Bridges vocabulary the lexical entity channel misses: 'my cousin
        Rachel' matches the 'Rachel' entity, 'the company she works for'
        reaches 'Acme'. Returns [(name, sim)] descending; lexical hits from
        query_entities() stay first when merged in retrieve()."""
        if query_vec is None or np is None:
            return []
        names, mat = self._entity_vecs(embedder)
        if mat is None or not names:
            return []
        q = np.asarray(query_vec, dtype="float32")
        n = float(np.linalg.norm(q))
        if n == 0:
            return []
        sims = mat @ (q / n)
        order = np.argsort(-sims)
        out = []
        for i in order:
            s = float(sims[i])
            if s < threshold:
                break
            out.append((names[i], s))
            if len(out) >= limit:
                break
        return out

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

    # ------------------------------------------------------ entity aliases
    def add_alias(self, alias: str, canonical: str) -> str:
        """Register alias -> canonical ("rachel smith" -> "rachel"). Chains are
        flattened at write time so lookups are always a single hop."""
        alias = alias.lower().strip()
        canonical = self.resolve_entity(canonical)
        if not alias or alias == canonical:
            return canonical
        self.db.execute(
            "INSERT INTO entity_aliases(alias, canonical) VALUES(?,?) "
            "ON CONFLICT(alias) DO UPDATE SET canonical=excluded.canonical",
            (alias, canonical))
        # re-point any aliases that resolved to the old name, and migrate
        # existing entity links so history consolidates under the canonical
        self.db.execute("UPDATE entity_aliases SET canonical=? WHERE canonical=?",
                        (canonical, alias))
        self.db.execute("UPDATE entities SET name=? WHERE name=?", (canonical, alias))
        self._dirty["entity"] = True
        return canonical

    def resolve_entity(self, name: str) -> str:
        name = (name or "").lower().strip()
        row = self.db.execute(
            "SELECT canonical FROM entity_aliases WHERE alias=?", (name,)).fetchone()
        return row[0] if row else name

    def match_aliases(self, tokens: set) -> List[str]:
        """Canonical entities whose ALIAS tokens all appear in the query —
        the read-time half of alias handling (write-time half: add_fact)."""
        rows = self.db.execute("SELECT alias, canonical FROM entity_aliases").fetchall()
        out = []
        for alias, canonical in rows:
            at = set(alias.split())
            if alias in tokens or (at and at <= tokens):
                if canonical not in out:
                    out.append(canonical)
        return out[:10]

    # -------------------------------------------------------- transactions
    def begin(self):
        """BEGIN IMMEDIATE — take the write lock up front so concurrent
        ingests serialize here (waiting via busy_timeout) instead of
        interleaving autocommit writes. Makes add() all-or-nothing."""
        if not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")

    def commit(self):
        if self.db.in_transaction:
            self.db.execute("COMMIT")

    def rollback(self):
        if self.db.in_transaction:
            self.db.execute("ROLLBACK")
        # rolled-back rows may already sit in the incremental vector cache
        # queue — drop everything and rebuild lazily from the db truth.
        self._dirty = {"episode": True, "fact": True, "entity": True}
        self._pending = {"episode": [], "fact": []}

    # ------------------------------------------------------ idempotent ingest
    def seen_ingest(self, h: str) -> Optional[str]:
        row = self.db.execute(
            "SELECT session_id FROM ingest_log WHERE hash=?", (h,)).fetchone()
        return row[0] if row else None

    def log_ingest_claim(self, h: str, session_id: str) -> bool:
        """Atomically claim an ingest hash (call inside the transaction, BEFORE
        writing). Two concurrent ingests of the same session serialize on
        BEGIN IMMEDIATE; the loser's INSERT OR IGNORE hits the PK and returns
        False. A crash before COMMIT rolls the claim back with the data, so
        a retry re-ingests cleanly — no partial sessions, no double sessions."""
        cur = self.db.execute(
            "INSERT OR IGNORE INTO ingest_log(hash, session_id, ingested_at) VALUES(?,?,?)",
            (h, session_id, utcnow()))
        return cur.rowcount == 1

    # ----------------------------------------------------- erasure (cascade)
    def _erase_facts(self, fact_ids: List[int]) -> int:
        """Cascade-delete facts: FTS rows, key index, entity links, and any
        dangling superseded_by pointers. Distinct from supersession — this is
        owner-initiated erasure (data ownership), not knowledge update."""
        if not fact_ids:
            return 0
        marks = ",".join("?" for _ in fact_ids)
        for (fid, stmt) in self.db.execute(
                f"SELECT id, statement FROM facts WHERE id IN ({marks})", fact_ids):
            self.db.execute(
                "INSERT INTO facts_fts(facts_fts, rowid, statement) VALUES('delete',?,?)",
                (fid, stmt))
            self.db.execute("DELETE FROM fact_keys_fts WHERE rowid=?", (fid,))
        self.db.execute(f"DELETE FROM entities WHERE fact_id IN ({marks})", fact_ids)
        self.db.execute(
            f"UPDATE facts SET superseded_by=NULL WHERE superseded_by IN ({marks})",
            fact_ids)
        cur = self.db.execute(f"DELETE FROM facts WHERE id IN ({marks})", fact_ids)
        self._dirty = {"episode": True, "fact": True, "entity": True}
        self._pending = {"episode": [], "fact": []}
        return cur.rowcount

    def erase_session(self, session_id: str) -> dict:
        """Erase everything ingested under a session: episodes, their FTS rows,
        facts extracted from them, entity links, embeddings — AND any derived
        observation/digest summaries whose subject, predicate digest, or
        entities overlap the erased facts. Digests aggregate across sessions,
        so we over-delete in the safe direction: the dropped summaries are
        regenerable from surviving facts via refresh_observations()."""
        eps = self.db.execute(
            "SELECT id, content FROM episodes WHERE session_id=?", (session_id,)).fetchall()
        for eid, content in eps:
            self.db.execute(
                "INSERT INTO episodes_fts(episodes_fts, rowid, content) VALUES('delete',?,?)",
                (eid, content))
        self.db.execute("DELETE FROM episodes WHERE session_id=?", (session_id,))
        fids = [r[0] for r in self.db.execute(
            "SELECT id FROM facts WHERE session_id=?", (session_id,)).fetchall()]
        # collect the contamination surface BEFORE the cascade removes it
        obs_targets = set()
        if fids:
            marks = ",".join("?" for _ in fids)
            for s, p in self.db.execute(
                    f"SELECT DISTINCT subject, predicate FROM facts WHERE id IN ({marks})",
                    fids):
                obs_targets.add(s)
                obs_targets.add(f"digest:{p}")
            obs_targets.update(self.entities_of_facts(fids))
        facts_gone = self._erase_facts(fids)
        obs_gone = 0
        if obs_targets:
            targets = list(obs_targets)
            marks = ",".join("?" for _ in targets)
            obs_ids = [r[0] for r in self.db.execute(
                f"SELECT id FROM facts WHERE kind='observation' AND "
                f"(subject IN ({marks}) OR predicate IN ({marks}))",
                targets * 2)]
            obs_gone = self._erase_facts(obs_ids)
        self.db.execute("DELETE FROM ingest_log WHERE session_id=?", (session_id,))
        return {"episodes": len(eps), "facts": facts_gone, "observations": obs_gone}

    def erase_entity(self, name: str) -> dict:
        """Erase all facts linked to an entity (raw episodes are untouched —
        use erase_session for transcript-level erasure)."""
        canonical = self.resolve_entity(name)
        fids = [r[0] for r in self.db.execute(
            "SELECT DISTINCT fact_id FROM entities WHERE name=?", (canonical,)).fetchall()]
        facts_gone = self._erase_facts(fids)
        self.db.execute("DELETE FROM entity_aliases WHERE canonical=?", (canonical,))
        return {"entity": canonical, "facts": facts_gone}

    # ----------------------------------------------------- export / import
    def export_data(self) -> dict:
        """Everything needed to reconstruct the store, embeddings included
        (base64 float32), so restore needs no re-embedding and no network."""
        import base64
        b64 = lambda b: base64.b64encode(b).decode() if b else None
        episodes = [dict(id=r[0], session_id=r[1], role=r[2], content=r[3],
                         ts=r[4], emb=b64(r[5]))
                    for r in self.db.execute(
                        "SELECT id, session_id, role, content, ts, emb FROM episodes")]
        facts = []
        for r in self.db.execute(
                """SELECT id, statement, subject, predicate, object, kind,
                   event_date, ingested_at, valid_from, invalid_at,
                   superseded_by, episode_id, session_id, emb FROM facts"""):
            krow = self.db.execute(
                "SELECT keys FROM fact_keys_fts WHERE rowid=?", (r[0],)).fetchone()
            facts.append(dict(
                id=r[0], statement=r[1], subject=r[2], predicate=r[3],
                object=r[4], kind=r[5], event_date=r[6], ingested_at=r[7],
                valid_from=r[8], invalid_at=r[9], superseded_by=r[10],
                episode_id=r[11], session_id=r[12], emb=b64(r[13]),
                search_keys=krow[0] if krow else None))
        entities = [dict(name=r[0], fact_id=r[1]) for r in
                    self.db.execute("SELECT name, fact_id FROM entities")]
        aliases = [dict(alias=r[0], canonical=r[1]) for r in
                   self.db.execute("SELECT alias, canonical FROM entity_aliases")]
        ingest_log = [dict(hash=r[0], session_id=r[1], ingested_at=r[2]) for r in
                      self.db.execute("SELECT hash, session_id, ingested_at FROM ingest_log")]
        return {"format": "smriti-export", "version": 2, "exported_at": utcnow(),
                "episodes": episodes, "facts": facts, "entities": entities,
                "aliases": aliases, "ingest_log": ingest_log}

    def import_data(self, data: dict):
        """Restore an export into an EMPTY store (strict, lossless restore —
        ids are preserved so supersession chains and episode links survive)."""
        import base64
        if data.get("format") != "smriti-export":
            raise ValueError("not a smriti export")
        s = self.stats()
        if s["episodes"] or s["facts"]:
            raise ValueError("import requires an empty store (restore semantics)")
        unb64 = lambda t: base64.b64decode(t) if t else None
        for e in data.get("episodes", []):
            self.db.execute(
                "INSERT INTO episodes(id, session_id, role, content, ts, emb) VALUES(?,?,?,?,?,?)",
                (e["id"], e["session_id"], e["role"], e["content"], e["ts"], unb64(e.get("emb"))))
            self.db.execute("INSERT INTO episodes_fts(rowid, content) VALUES(?,?)",
                            (e["id"], e["content"]))
        for f in data.get("facts", []):
            self.db.execute(
                """INSERT INTO facts(id, statement, subject, predicate, object, kind,
                   event_date, ingested_at, valid_from, invalid_at, superseded_by,
                   episode_id, session_id, emb) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (f["id"], f["statement"], f["subject"], f["predicate"], f["object"],
                 f["kind"], f["event_date"], f["ingested_at"], f["valid_from"],
                 f["invalid_at"], f["superseded_by"], f["episode_id"],
                 f["session_id"], unb64(f.get("emb"))))
            self.db.execute("INSERT INTO facts_fts(rowid, statement) VALUES(?,?)",
                            (f["id"], f["statement"]))
            if f.get("search_keys"):
                self.db.execute("INSERT INTO fact_keys_fts(rowid, keys) VALUES(?,?)",
                                (f["id"], f["search_keys"]))
        for ent in data.get("entities", []):
            self.db.execute("INSERT INTO entities(name, fact_id) VALUES(?,?)",
                            (ent["name"], ent["fact_id"]))
        for al in data.get("aliases", []):
            self.db.execute(
                "INSERT OR REPLACE INTO entity_aliases(alias, canonical) VALUES(?,?)",
                (al["alias"], al["canonical"]))
        for il in data.get("ingest_log", []):
            self.db.execute(
                "INSERT OR IGNORE INTO ingest_log(hash, session_id, ingested_at) VALUES(?,?,?)",
                (il["hash"], il["session_id"], il["ingested_at"]))
        self._dirty = {"episode": True, "fact": True, "entity": True}
        self._pending = {"episode": [], "fact": []}
