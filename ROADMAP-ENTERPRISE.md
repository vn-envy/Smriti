# Enterprise SMRITI — the roadmap (v2, finalized)

*Supersedes the v1 draft (July 17). In proper SMRITI fashion the v1 claims are superseded, not deleted — the corrections are listed at the end (*badha* applies to roadmaps too). v2 incorporates an independent expert review (July 18) that audited v1 against the current code, market, and law. Principles unchanged and now enforced as acceptance tests: simplest, lowest-dependency architecture; same or better results; core readable in a sitting; everything enterprise-shaped is a replaceable module.*

## Position

> **SMRITI is a minimal, customer-controlled temporal-memory kernel for AI agents. It preserves how knowledge changes and emits canonical, integrity-checkable receipts for the evidence delivered to an agent. It helps customers implement governance controls; it does not make the surrounding AI system compliant by itself.**

That is a narrower claim than v1's "compliance artifact" — and a stronger product. The wedge is not "the only sovereign memory" (self-hosting, audit logs, retention, legal hold, and BYOC now appear across the market — Zep advertises BYOC/RBAC/legal hold; mem0 documents a self-hosted service; Microsoft and Google document permission-aware grounding and memory controls). The wedge is what none of them are: an **embedded, offline-capable, ~2k-line kernel whose temporal state, data movement, and retrieval evidence are legible enough to verify** — and whose enterprise integrations remain replaceable. Governance features are table stakes at the platform tier; at the embedded-library tier, verifiable behavior is still whitespace.

## The regulatory reality (corrected)

- **EU AI Act:** the Digital Omnibus political agreement (May 6–7, 2026; formal adoption expected before Aug 2, 2026) defers Annex III high-risk obligations to **Dec 2, 2027** and Annex I product-embedded obligations to **Aug 2, 2028**. Until adoption, the original dates remain formally operative. Article 12 requires lifecycle event logging for *high-risk systems as a whole* — a memory component supports that evidence; it cannot deliver "full decision reconstruction" alone (the host owns prompts, models, tools, approvals, outcomes).
- **India:** DPDP does not impose blanket localization; rules are phasing in, and RBI localization is workload-specific. Local-first is justified by **customer control and reduced data movement**, not a universal legal mandate.
- **What this buys us:** the deadline panic is gone; the direction is unchanged. Regulated buyers procure ahead of deadlines, and the corrected claim — *"once receipts and lineage ship, SMRITI produces evidence that supports a customer's Article 12 and governance implementation"* — is durable under any timeline.

## Principles as acceptance tests

| Principle | Enterprise meaning | Rules out |
|---|---|---|
| Minimal | Core = memory semantics, provenance, lifecycle, receipts; enterprise systems connect via narrow interfaces | IdP, KMS, SIEM, DLP, connectors, dashboards in core |
| Simple | One writable store per owner/security domain; immutable read-only packs; boring migrations | in-file row filters as tenant security; hidden distributed state |
| Private | Egress explicit and technically denyable; minimize before storing/logging; deletion scope documented | silent remote embedding; "zero retention" theater; privacy claims resting on self-hosting alone |
| Transparent | Customer can inspect schema, data flows, lineage, pack manifests, responsibility boundary | "inherits your compliance"; a checksum called a signature |

## Ideal customer (and who we don't fight)

Teams that already own an agent application and need embedded memory under their own control: regulated/sensitive internal agents, on-prem/edge/air-gapped deployments, platforms that can't depend on vendor-hosted memory, workflows where stale-memory correction and evidence matter, teams that value a forkable component. We do **not** position against Microsoft/Google/Glean/Notion as organization-wide search — different category, different surface.

---

## The plan (12 weeks, then customer-pulled)

### E0 — Truth reset + assurance pack (week 0–1, mostly documents)

`ASSURANCE.md` (control map with supported/partial/absent + limitations + customer responsibility), `SECURITY.md` + threat model + data-flow/egress map + shared-responsibility matrix, receipt schema v0 (defining exactly what it can and cannot verify), three deployment profiles (local/offline · team/self-hosted · regulated). Replace every v1 overclaim per the appendix. **Parallel GTM track (founder-owned): recruit 3–5 design partners** with on-prem/edge/air-gapped agent workloads. *Exit gate: no statement claims certification, physical erasure, or full decision reconstruction; ≥3 partners validate the problem.*

