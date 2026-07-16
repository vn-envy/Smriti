# Changelog

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
