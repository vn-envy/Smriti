# Quality next steps

This is a future quality roadmap based on the completed, frozen paired
LongMemEval-S50 and LoCoMo50 reviews. It does not change official scores, and
it does not turn the exploratory samples into a superiority claim. The current
harness controls that are already complete—same selected IDs and dataset
hashes, pinned reader/judge configuration, opaque source labels, raw contexts,
failure-inclusive denominators, and cleanup reporting—remain the baseline for
these follow-ups.

## Evidence that sets the priority

- **LongMemEval-S50:** both adapters completed all 50 rows with zero operational
  or cleanup failures and recorded 32/50 overall, 14/30 answerable, and 18/20
  abstention rows correct. The paired review found 30 rows correct for both, 16
  for neither, and four disagreements. In `118b2229`, the official user
  statement says **“45 minutes each way”**; Smriti's reader context omitted
  that statement while retaining an assistant approximation, **“an hour of
  commute time each way,”** and Mem0 retained the user statement. In
  `75832dbd`, Smriti retained the medical-imaging research context while Mem0
  retained a generic conference preference. In `852ce960`, both contexts
  contained the earlier `$350,000` and later `$400,000` statements, but the
  adapters selected different updates. The `6d550036` gold construction also
  has a recorded interpretation caveat: one source says “solo project” without
  explicitly saying the user led it.
- **Targeted context review:** among 16 failed answerable Smriti rows, three
  lacked an official answer session in retrieval, one retained all answer
  sessions but lost a session header in the final reader context, and 12
  retained all headers. Header presence is not proof that the supporting
  utterance survived. The five exact-chunk checks found a newer value cut after
  “which is” (`945e3d21`), an older `27:12` selected although `25:50` was also
  available (`6a1eabeb`), and the ambiguous clothing-count construction
  (`0a995998`). These observations identify testable availability and reading
  problems; they do not prove that retrieval caused every answer failure.
- **LoCoMo50:** Smriti recorded 27/50 and Mem0 26/50, with 24 correct for both,
  21 incorrect for both, and five disagreements. The date audit found a known
  judge false positive: `conv-30-q0` has gold **19 January 2023**, while both
  hypotheses say **20 January 2023** and were accepted. This disagreement
  between the explicit gold and hypotheses requires a judge-control check.

The raw evidence is preserved in
[`longmemeval-smriti-s50-answerable-failure-review.json`](raw/longmemeval-smriti-s50-answerable-failure-review.json),
[`longmemeval-smriti-s50-selected-chunk-review.json`](raw/longmemeval-smriti-s50-selected-chunk-review.json),
[`longmemeval-pair-four-disagreement-review.json`](raw/longmemeval-pair-four-disagreement-review.json),
and
[`locomo-smriti-mem0-s50-paired-quality-review.json`](raw/locomo-smriti-mem0-s50-paired-quality-review.json).

## Prioritized follow-ups

1. **Preserve supporting source messages and diversify multi-session context.**
   Create a reviewed evidence-message annotation set from official source sessions,
   preserving ambiguity where the dataset supplies only session-level labels.
   Add a diagnostic mode that records, for each annotated evidence message, exact
   retrieval presence, exact reader-context presence, source ID, and truncation
   boundaries. Compare default retrieval with the existing opt-in
   `session_diverse=True, session_overfetch=3` path on a new held-out selection
   with identical IDs and budgets. Keep source-message fidelity and session
   coverage as reported measures; do not tune against the five inspected rows.

   Acceptance criteria: every row has a machine-checkable evidence ledger;
   every omitted or truncated annotated supporting message is counted; default and opt-in
   runs preserve identical question/config metadata; and any quality change is
   reported with failure-inclusive denominators and a predeclared held-out
   sample. A context-header hit alone cannot be counted as evidence presence.

2. **Make competing updates explicit to the reader.** Retrieve complete user
   statements when multiple values exist, retain their source dates and order,
   and expose the relevant “as of” condition in the reader input. Exercise this
   with fixtures modeled on `6a1eabeb` (27:12 then 25:50) and `852ce960`
   ($350,000 then $400,000), plus an as-of query whose correct value is the
   earlier one. Keep ambiguous gold constructions such as `6d550036` labeled
   for review rather than using them as clean regression targets.

   Acceptance criteria: the fixture suite returns the latest value for current
   queries and the earlier value for explicit as-of queries, while retaining
   both source messages and their dates in the evidence ledger. A pass is a
   contract result for these fixtures, not a general semantic-quality claim.

3. **Harden judge and date reliability before using answer scores for decisions.**
   Preserve raw judge requests/responses, parse dates only at matching
   granularity, and emit `needs_review` when an explicit date differs from the
   gold or when the answer is ambiguous. Add `conv-30-q0` as a permanent
   negative control and retain `conv-26-q0` as a relative-date control; do not
   rewrite the historical scores.

   Acceptance criteria: the negative control is rejected, the relative-date
   control is evaluated against the stated “yesterday” relation, ambiguous
   date formats are not auto-normalized, and every adjudication is traceable to
   the raw response and official source evidence. Report judge disagreements
   separately from retrieval and reader failures.

These are follow-up gates for representative held-out evaluation. They do not
reclassify the completed S50 results, and shared-host timing remains excluded
from quality or speed ranking.
