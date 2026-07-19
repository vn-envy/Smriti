# SMRITI Enterprise — Assurance & Control Map

**Last reviewed:** 2026-07-19 · **Applies to:** smriti-agents 0.3.2 + smriti-enterprise 0.1.0

This document states what the software does, what it does **not** do, and what remains the customer's responsibility. It is engineering documentation, not legal advice, and not a certification.

## Position

> SMRITI is a minimal, customer-controlled temporal-memory kernel for AI agents. It preserves how knowledge changes and emits canonical, integrity-checkable receipts for the evidence delivered to an agent. **It helps customers implement governance controls; it does not make the surrounding AI system compliant by itself.**

## Control map

Legend: **supported** = implemented and covered by tests · **partial** = implemented with stated limits · **absent** = not implemented (customer or host responsibility).

| Control | Status | Mechanism | Evidence | Limitations |
|---|---|---|---|---|
| Change history preserved (no destructive update) | supported | supersession: `invalid_at` + `superseded_by`, never delete-on-write | core suite | applies to extracted facts; raw episodes are append-only |
| World-time vs knowledge-time separation | supported | `valid_from/invalid_at` (world) vs `recorded_at/withdrawn_at` (knowledge) | `test_asof_known_reconstructs_historical_belief`, `test_world_and_knowledge_axes_are_independent` | knowledge time for rows migrated from a pre-enterprise store is **approximated** from `ingested_at`/`ts` |
| As-of retrieval ("what did we believe on date X") | supported | `facts_asof(world=, known=)` | 3 tests | operates on facts; episode-level as-of is not modelled |
| Derivation lineage (exact parents) | supported | `derivations` table: episode→fact (all episodes), fact→observation | `test_facts_link_to_every_episode_in_session`, `test_observation_carries_exact_parent_facts` | lineage recorded from the enterprise wrapper; direct core writes bypass it |
| Memory-evidence receipts | supported | canonical JSON receipt per ingest/search/context/lifecycle op, binds exact packed-context digest | `test_context_receipt_binds_exact_packed_bytes` | binds **what SMRITI delivered**; it cannot reconstruct the agent's decision (host must correlate prompts/tools/approvals via `correlation_id`) |
| Receipt minimization | supported | query and result text stored as SHA-256 digests by default | `test_receipts_minimize_by_default` | a digest is not anonymity for low-entropy personal data |
| Tamper **evidence** (accidental/partial) | supported | hash chain (`prev_hash`, `seq`) verified by `verify_audit()` | `test_chain_detects_row_modification`, `test_chain_detects_truncation` | an unkeyed chain does **not** prove authenticity against an administrator with write access to the sink |
| Tamper **authenticity** | partial | HMAC-SHA256 checkpoints with a customer-held key | `test_keyed_checkpoints_verify_and_detect_wrong_key` | shared-key MAC, not an asymmetric signature; strength = key custody. External anchoring is not implemented (interface only) |
| Audit isolated from memory | supported | `AuditSink` writes to a sidecar file/SIEM, never the memory DB | `test_audit_lives_outside_the_memory_file` | — |
| Retention windows | supported | `retain_until` + `sweep()` | `test_retention_sweep_erases_expired_and_skips_held` | sweep is caller-invoked; no scheduler in core |
| Legal hold | supported | structured `holds` record (scope, reason, authority, expiry, release); blocks erasure and sweeps | `test_hold_blocks_erasure_until_released` | hold is a storage control, not a legal determination |
| Owner-initiated deletion | **partial** | transactional, hold-aware, lineage-exact erasure of episodes/facts/derived observations/FTS/entity links/embeddings | `test_erasure_follows_exact_lineage_not_heuristics`, `test_erasure_is_transactional_under_failure` | **logical unreachability from the active store.** Residuals may persist in: WAL/free pages, prior snapshots/exports/packs, backups, audit receipts (digests), and any remote processor that already received the content. See "Deletion coverage" below |
| Deployment profiles / egress control | partial | `local` rejects non-loopback built-in adapters; `team`/`regulated` enforce an allowlist; fail closed | `test_local_profile_rejects_remote_adapter`, `test_team_profile_enforces_allowlist` | covers **built-in** adapters only. Custom Python adapters and process-level egress must be constrained by container/firewall policy — that is the deployment boundary's job |
| Data-flow transparency | supported | `describe_data_flow()` machine-readable map | `test_describe_data_flow_is_machine_readable` | reports configured adapters, not runtime network activity |
| Secret redaction before persistence | partial | forced on in `local`; applied on **every** write path incl. direct `add_fact` | `test_local_profile_forces_redaction_on_every_write_path` | conservative pattern set (API keys/tokens/passwords); not a DLP engine, no PII classification |
| Untrusted-content boundary | partial | immutable `origin` at write + mutable `quarantined` review state + `strict=True` retrieval filter | `test_strict_profile_excludes_quarantined_and_untrusted` | origin is assigned by the calling host; a caller-declared label is only as trustworthy as the caller |
| Verified knowledge packs | supported | consistent snapshot (SQLite backup API), manifest with versions + embedder fingerprint, SHA-256, optional keyed signature, verify-before-open, read-only mount | 7 pack tests | revocation is effective only when the client refreshes; a checksummed-only pack is **not** signed |
| Read-only enforcement | supported | `mode=ro` URI + `PRAGMA query_only` | `test_pack_mount_is_read_only`, `test_federation_never_writes_to_packs` | — |
| Multi-store federation | supported | RRF fusion across stores, provenance tag per result, writes only to the personal store | 2 federation tests | **same-access cohorts only** — packs must not contain mixed-ACL content flattened into one file |
| Schema migrations | supported | `PRAGMA user_version`, transactional, idempotent, backfilling | 3 migration tests | forward migration only; downgrade = restore from backup |
| Crash-safe ingest | supported (core) | `BEGIN IMMEDIATE` claim + writes, rollback on failure | core `test_failed_ingest_rolls_back_completely` | — |
| Authentication / authorization | **absent** | — | — | no network listener exists; identity/authorization belong to the host (and to the optional future `smriti-server` module) |
| Multi-tenant isolation | **absent** | — | — | file-per-scope is *containment*, not isolation by construction; namespaces are never a security boundary |
| Encryption at rest | **absent** | — | — | use filesystem/FDE/LUKS or an optional SQLCipher build; no application-layer encryption in core |
| SIEM/OpenTelemetry export | partial | JSONL sink is SIEM-ingestable | — | no native OTel exporter yet |
| External anchoring of checkpoints | **absent** | interface only | — | publishing checkpoint digests to an external authority is module territory |

