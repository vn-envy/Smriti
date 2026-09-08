# Core hardening receipt

Date: 2026-09-05–06  
Baseline: `a2afb3d5f7d2b896585c91abb8bcce2f7c4a9585` (`0.3.2`)

## Confirmed baseline defects

The installed baseline was probed before changes. Raw reproduction output is in
[`raw/baseline-defect-probes.json`](raw/baseline-defect-probes.json), with install,
quickstart, MCP SDK, scale, and local-model evidence beside it in `raw/`.

- A direct `add_fact()` bypassed `redact=True` and persisted credential-shaped text.
- An invalid mode such as `ltei` was silently accepted.
- A warmed vector cache did not see rows committed by another SQLite connection.
- Late-arriving historical facts could supersede newer current truth. Inserting a
  middle event also left overlapping validity intervals.
- `add_fact()` was not transactional, while session ingestion was.
- Restore was autocommit row-by-row. A malformed later row left a partial database
  that could not be retried as an empty restore.
- MCP initialization echoed unsupported protocol versions, accepted requests without
  `jsonrpc: "2.0"`, accepted invalid `params` shapes, and returned JSON only as text,
  leaving modern clients' `structuredContent` empty.
- The source-install guide described the full-mode `MockLLM` quickstart as lite mode.
- Current setuptools emitted deprecation warnings for the legacy license table and
  license classifier.
- The enterprise two-axis query removed an earlier world-time fact merely because
  its later withdrawal was known by the requested knowledge time.
- Semantic LLM arbitration trusted an arbitrary `target_id`, allowing malformed or
  hallucinated output to invalidate a fact outside the candidates shown to the model.

## Changes implemented

- Validate modes at construction.
- Apply secret redaction to every textual field on direct fact writes, without
  mutating the caller's `Fact` object.
- Make direct fact writes transactional.
- Track SQLite `PRAGMA data_version` and invalidate episode, fact, and entity vector
  caches after external commits. The check remains compatible with read-only
  enterprise stores that bypass the core initializer.
- Rebuild complete single-valued fact validity chains in event-time order. A late
  January or middle March fact can no longer displace June current truth or leave
  overlapping January-to-June history.
- Constrain semantic-arbitration actions to the documented enum and supersession
  targets to the exact candidate set shown to the model. Semantic supersession now
  also respects event chronology for late-arriving history.
- Reject non-finite, malformed, and dimension-changing embeddings before persistent
  rows are written. Legal zero vectors from short `HashEmbedder` inputs remain
  supported and are ignored by cosine retrieval as before.
- Validate export format/version/list fields/base64 alignment and restore all rows,
  FTS entries, aliases, entities, and ingest claims in one transaction. Failed
  restores roll back to an empty, retryable store.
- Tighten JSON-RPC validation, negotiate the protocol revision actually implemented,
  and return both backwards-compatible JSON text and native MCP structured content.
- Add `Smriti.close()` and context-manager lifecycle support.
- Add `smriti-doctor --db PATH`, which opens the database in SQLite read-only mode
  and reports integrity, required schema, counts, WAL mode, and inferred embedding
  dimensions. URI metacharacters in paths are handled correctly.
- Persist a secret-free embedder identity (adapter class, model/provider/dimension,
  and sanitized endpoint when available). Reopening with a different identity now
  fails before reads or writes can mix vector spaces. Databases with pre-metadata
  vectors require explicit `adopt_legacy_embedder=True`; doctor reports tracked,
  legacy-untracked, and empty-untracked states.
- Carry embedder identity through JSON backup/restore and reject a restore under a
  different embedder even when dimensions match. Version 1 and identity-free version
  2 backups remain restorable only through the explicit legacy-adoption flag.
- Change core CI to build the wheel, install it, copy tests outside the checkout,
  and run with importlib mode so source-tree imports cannot mask packaging defects.
- Replace bracket-count JSON extraction with `JSONDecoder.raw_decode`, so brackets
  inside quoted fact text cannot truncate otherwise valid model output. Extraction
  now reports `ok`, `malformed`, `wrong_shape`, or `all_items_rejected` diagnostics,
  validates list-valued entities/search keys, and records accepted/skipped counts.
- Normalize the narrow residence-update aliases `moved_to` and `relocated_to` to
  `lives_in`; subjects remain untouched, so facts about different people cannot
  supersede one another through this normalization.
- Restrict JSON-mode fallback retries to HTTP 400/422 format rejection. Network and
  server failures no longer trigger a second potentially paid request. LLM clients
  expose attempts and missing-usage counts alongside successful calls/tokens.
- Correct the quickstart mode description and modernize SPDX license metadata.
- Align the build backend minimum with the setuptools release that supports the SPDX
  license field (`setuptools>=77`) in both distributions.
- Correct combined world-time/knowledge-time reconstruction in enterprise temporal
  reads.

## Verification after changes

Commands were run in isolated `/tmp` virtual environments; no global configuration
or user memory database was changed.

```text
/tmp/smriti-audit-venv/bin/python -m pytest tests -q
104 passed

PYTHONPATH=.:enterprise /tmp/smriti-audit-venv/bin/python -m pytest tests enterprise/tests --import-mode=importlib -q
169 passed in 0.47s

/tmp/smriti-audit-venv/bin/python -m build --no-isolation --wheel --outdir /tmp/smriti-final-dist
Successfully built smriti_agents-0.3.2-py3-none-any.whl

/tmp/smriti-final-venv/bin/python -m pip install /tmp/smriti-final-dist/smriti_agents-0.3.2-py3-none-any.whl
Successfully installed numpy-2.5.2 smriti-agents-0.3.2

/tmp/smriti-final-venv/bin/python -m pip check
No broken requirements found.

/tmp/smriti-final-venv/bin/smriti-doctor --db /tmp/smriti-final-doctor.db
ok=true; integrity=ok; journal_mode=wal; missing_tables=[]; episode embedding dimension=256
```

The installed-wheel MCP probe returned protocol `2025-06-18`, populated
`structuredContent` for `stats`, and rejected a request missing the JSON-RPC version
with error `-32600`.

## Residual limits and next checks

- Full-mode correctness depends on extraction quality and predicate normalization.
  The local Qwen probes in `raw/baseline-local-llm.json` produced unsupported facts
  with the small model, and a later 8B probe used `moved_to` instead of `lives_in`, so
  automatic supersession could not connect the update. This is model/output quality,
  not a transport failure. Diagnostics and two conservative residence aliases now
  make this visible and repair the observed predicate mismatch, but unsupported facts
  still require representative-model conformance tests rather than brittle string
  censorship.
- Core JSON export is lossless for the core schema. Enterprise governance metadata is
  not represented by that format; enterprise backup/transfer should use its verified
  snapshot/pack path until a versioned governance-aware restore format is designed.
- `HashEmbedder` is a deterministic character-hash fallback for offline/lite use. It
  exercises retrieval but should not be presented as a semantic embedding model.
- Custom embedders should expose stable `model`, `provider`, `dim`, and `base_url`
  attributes when applicable. For adapters without them, compatibility can only be
  bound to the adapter's module and class name.
- These changes are verified in the workspace and built wheel. They are not committed,
  published to PyPI, or deployed to the live site by this receipt.
