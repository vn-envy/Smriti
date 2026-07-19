"""Deployment profiles and trust policy.

Profiles (SECURITY.md defines the full contract):
  * local     — built-in remote adapters must be loopback; redaction forced on;
                NullSink default. Custom adapters/process egress are the
                deployment boundary's job (documented, not pretended away).
  * team      — allowlisted endpoints; sidecar audit sink expected.
  * regulated — team + signer required on the sink; strict retrieval default.

Trust: immutable ORIGIN is assigned at the trusted host boundary at write
time (owner | agent | tool | untrusted). Mutable REVIEW state (quarantine)
is separate — a source label is not a trust boundary, review is.
"""
from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlparse

VALID_ORIGINS = ("owner", "agent", "tool", "untrusted")
PROFILES = ("local", "team", "regulated")

_LOOPBACK = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class EgressError(RuntimeError):
    """A built-in adapter points outside the profile's allowed endpoints."""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def check_egress(profile: str, adapters: Iterable, allowlist: Optional[set] = None):
    """Inspect built-in adapters (anything with a base_url/url attribute).
    local: loopback only. team/regulated: allowlist required for non-loopback."""
    for a in adapters:
        if a is None:
            continue
        url = getattr(a, "base_url", None) or getattr(a, "url", None)
        if not url:
            continue  # offline adapters (HashEmbedder, MockLLM) have no endpoint
        host = _host(str(url))
        if host in _LOOPBACK:
            continue
        if profile == "local":
            raise EgressError(
                f"profile 'local' forbids non-loopback endpoint {url!r} "
                f"({type(a).__name__}); use an allowlisted 'team' profile instead")
        if allowlist is not None and host not in allowlist:
            raise EgressError(
                f"endpoint {url!r} is not in the {profile} allowlist")


def describe_data_flow(mem) -> dict:
    """Machine-readable egress/data-flow map — what leaves the process, where."""
    def _ep(a):
        if a is None:
            return None
        url = getattr(a, "base_url", None) or getattr(a, "url", None)
        return {"adapter": type(a).__name__, "endpoint": str(url) if url else None,
                "remote": bool(url) and _host(str(url)) not in _LOOPBACK}
    return {
        "store_path": "local sqlite file (no network)",
        "extraction_llm": _ep(getattr(mem, "llm", None)),
        "embedder": _ep(getattr(mem, "embedder", None)),
        "reranker": _ep(getattr(mem, "reranker", None)),
        "audit_sink": type(getattr(mem, "sink", None)).__name__,
        "redaction": bool(getattr(mem, "redact", False)),
        "telemetry": None,  # none exists; stated explicitly
        "notes": "custom python adapters and process-level egress are governed "
                 "by the deployment boundary (container/firewall), not by this check",
    }


def quarantine(store, fact_id: int, flag: bool = True) -> bool:
    cur = store.db.execute("UPDATE facts SET quarantined=? WHERE id=?",
                           (1 if flag else 0, fact_id))
    return cur.rowcount == 1


def is_quarantined(store, fact_id: int) -> bool:
    row = store.db.execute("SELECT quarantined FROM facts WHERE id=?",
                           (fact_id,)).fetchone()
    return bool(row and row[0])


def strict_filter(store, results, allowed_origins=("owner", "agent", "tool")):
    """The 'strict action profile': drop quarantined and untrusted-origin
    facts from a result list before it reaches a consequential action."""
    out = []
    for r in results:
        if r.kind == "fact" and r.id is not None:
            row = store.db.execute(
                "SELECT origin, quarantined FROM facts WHERE id=?", (r.id,)).fetchone()
            if row:
                origin = row[0] or "owner"
                if row[1] or origin not in allowed_origins:
                    continue
        out.append(r)
    return out
