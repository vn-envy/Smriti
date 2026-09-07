# Parent verification of pending benchmark claims

PR snapshot: 9351ec5, reviewed 2026-09-07.

The filenames of growth-mem0-nomic.json and growth-smriti-nomic.json suggest a matched embedding comparison, but the former records FastEmbed BGE-small in its configuration label. The recorded data does not independently establish model parity. Do not publish a speedup ratio from this pair until effective runtime configuration is captured and matching runs are verified.

The existing growth artifacts use cold_query_ms for the first query after ingestion. This is not a process-restart or unloaded-model cold measurement. Schema 2 names the operation more accurately; old measurements retain their original meaning.

The GBrain growth result contains one 20-document checkpoint and includes a new CLI process per operation. It does not prove database scaling or persistent-server latency. The requested comparison over time requires multiple matched checkpoints and explicit process boundaries.

The current LongMemEval oracle result is an evidence-only sanity check. A full-haystack comparison needs distractors, identical input limits, validated dataset arrays, and failure-inclusive metrics. It remains outstanding.

Luna (high) owns the follow-up implementation. Parent acceptance requires direct review of configuration, raw outputs, and the implemented measurement boundary, followed by independent checks. The existing 169 passing package tests are evidence for the package changes, not validation of these benchmark claims.
