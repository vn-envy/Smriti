# Parent verification of pending benchmark claims

PR snapshot: 9351ec5, reviewed 2026-09-07.

The filenames of growth-mem0-nomic.json and growth-smriti-nomic.json suggest a matched embedding comparison, but the former records FastEmbed BGE-small in its configuration label. The recorded data does not independently establish model parity. Do not publish a speedup ratio from this pair until effective runtime configuration is captured and matching runs are verified.

The existing growth artifacts use cold_query_ms for the first query after ingestion. This is not a process-restart or unloaded-model cold measurement. Schema 2 names the operation more accurately; old measurements retain their original meaning.

The GBrain growth result contains one 20-document checkpoint and includes a new CLI process per operation. It does not prove database scaling or persistent-server latency. The requested comparison over time requires multiple matched checkpoints and explicit process boundaries.

The current LongMemEval oracle result is an evidence-only sanity check. A full-haystack comparison needs distractors, identical input limits, validated dataset arrays, and failure-inclusive metrics. It remains outstanding.

Luna (high) owns the follow-up implementation. Parent acceptance requires direct review of configuration, raw outputs, and the implemented measurement boundary, followed by independent checks. The existing 169 passing package tests are evidence for the package changes, not validation of these benchmark claims.

## Additional installed-path checks (September 7)

- HTTP fault injection found that permanent 400/401/403 errors each produce three
  requests. `LLM.attempts` reports one for those three underlying requests.
  See `raw/http-retry-review.json`. The retry policy and request accounting need
  correction before treating the cost counters as actual HTTP attempt totals.
  The reviewed fix now fails fast on permanent errors and adds `http_attempts`;
  its isolated wheel passed 185 tests. See
  `raw/http-retry-installed-verification.json`.
- A full-mode three-update Smriti probe timed out on its first ingestion while
  other local-model work was active. Root interrupted the remaining probe to
  remove that extra contention; this is an incomplete run, not an accuracy
  score. See `raw/smriti-mira-full-smoke.json`. Repeat this quality check after
  the timed benchmark workloads finish.
