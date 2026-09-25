# Evidence-first recall — lab report (2026-09-25)

**Question:** where was Smriti weakest, what can be fixed now without an LLM
at query time, and how does the result compare with a leading open-source
memory layer on the same data, reader and judge?

**Answer in one paragraph.** Retrieval was not the main problem: the 0.3.x
read path usually *found* the supporting turn but then threw it away while
packing (12 items, each cut at 700 characters, about 1.8k of a 9k-character
budget used on LoCoMo). A new read engine keeps the evidence: it ranks turns
by score-level lexical + semantic fusion, rolls turn scores up to sessions,
resolves relative dates, and fills the budget with complete turns grouped by
dated session. On held-out test splits, the share of evidence turns that reach
the reader complete rose from 55.9% to 84.7% (LoCoMo) and from 43.2% to 87.6%
(LME-X). In blinded QA with the same reader and judge for every system,
accuracy rose by 19–23 points over the 0.3.x path. Against **Mem0 OSS 2.2.0**
over the same turns, Smriti was **+8.8 points on LME-X** (pooled over two
reads; bootstrap 95% CI +1.7 to +15.4, sign test p = 0.07) and **statistically
tied on LoCoMo** (+2.8, CI −1.8 to +7.2). At 100k stored turns the new engine
answers in about 32 ms p50, about 4× faster than the old path. It is local,
needs no query-time LLM, and is now the default.

Everything below is reproducible with `bench/lab/` (see
[`bench/lab/README.md`](../../bench/lab/README.md)); raw result files are in
[`results/`](results/). The research that picked these experiments is in
[`RESEARCH-SURVEY.md`](RESEARCH-SURVEY.md).

## 1. Diagnosis: where evidence was lost

The first lab run measured each system in two stages: whether the supporting
turns were *ranked* high (recall@k) and whether they *survived*, complete, into
the context given to the reader (`ctx_full`).

| LME-X test, 0.3.x read path | Value |
|---|---:|
| Recall@10 (evidence turn ranked in the top 10) | 78.1% |
| Evidence turns complete in the packed context | 43.2% |
| Multi-session questions: evidence complete in context | 16.4% |
| Assistant-said questions: evidence complete in context | 19.4% |

So most losses happened after retrieval. The same pattern appears in the
SmartSearch paper (98.6% recall, 22.5% survival). The 0.3.x packer took 12
fused results, cut every turn at 700 characters, and left relative dates
("last Friday") unresolved. Long assistant turns were usually cut before the
answer.

## 2. What was built

All of it is deterministic and runs on a CPU. No tokens are spent at query
time.

| Component | Where | What it does |
|---|---|---|
| Evidence-first ranking | `smriti/recall.py` `rank_episodes` | FTS5 BM25 (stopword-stripped, light-stem prefix terms) and exact cosine over the same candidate depth (200); **score-level convex fusion** (BM25 max-ratio, cosine min-max with a minimum spread); turn → session roll-up (`session_weight`); alternative sub-queries for "X or Y" ordering questions |
| Priors | same | Assistant turns ×0.55 unless the question addresses the assistant ("you said…", "remind me…", "we talked about…"); named-speaker prior; soft time-window prior from the question (`time_boost`); date-bearing turns lifted for "when" questions (`when_boost`) |
| Temporal grounding | `smriti/temporal.py` | Resolves "yesterday", "last weekend", "two weeks ago", "last Friday", seasons, "in 3 days"… against each turn's timestamp and shows the result inline: `yesterday [2023-05-07]`. Parses question windows ("in March", "past two months", explicit dates). Results are cached per turn text |
| Budget-adaptive packing | `smriti/recall.py` `pack_evidence` | Exact character accounting; whole turns while they fit, otherwise **query-focused excerpts** in place of a prefix cut; turns grouped under `[Session YYYY-MM-DD Ddd]` headers in chronological order, with the current date and a "most recent statement wins" note for update questions; facts and entity summaries get a bounded share (35%) |
| In-process embeddings | `smriti/onnx_embedder.py` | `OnnxEmbedder` runs all-MiniLM-L6-v2 (or any sentence-transformer ONNX export) with `onnxruntime` + `tokenizers`; no embedding server |
| Contextual episode embeddings (opt-in) | `Smriti(contextual_embeddings=N)` | Each turn's vector also sees the last N characters of the previous turn; stored text is unchanged |
| Wiring | `smriti/memory.py`, `profiles.py`, `mcp_server.py` | `read_engine="evidence"` is the default for `search()`/`context()`; `read_engine="fusion"` and every named profile keep the 0.3.x behaviour; MCP gains the `evidence` profile and a `now` anchor |

