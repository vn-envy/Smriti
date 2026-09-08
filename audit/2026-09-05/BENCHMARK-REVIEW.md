# Parent verification of benchmark claims

PR snapshot: 9351ec5; status updated 2026-09-08. This review preserves historical findings and current bounded evidence; it is not a release or leaderboard claim.

The next three paragraphs describe the initial artifacts, not the final growth comparison. Later matched nomic runs cover five checkpoints through 36,500 records, including a separate GBrain semantic route; see `VERIFIED-RESULTS.md` and `raw/gbrain-semantic-growth-independent-review.json`. The initial failures remain documented below.

The filenames of growth-mem0-nomic.json and growth-smriti-nomic.json suggest a matched embedding comparison, but the former records FastEmbed BGE-small in its configuration label. The recorded data does not independently establish model parity. Do not publish a speedup ratio from this pair until effective runtime configuration is captured and matching runs are verified.

The existing growth artifacts use cold_query_ms for the first query after ingestion. This is not a process-restart or unloaded-model cold measurement. Schema 2 names the operation more accurately; old measurements retain their original meaning.

The GBrain growth result contains one 20-document checkpoint and includes a new CLI process per operation. It does not prove database scaling or persistent-server latency. The requested comparison over time requires multiple matched checkpoints and explicit process boundaries.

The bounded paired frozen-v4 LongMemEval-S50 answer/judge run is now complete for
both adapters: 50/50 selected questions, zero operational/cleanup failures, and
32/50 recorded correct for each (14/30 answerable; 18/20 abstention). Independent
review verified identical selected IDs, gold labels, reader/judge models,
embedding/context budgets, and dataset; 30 questions were correct for both, 16
for neither, 2 Smriti-only, and 2 Mem0-only. Forty percent of the selected sample
is abstention, so 64% is exploratory and not a broad 500-question quality claim.
Smriti elapsed 3994.4346s and Mem0 20694.5133s under uncontrolled host load, so
these times are not a speed ranking. Mem0 recorded 50 logical answer calls and
51 HTTP requests; the extra request has no recorded error cause. See
`raw/longmemeval-pair-final-independent-review.json`. The LongMemEval oracle
result remains an evidence-only sanity check and must not substitute for the
bounded answer/judge comparison or support a dataset-wide claim. The bounded GBrain held-out20 semantic retrieval run is now complete: GBrain
recall@5 0.8791667 / deduplicated-session RR 0.9083333; Smriti default
0.8458333 / 0.8875; Smriti session-diverse 0.9333333 / 0.9041667. All 20
questions share 991 sessions and 10,047 input chunks; independent review
verified matching IDs, labels, budgets, dataset, vector coverage, and zero
failures. RR is deduplicated-session order within the top five chunks. This is
retrieval-only evidence and makes no answer-quality, superiority, or speed
claim. See `raw/gbrain-heldout20-independent-review.json`. The bounded Hindsight
comparative probe is terminal-complete: 20 retains and 12 recalls succeeded
with cleanup; every query returned 20 facts, answerable top-five source
coverage was 10/10, and the first result was relevant for 9/10 answerable
queries. The current-drink query ranked old coffee first and new tea second.
Observations and reranking were disabled, and the bank configuration does not
expose its embedding model, so this is descriptive retrieval evidence only;
it does not establish answer quality, superiority, embedding parity, or speed.
See `hindsight-comparative-v1.json` and
`raw/hindsight-comparative-independent-review.json`.

Luna (high) owns the follow-up implementation. Parent acceptance requires direct review of configuration, raw outputs, and the implemented measurement boundary, followed by independent checks. The historical 169 passing package tests are evidence for the package changes, not validation of these benchmark claims.

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
  score. See `raw/smriti-mira-full-smoke.json`. Later installed-v7 Mira and independent generalization checks passed; see
  `ROADMAP.md` for the raw artifacts and bounded acceptance.
