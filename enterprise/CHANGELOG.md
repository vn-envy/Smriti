# Changelog — smriti-enterprise

## v0.1.0 — E1A + E1B + E2 (2026-07-19)

First enterprise release. Built against `smriti-agents` 0.3.2 with **zero core edits** — the core suite (85 tests) is unchanged and still green.

**E1A — correct substrate (roadmap prerequisite before any compliance positioning)**

- Transactional, idempotent `PRAGMA user_version` migration; backfills stable UUIDs and approximate knowledge time for pre-existing stores.
- **Tri-temporal model**: world validity (`valid_from`/`invalid_at`, core) · system knowledge (`recorded_at`/`withdrawn_at`, new) · storage lifecycle (`retain_until`/`hold_id`, new). Three concepts, never one reused column.
- **Real as-of retrieval** — `facts_asof(world=, known=)` reconstructs historical belief; late-arriving corrections no longer rewrite what the store believed then.
- **Exact derivation lineage** — `derivations` edges for episode→fact (every episode, not just the first) and fact→observation.
- Stable `store_id` + record UUIDs; read-only store opening (`mode=ro` + `query_only`).

**E1B — receipts, policy, lifecycle**

- Canonical, versioned **memory-evidence receipts** to a replaceable `AuditSink` (Null / JSONL / sidecar SQLite) — never the memory file. Binds versions, policy decision, ordered result identities with validity state, and the exact packed-context digest.
- Hash chain (detects modification/truncation) + optional **HMAC-SHA256 checkpoints with a customer-held key** (detects rewrites). Integrity tiers documented honestly; external anchoring is interface-only.
- Receipts minimize by default: query and result text as digests, not plaintext.
- **Retention classes** (`retain_until`, `sweep()`) and **structured legal holds** (scope, reason, authority, expiry, release) that block both sweeps and owner erasure.
- Hold-aware, transactional, **lineage-exact erasure**; documented as logical unreachability with an explicit residuals list.
- **Deployment profiles** (`local`/`team`/`regulated`) with fail-closed egress checks on built-in adapters; `regulated` refuses a null sink; redaction forced on in `local` and applied to every write path including direct `add_fact`.
- Immutable `origin` + mutable `quarantined` review state + `strict=True` retrieval filter for consequential actions. `describe_data_flow()` machine-readable egress map.

**E2 — verified knowledge packs + federation**

- Packs: consistent snapshot via the SQLite **backup API**, manifest binding store identity/versions/embedder fingerprint, SHA-256, optional keyed signature, expiry; **verify-before-open**; immutable read-only mounts. A checksummed-only pack is never presented as signed.
- `retrieve_multi()` fuses ranked lists across stores with the same RRF math the four channels use; results carry `store:<name>` provenance; writes never reach a pack.

**Docs & proof**

- `ASSURANCE.md` (control map with supported/partial/**absent**, deletion coverage, shared responsibility, corrected regulatory posture), `SECURITY.md` (trust boundaries, 12 threats + residual risk, operator checklist), `RECEIPT-SCHEMA.md` (canonical v0, integrity tiers, what a receipt cannot prove).
- **39 offline enterprise tests** (no network, no keys) including negative tests: egress fails closed, packs fail closed on tamper/expiry/wrong-key/unsigned/embedder-mismatch, holds beat erasure, erasure rolls back under failure injection, audit chain detects modification and truncation.
- `demo.py` end-to-end walkthrough; CI runs core + enterprise + demo on 3.9 and 3.12.
