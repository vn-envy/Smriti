"""AuditSink implementations — receipts never live in the memory file.

Reads must not become writes in the primary store; packs must stay truly
read-only; audit retention must decouple from memory retention. Profiles:
  * NullSink            local mode — receipts discarded (still returned to caller)
  * JSONLSink           append-only file, chain fields included
  * SidecarSQLiteSink   team/regulated mode — separate `<name>.audit.db`
"""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from .receipts import HMACSigner, canonical, digest, verify_chain


class NullSink:
    def append(self, receipt: dict) -> dict:
        return {"seq": -1, "hash": digest(receipt), "persisted": False}

    def verify(self, signer=None) -> dict:
        return {"receipts": 0, "violations": 0, "checkpoints_verified": 0, "ok": True}


class JSONLSink:
    def __init__(self, path: str, signer: Optional[HMACSigner] = None,
                 checkpoint_every: int = 100):
        self.path, self.signer, self.every = path, signer, checkpoint_every
        self._seq, self._prev = self._tail()

    def _tail(self):
        seq, prev = 0, ""
        try:
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    row = json.loads(line)
                    seq, prev = row["seq"], row["hash"]
        except FileNotFoundError:
            pass
        return seq, prev

    def append(self, receipt: dict) -> dict:
        body = canonical(receipt).decode()
        self._seq += 1
        h = digest(self._prev + body)
        row = {"seq": self._seq, "body": body, "hash": h, "prev_hash": self._prev}
        if self.signer and self._seq % self.every == 0:
            row["checkpoint"] = self.signer.sign(h.encode())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._prev = h
        return {"seq": self._seq, "hash": h, "persisted": True}

    def rows(self):
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                yield (r["seq"], r["body"], r["hash"], r["prev_hash"],
                       json.dumps(r["checkpoint"]) if "checkpoint" in r else None)

    def verify(self, signer=None) -> dict:
        return verify_chain(self.rows(), signer=signer or self.signer)


class SidecarSQLiteSink:
    """Separate SQLite file (`memory.audit.db`), WAL, append-only by convention;
    integrity by chain + optional keyed checkpoints, not by trusting the file."""

    def __init__(self, path: str, signer: Optional[HMACSigner] = None,
                 checkpoint_every: int = 100):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS receipts("
            "seq INTEGER PRIMARY KEY, ts TEXT, op TEXT, body TEXT,"
            "hash TEXT, prev_hash TEXT, checkpoint TEXT)")
        self.signer, self.every = signer, checkpoint_every

    def append(self, receipt: dict) -> dict:
        body = canonical(receipt).decode()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT seq, hash FROM receipts ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (row[0] if row else 0) + 1
            prev = row[1] if row else ""
            h = digest(prev + body)
            cp = None
            if self.signer and seq % self.every == 0:
                cp = json.dumps(self.signer.sign(h.encode()))
            self.db.execute(
                "INSERT INTO receipts(seq, ts, op, body, hash, prev_hash, checkpoint)"
                " VALUES(?,?,?,?,?,?,?)",
                (seq, receipt.get("ts"), receipt.get("op"), body, h, prev, cp))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return {"seq": seq, "hash": h, "persisted": True}

    def rows(self):
        yield from self.db.execute(
            "SELECT seq, body, hash, prev_hash, checkpoint FROM receipts ORDER BY seq")

    def verify(self, signer=None) -> dict:
        return verify_chain(self.rows(), signer=signer or self.signer)
