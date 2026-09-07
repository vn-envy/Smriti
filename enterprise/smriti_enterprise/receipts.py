"""Memory-evidence receipts — canonical, chained, verifiable.

A receipt binds what SMRITI delivered: operation, versions, policy, ordered
result identities with validity/knowledge state, and the exact packed-context
digest. It does NOT claim to reconstruct the agent's whole decision — the
host correlates receipts with its own prompt/tool/approval records via
`correlation_id`.

Honesty about integrity tiers (see RECEIPT-SCHEMA.md):
  * chain (prev_hash/seq): detects accidental modification and truncation
    from outside the tail — NOT proof against an administrator with write
    access to the sink.
  * keyed checkpoints (HMAC-SHA256, customer key): authenticity against
    sink rewrites, as strong as the key's custody. Stdlib only.
  * external anchoring (publishing checkpoint digests elsewhere): module
    territory, interface provided.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
from typing import Optional

from smriti.store import utcnow

RECEIPT_SCHEMA_VERSION = "0"


def canonical(obj) -> bytes:
    """Deterministic serialization: sorted keys, tight separators, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def digest(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    elif not isinstance(data, (bytes, bytearray)):
        data = canonical(data)
    return hashlib.sha256(data).hexdigest()


def build_receipt(op: str, body: dict, versions: dict,
                  correlation_id: Optional[str] = None) -> dict:
    return {
        "schema": RECEIPT_SCHEMA_VERSION,
        "op": op,
        "ts": utcnow(),
        "correlation_id": correlation_id,
        "versions": versions,
        "body": body,
    }


class HMACSigner:
    """Keyed checkpoint signer (customer-held key). HMAC-SHA256 — a shared-key
    MAC, deliberately not marketed as an asymmetric signature."""

    def __init__(self, key: bytes, key_id: str = "default"):
        if not isinstance(key, bytes) or not key:
            raise ValueError("HMAC key must be non-empty bytes")
        if not key_id:
            raise ValueError("HMAC key_id must be non-empty")
        self.key = key
        self.key_id = key_id

    def sign(self, payload: bytes) -> dict:
        return {"alg": "HMAC-SHA256", "key_id": self.key_id,
                "mac": _hmac.new(self.key, payload, hashlib.sha256).hexdigest()}

    def verify(self, payload: bytes, sig: dict) -> bool:
        if sig.get("alg") != "HMAC-SHA256" or sig.get("key_id") != self.key_id:
            return False
        expect = _hmac.new(self.key, payload, hashlib.sha256).hexdigest()
        return _hmac.compare_digest(expect, sig.get("mac", ""))


def verify_chain(rows, signer: Optional[HMACSigner] = None,
                 checkpoint_every: Optional[int] = None) -> dict:
    """rows: iterable of (seq, body_json, hash, prev_hash, checkpoint_json|None).
    Recomputes every link; verifies checkpoints when a signer is supplied."""
    prev = ""
    expected_seq = 1
    checked = bad = checkpoints = 0
    for seq, body_json, h, prev_hash, checkpoint in rows:
        checked += 1
        if seq != expected_seq:
            bad += 1
        if prev_hash != prev:
            bad += 1
        if digest(prev_hash + body_json) != h:
            bad += 1
        checkpoint_required = bool(signer and checkpoint_every
                                   and seq % checkpoint_every == 0)
        if checkpoint_required and not checkpoint:
            bad += 1
        if checkpoint and signer is not None:
            checkpoints += 1
            try:
                cp = json.loads(checkpoint)
                valid = isinstance(cp, dict) and signer.verify(h.encode(), cp)
            except (TypeError, ValueError, json.JSONDecodeError):
                valid = False
            if not valid:
                bad += 1
        prev = h
        expected_seq += 1
    return {"receipts": checked, "violations": bad,
            "checkpoints_verified": checkpoints, "ok": bad == 0}
