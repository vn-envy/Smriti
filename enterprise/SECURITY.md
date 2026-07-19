# SMRITI Enterprise — Security Model & Threat Model

**Applies to:** smriti-agents 0.3.2 + smriti-enterprise 0.1.0 · **Reviewed:** 2026-07-19

## Trust boundaries

```
[ untrusted content ] -> [ HOST: identity, intent, approval, origin assignment ]
                              -> [ SMRITI: memory semantics, policy filter, receipts ]
                                   -> [ one writable SQLite file per owner/domain ]
                                   -> [ verified read-only packs ]
                                   -> [ AuditSink: sidecar / SIEM ]
                              -> [ model adapters -> allowlisted endpoints only ]
```

SMRITI runs **in-process with the host agent's privileges**. It is a library, not a security perimeter. Its job is to make memory behavior legible and constrainable; the perimeter is the host's process, container, and network policy.

## Deployment profiles

| Profile | Built-in adapter egress | Redaction | Audit sink | Intended use |
|---|---|---|---|---|
| `local` | loopback only — non-loopback **raises `EgressError`** | forced on | optional (Null by default) | desktop/edge/air-gapped, single owner |
| `team` | allowlisted hosts only | recommended | sidecar SQLite expected | shared internal deployment |
| `regulated` | allowlisted hosts only | recommended | **required**, keyed checkpoints recommended | evidence-retaining deployments |

`regulated` refuses to start with a `NullSink`. Profiles fail **closed**.

## Threats and mitigations

| # | Threat | Mitigation | Residual risk |
|---|---|---|---|
| T1 | Untrusted conversation content poisons memory | immutable `origin` set at the host boundary; `quarantined` review state; `strict=True` excludes untrusted/quarantined facts before consequential actions | origin is only as trustworthy as the host that assigns it; no automated poisoning detection |
| T2 | Agent is talked into destroying its own memory | destructive/identity ops (`erase_*`, `add_alias`, holds) are **owner-API only** — never exposed as MCP tools | a compromised host process can call the owner API directly |
| T3 | Silent data exfiltration to a model provider | profile egress checks on built-in adapters; `describe_data_flow()`; `local` profile blocks non-loopback | custom Python adapters and process-level egress require container/firewall enforcement |
| T4 | Secrets persisted into long-term memory | redaction on every write path (incl. direct `add_fact`), forced in `local` | conservative pattern set; not a DLP engine |
| T5 | Audit log rewritten to hide an event | hash chain detects modification/truncation; HMAC checkpoints with a customer key detect rewrites without the key; sink is separate from the memory DB | an unkeyed chain is not authenticity; key custody is the customer's; no external anchoring yet |
| T6 | Tampered or stale knowledge pack mounted | SHA-256 checksum, manifest version/embedder binding, expiry, optional keyed signature, verify-before-open, read-only mount | revocation takes effect only at the next client refresh; host must authorize *which* packs may mount |
| T7 | Cross-scope data leakage via shared packs | packs are for **same-access cohorts**; mixed-ACL flattening is documented as unsupported; writes never reach a pack (enforced read-only) | no per-row ACL model — scope separation is by file |
| T8 | Partial write / crash corrupts state | `BEGIN IMMEDIATE` transactions for ingest, erasure, holds, migrations; rollback tested with failure injection | SQLite-level durability assumptions (no network filesystems) |
| T9 | Concurrent writers corrupt or duplicate | WAL + busy_timeout + first-writer-wins ingest claim; cold-start race fixed and tested | single-writer model; heavy multi-writer needs the future server module |
| T10 | Backup taken from a live WAL database is inconsistent | `snapshot()` and pack building use the SQLite **backup API** | copying the main file by hand is still unsafe — documented |
| T11 | Restore from a foreign/incompatible export | manifest binds core/enterprise/schema versions + embedder fingerprint; mismatch fails closed | — |
| T12 | Multi-tenant cross-access | *not addressed in this package* — file-per-scope is containment; the optional server module owns identity, authz, path allowlisting, per-tenant caches | do not build multi-tenant SaaS on this package alone |

## Reporting a vulnerability

Report privately (see the repository's security contact). Please include version, profile, and a reproduction. We aim to acknowledge within 3 business days. Do not open public issues for exploitable defects.

## Hardening checklist for operators

1. Choose the narrowest profile that works (`local` unless you truly need remote adapters).
2. Enforce egress at the container/firewall level too — the library check covers built-in adapters only.
3. Put the memory file on encrypted storage (FDE/LUKS); SMRITI does not encrypt at rest.
4. Use `regulated` with a keyed sink where evidence matters; store the key in your KMS, not next to the audit file.
5. Run `verify_audit()` on a schedule and alert on `ok: false`.
6. Snapshot via `snapshot()`/pack build, never `cp` on a live WAL database; expire old snapshots on your retention schedule.
7. Set `retain_until` at ingest and run `sweep()` on a schedule; use holds for litigation/audit, and release them explicitly.
8. Assign `origin` honestly at the host boundary and use `strict=True` for consequential actions.
9. Keep destructive operations behind human approval in your host application.
10. Pin versions; migrations are forward-only and downgrades require a restore.