## 3. Method

**Data.** *LoCoMo10* (10 conversations, 1,540 answerable questions,
turn-level evidence ids). *LME-X*: the 500 LongMemEval questions, each with
its own evidence sessions plus **48 distractor sessions taken from other
questions**, re-dated before the question date. LME-X exists because the
official LongMemEval-S haystack could not be downloaded here. It is harder
than the oracle setting, but **it is not LongMemEval-S**, and its scores are
not comparable with published LongMemEval-S numbers.

**Splits.** LoCoMo dev = conversations 26, 41, 43, 47, 49; test = 30, 42, 44,
48, 50. LME-X splits by question-id hash. **Every tuning decision used dev
only.** Test numbers were produced once, after the defaults were frozen.

**Systems (same turns, timestamps, question date, 9,000-character budget and
cached MiniLM vectors for every arm):**

- *Smriti 0.3.x read path*: the previous default (`read_engine="fusion"`).
- *Smriti evidence-first*: the new default. *First cut* is the first frozen
  version, before speaker, stemming and budget refinements.
- *Mem0 OSS 2.2.0*, `infer=False`: Mem0's own hybrid scoring (semantic +
  spaCy-lemmatized BM25 via fastembed `Qdrant/bm25`) over the same raw turns
  in a local Qdrant, packed in rank order with timestamps. `infer=False`
  stores turns verbatim (no LLM extraction), so both systems retrieve over
  identical text. Mem0's LLM-extraction mode was not run (no extraction model
  was available offline).
- *BM25* and *dense MiniLM* with a rank-order packer, as floors.

**Retrieval metrics.** `ctx_full`: share of evidence turns whose complete
text is in the context. `ctx_all_full`: every evidence turn is complete.
`ans_in_ctx`: the gold answer string, when it occurs verbatim in an evidence
turn, reaches the context. `r@k`: evidence turns in the top-k ranked turns.
Latency: wall time of `search` + `context`, query vectors served from the
shared cache.

**Answer quality.** 200 stratified LoCoMo test questions and 120 LME-X test
questions. The protocol:

1. Every system's context for every question is shuffled together under an
   opaque id. Readers see no system names.
2. **Reader: Claude Haiku** subagents answer from the context only, with
   today's date given. Tools were limited to reading the batch and writing
   answers; one batch whose agent wrote helper scripts was discarded and
   re-read.
3. **Judge: Claude Sonnet**, blind to system, uses a strict
   LongMemEval-style rubric: every listed item required, counts and dates must
   match, and abstaining is wrong unless the gold answer says the information
   is unavailable. Abstention questions are scored by rule.
4. Paired McNemar tests within a run. Across runs: a question-level sign test
   and a question-level bootstrap CI, so a question read twice never counts as
   two samples.

**A finding about the protocol itself.** Run 2 re-read **byte-identical
contexts** from run 1 in one fresh shuffled run. The same Smriti contexts
scored 65.0% and 75.8% on LME-X, and Mem0 moved from 64.2% to 59.2%. With
120 questions, reader and judge drift alone can move a system by 10 points
between runs, so **only arms read in the same run are compared directly**, and
the headline figures pool both reads. Published single-run cross-vendor
leaderboards seldom control for this.

## 4. Retrieval and context survival (test splits)

**LoCoMo test (749 questions with evidence labels)**

| System | Evidence fully in context | All evidence in context | Answer string in context | Recall@5 | Recall@10 | p50 ms |
|---|---:|---:|---:|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 55.9 | 50.6 | 64.3 | 39.6 | 51.4 | 4.3 |
| **Smriti evidence-first (new default)** | **84.7** | **78.2** | **95.5** | 58.2 | 66.9 | 10.1 |
| Smriti evidence-first + contextual embeddings | 86.3 | 79.6 | 95.1 | 61.7 | 70.7 | 10.4 |
| BM25 (rank-order packer) | 69.1 | 62.6 | 81.6 | 47.9 | 54.8 | 0.9 |
| Dense MiniLM (rank-order packer) | 66.7 | 60.1 | 73.8 | 30.9 | 39.1 | 0.3 |
| Mem0 OSS 2.2.0 hybrid (`infer=False`) | 79.4 | 73.2 | 86.5 | 51.1 | 63.8 | 59.6 |

| Evidence fully in context | multi-hop | open-domain | single-hop | temporal |
|---|---:|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 30.7 | 28.0 | 63.7 | 61.5 |
| **Smriti evidence-first** | 62.4 | 53.6 | 92.2 | 89.5 |
| Mem0 OSS 2.2.0 | 63.7 | 53.3 | 84.7 | 83.6 |

