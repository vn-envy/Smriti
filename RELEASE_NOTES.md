# Release notes

| Package | Version | Date | Who it is for |
|---|---|---|---|
| [`smriti-agents`](#smriti-042--the-judge-trials-finished) (core) | **0.4.2** | 2026-09-26 | Developers and individual agents: local, private memory in one SQLite file |
| [`smriti-enterprise`](#smriti-enterprise-020) | **0.2.0** | 2026-09-25 | Governed deployments: audit receipts, retention, legal holds, verified packs. Works with core 0.4.0 to 0.4.2 |

Versions are set in package metadata. No git tag or PyPI publication has
been made; install from the repository (see
[Install and upgrade](#install-and-upgrade)).

## The 0.4 series at a glance

| Release | What you get | Default behaviour |
|---|---|---|
| [0.4.0](#smriti-040--evidence-first-recall) · evidence-first recall | A new default read engine that keeps whole, dated evidence turns instead of cutting them. Held-out LongMemEval questions (LME-X): evidence complete in context 43.2% → 87.6%; blinded answer accuracy 47.5% → 70.4% (Mem0 OSS on the same turns: 61.7%). | Changed. `read_engine="fusion"` keeps the 0.3.x path. |
| [0.4.1](#smriti-041--sharper-evidence-from-chat-logs) · sharper evidence | The assistant's own replies rank lower (`assistant_prior` 0.55 → 0.2): +4.7 points of evidence at 3,000 characters and +5.4 at 9,000, no model involved. Optional decision-model rerankers. | Changed (ranking of assistant turns). |
| [0.4.2](#smriti-042--the-judge-trials-finished) · judge trials finished | A `rank` mode for contrastive judges, and the full results of four rounds testing Jev, Laya and CLM-8B as relevance judges, with guidance on when a judge is worth turning on. | Unchanged. |

---

## Smriti 0.4.2 — the judge trials, finished

**Nothing changes on Smriti's default read path.** 0.4.2 closes the
decision-model trials that began in 0.4.1. We tested three kinds of
"System One" model as an extra relevance check on Smriti's top memories:
hosted **Jev** (TypeSafe), the open **Laya** encoder and the open,
contrastive **CLM-8B** (Contrastive-LM). The default stays judge-free. This
release adds one reranker mode and publishes what each judge is worth, so you
can decide whether to turn one on.

### What's new

- **`SystemOneReranker(mode="rank")`.** Sends an empty state with the user's
  question as the instruction and each candidate memory as an option. This is
  the layout contrastive System One models such as CLM-8B are trained on:
  the question comes last and each candidate is embedded verbatim. The
  existing `choice` mode ends with a fixed "which memory best helps?" line,
  which a contrastive model reads as the question, so every query looks the
  same to it. On CLM-8B, `rank` raised held-out ranking skill (AUC) from 0.605
  to 0.731. `noul` (one yes/no question per memory) stays the default mode.
- **GPU arms on Google Colab** (`bench/lab/colab/`). Two notebooks run the
  GPU-bound judges: the official Laya encoder with a trained head (any GPU)
  and CLM-8B through `clm-serve` on vLLM 0.19.1 (L4 or A100). Results come
  back as one zip in the runner's Google Drive and replay through the lab's
  caches with no model on the CPU box.
- **Fixed candidate pools** (`audit/2026-09-25/decision-models/pools/`).
  Smriti's top 20 memories for 256 dev and 244 held-out LME-X questions,
  exported by `bench/lab/judge_head/export_pools.py`. Every judge scored the
  same 10,000 question and memory pairs; replaying the round 3 Jev scores over
  the exported pools reproduces its results exactly.
- **Lab tools:** `pool_eval.py` (judge a pools file, single-stream latency
  probe, per-question AUC), `extract_pools.py` (frozen-encoder features on a
  GPU, in the formats `train.py` and the lab's feature cache read), and a
  thread-safe judge cache for concurrent judging.
- **Experiment record:** rounds 3 and 4 in
  [`NOTES.md`](audit/2026-09-25/decision-models/NOTES.md), result files, an
  [X article](audit/2026-09-25/decision-models/x-article/) and the source of a
  [2-minute explainer video](audit/2026-09-25/decision-models/explainer-video/).

### What a judge is worth

Held-out LME-X questions (Smriti's top 20 per question). Each judge re-ranks
the top 20, with settings fixed on dev before the test. "Right memory first"
and AUC score the judge on its own; the evidence columns score it plugged
into Smriti.

| Judge | Right memory first | AUC | Evidence at 1,500 chars | Evidence at 3,000 chars | Time per question | Cost | Memories leave the machine |
|---|---:|---:|---:|---:|---|---|---|
| Smriti 0.4.x alone | 63.8% | 0.891 | 65.6% | 83.2% | 10–15 ms (CPU) | $0 | No |
| + hosted Jev, 35% blend | 72.5% | **0.954** | **74.8%** (+9.2) | **86.5%** (+3.4) | 1.4 s | $0.37 per 1,000 questions | **Yes** |
| + trained Laya head (lab) | **74.2%** | 0.936 | 72.6% (+7.0) | 86.0% (+2.8) | 0.8 s on an L4 GPU; 15–20 s on CPU | $0 | No |
| + CLM-8B, 65% blend | 27.1% | 0.752 | 68.6% (+2.9) | 82.6% (−0.6, n.s.) | 1.0 s on an L4 GPU | $0 | No |
| Perfect judge (ceiling) | 100% | 1.000 | 87.1% | 91.3% | – | – | – |

- **Jev** (zero-shot, `noul`, depth 20, 35% blend chosen on dev): +9.2 points
  at 1,500 characters (95% CI +6.0 to +12.5; 41 questions better, 3 worse)
  and +3.4 at 3,000 (22 / 1). Its per-question ranking beats Smriti's on 104
  questions and trails on 49 (p = 1×10⁻⁵). Every candidate memory is sent to
  `api.typesafe.ai`.
- **Trained Laya head** (frozen official `convaiinnovations/laya` encoder at
  `55cf4c4` plus a logistic head on Laya and Smriti signals, trained on 256 dev
  questions): +7.0 points at 1,500 characters (CI +3.4 to +10.9; 50 / 17) and
  +2.8 at 3,000 (23 / 6). Against Jev it is a statistical tie: right memory
  first 34 vs 30 questions (p = 0.71), evidence at 1,500 characters 19 vs 23
  (p = 0.64). Zero-shot, official Laya ranks below Smriti (AUC 0.830).
- **CLM-8B** (zero-shot, three prompt layouts): best alone is `noul` at AUC
  0.752; `rank` 0.731; `choice` 0.605. Blended at 65% (chosen on dev) it adds
  +2.9 points at 1,500 characters (p = 0.007) and nothing at 3,000.
- **At 9,000 characters no judge helps:** Smriti's top 20 already fit.

### When to turn a judge on

- **Tight context budgets and hosted processing is acceptable:** Jev as a 35%
  blend over the top 20. Remember that the memories it judges leave your
  machine.
- **Private, with a GPU:** the trained Laya head is the local option that
  matches Jev. It is not packaged yet: `bench/lab/judge_head/` reproduces it,
  and packaging it as an optional extra is next on the roadmap.
- **Large budgets (about 9,000 characters or more):** no judge.
- **CLM-8B as released:** not recommended for memory ranking.

```python
import os
from smriti import Smriti, PROFILES
from smriti.decision import SystemOneReranker
from smriti.recall import RecallConfig

# Hosted Jev: every candidate memory is sent to api.typesafe.ai
jev = SystemOneReranker(api_key=os.environ["TYPESAFE_API_KEY"], price_per_mtok=0.042)
mem = Smriti(path="memory.db", reranker=jev)          # plus your embedder
judged = PROFILES["evidence"].with_overrides(
    recall=RecallConfig(rerank_depth=20, rerank_weight=0.35))
print(mem.context("When did I go to the support group?", profile=judged))
print(jev.stats.as_dict(), f"${jev.cost_usd:.4f}")
```

Without the override, a reranker on the default profile judges the top 48
turns and replaces Smriti's score (`rerank_weight=1.0`). On dev, blending
scored higher than replacing for both Jev and CLM-8B.

**Enterprise:** judge endpoints go through the same egress check as any
remote adapter. The `local` profile allows loopback endpoints only, so a
`laya-serve` or `clm-serve` on the same machine passes and hosted Jev is
rejected; `team` and `regulated` profiles need the host on the allowlist.
`describe_data_flow()` lists the reranker endpoint.

### Behaviour changes

None on default paths. `SystemOneReranker` accepts `mode="rank"`; an unknown
mode still raises `ValueError`, whose message now lists `rank`.

### Upgrade notes

Drop-in from 0.4.1. No migration, no change to stored data or to `context()`
output unless you configure a reranker. `smriti-enterprise` 0.2.0 is
unchanged and works with 0.4.2.

### Known limits

- The judge trials used LME-X only (LongMemEval questions with 48
  cross-question distractor sessions each; not the official LongMemEval-S
  haystack). Judges were not tested on LoCoMo.
- The trials measure evidence reaching the context, not answer accuracy;
  blinded QA was not re-run with judges.
- The Laya head was trained on 256 LME-X questions and may not transfer to
  other conversations without retraining. Latency figures are for the named
  hardware; Jev's cost uses its list price on 2026-09-25.
- The first 0.4.1 trial figures were affected by a lab harness bug (see the
  correction in the 0.4.1 notes); all 0.4.2 figures were measured with the
  fixed harness.

---

## Smriti 0.4.1 — sharper evidence from chat logs

**More of the right memories reach the LLM when a memory holds long
assistant replies.** Smriti already ranked the assistant's own replies below
the user's statements, unless the question asks what the assistant said.
0.4.1 demotes them more firmly (`RecallConfig.assistant_prior` 0.55 → 0.2).
The change came out of our decision-model trials: a relevance judge trained
on labelled memories put its largest weight on exactly this signal.

| Held-out LME-X questions (232) | 0.4.0 | **0.4.1** | Questions better / worse |
|---|---:|---:|---:|
| Evidence complete in context, 1,500 characters | 64.8% | 65.6% | 5 / 1 (not significant) |
| Evidence complete in context, 3,000 characters | 78.5% | **83.2%** | 23 / 1 |
| Evidence complete in context, 9,000 characters | 87.6% | **93.0%** | 26 / 0 |

The value was chosen on the dev split and tested once on held-out questions
(3,000 characters: +4.7 points, 95% CI +2.5 to +7.0, p = 3×10⁻⁶; 9,000
characters: +5.4 points, p = 3×10⁻⁸). *Correction (2026-09-25):* the first
version of these notes reported +2.6 / +4.9 points at 1,500 / 3,000
characters. Those runs compared the shipped profile against a lab variant
that skipped the aggregation-question header, which saves about 150
characters of budget; with the harness fixed, the like-for-like changes are
the ones above. LoCoMo, which has no assistant turns, is
unchanged at every budget. It costs nothing: no model, no extra latency.
Questions that address the assistant ("what did you recommend…") are not
affected. Answer-accuracy (QA) runs were not repeated for this release.

### Also new (optional)

- **Decision-model rerankers** in `smriti/decision.py`: `SystemOneReranker`
  talks to any TypeSafe-compatible `/v1/systemone` endpoint (hosted Jev, a
  local `laya-serve`, a `clm-serve` GPU host); `LayaReranker` runs Laya in
  process. Both report calls, tokens, time and cost. Nothing is sent anywhere
  unless you configure a remote endpoint.
- **Reranker controls**: `RecallConfig.rerank_depth` (how many top turns a
  reranker judges, default 48) and `rerank_weight` (1.0 replaces Smriti's
  score, as before; lower values blend).
- **Hit-aware rerankers**: a reranker that defines
  `rerank_hits(query, hits)` sees Smriti's score, rank and role for each
  candidate.

Trial results so far, including what did not work: a zero-shot Laya-family
judge ranked memories no better than chance; trained on our labels it beats
Smriti's order (AUC 0.928 vs 0.890 on held-out questions) and is the best
option at a 1,500-character budget, at about 5.5 s per question on CPU. It
remains an experiment. Details: `audit/2026-09-25/decision-models/NOTES.md`.

### Upgrade notes

- Contexts for the same query can differ from 0.4.0 where assistant turns
  compete with user turns. To keep 0.4.0 ranking for a call, pass
  `profile=PROFILES["evidence"].with_overrides(recall=RecallConfig(assistant_prior=0.55))`.
- **Enterprise:** no package change. `smriti-enterprise` 0.2.0 picks up the
  new ranking with core 0.4.1. Receipt `context_digest` values change where
  the packed context changes; `versions.core` reads `0.4.1`.

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
python -m pip install '.[onnx]'        # core 0.4.2 (+ optional in-process embeddings)
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

- **0.4.2:** 266 core and 59 enterprise tests pass in the checkout and on
  Python 3.9 and 3.12 in CI.
- **0.4.0:** 254 core and 59 enterprise tests pass in the checkout. From freshly built
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