### E1A — Correct substrate before compliance positioning (weeks 1–4)

The review's deepest catch: today `now` is plumbed but never filters, and `invalid_at` conflates *when the world changed* with *when we learned it*. Fix the semantics first:

1. **Tri-temporal split:** world validity (`valid_from/valid_until`) · system knowledge (`recorded_at/withdrawn_at`) · storage lifecycle (`retain_until/deleted_at/hold`) — three concepts, never one reused column. Real **as-of retrieval** with late-arriving-correction tests ("on July 1 we still believed X").
2. **Evidence-grade lineage:** stable store + record UUIDs; exact episode→fact and fact→observation derivation edges (today facts link only the first episode; observations carry no parents). Erasure cascades then follow exact derivation, not heuristic overlap.
3. **Boring load-bearing:** `PRAGMA user_version` migrations with fixtures from every supported schema; transactional erase/import/restore with failure injection; true read-only store opening; embedding-dimension guard.
4. **Privacy enforcement, not intention:** offline profile makes built-in remote adapters fail closed; redaction/policy runs on *every* write path including `add_fact` and MCP; `describe_data_flow()` inspection command.

*Exit gate: historical-belief property tests pass; every derived record reaches exact parents; failed erase/import leaves the store unchanged; offline profile fails closed.*

### E1B — Receipts, policy, lifecycle (weeks 5–8)

1. **Memory-evidence receipts** via a replaceable **`AuditSink`** — never the same file (reads must not become writes; packs stay truly read-only). Canonical, versioned, minimized by default (IDs, versions, policy decisions, query/context *digests*; plaintext only under explicit policy). Sinks per profile: absent/minimal → sidecar SQLite → SIEM/WORM with **customer-key-signed checkpoints** (an unkeyed hash chain detects accidents, not administrators — "signed" means a customer key, or we say "checksummed").
2. **Receipts cover the lifecycle:** ingest/dedupe, extraction, supersession/correction, search/context, export/import, erase/sweep/hold, pack mount.
3. **User memory controls:** list/inspect/explain, append-only correct/supersede/revert, forget, temporary no-memory mode.
4. **Trust and retention:** immutable origin assigned at the trusted host boundary (separate from mutable review status); quarantine + a strict action profile that excludes unapproved records; structured retention classes and hold records (scope, authority, expiry, release — not a Boolean); snapshots via SQLite's backup API.
5. **MCP capability separation:** read/search granted separately from write; writes policy-gated. (Erase stays out entirely, as shipped.)

*Exit gate: receipt digests verify the exact packed context; tamper/truncation/clock-rollback behavior documented and tested; regulated mode externally anchors checkpoints.*

### E2 — Verified offline knowledge packs (weeks 9–12)

The honest name for "federation": **artifact distribution, not live collaboration.** Personal writable store + verified read-only packs for **same-access cohorts** (policies, manuals, product releases, field knowledge, air-gapped corpora) — never mixed-ACL content flattened into one file.

Pack semantics: versioned manifest (schema/software/embedder/tokenizer fingerprints), checksum + **optional customer-key signature**, expiry/revocation/rollback, verify-before-open, immutable mounts with composite `(store_id, record_id)` identity, declared precedence and visible conflicts, atomic update. Multi-store retrieval fuses ranked lists with the existing RRF machinery. Host authorizes the mount; core verifies integrity. A minimal delta contract (external ID, version/hash, ACL metadata, tombstones) lets *others* build connectors — none in core.

**Scale, sequenced honestly:** numpy int8/binary quantization enters here — after E1A correctness gates, justified by the measured envelope we already have (78ms warm at 312k rows, exact O(N) scan), gated on a recall A/B like every retrieval change. Packs shard by scope, so per-file headroom plus quantization covers the honest majority of embedded-agent corpora; sqlite-vec stays the opt-in tier beyond. In-file namespaces remain a convenience, **never a security boundary** — the file is the security boundary.

*Exit gate: tampered/expired/revoked/mismatched-embedder/unauthorized packs fail closed; interrupted updates roll back; no write ever reaches a shared pack.*

### E3 — Served profile (only on repeated customer pull)

