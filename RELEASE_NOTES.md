# Release notes

| Package | Version | Date | Who it is for |
|---|---|---|---|
| [`smriti-agents`](#smriti-040--evidence-first-recall) (core) | **0.4.0** | 2026-09-25 | Developers and individual agents: local, private memory in one SQLite file |
| [`smriti-enterprise`](#smriti-enterprise-020) | **0.2.0** | 2026-09-25 | Governed deployments: audit receipts, retention, legal holds, verified packs |

Versions are set in package metadata. No git tag or PyPI publication has
been made; install from the repository (see
[Install and upgrade](#install-and-upgrade)).

---

## Smriti 0.4.0 — evidence-first recall

**Your agent now gets the evidence it retrieves.** The 0.3.x read path usually
found the right conversation turn and then lost it while building the context:
it kept 12 items and cut each one at 700 characters. The new default read
engine keeps complete turns, groups them by dated session, and writes relative
dates out in full. It runs locally, is deterministic, and makes no LLM calls
at query time.

### Highlights

- **About 20 points more questions answered correctly** than 0.3.x, with the
  same reader, judge and budget (LoCoMo 46.0% → 65.5%, LME-X 47.5% → 70.4%).
- **Ahead of or level with Mem0 OSS 2.2.0** over identical turns: +8.8 points
  on LME-X, a statistical tie on LoCoMo.
- **Evidence reaches the model intact:** 84.7% of evidence turns on LoCoMo
  (was 55.9%) and 87.6% on LME-X (was 43.2%).
- **4× faster on large stores:** 32 ms p50 at 100,000 turns (was 132 ms).
- **Fully offline semantic memory** with the new in-process `OnnxEmbedder`.

### What's new

**Evidence-first recall is the default** (`smriti/recall.py`). `search()` and
`context()` rank conversation turns by fused keyword (BM25) and embedding
scores, lift turns from sessions that match well overall, and apply
question-aware priors:

- turns that address the assistant rank higher when the question asks what
  the assistant said ("what did you recommend…", "remind me…");
- a named speaker's turns rank higher when the question names that speaker;
- date-bearing turns rank higher for "when" questions;
- "X or Y first?" questions are split into one sub-query per option.

The context is then filled with complete turns while they fit, and with
query-focused excerpts in place of prefix cuts when they do not.

**Dates in memory.** Relative dates are resolved against each turn's
timestamp and shown inline, for example
`I went to the support group yesterday [2023-05-07]`. Covered forms include
"last weekend", "two weeks ago", "last Friday" and seasons. A time window in
the question ("in March", "past two months", an explicit date) becomes a soft
retrieval prior. Sessions carry dated headers, and when you pass `now` (the
MCP server passes today's date by default) the context opens with the current
date. No tokens are spent on any of this.

**`OnnxEmbedder`.** Runs a sentence-transformer ONNX export (for example
`all-MiniLM-L6-v2`) inside the Python process. Install it with
`pip install -e '.[onnx]'`, which adds `onnxruntime` and `tokenizers`; the core
dependency surface stays stdlib + numpy.

```python
from smriti import Smriti, OnnxEmbedder

mem = Smriti(path="memory.db", embedder=OnnxEmbedder("models/all-MiniLM-L6-v2"))
print(mem.context("When did I go to the support group?", now="2023-07-01"))
```

**Opt-in contextual embeddings.** `Smriti(contextual_embeddings=150)` lets
each turn's vector also see the last 150 characters of the previous turn in
the same `add()` call, so short replies ("yes, book it!") can be found by
what they answer. Stored text is unchanged. It applies to turns written
after it is enabled. It helped LoCoMo ranking (+3.5 recall@5) and was neutral
on LME-X.

**MCP.** The `recall` and `search` tools accept `profile="evidence"` and a
`now` date (default: today). With no profile they use the evidence-first
engine.

**Benchmark lab** (`bench/lab/`). An LLM-free harness that measures whether
the supporting turn is ranked and whether it survives complete into the
context. It includes adapters for Mem0 OSS, BM25 and dense retrieval, a
blinded reader/judge QA pipeline, and a scale probe. It can evaluate any
Smriti checkout.

### Measured results

Held-out test splits. Every system received the same turns, timestamps,
MiniLM vectors and 9,000-character budget. Answers were read by Claude Haiku
and graded by a strict Claude Sonnet judge, neither of which knew which
system produced a context. QA accuracy is pooled over two reads of the same
contexts.

| | Smriti 0.3.x | **Smriti 0.4.0** | Mem0 OSS 2.2.0 |
|---|---:|---:|---:|
| Evidence complete in context, LoCoMo | 55.9% | **84.7%** | 79.4% |
| Evidence complete in context, LME-X | 43.2% | **87.6%** | 69.1% |
| QA accuracy, LoCoMo (200 questions) | 46.0% | **65.5%** | 62.7% |
| QA accuracy, LME-X (120 questions) | 47.5% | **70.4%** | 61.7% |
| Search p50 at 100,000 turns | 131.6 ms | **32.2 ms** | – |

LME-X is the LongMemEval questions with 48 cross-question distractor sessions
each; it is **not** the official LongMemEval-S haystack. Mem0 ran with
`infer=False`, its own hybrid semantic + BM25 retrieval over the verbatim
turns. These numbers are not comparable with published leaderboard scores.
Full method, confidence intervals and null results:
[lab report](audit/2026-09-25/LAB-REPORT.md).

### Behaviour changes

- **`context()` output format changed.** Evidence is grouped under
  `[Session YYYY-MM-DD Ddd]` headers in chronological order, preceded by
  `(Current date: …)`, and relative dates carry resolved dates in brackets.
  If your prompts or parsers depend on the 0.3.x
  `RAW CONVERSATION EVIDENCE (timestamped)` block, pass
  `Smriti(..., read_engine="fusion")`. That path is byte-identical to 0.3.2.
- **`search()` ranking changed.** Raw turns are ranked by the new engine.
  Facts are still retrieved through the fact channels, and observation
  summaries still ride in their own slots.
- **Unchanged:** the named profiles (`facts`, `relations`, `timeline`,
  `deep`, `auto`), `session_diverse=True` and every write path keep the 0.3.x
  behaviour. There is no schema migration, and existing vectors are reused as
  they are.
- **Iterative retrieval:** `context_iterative()` packs with the new engine;
  `search_iterative()` starts from the new `search()` ranking and merges
  follow-up results from the 0.3.x retrieval.
- **Latency profile:** on small stores the default read takes about 10–15 ms
  instead of 4–8 ms. From about 10,000 turns upward it is faster than 0.3.x.

### Known limits

- LoCoMo list and aggregation questions ("what activities does X do?") still
  trail Mem0 (47–53% vs 53–58%). In the misses we inspected, the evidence was
  in the context and the reader did not use it; a list-oriented layout is the
  next experiment.
- Excerpting keeps the relevant part of very long assistant turns rather than
  the whole turn.
- Cross-encoder reranking is supported through any `.rerank()` object but
  was not evaluated here; no local model was available.

---

## Smriti Enterprise 0.2.0

**The governance layer, updated for evidence-first recall.** Enterprise
deployments inherit the 0.4.0 read engine. This release makes its receipts say
which engine packed a context, and extends strict mode to raw conversation
turns. It requires `smriti-agents>=0.4.0`.

### What's new

**`EnterpriseSmriti.search()` and `context()` use evidence-first recall** by
default and get the answer-quality and large-store latency gains above.
Construct with `read_engine="fusion"` to keep 0.1.0 read behaviour, for
example while a regression suite compares context digests across releases.

**Receipts record the read engine.** `search` and `context` receipt bodies
now include `read_engine` (`"evidence"` or `"fusion"`). Together with
`retrieval_profile`, this identifies how a context was packed. Without it, a
receipt could not distinguish two engines running under the same core
version. The field is additive: receipt schema `"0"`, canonical serialization
and the hash chain are unchanged. Receipts written before the upgrade still
verify, and new receipts append to the same chain.
[Receipt schema](enterprise/RECEIPT-SCHEMA.md).

**Strict mode now covers raw turns** (security fix). `search(strict=True)`
previously removed only quarantined or untrusted-origin *facts*. Raw
conversation turns from a session ingested with `origin="untrusted"` still
came through, and under the new engine such a turn could rank first. Strict
mode now drops raw turns whose origin is outside the allowed set
(`owner`, `agent`, `tool`). Those drops are counted in `dropped_by_policy`.

### Verified under the new engine

- **Erasure:** after `erase_session()` on the same connection, with a warm
  vector cache, erased content appears in neither `context()` nor `search()`
  (new regression test).
- **Egress:** `OnnxEmbedder` has no endpoint, so it passes the `local`,
  `team` and `regulated` egress checks, and `describe_data_flow()` reports it
  as not remote.
- **Unaffected paths:** verified packs and `retrieve_multi()` federation
  still use fusion retrieval. Legal holds, retention sweeps, lineage erasure,
  tri-temporal as-of queries and signed checkpoints are unchanged.

### Behaviour changes

- **Context digests change.** The same query over the same store packs
  different bytes than in 0.1.0 (see the core notes), so its
  `context_digest` differs. Receipts bind exact bytes, so this is expected.
- **Strict searches may return fewer results** where untrusted-origin
  sessions exist. The receipt records each drop.
- **Requirement change:** `smriti-agents>=0.4.0` (was `>=0.3.2`). There is no
  enterprise schema migration; `ENTERPRISE_SCHEMA_VERSION` is unchanged.

### Known limits

- `context()` has no strict mode. For consequential actions, build the prompt
  from `search(strict=True)` results, as `SECURITY.md` recommends.
- `origin` is assigned by the calling host, so a caller-declared label is
  only as trustworthy as the caller.

---

## Install and upgrade

```bash
git clone https://github.com/vn-envy/Smriti && cd Smriti
python -m pip install '.[onnx]'        # core 0.4.0 (+ optional in-process embeddings)
python -m pip install ./enterprise     # enterprise 0.2.0, if you use it
python -m pytest tests/ -q && python -m pytest enterprise/tests/ -q
```

1. **Back up first.** Use `export_json()` for core stores, and
   `snapshot()` or `build_pack()` for enterprise stores.
2. **Upgrade in place.** No migration runs and existing vectors are reused;
   reopen with the same embedder you used before.
3. **Check prompt consumers.** If anything parses `context()` output, test it
   against the new format or pin `read_engine="fusion"`.
4. **Enterprise:** upgrade both packages together, then run
   `verify_audit()`. We reopened a store and signed receipt chain written by
   0.3.2 / 0.1.0 with 0.4.0 / 0.2.0; new receipts appended and the whole chain
   verified with no violations.

### Validation

- 254 core and 59 enterprise tests pass in the checkout. From freshly built
  wheels in a clean virtual environment, 253 core tests pass with 1 skipped
  (`onnxruntime` absent), all 59 enterprise tests pass, and `pip check` is
  clean. The enterprise demo runs end to end.
- CI (Python 3.9 and 3.12, core and enterprise) passed on `main` for the
  evidence-first commits.
- Benchmark evidence, raw per-question results and reproduction commands:
  [`audit/2026-09-25/`](audit/2026-09-25/).

---

# Earlier release notes

## PR #2 hardening — September 8, 2026 (core 0.3.2 / enterprise 0.1.0 metadata)

**September 8, 2026 · Unreleased · Core metadata 0.3.2 / enterprise metadata 0.1.0**

[PR #2](https://github.com/vn-envy/Smriti/pull/2) hardens Smriti's temporal-memory
kernel and adds completed comparative evidence. The previous baseline is main
commit `a2afb3d`, carrying core v0.3.2 and enterprise v0.1.0. This document describes
the candidate changes since that snapshot; it does not announce a new package
version, tag, PyPI publication or deployment.

### What developers gain

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

### Where the measurements place Smriti

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

### Installation and upgrade notes

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

### Validation

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

### Known limits and next priorities

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
