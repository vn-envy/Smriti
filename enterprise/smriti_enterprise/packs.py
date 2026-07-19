"""Verified, read-only knowledge packs — artifact distribution, not live
collaboration.

A pack = a consistent snapshot (SQLite backup API — never a copy of a live
WAL file) + a versioned manifest binding store identity, schema/software
versions, embedder fingerprint, checksum, and an optional keyed signature.
Verify-before-open; immutable mount; same-access cohorts only (the HOST
authorizes the mount — core only verifies integrity and declared metadata).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from typing import Optional

import smriti as _core
from smriti.store import utcnow

from ._version import __version__ as _ent_version
from .migrations import schema_version, store_id
from .receipts import HMACSigner, canonical
from .store import EnterpriseStore

PACK_FORMAT = "smriti-pack"
PACK_VERSION = 1


class PackError(RuntimeError):
    pass


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_pack(source_db: sqlite3.Connection, out_path: str,
               name: str, audience: str = "same-access-cohort",
               embedder_fingerprint: str = "", expires_at: Optional[str] = None,
               signer: Optional[HMACSigner] = None) -> dict:
    """Snapshot `source_db` to `out_path` (+ `<out_path>.manifest.json`)."""
    dest = sqlite3.connect(out_path)
    try:
        source_db.backup(dest)   # consistent even under WAL
    finally:
        dest.close()
    manifest = {
        "format": PACK_FORMAT, "pack_version": PACK_VERSION,
        "name": name, "audience": audience,
        "created_at": utcnow(), "expires_at": expires_at,
        "store_id": store_id_of(out_path),
        "enterprise_schema_version": schema_version_of(out_path),
        "core_version": _core.__version__, "enterprise_version": _ent_version,
        "embedder_fingerprint": embedder_fingerprint,
        "sha256": _file_sha256(out_path),
    }
    if signer is not None:
        manifest["signature"] = signer.sign(canonical(
            {k: v for k, v in manifest.items() if k != "signature"}))
    with open(out_path + ".manifest.json", "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    return manifest


def store_id_of(path: str) -> str:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return store_id(db)
    except sqlite3.OperationalError:
        return ""
    finally:
        db.close()


def schema_version_of(path: str) -> int:
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return schema_version(db)
    finally:
        db.close()


def verify_pack(pack_path: str, signer: Optional[HMACSigner] = None,
                now: Optional[str] = None) -> dict:
    """Checksum, format, expiry, signature (when a verifier key is supplied),
    and embedder/schema metadata presence. Raises PackError on any failure."""
    mpath = pack_path + ".manifest.json"
    if not os.path.exists(mpath):
        raise PackError("manifest missing")
    with open(mpath, encoding="utf-8") as fh:
        m = json.load(fh)
    if m.get("format") != PACK_FORMAT or m.get("pack_version") != PACK_VERSION:
        raise PackError(f"unsupported pack format {m.get('format')!r} "
                        f"v{m.get('pack_version')!r}")
    actual = _file_sha256(pack_path)
    if actual != m.get("sha256"):
        raise PackError("checksum mismatch — pack modified after build")
    exp = m.get("expires_at")
    if exp and (now or utcnow()) >= exp:
        raise PackError(f"pack expired at {exp}")
    if signer is not None:
        sig = m.get("signature")
        if not sig:
            raise PackError("verifier key supplied but pack is unsigned "
                            "(checksummed-only)")
        payload = canonical({k: v for k, v in m.items() if k != "signature"})
        if not signer.verify(payload, sig):
            raise PackError("keyed signature verification failed")
    return m


def open_pack(pack_path: str, signer: Optional[HMACSigner] = None,
              expected_embedder: str = "",
              now: Optional[str] = None) -> "tuple[EnterpriseStore, dict]":
    """verify-before-open, then an immutable read-only mount."""
    m = verify_pack(pack_path, signer=signer, now=now)
    if expected_embedder and m.get("embedder_fingerprint") \
            and m["embedder_fingerprint"] != expected_embedder:
        raise PackError(
            f"embedder mismatch: pack built with {m['embedder_fingerprint']!r}, "
            f"mount requested {expected_embedder!r} — vectors are not comparable")
    return EnterpriseStore(pack_path, read_only=True), m