Starts only when ≥2 design partners independently need live shared state. Separate package, larger control surface, honestly named **containment** (not "isolation by construction"): validated OIDC/JWT or trusted proxy hop (never bare identity headers); deny-by-default role/action matrix before any ABAC; opaque tenant→allowlisted-path mapping (never caller paths); per-tenant stores, caches, temp, keys, quotas, backups, logs; adversarial tests (spoofing, traversal, confused-deputy, cross-tenant cache); optional SQLCipher/KMS; a read-only inspector, not a dashboard platform. Defer SAML to proxies, SCIM until we persist identities, TS SDK until a real integration pulls it.

---

## Proof & release gates (evidence before claims)

Temporal correctness (as-of + late corrections) · lineage completeness (no heuristic-only cascades) · migration round-trips + interrupted-migration recovery · no-egress and direct-write-policy tests · crash-injected lifecycle ops + erasure **coverage report** (logical unreachability vs local purge vs backup expiry vs crypto-erasure — never "the bytes are gone") · audit canonicalization + tamper/truncation/anchor tests · pack integrity/revocation/precedence tests · server adversarial suite · supply chain (SBOM, signed releases, disclosure policy, pen test before GA) · quality (full fixed-judge LongMemEval/LoCoMo + stale-memory/action-error tests — the bring-your-own-benchmark posture stays; no new self-graded headlines).

## Commercial model

Core stays Apache-2.0, everything included. Monetize operational assurance: LTS + security backports, signed release channels + SBOM/provenance, regulated deployment profiles + reference architectures, migration/threat-model/evidence-review support, SLAs, and the optional server/adapters when pulled. Price per deployment/site or support tier — not per-seat knowledge-suite pricing. Pilot metrics stay within our influence: retrieval accuracy, stale/corrected-memory error rate, wrong-scope retrieval rate, tokens/cost/p95, time-to-integrate, time-to-reconstruct evidence, deletion coverage, restore RTO/RPO.

## Refuse list (unchanged, sharpened)

No hosted control plane before demand; no enterprise search or connector marketplace; no graph DB or mandatory Postgres/ANN tier; no in-file namespaces as security; no proprietary IAM/KMS/DLP/eDiscovery; no live collaborative memory disguised as file federation; no "signed/tamper-proof/zero-retention/compliant" language without the mechanism and evidence behind it.

## Mapping to the existing public roadmap

Profile bench matrix (#1) → unchanged, feeds every gate. Quantization (#2) → re-sequenced into E2 behind correctness gates. Canonicalization v2 (#3) → E1A lineage prerequisite, then E2. `valid_until` (#4) → subsumed by the tri-temporal split (as *world* validity — retention is a separate lifecycle field). Namespaces (#5) → convenience only. Full benchmark runs (#6) → proof track. Hermes/platform adapters (#7) → post-E1B, receipts make the adapter story stronger. Hardening (#8) → absorbed into E1A/E3.

## Appendix — superseded v1 claims (badha, applied to ourselves)

| v1 claim | Status | v2 replacement |
|---|---|---|
| "One audit table away from being the compliance artifact" | superseded | "A compact substrate for producing memory and retrieval evidence" |
| "Bi-temporal supersession reconstructs what the system believed" | superseded — `now` never filtered; knowledge-time not modeled | "Supersession preserves change history; as-of belief is the E1A milestone" |
| "Article 12-ready by Aug 2, 2026" | superseded — Omnibus defers Annex III to Dec 2, 2027 (adoption pending) | "Produces evidence supporting a customer's Art. 12 implementation, under whichever dates apply to their system" |
| "Self-hosted inherits your compliance" | superseded | "Runs inside, and can be governed by, customer-controlled infrastructure" |
| "Erasure cascade / prove the bytes are gone" | superseded | "Owner-initiated logical deletion with documented coverage and residuals" |
| "Signed bundle = manifest + SHA-256" | superseded | "Checksummed bundle; customer-key signature for authenticity" |
| "500 people share memory without a server" | superseded | "Versioned, verified, read-only knowledge packs for same-access cohorts" |
| "Governance is missing everywhere" | superseded | "Governance is platform-tier table stakes; verifiable embedded behavior is the whitespace" |