**LME-X test (232 questions with evidence labels)**

| System | Evidence fully in context | All evidence in context | Answer string in context | Recall@5 | Recall@10 | p50 ms |
|---|---:|---:|---:|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 43.2 | 35.8 | 82.0 | 62.8 | 78.1 | 8.1 |
| **Smriti evidence-first (new default)** | **87.6** | **81.0** | **96.2** | **79.0** | **87.3** | 14.7 |
| Smriti evidence-first + contextual embeddings | 87.8 | 81.0 | 96.2 | 79.1 | 86.9 | 13.8 |
| BM25 (rank-order packer) | 73.7 | 66.0 | 89.7 | 65.6 | 76.5 | 1.7 |
| Dense MiniLM (rank-order packer) | 69.1 | 56.9 | 80.8 | 56.5 | 71.5 | 0.5 |
| Mem0 OSS 2.2.0 hybrid (`infer=False`) | 69.1 | 57.8 | 84.6 | 59.7 | 75.2 | 90.7 |

| Evidence fully in context | knowledge-update | multi-session | assistant-said | preference | user-said | temporal |
|---|---:|---:|---:|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 51.3 | 16.4 | 19.4 | 60.8 | 84.7 | 43.8 |
| **Smriti evidence-first** | 97.3 | 80.7 | 80.7 | 75.5 | 95.8 | 89.7 |
| Mem0 OSS 2.2.0 | 81.1 | 55.0 | 96.8 | 38.2 | 81.9 | 60.5 |

Smriti's assistant-said figure (80.7) is below Mem0's (96.8) because long
assistant turns are excerpted rather than included whole. The answer string
still reaches the context in 100% of those questions, and QA accuracy on the
category is 90–100%.

Source: `results/retrieval-locomo-all.json`, `results/retrieval-lmex-test.json`
(the LME-X Mem0 arm comes from the earlier identical-data run; Mem0 does not
depend on Smriti code). A late change widening assistant-reference detection
("remind me…", "we talked about…") was re-run on all 500 LME-X questions:
the test split is unchanged to the decimal, and the dev split improves
slightly (assistant-said r@10 96 → 100).

## 5. Answer quality (blinded reader and judge)

### Headline: pooled over two reads of the same contexts

**LoCoMo (200 test questions × 2 reads)**

| System | Pooled accuracy | Run 1 | Run 2 |
|---|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 46.0 | 47.5 | 44.5 |
| Mem0 OSS 2.2.0 hybrid (`infer=False`) | 62.7 | 64.0 | 61.5 |
| **Smriti evidence-first (new default)** | **65.5** | 67.0 | 64.0 |
| *Full conversation in context (run 1 only)* | *71.0* | *71.0* | – |

| Pair | Difference (pts) | 95% CI | first better | second better | sign-test p |
|---|---:|---:|---:|---:|---:|
| Smriti 0.3.x vs Smriti evidence-first | −19.5 | −25.2 to −14.0 | 11 | 64 | <0.0001 |
| Mem0 OSS 2.2.0 vs Smriti evidence-first | −2.8 | −7.2 to +1.8 | 23 | 31 | 0.34 |

**LME-X (120 test questions × 2 reads)**

| System | Pooled accuracy | Run 1 | Run 2 |
|---|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 47.5 | 49.2 | 45.8 |
| Smriti evidence-first, first cut | 70.8 | 72.5 | 69.2 |
| Mem0 OSS 2.2.0 hybrid (`infer=False`) | 61.7 | 64.2 | 59.2 |
| **Smriti evidence-first (new default)** | **70.4** | 65.0 | 75.8 |

| Pair | Difference (pts) | 95% CI | first better | second better | sign-test p |
|---|---:|---:|---:|---:|---:|
| Smriti 0.3.x vs Smriti evidence-first | −22.9 | −31.2 to −15.0 | 10 | 46 | <0.0001 |
| Mem0 OSS 2.2.0 vs Smriti evidence-first | −8.8 | −15.4 to −1.7 | 13 | 25 | 0.073 |
| Evidence-first first cut vs new default | +0.4 | −4.2 to +5.4 | 13 | 13 | 1.0 |

Reading the tables:

- **The evidence-first engine answers 19–23 points more questions correctly
  than the 0.3.x path**, with p < 0.0001 on both datasets and in every
  individual run.
- **Against Mem0 OSS: ahead on LME-X, level on LoCoMo.** On LME-X the
  bootstrap CI excludes zero but the stricter sign test does not reach 0.05,
  so the lead is likely but not proven at n = 120. On LoCoMo the difference
  is within noise.
