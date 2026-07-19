# SMRITI Enterprise

**Replaceable enterprise modules over an untouched core.** Zero core edits: the base package (`smriti-agents`) and its 85 tests are unchanged — everything here layers on top. Dependencies: `smriti-agents` + the Python standard library. No graph DB, no Postgres, no server, no vendor cloud.

> SMRITI is a minimal, customer-controlled temporal-memory kernel for AI agents. It preserves how knowledge changes and emits canonical, integrity-checkable receipts for the evidence delivered to an agent. **It helps customers implement governance controls; it does not make the surrounding AI system compliant by itself.** — [ASSURANCE.md](ASSURANCE.md)

## Install

```bash
pip install -e .          # from this directory (requires smriti-agents >= 0.3.2)
python -m pytest tests/   # 39 offline tests — no network, no keys
python demo.py            # end-to-end walkthrough
```

## What it adds

### 1. Tri-temporal semantics — three concepts, never one column

| Axis | Fields | Question it answers |
|---|---|---|
| World validity | `valid_from` / `invalid_at` | when was this true in the world? |
| System knowledge | `recorded_at` / `withdrawn_at` | when did this store believe it? |
| Storage lifecycle | `retain_until` / `hold_id` | when may/must it remain stored? |

```python
mem.facts_asof(known="2026-03-01T00:00:00Z")   # what we believed in March
mem.facts_asof(world="2026-03-01T00:00:00Z")   # what was true in March
```

The user moved on **June 1**; the store learned it on **July 10**. As-of-known on March 1 still returns Hyderabad — late-arriving corrections no longer rewrite history.

### 2. Exact derivation lineage

`derivations` edges record episode→fact (every episode in the session, not just the first) and fact→observation. Erasure follows those edges instead of heuristic subject/entity overlap.

### 3. Memory-evidence receipts

Every ingest, search, context, and lifecycle operation emits a canonical receipt binding versions, policy decision, ordered result identities with validity state, and the **exact packed-context digest** — to a replaceable `AuditSink` (never the memory file). Chain detects tampering; customer-key HMAC checkpoints detect rewrites. Integrity tiers are stated honestly in [RECEIPT-SCHEMA.md](RECEIPT-SCHEMA.md).

```python
from smriti_enterprise import EnterpriseSmriti, SidecarSQLiteSink, HMACSigner

signer = HMACSigner(open("/run/secrets/audit.key","rb").read(), key_id="k1")
mem = EnterpriseSmriti("memory.db", profile="regulated",
                       sink=SidecarSQLiteSink("memory.audit.db", signer=signer),
                       signer=signer)
ctx = mem.context("where do I live?", correlation_id="req-4f2a")
mem.verify_audit()   # {'receipts': 12, 'violations': 0, 'ok': True}
```

### 4. Lifecycle: retention, legal holds, hold-aware erasure

```python
mem.set_retention("session-42", "2027-01-01T00:00:00Z")
hid = mem.place_hold("session", "session-42", reason="litigation", authority="legal@corp")
mem.erase_session("session-42")   # raises HeldError until released
mem.sweep()                       # erases expired, reports skipped_held
```

Deletion is documented as **logical unreachability from the active store**, with residuals (WAL/free pages, snapshots, backups, remote processors) listed explicitly — never "the bytes are gone".

### 5. Deployment profiles that fail closed

| Profile | Built-in adapter egress | Redaction | Sink |
|---|---|---|---|
| `local` | loopback only (`EgressError` otherwise) | forced on | optional |
| `team` | allowlist required | recommended | sidecar expected |
| `regulated` | allowlist required | recommended | **required** |

Plus `describe_data_flow()` for a machine-readable egress map. The library check covers built-in adapters; custom adapters and process egress are the deployment boundary's job — stated, not pretended away.

### 6. Verified knowledge packs + federation

Artifact distribution, **not** live collaboration. A pack is a consistent snapshot (SQLite backup API) plus a manifest binding store identity, versions, embedder fingerprint, SHA-256, and an optional keyed signature. Verify-before-open, immutable read-only mount, same-access cohorts only.

```python
mem.build_pack("org-knowledge.pack.db", name="org-handbook",
               embedder_fingerprint="nomic-embed-text-768", expires_at="2026-12-31T00:00:00Z")

org, manifest = open_pack("org-knowledge.pack.db", signer=signer,
                          expected_embedder="nomic-embed-text-768")
hits = retrieve_multi([("personal", mem.store), ("org", org)], mem.embedder,
                      "what's the expense policy?", k=8)   # RRF across stores
```

Writes go to your store only; results carry `store:<name>` provenance.

## What is deliberately absent

Authentication/authorization (no network listener exists — host territory), multi-tenant isolation (file-per-scope is *containment*; namespaces are never a security boundary), encryption at rest (use FDE/LUKS or a future SQLCipher module), external audit anchoring (interface only), dashboards, connectors. See [SECURITY.md](SECURITY.md) for the full threat model and the operator hardening checklist.

## Docs

- [ASSURANCE.md](ASSURANCE.md) — control map (supported / partial / absent), deletion coverage, shared responsibility, regulatory posture
- [SECURITY.md](SECURITY.md) — trust boundaries, 12 threats with mitigations and residual risk, hardening checklist
- [RECEIPT-SCHEMA.md](RECEIPT-SCHEMA.md) — canonical receipt v0, integrity tiers, what a receipt can and cannot prove