## Deletion coverage (explicit)

Erasure is scoped and stated, never claimed as physical destruction:

1. **Active store — removed.** Rows, FTS entries, entity links, embeddings, derived observations (by exact lineage), ingest-log entry. Transactional.
2. **WAL / free pages — not guaranteed.** SQLite keeps state outside the main file; `secure_delete` is off by default and virtual tables may retain traces. Run `VACUUM` (+ `PRAGMA secure_delete=ON` before writes) if local purge matters.
3. **Snapshots, packs, exports, backups — not covered.** They are independent artifacts; expire them via your own retention process.
4. **Audit receipts — retained by design.** They hold digests and IDs, not content, and their retention is deliberately decoupled from memory retention.
5. **Remote processors — out of scope.** Anything already sent to a remote LLM/embedder is governed by that processor's agreement. Use `local` profile to avoid this class entirely.
6. **Cryptographic erasure — not implemented.** Meaningful only with per-store keys (future module).

## Shared responsibility

| Layer | Owner |
|---|---|
| Memory semantics, lineage, receipts, lifecycle primitives, read-only enforcement, secure defaults, release provenance, vulnerability response | **SMRITI** |
| User/workload identity, delegated authority, human approval, prompt/model/tool traces, action execution and reversal, correlating receipts with the end-to-end record | **Host application** |
| Legal basis and system classification, IAM, network/firewall/container boundary, keys, backups, monitoring, retention & hold policy, authorized administrators, model/provider choice and processor agreements, the compliance conclusion for the complete system | **Customer** |

## Regulatory posture (not legal advice)

- **EU AI Act:** the Digital Omnibus political agreement (May 2026) defers Annex III high-risk obligations to **2 Dec 2027** and Annex I product-embedded obligations to **2 Aug 2028**; until formal adoption the original dates remain operative. Article 12 applies to a high-risk **system**; SMRITI is a component that can supply lifecycle and retrieval-evidence records toward that obligation. It cannot satisfy it alone.
- **GDPR / DPDP:** SMRITI provides mechanisms (erasure scope, retention, holds, export, minimization). Legal basis, exceptions, and the erasure decision remain the controller's.
- **Localization:** DPDP does not impose blanket India-only localization; RBI localization is workload-specific. Local-first is justified here by **customer control and reduced data movement**, not by a universal mandate.

## Claims we do not make

No certification (SOC 2 / ISO / HIPAA) is conferred by installing a library. We do not claim "inherits your compliance", "zero retention" while retaining memory, "tamper-proof", "physical erasure", "isolation by construction" for multi-tenancy, or "full reconstruction of an agent's decision".