- Smriti's evidence context on LoCoMo uses about 9k characters, roughly a
  tenth of a conversation. The full-conversation reference scored 71.0 in run
  1, against 67.0 for Smriti in the same run. Full context alone was right on
  20 questions and Smriti alone on 12 (McNemar p = 0.22).
- The refinements after the first cut improved retrieval metrics on dev and
  test but did not produce a measurable QA change.

### Per-category, run 2 (all arms read together)

LoCoMo:

| System | Accuracy | 95% CI | multi-hop | open-domain | single-hop | temporal |
|---|---:|---:|---:|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 44.5 | 37.5–51.5 | 23.6 | 34.3 | 63.6 | 52.7 |
| Mem0 OSS 2.2.0 hybrid (`infer=False`) | 61.5 | 55.0–68.5 | 52.7 | 37.1 | 80.0 | 67.3 |
| **Smriti evidence-first (new default)** | 64.0 | 57.5–70.5 | 47.3 | 37.1 | 85.5 | 76.4 |

LME-X:

| System | Accuracy | 95% CI | knowledge-update | multi-session | assistant-said | preference | user-said | temporal |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Smriti 0.3.x read path (fusion) | 45.8 | 36.7–54.2 | 28.6 | 23.8 | 71.4 | 17.6 | 85.0 | 45.0 |
| Smriti evidence-first, first cut | 69.2 | 60.8–77.5 | 81.0 | 52.4 | 85.7 | 23.5 | 95.0 | 70.0 |
| Mem0 OSS 2.2.0 hybrid (`infer=False`) | 59.2 | 50.0–67.5 | 61.9 | 38.1 | 90.5 | 11.8 | 100.0 | 45.0 |
| **Smriti evidence-first (new default)** | 75.8 | 67.5–83.3 | 76.2 | 71.4 | 100.0 | 41.2 | 100.0 | 60.0 |

Category cells hold 17–55 questions. Treat single-category gaps below about
15 points as noise.

