# Memory-Evidence Receipt — schema v0

A receipt is a canonical, versioned record of **what SMRITI delivered or changed**. It is deliberately *not* a decision record: the host owns prompts, model versions, tool calls, approvals, and outcomes, and correlates them with a receipt through `correlation_id`.

## Canonical form

Serialization is `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` encoded UTF-8. Digests are SHA-256 hex. Canonicalization is part of the schema: two verifiers must produce identical bytes for identical receipts.

```json
{
  "schema": "0",
  "op": "context",
  "ts": "2026-07-19T09:14:22Z",
  "correlation_id": "req-4f2a",
  "versions": {
    "core": "0.3.2", "enterprise": "0.1.0", "schema": 1,
    "store_id": "8056c781…", "profile": "regulated"
  },
  "body": { "…op-specific…" }
}
```

## Operations and bodies

| `op` | Body fields |
|---|---|
| `ingest` | `session_id`, `episodes`, `facts`, `deduped`, `origin` |
| `add_fact` | `fact_id`, `stored`, `origin` |
| `search` | `query_digest`, `retrieval_profile`, `strict`, `dropped_by_policy`, `results[]` |
| `context` | `query_digest`, `retrieval_profile`, `k`, `char_budget`, `context_digest`, `context_chars` |
| `erase_session` / `erase_entity` | scope, `episodes`, `facts`, `derived`, `lineage_exact` |
| `hold_place` / `hold_release` | `hold_id`, scope, `authority`, `released` |
| `sweep` | `sessions`, `episodes`, `facts`, `skipped_held` |
| `quarantine` | `fact_id`, `flag`, `ok` |
| `pack_build` | `name`, `sha256`, `path` |

`results[]` entries: `kind`, `id`, `score`, `valid_from`, `invalid_at`, `channels`, `text_digest` — ordered exactly as delivered, so ranking is reconstructable.

## Minimization

Default: **digests, not plaintext.** Queries and result text are hashed; only IDs, versions, policy decisions, and validity state are stored in clear. Plaintext capture must be an explicit, separately-retained, access-controlled decision.

A hash is *not* anonymity for low-entropy values (a short address, a phone number). Treat receipts as sensitive.

## Chain and integrity tiers

Each sink row: `seq` (monotonic), `body` (canonical), `hash = SHA256(prev_hash + body)`, `prev_hash`, optional `checkpoint`.

| Tier | Mechanism | Detects | Does **not** detect |
|---|---|---|---|
| 1 — chain | `prev_hash` + `seq` | accidental modification, deletion/truncation inside the sequence | a full rewrite of the chain by anyone with write access |
| 2 — keyed checkpoint | HMAC-SHA256 over the row hash with a **customer-held key**, every N rows | rewrites by anyone without the key; forged tails | compromise of the key itself; a shared-key MAC is not an asymmetric signature |
| 3 — external anchor | publish checkpoint digests to an independent authority | rewrites by anyone including the key holder | *not implemented — interface only* |

`verify_audit()` returns `{receipts, violations, checkpoints_verified, ok}`.

## What a receipt can and cannot prove

**Can:** that a given store (by `store_id`) produced exactly this packed context, in this order, from these record IDs with these validity states, under this profile and policy decision, at this time, in this software/schema version — verifiable against the exact returned bytes when they are supplied.

**Cannot:** recreate content later erased or modified (unless policy separately retains the bytes); prove *why* the agent acted; prove authenticity beyond the strength of the checkpoint key; establish that the surrounding system is compliant.

## Host correlation

The host should extend the same `correlation_id` with its own record: user/workload identity, prompt and model version, tool arguments, approval decision, execution result, error, and reversal. The pair (host record + SMRITI receipt) is the auditable unit; neither half is sufficient alone.
