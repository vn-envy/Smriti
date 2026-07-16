# SMRITI Nomenclature — the stack, named in its own tongue

SMRITI's vocabulary isn't branding sprinkled on top. Indian epistemology worked
out a precise technical language for memory two millennia before vector
databases, and the pipeline maps onto it almost one-to-one.

The Nyaya account of memory runs: **anubhava → samskara → smriti** — direct
experience leaves impressions, and recollection arises from those impressions.
That is SMRITI's write path, literally. And Vedanta's **badha** (sublation — a
later cognition invalidating an earlier one *without erasing that it occurred*,
as when the rope is seen and the snake is sublated) is the exact concept behind
supersession: `invalid_at` is set, `superseded_by` points forward, history
stays queryable.

## The lexicon

| Term | Devanagari | Meaning | Maps to |
|---|---|---|---|
| **smriti** | स्मृति | that which is remembered | the system itself |
| **anubhava** | अनुभव | direct experience | episodic store — append-only raw turns |
| **grahana** | ग्रहण | grasping, apprehension | fact extraction (experience → impression) |
| **samskara** | संस्कार | impression left by experience | the consolidated fact store |
| **badha** | बाध | sublation (Vedanta) | supersession — invalidate, never delete |
| **avadhi** | अवधि | term, duration | a fact's validity window `[valid_from, invalid_at)` |
| **padartha** | पदार्थ | entity, category (Nyaya-Vaisheshika) | the entity table (graph-lite links) |
| **smarana** | स्मरण | the act of recollection | retrieval |
| **shabda** | शब्द | word | channel 1 — BM25 lexical (FTS5) |
| **artha** | अर्थ | meaning | channel 2 — vector semantic |
| **sambandha** | सम्बन्ध | relation | channel 3 — entity-hop |
| **kala** | काल | time | channel 4 — temporal proximity |
| **sangama** | संगम | confluence (of rivers) | RRF fusion — four streams, one ranking |
| **prasanga** | प्रसंग | context, occasion | the packed context block |
| **drishti** | दृष्टि | way of seeing, viewpoint | retrieval profiles — named per-query policies (0.2.0) |
| **laghu** | लघु | light | `mode="lite"` (alias accepted in code) |
| **purna** | पूर्ण | complete | `mode="full"` (alias accepted in code) |
| **pariksha** | परीक्षा | examination | the benchmark harness (`bench/`) |
| **nyaya** | न्याय | logic, right judgment | the LLM judge |
| **mauna** | मौन | deliberate silence | abstention — knowing when not to answer |

## Usage rules

1. **Code stays ergonomic.** Field names, function names, and CLI flags remain
   English (`valid_from`, `retrieve`, `--mode lite`) so the library is usable
   by anyone. The exceptions: `mode="laghu"` / `mode="purna"` and the channel
   aliases `shabda`/`artha`/`sambandha`/`kala` are accepted as first-class
   aliases, and module docstrings carry the lexicon where each concept lives.
2. **Docs lead with the concept, gloss with the term.** "Supersession (*badha*,
   बाध)" — never the reverse. The vocabulary should teach, not gatekeep.
3. **The terms are load-bearing.** Each was chosen because the classical
   meaning matches the engineering meaning. If a future component has no honest
   Sanskrit fit, it gets an English name. No forced poetry.

## Why this matters beyond aesthetics

The anubhava→samskara→smriti line encodes a real design argument: memory is
*derived* from experience but is not the experience itself — which is why
SMRITI retrieves over **both** (facts for precision, episodes as the recall
safety net). And badha encodes the second argument: correction is an event in
time, not an overwrite — which is why "where do I live?" and "where did I live
before June?" are both answerable from one store.
