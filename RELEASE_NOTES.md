# Release notes — PR #2 candidate

**September 8, 2026 · Unreleased · Core metadata 0.3.2 / enterprise metadata 0.1.0**

[PR #2](https://github.com/vn-envy/Smriti/pull/2) hardens Smriti's temporal-memory
kernel and adds completed comparative evidence. The previous baseline is main
commit `a2afb3d`, carrying core v0.3.2 and enterprise v0.1.0. This document describes
the candidate changes since that snapshot; it does not announce a new package
version, tag, PyPI publication or deployment.

## What developers gain

**Separate applicability without losing history.** Facts can carry a `scope`
such as `project:Atlas`. Consolidation uses subject, predicate and scope, so a
project-specific primary language does not overwrite a value in a different
project. Explicit single-valued predicates supersede older values within that
identity; generic `prefers` facts remain multi-valued. Scope follows the fact
through retrieval evidence, MCP structured responses, enterprise receipts and
portable JSON v3. It is applicability metadata, not a tenant authorization
boundary.

**Better handling of changes that arrive out of order.** Temporal-chain repairs
preserve event-time ordering, including late-middle insertions. Enterprise
world-time and system-known-time queries retain their distinct boundaries.
Supersession retains historical facts; owner-requested erasure is separate.

**Inspect extraction failures before trusting them.** Model-generated scope is
checked against source turns and the returned statement before persistence.
Invalid scope can cause one bounded correction call. Unresolved candidates are
omitted from fact writes while the raw episode is retained. `add()`, MCP
`remember`, and extraction diagnostics expose the outcome. The guard checks
lexical support; it is not general proof of semantic applicability, identity
or quotation boundaries. Direct `add_fact()` remains an explicit trusted write.

**A more predictable local store.** The candidate hardens atomic direct writes,
rollback, cross-connection semantic-cache refresh, redaction before embedding
and persistence, vector/model configuration validation and HTTP retries.
Permanent HTTP errors fail fast; actual HTTP attempts are reported separately
from logical calls and successful-response usage. `close()` and context-manager
support make resource ownership explicit. `smriti-doctor` inspects the database
without modifying it.

**A bounded retrieval experiment you can opt into.** `search()` and `context()`
accept `session_diverse=True, session_overfetch=3` to favor evidence from distinct
sessions. Ordinary defaults remain unchanged; iterative search/context reject
this option. It improved source-session recall in the selected held-out
comparison, but generated-answer improvement has not been established.

**Enterprise compatibility and evidence controls.** Policy, legal-hold,
lineage-erasure, signed-receipt and verified-pack paths were hardened. A real
pre-scope knowledge pack was reopened and queried read-only without changing
its checksum or adding columns. Core JSON remains a core-schema export;
enterprise snapshots and verified packs preserve the corresponding governance
boundary.

## Where the measurements place Smriti

| Completed measurement | Smriti | Comparison | Interpretation |
|---|---:|---:|---|
| LongMemEval-S50 answer/judge | 32/50 · 64% | Mem0 32/50 · 64% | Same recorded score |
| LoCoMo50 answer/judge | 27/50 · 54% | Mem0 26/50 · 52% | One-question difference, not demonstrated superiority |
| Retrieval50 recall@5 | .8383 | Mem0 .8300 | Failure-inclusive; 48/50 completed each |
| Held-out20 source-session recall@5 | .8458 default / .9333 session-diverse | GBrain semantic .8792 | Matched selected retrieval workload, not answer accuracy |
| 36,500-record warm retrieval p50 | 20.474ms | GBrain semantic 66.268ms; Mem0 OSS 381.298ms | Same local nomic model, synthetic corpus, 20 warm queries |
| Store footprint at 36,500 records | 161.075MB | GBrain semantic 840.246MB; Mem0 OSS 313.803MB | Measured store boundaries; model cache excluded |

The strongest current position is **local, inspectable memory with explicit
history and low warm-retrieval latency in the measured workload**. The answer
scores are competitive in selected samples but do not establish a quality
lead. There is no matched previous-v0.3.2 versus current-v7 quality or speed run;
these measurements cannot support a version-to-version performance-lift claim.

The answer/judge pairs use the frozen installed-v4 candidate, the same selected
IDs, datasets and local reader/judge configuration (abstention rows use the
harness heuristic), and Mem0 OSS with
`infer=False`. Both pairs completed with zero operational/cleanup failures.
LongMemEval's selected sample contains 40% abstention questions. LoCoMo retains
known judge errors; its exploratory paired interval includes zero and does not
model shared-conversation dependence. The current installed-v7 candidate has
separate bounded model checks, not a rerun of those paired QA scores.

Growth covers 100, 1,000, 3,000, 9,000 and 36,500 synthetic records. The semantic
routes share `nomic-embed-text:v1.5` at 768 dimensions on Apple M5/24GB; Smriti
uses lite ingestion, Mem0 local Qdrant, and GBrain persistent PGLite hybrid
search. Maintained lexical GBrain is a separate faster-small-corpus route:
2.861ms p50 at 100 records and 39.022ms at 36,500. It has no embedding calls.

All local growth routes recorded $0 paid model/API charges; hardware,
electricity and operator costs were not measured. The 30/90/365-day labels
represent corpus volume at 100 additions/day, not a year-long observation.
Managed-Mem0 subscription scenarios are dated pricing estimates for a different,
untested deployment. Neither those scenarios nor uncontrolled QA runtimes are
used as a speed or total-cost ranking.

Hindsight's 20-retain/12-recall probe and Graphify's real AST install are included
as distinct evidence. Hindsight retrieved expected sources in the first five
results for 10/10 answerable queries, but every query returned all 20 facts;
there was no generated-answer stage, observations/reranking were disabled, and
bank embedding identity was not exposed. Graphify extracted 229 nodes and 531
edges from 13 core files and passed a source-linked query check. Its code-graph
workload is not interchangeable with conversational memory.

[Full benchmark tables, limitations and reproduction](README.md#benchmarks) ·
[Cost and growth details](audit/2026-09-05/cost-speed-projections.md) ·
[Independent evidence index](audit/2026-09-05/VERIFIED-RESULTS.md)

## Installation and upgrade notes

1. Evaluate the candidate from the PR branch:

   ```bash
   git clone --branch codex/smriti-hardening-benchmarks-teaser https://github.com/vn-envy/Smriti
   cd Smriti
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install '.[dev]'
   python examples/quickstart.py
   python -m pytest tests/ -q
   ```

2. Back up an existing store before upgrading. Use core export for core data;
   use the enterprise snapshot/pack APIs for enterprise governance data. An old
   binary is not a supported downgrade path for a migrated writable database;
   keep the pre-upgrade backup if you need to return to the old installation.
3. Existing facts without scope retain the legacy empty scope. JSON v3 carries
   scope; v1/v2 imports remain supported with their embedding-identity checks.
   Pre-scope verified packs can be inspected through the tested read-only path.
4. Reopen with the original embedder identity and dimensions. Legacy stores
   without identity metadata require explicit
   `Smriti(..., adopt_legacy_embedder=True)` only after checking the original
   configuration; MCP exposes `--adopt-legacy-embedder`. Adoption does not
   re-embed data or make different vector spaces compatible.
5. Run `smriti-doctor --db memory.db` for read-only integrity/schema/embedding
   checks. Repairs cannot recover revisions already lost before this upgrade.
6. Full-mode extraction may make a scope-correction call in addition to ordinary
   extraction, semantic arbitration and provider retries. Inspect diagnostics
   and budget for the configured provider rather than assuming one fixed call.

## Validation

- **276 core and enterprise tests** passed from non-editable wheels outside the
  checkout, with clean `pip check`. Historical counts refer to different
  snapshots/scopes and should not be added together.
- Final implementation CI passed core/offline and enterprise jobs on **Python
  3.9 and 3.12**. The [CI receipt](audit/2026-09-05/raw/ci-38bda3d.json) identifies
  the implementation head; PR checks report subsequent documentation commits.
- Installed-v7 model checks passed **26/26 Mira assertions** and **8/8 Leila/Omar
  checks**. Independent review verified retained Sketch history and active
  Figma under the correct as-of query. Earlier rejected runs and the corrected
  historical-probe assertion remain in the audit record.
- The 30-second teaser and two separate 60-second social-film compositions are
  included as reproducible source. The camera version preserves the original
  export byte-for-byte. MP4s and supplied media remain local; visual sampling,
  full decoding, duration and measured audio/cue checks are recorded in the
  [film verification](audit/2026-09-05/social-film-verification.md).

## Known limits and next priorities

The extraction guard does not prove arbitrary semantic scope. Model-generated
fact quality, multi-hop reasoning, abstention and current-versus-historical
reading still need broader evaluation. Exact vector scanning has a measured
local envelope, not a multi-million-row concurrent-serving guarantee.

The next quality work is ordered by inspected failures: preserve complete
supporting user statements through context packing; present competing updates
with dates and provenance; then improve judge/date controls. Evaluate these on
new held-out examples and representative models before expanding the core with
ANN, richer graphs or reflection. See the
[quality roadmap and acceptance gates](audit/2026-09-05/QUALITY-NEXT-STEPS.md).