**Where Smriti still loses.** LoCoMo *multi-hop* (list and aggregation
questions): Mem0 is ahead in both runs (58.2 vs 52.7, then 52.7 vs 47.3).
Inspecting the 18 run-2 questions that Mem0 answered and Smriti missed:
**in every case checked, the supporting turn was in Smriti's context**
(for example "Indiana", "Walking Dead … next Saturday [2023-01-28]", "letter I
received yesterday [2023-01-26]"). The reader abstained or picked a different
item from a longer, denser context. Smriti's contexts produce *fewer*
abstentions overall (25 vs 29 on LoCoMo; 13 vs 31 on LME-X). The remaining
gap is reading, not retrieval, which points to per-question-type packing
(below) rather than more recall.

Files: `results/qa-*-run1.json`, `results/qa-*-run2-paired.json`,
`results/qa-*-pooled.json`. Rows include every answer and verdict.

## 6. Scale and latency

Synthetic growth (`bench/lab/scale.py`, MiniLM 384-d, 4-vCPU Xeon, one SQLite
file), `search` and `context` p50/p95 in ms:

| Stored turns | Store size | Evidence search p50 / p95 | Evidence context p50 / p95 | 0.3.x search p50 / p95 | 0.3.x context p50 / p95 |
|---:|---:|---:|---:|---:|---:|
| 10,000 | 36.0 MB | 9.1 / 21.9 | 11.4 / 20.1 | 12.7 / 17.6 | 13.1 / 21.1 |
| 36,500 | 134.7 MB | 15.7 / 33.8 | 21.8 / 33.8 | 48.9 / 65.3 | 47.8 / 61.9 |
| 100,000 | 371.0 MB | 32.2 / 66.8 | 32.9 / 65.3 | 131.6 / 204.9 | 128.3 / 163.6 |

The new engine is about 4× faster at 100k because it runs one BM25 query
and one vector scan, then selects the top candidates with `argpartition`
instead of sorting everything. On the lab datasets its p50 is 10–15 ms,
against 60–90 ms for Mem0 OSS with local Qdrant.
Source: `results/scale-probe.json`.

## 7. What did not work, or was left off (dev split)

| Idea | Dev result | Decision |
|---|---|---|
| Reciprocal-rank fusion instead of score fusion | LoCoMo r@5 60.8 → 52.4, ctx_full −3.6; LME-X +2.7 r@5 | Convex score fusion default; RRF is `fusion="rrf"` |
| Blended RRF + score | LoCoMo −3.7 r@5, LME-X +0.6 | Off |
| Pseudo-relevance feedback (0.3 / 0.6) | r@5 −0.7 to −2.5 on both | Off |
| Neighbour-turn windows around hits | 0, 1 or 2 neighbours gave identical results; extra neighbours for the top hits moved ctx_full by −1.3 to +0.7, because direct hits use up the budget first | `neighbors=1`, `neighbor_top` off |
| Per-session caps for aggregation questions | Slightly lower ctx_full | `agg_session_cap=0` |
| Lexical/semantic weight 0.65/0.35 or 0.35/0.65 | Both lower r@5 on both datasets | 0.5/0.5 |
| Session roll-up 0.1 / 0.4 / 0.5 (vs 0.25) | 0.4–0.5 help LoCoMo and lower LME-X r@5; 0.1 hurts LoCoMo | 0.25 |
| Assistant prior 1.0 (no down-weighting) | LME-X ctx_full −4.0, r@5 −6.1 | 0.55 |
| Relevance-ordered or top-first layouts (QA, dev, n=120) | 72.5 / 72.5 vs 70.8 chronological, McNemar p ≈ 0.8 | Chronological kept; `layout=` knob available |
| Contextual episode embeddings | LoCoMo test r@5 +3.5, ctx_full +1.6; LME-X neutral | Opt-in: it changes stored vectors and ingest cost |
| Cross-encoder reranking | No local model was reachable to evaluate | Any `.rerank()` is supported on the head of the list |
| Entity graph / Personalized PageRank | Not attempted in this round | Next |

## 8. Limitations, and how this relates to published leaderboards

- **LME-X is not LongMemEval-S**, and the QA samples are 200 and 120
  questions. Do not put these numbers next to published LongMemEval-S or
  LoCoMo "J" scores.
- **Reader and judge.** Claude Haiku reads and Claude Sonnet judges. A
  stronger reader raises every system; published results show 3–10 point
  swings from the reader alone. The strict judge (every list item required,
  abstentions wrong) scores lower than the lenient gpt-4o-mini judge used by
  most LoCoMo leaderboards.
- **Mem0 comparison scope.** The comparison is Mem0 OSS 2.2.0 retrieval over
  verbatim turns (`infer=False`), with the same embedder and budget as Smriti.
  It is not Mem0's hosted platform, its LLM-extraction mode, or its 2026
  "token-efficient" algorithm with entity fusion (reported as 94.4
  LongMemEval / 92.5 LoCoMo, self-reported with a different reader, judge and
  context size).
- **Embedder.** Every arm used all-MiniLM-L6-v2 (384-d), the strongest model
  available offline here. Larger embedders would lift the semantic halves of
  both Smriti and Mem0.
- Zep, Letta, Hindsight, Supermemory and MemMachine were not re-run. Their
  published numbers are in `RESEARCH-SURVEY.md` with sourcing labels.

## 9. Next experiments

1. **Question-type packing for lists and aggregation.** The LoCoMo multi-hop
   gap is in reading. Try an "enumerate every mention" layout: one line per
   dated hit, with no session grouping.
2. **Local cross-encoder rerank** (for example a MiniLM or BGE reranker in
   ONNX) on the top 48 turns, evaluated with the same dev/test protocol.
3. **Entity-anchored expansion** (entity links or PPR over the existing
   `entity_links` table) for multi-hop questions.
4. **Official LongMemEval-S and a stronger reader** once the haystack and a
   local reader are reachable. Always read all arms together in the same run.

## Reproduce

```bash
pip install -e ".[onnx]" mem0ai==2.2.0 fastembed qdrant-client
python -m bench.lab.run --dataset locomo --split test --systems "smriti_fusion,evidence,ev(ctx_embed=150),bm25,dense,mem0" --out locomo.json
python -m bench.lab.run --dataset lmex   --split test --systems "smriti_fusion,evidence,ev(ctx_embed=150),bm25,dense,mem0" --out lmex.json
python -m bench.lab.report retrieval locomo.json test
python -m bench.lab.qa export --dataset lmex --split test --sample 120 --systems "smriti_fusion,evidence,mem0" --out qa/lmex
#   read batch_XX.txt -> answers_XX.jsonl; judge-export; judge -> verdicts_XX.jsonl
python -m bench.lab.qa score --dir qa/lmex --out qa-lmex.json
python -m bench.lab.qa rebatch --src qa/lmex:smriti_fusion,evidence,mem0 --out qa/lmex_rerun   # second read, same contexts
#   read, judge-export, judge and score qa/lmex_rerun -> qa-lmex-rerun.json
python -m bench.lab.qa pool qa-lmex.json qa-lmex-rerun.json --out qa-lmex-pooled.json
python -m bench.lab.report pooled qa-lmex-pooled.json
python -m bench.lab.scale --sizes 10000,36500,100000 --out scale.json
```
