# Changelog

## v0.3.2 — Audit fixes, round 2 (2026-07-17)

Second external audit pass; three findings, three fixes.

- **Validity-aware ranking in `search()`** — superseded facts now sink below current facts and episodes in structured results (stable sort; fused order preserved within groups). `context()` consumers were already protected by 0.3.1's packing fix; now `search()` and the MCP `search` tool are too — a stale fact can no longer be the first result a caller reads. The **timeline profile opts out** (`current_first=False`): historical ranking is the point of as-of queries, and its packed context now orders facts *chronologically* by `valid_from` instead.
- **Cold-start concurrency fix** — two workers creating a brand-new database simultaneously could race on `PRAGMA journal_mode=WAL` ("database is locked"). `busy_timeout` is now set *before* the WAL switch, with a bounded exponential-backoff retry around initialization. New regression tests exercise six real parallel connections on a cold file, plus cross-connection replay dedupe.
- **Query-aware packing** — `pack_context(current_first=)` makes ordering profile-driven: current-state profiles lead with CURRENT facts; timeline packs history in time order. Validity annotations unchanged.
- **Distribution name: `smriti-agents`** — `pyproject.toml` renamed (the PyPI `smriti-memory` name belongs to an unrelated project). Import name stays `smriti`.
- 5 new regression tests → **85 offline tests**.

## v0.3.1 — Audit fixes (2026-07-16)

Response to an external agent-run audit that checked our claims against the implementation. Four claims were overstated; now they aren't.

- **Atomic ingestion** — `add()` wraps the idempotency claim and every write in one `BEGIN IMMEDIATE` transaction. Concurrent ingests of the same session serialize and the loser exits as deduped; a crash mid-ingest rolls everything back (claim included), so retries re-ingest cleanly. The extraction LLM call runs *before* the transaction, so the write lock is never held during network I/O.
- **Validity-first is now real** — `pack_context` orders CURRENT facts before SUPERSEDED ones (stable within groups). Previously we shipped validity *annotation* with score-order packing; the audit's quickstart repro showed a superseded fact ranked first. Fixed and regression-tested.
- **Erasure purges derived observations** — `erase_session` now drops observation/digest facts whose subject, predicate digest, or entities overlap the erased facts (over-deletion in the safe direction; regenerate from surviving facts with `refresh_observations()`).
- **Export/import truly lossless** — now includes the search-key expansion index and the ingest/idempotency log (format v2), so deep-profile retrieval and session-replay dedupe behave identically after a restore.
- **Hygiene** — HTTP user-agent derives from `__version__` (was hardcoded `smriti/0.1`); stray zip artifact removed from the repo; version stamps aligned across `pyproject.toml`/`CITATION.cff`/`__init__.py`; README documents the measured scale envelope (3.2ms @ 12.5k → 78ms @ 312k rows, 256-dim) with honest suitability tiers, and warns that the `smriti-memory` PyPI name belongs to an unrelated project — install from source.
- 6 new regression tests → **80 offline tests**.

## v0.3.0 — Hardening (2026-07-16)

Production seatbelts, zero new dependencies. The dependency surface is still the Python stdlib + numpy; the core is still one SQLite file you can read in a sitting.

**Durability & correctness**

- WAL journal mode + `busy_timeout` + `synchronous=NORMAL`: readers proceed during writes, crashes recover cleanly, concurrent connections wait instead of erroring.
- **Idempotent ingestion**: replaying an identical (messages, timestamp, session) is a no-op — `add()` returns `{"deduped": True}`. Double-ingested sessions can't corrupt counts. `dedupe=False` to force.
- **Unicode lexical search**: non-Latin scripts (Devanagari, CJK, Cyrillic) now reach FTS5's tokenizer instead of being stripped by an ASCII-only regex. मैं बेंगलुरु में रहता हूँ is now findable by BM25, not just vectors.

**Data ownership**

- **Owner-initiated erasure** — `erase_session()` / `erase_entity()` cascade across episodes, facts, FTS rows, entity links, embeddings, and dangling supersession pointers. Deliberately distinct from supersession (correction is history; erasure is ownership), and deliberately **not exposed via MCP** — untrusted conversation content can never talk an agent into deleting its own memory.
- **Lossless export/import** — `export_json()` / `import_json()` round-trip everything including embeddings (base64) and supersession chains. Backup, restore, migrate, leave.
- **Opt-in secret redaction** — `Smriti(redact=True)` scrubs credential-shaped strings (API keys, tokens, passwords) before anything is persisted or sent to an extraction model.

**Entity aliases (canonicalization v1)**

- `add_alias("Rachel Smith", "Rachel")` — write-time canonicalization (new facts consolidate under the canonical entity) + read-time resolution (queries mentioning the alias reach it) + chain flattening. Conservative by design: nothing merges unless the owner says so.

**Testing**

- +22 regression tests: contradictions, knowledge updates, date formats, aliases, multilingual content, noisy haystacks, idempotency, erasure cascades, export round-trips, WAL durability. **74 offline tests total** — no network, no keys.

## v0.2.0 — Agile retrieval / drishti (2026-07-15)

- **Retrieval profiles** (*drishti*, दृष्टि — "way of seeing"): named, per-query retrieval policies — `facts` (current-state precision), `relations` (2-hop entity + semantic linking), `timeline` (date-anchored), `deep` (high-recall aggregation), `auto` (zero-token router). Every built-in profile carries an `evidence` field citing the A/B that justified it.
- **Switchable channels**: the four channels (lexical / semantic / entity / temporal — Sanskrit aliases accepted) are individually maskable per call; a lexical-only call skips the query embedding entirely.
- **Profile-aware MCP tools**: `recall` and `search` take `profile` and `channels`, so agents shape retrieval with one enum per call.
- Legacy default path byte-identical to 0.1.0 — existing A/B evidence still describes default behavior.
- CI workflow, CITATION.cff, README overhaul, landing site (smriti-memory.netlify.app).

## v0.1.0 — Initial release

- Bi-temporal fact store with supersession (*badha*) — facts invalidated, never deleted; validity windows printed into the packed context.
- Four-channel hybrid retrieval fused with RRF: BM25 (FTS5), vectors (numpy), entity-hop (graph-lite), temporal proximity.
- Lite mode (zero write-time LLM calls, fully offline) and full mode (one extraction call per session, two-tier conflict resolution).
- Observation/digest layer, per-type router (+10.3 multi-session, p=0.046), MCP server, LongMemEval/LoCoMo benchmark harness (`bench/ab.sh`).
