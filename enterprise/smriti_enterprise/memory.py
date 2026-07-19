"""EnterpriseSmriti — the composed enterprise surface over an untouched core.

Everything here is a wrapper: profiles enforce egress, writes are stamped with
identity/knowledge-time/origin, lineage edges are recorded, reads emit
memory-evidence receipts to a replaceable AuditSink, and lifecycle operations
(erase/hold/retention/sweep) are transactional and hold-aware. Core behavior
and its A/B evidence remain byte-identical underneath.
"""
from __future__ import annotations

import uuid as _uuid
from typing import List, Optional

import smriti as _core
from smriti import Smriti
from smriti.memory import redact_secrets
from smriti.store import utcnow
from smriti.types import Fact, RetrievalResult

from ._version import __version__ as _ent_version
from . import lifecycle, lineage, policy
from .migrations import ENTERPRISE_SCHEMA_VERSION
from .packs import build_pack
from .receipts import HMACSigner, build_receipt, digest
from .sinks import NullSink
from .store import EnterpriseStore
from .temporal import facts_asof


class EnterpriseSmriti(Smriti):
    def __init__(self, path: str = ":memory:", profile: str = "local",
                 sink=None, signer: Optional[HMACSigner] = None,
                 allowlist: Optional[set] = None, origin_default: str = "owner",
                 **kw):
        if profile not in policy.PROFILES:
            raise ValueError(f"unknown profile {profile!r}; known: {policy.PROFILES}")
        if profile == "local":
            kw.setdefault("redact", True)   # forced-on unless caller overrides
        super().__init__(path=path, **kw)
        # replace the core store with the enterprise store (runs migration)
        stem = kw.get("stem", False)
        self.store.db.close()
        self.store = EnterpriseStore(path, stem=stem)
        # profile enforcement: built-in adapter egress fails closed
        policy.check_egress(profile, [self.embedder, self.llm, self.reranker],
                            allowlist=allowlist)
        if profile == "regulated" and (sink is None or isinstance(sink, NullSink)):
            raise ValueError("profile 'regulated' requires a persistent AuditSink")
        self.profile = profile
        self.sink = sink or NullSink()
        self.signer = signer
        self.origin_default = origin_default
        self.last_receipt: Optional[dict] = None

    # ------------------------------------------------------------ internals
    def _versions(self) -> dict:
        return {"core": _core.__version__, "enterprise": _ent_version,
                "schema": ENTERPRISE_SCHEMA_VERSION,
                "store_id": self.store.store_id, "profile": self.profile}

    def _emit(self, op: str, body: dict, correlation_id: Optional[str] = None) -> dict:
        receipt = build_receipt(op, body, self._versions(),
                                correlation_id=correlation_id)
        meta = self.sink.append(receipt)
        receipt["_sink"] = meta
        self.last_receipt = receipt
        return receipt

    def _stamp_session(self, session_id: str, origin: str,
                       recorded_at: Optional[str] = None):
        """Post-ingest stamping: stable uuids, knowledge time, origin — plus
        full episode->fact derivation edges (core links only the first).

        recorded_at (system-knowledge time) = the ingestion timestamp: 'when
        this store learned it'. For a live turn that equals wall-clock; for a
        replay/backfill it is the provided timestamp, which is what makes
        as-of-known queries reconstruct historical belief deterministically."""
        db = self.store.db
        db.execute("BEGIN IMMEDIATE")
        try:
            now = recorded_at or utcnow()
            for (eid,) in db.execute(
                    "SELECT id FROM episodes WHERE session_id=? AND uuid IS NULL",
                    (session_id,)).fetchall():
                db.execute(
                    "UPDATE episodes SET uuid=?, recorded_at=?, origin=? WHERE id=?",
                    (_uuid.uuid4().hex, now, origin, eid))
            for (fid,) in db.execute(
                    "SELECT id FROM facts WHERE session_id=? AND uuid IS NULL",
                    (session_id,)).fetchall():
                db.execute(
                    "UPDATE facts SET uuid=?, recorded_at=?, origin=? WHERE id=?",
                    (_uuid.uuid4().hex, now, origin, fid))
            eids = [r[0] for r in db.execute(
                "SELECT id FROM episodes WHERE session_id=?", (session_id,))]
            fids = [r[0] for r in db.execute(
                "SELECT id FROM facts WHERE session_id=? AND kind != 'observation'",
                (session_id,))]
            for fid in fids:
                if not lineage.parents_of(self.store, "fact", fid):
                    lineage.add_edges(self.store, "fact", fid,
                                      [("episode", e) for e in eids],
                                      "extract", _core.__version__)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

    @staticmethod
    def _result_evidence(results: List[RetrievalResult]) -> list:
        return [{"kind": r.kind, "id": r.id, "score": round(r.score, 6),
                 "valid_from": r.valid_from, "invalid_at": r.invalid_at,
                 "channels": r.channels, "text_digest": digest(r.text)}
                for r in results]

    # ------------------------------------------------------------ writes
    def add(self, messages, session_id=None, timestamp=None, dedupe=None,
            origin: Optional[str] = None, correlation_id=None) -> dict:
        origin = origin or self.origin_default
        if origin not in policy.VALID_ORIGINS:
            raise ValueError(f"invalid origin {origin!r}")
        out = super().add(messages, session_id=session_id, timestamp=timestamp,
                          dedupe=dedupe)
        if not out.get("deduped"):
            self._stamp_session(out["session_id"], origin, recorded_at=timestamp)
        self._emit("ingest", {"session_id": out["session_id"],
                              "episodes": out["episodes"], "facts": out["facts"],
                              "deduped": bool(out.get("deduped")),
                              "origin": origin}, correlation_id)
        return out

    def add_fact(self, fact: Fact, resolve_conflicts: bool = True,
                 origin: Optional[str] = None, correlation_id=None):
        # redaction covers EVERY write path here, including direct fact writes
        if self.redact:
            fact.statement = redact_secrets(fact.statement)
        fid = super().add_fact(fact, resolve_conflicts=resolve_conflicts)
        if fid is not None:
            self.store.db.execute(
                "UPDATE facts SET uuid=?, recorded_at=?, origin=? WHERE id=?",
                (_uuid.uuid4().hex, utcnow(),
                 origin or self.origin_default, fid))
        self._emit("add_fact", {"fact_id": fid, "stored": fid is not None,
                                "origin": origin or self.origin_default},
                   correlation_id)
        return fid

    def _write_observation(self, subject, predicate, label, facts) -> bool:
        ok = super()._write_observation(subject, predicate, label, facts)
        if ok:
            row = self.store.db.execute(
                "SELECT id FROM facts WHERE kind='observation' AND subject=? "
                "AND predicate=? AND invalid_at IS NULL ORDER BY id DESC LIMIT 1",
                (subject, predicate)).fetchone()
            if row:
                self.store.db.execute(
                    "UPDATE facts SET uuid=?, recorded_at=? WHERE id=? AND uuid IS NULL",
                    (_uuid.uuid4().hex, utcnow(), row[0]))
                lineage.add_edges(self.store, "fact", row[0],
                                  [("fact", f.id) for f in facts if f.id],
                                  "observe", _core.__version__)
        return ok

    # ------------------------------------------------------------- reads
    def context(self, query: str, k=None, now=None, char_budget: int = 9000,
                profile=None, channels=None, correlation_id=None) -> str:
        ctx = super().context(query, k=k, now=now, char_budget=char_budget,
                              profile=profile, channels=channels)
        self._emit("context", {
            "query_digest": digest(query), "retrieval_profile": str(profile),
            "k": k, "char_budget": char_budget,
            "context_digest": digest(ctx), "context_chars": len(ctx),
        }, correlation_id)
        return ctx

    def search(self, query: str, k=None, now=None, profile=None, channels=None,
               strict: bool = False, correlation_id=None):
        hits = super().search(query, k=k, now=now, profile=profile,
                              channels=channels)
        dropped = 0
        if strict:
            kept = policy.strict_filter(self.store, hits)
            dropped = len(hits) - len(kept)
            hits = kept
        self._emit("search", {
            "query_digest": digest(query), "retrieval_profile": str(profile),
            "strict": strict, "dropped_by_policy": dropped,
            "results": self._result_evidence(hits),
        }, correlation_id)
        return hits

    def facts_asof(self, world: Optional[str] = None, known: Optional[str] = None,
                   subject: Optional[str] = None):
        return facts_asof(self.store, world=world, known=known, subject=subject)

    # ---------------------------------------------------------- lifecycle
    def erase_session(self, session_id: str, correlation_id=None) -> dict:
        out = lifecycle.erase_session(self.store, session_id)
        self._emit("erase_session", {"session_id": session_id, **out},
                   correlation_id)
        return out

    def erase_entity(self, name: str, correlation_id=None) -> dict:
        canonical = self.store.resolve_entity(name)
        if lifecycle._active_holds(self.store, "entity", canonical):
            raise lifecycle.HeldError(
                f"entity {canonical!r} is under an active legal hold")
        out = super().erase_entity(name)
        self._emit("erase_entity", out, correlation_id)
        return out

    def place_hold(self, scope_kind: str, scope_value: str, reason: str,
                   authority: str, expires_at=None, correlation_id=None) -> str:
        hid = lifecycle.place_hold(self.store, scope_kind, scope_value,
                                   reason, authority, expires_at)
        self._emit("hold_place", {"hold_id": hid, "scope_kind": scope_kind,
                                  "scope_value": scope_value,
                                  "authority": authority}, correlation_id)
        return hid

    def release_hold(self, hold_id: str, correlation_id=None) -> bool:
        ok = lifecycle.release_hold(self.store, hold_id)
        self._emit("hold_release", {"hold_id": hold_id, "released": ok},
                   correlation_id)
        return ok

    def set_retention(self, session_id: str, retain_until: str) -> int:
        return lifecycle.set_retention(self.store, session_id, retain_until)

    def sweep(self, now=None, correlation_id=None) -> dict:
        out = lifecycle.sweep(self.store, now=now)
        self._emit("sweep", out, correlation_id)
        return out

    def quarantine(self, fact_id: int, flag: bool = True, correlation_id=None) -> bool:
        ok = policy.quarantine(self.store, fact_id, flag)
        self._emit("quarantine", {"fact_id": fact_id, "flag": flag, "ok": ok},
                   correlation_id)
        return ok

    # ------------------------------------------------------ ops & evidence
    def snapshot(self, out_path: str) -> str:
        """Consistent live snapshot via the SQLite backup API (never a raw
        file copy of a WAL database)."""
        import sqlite3
        dest = sqlite3.connect(out_path)
        try:
            self.store.db.backup(dest)
        finally:
            dest.close()
        return out_path

    def build_pack(self, out_path: str, name: str, **pack_kw) -> dict:
        m = build_pack(self.store.db, out_path, name, signer=self.signer,
                       **pack_kw)
        self._emit("pack_build", {"name": name, "sha256": m["sha256"],
                                  "path": out_path})
        return m

    def verify_audit(self) -> dict:
        return self.sink.verify(signer=self.signer)

    def describe_data_flow(self) -> dict:
        return policy.describe_data_flow(self)
