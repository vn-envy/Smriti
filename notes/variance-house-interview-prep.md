# Variance House interview prep — SMRITI

*Built from the repo state on 2026-09-01 (v0.3.2, enterprise modules, BENCHMARKS.md, landscape page) plus public information on Variance House and the competing systems. Every number below is either in this repo or cited to a public source; the caveats are real — use them, they are part of the pitch.*

---

## 0. Read this first: who is across the table, and what that changes

**The program.** 30 days (15 Sep – 15 Oct), 14 residents, Bengaluru, run under The Residency by **Yug Gupta** (ex-founding SWE at AGI Inc — Div Garg's agent company) and **Vedant Nayak** (19, ex-Dench, YC S24). No equity, $30k+ credits per head incl. $10k Anthropic. Demo Day 16 Oct: *"show what changed, not a polished pitch."* They say they select for **technical ability, ambition, speed, and what you can accomplish in 30 days** — not credentials. Their application literally asks for **one specific, measurable milestone demonstrable by 15 Oct**. Have that answer memorised (Section B).

**The cohort.** Robotics, hardware, applied physics, biotech, neurotech, foundational AI. You will be the software-only person in a hardware house. Two consequences:

1. You must frame SMRITI as **foundational infrastructure with a falsifiable technical claim**, not as a dev-tool. The claim: *for the majority of agent workloads, a ~2.5k-line, single-file, bi-temporal memory kernel delivers equal-or-better correctness per rupee than platform memory systems requiring Postgres/Neo4j/cloud — and you can verify that yourself in one command.*
2. You have a natural bridge to the room: **robots and devices need memory that runs offline, on the device, with no cloud dependency.** SQLite is already on every phone and Jetson. A memory layer that is one SQLite file + numpy is the only architecture in this landscape that fits an edge robot. Say this early.

**Mentors whose lenses to prepare for.**

| Mentor | Lens | What they will poke |
|---|---|---|
| Shyamal Anadkat (ex-Applied Evals lead, OpenAI) | Evaluation rigor | Oracle split vs full haystack, judge bias, n and p-values, LLM-as-judge validity. Be exact. |
| Soumyadeep Bakshi (Collinear — evals/judges) | Same | Fixed-judge protocol, self-grading. |
| Div Garg (AGI Inc) | Agents in production | What breaks when agents run for weeks; stale memory as an action-error source. |
| Abhishek Kankani (Cloudflare ETI) | Edge/infra | SQLite-at-the-edge story; concurrency; scale envelope. |
| Atharva Gundawar (Markov Robotics) | Robotics | Offline memory for embodied agents. |
| Hemant Mohapatra (Lightspeed), Harshita Arora (YC), Rajeev Mantri (Navam) | Market | Is this a company or a component? Who pays? |
| Danielle Strachman (1517), Cory Levy (Z Fellows) | Contrarian founders | Why you, why now, why small beats big. |
| Terry Winograd (Stanford, HCI/language) | Human–machine understanding | What does it mean for an agent to "remember" — your Nyaya framing lands here. |

---

## 1. The 90-second opener (memorise the shape, not the words)

> Agents forget, and every fix on the market is a database. mem0 wants Postgres and Qdrant; Zep wants Neo4j; GBrain wants Postgres; Hindsight wants Postgres plus a service. I built SMRITI on a different bet: memory is a *data-ownership* problem before it is a retrieval problem, so it should live in one file the owner controls — like SQLite itself, the most deployed database on earth precisely because it has no server.
>
> SMRITI is ~2.5k lines, stdlib + numpy, one SQLite file. Two ideas do the work. First, **supersession instead of mutation**: when a fact changes, the old one is marked invalid with a date, never deleted, and the validity window is printed into the context the model reads — so "where do I live" and "where did I live in March" are both answerable from the same store. Second, **four retrieval channels fused by RRF, routed per question type** — because I measured that the recall tricks that lift aggregation questions *launder stale values* into current-state questions. Routing fixed it: +10 points on multi-session, p=0.046, zero regression on knowledge-update.
>
> I ship the benchmark harness in the box. On the leaderboard, hosted platforms post higher numbers than my self-run figure. On quality per rupee, for personal, coding, on-device and edge agents — the majority of agents that will exist — I think a small verified kernel wins, and in 30 days I want to prove or disprove that with the first same-judge, same-reader, cost-included comparison against mem0 and Zep.

---

## 2. Section A — First-principles Q&A: why simplicity beats the big brothers on quality per cost

Each answer has: the first-principles core → the number → the honest caveat. Interviewers trust the caveat more than the claim.

### A1. "Start from zero. What is agent memory actually for?"

**Core.** Three jobs, in order of difficulty: (1) write cheaply enough that you can afford to remember everything; (2) at question time, pick the ~1–2k tokens out of ~100k+ of history that make the answer correct; (3) **do not lie about time** — the world changes, and a memory that forgets *when* something was true will confidently give a stale answer.

Most systems optimise (2) and treat (3) as a cleanup job. SMRITI treats (3) as the schema: every fact has `valid_from` / `invalid_at` / `superseded_by`.

**Number.** Full-context (dump everything, no memory layer) scores 60.2% on LongMemEval with GPT-4o at ~115k tokens per question. SMRITI packs ~1,600 tokens per answer. That is the entire economic reason memory layers exist: a ~70× token reduction.

**Caveat.** Job (2) is largely commodity now (hybrid BM25+vector+RRF). The defensible work is in (3) and in *how you route* (2) per question — which is where my measured results are.

### A2. "Where is the technical breakthrough? Hybrid retrieval and SQLite are old."

**Core.** Three things I have not seen combined elsewhere, and one measured finding:

1. **Bi-temporal supersession in the write path with zero tokens for the common case.** `(subject, predicate)` collisions supersede deterministically; only semantic collisions pay one tiny arbitration call. Zep has the temporal model but needs a graph database; mem0 added supersession this year as a background job on paid tiers.
2. **Validity annotated *and ordered* in the packed context** — the model sees `[2026-01-15 | SUPERSEDED on 2026-06-01]` vs `[2026-06-01 | CURRENT]`, CURRENT first. An external audit caught that I shipped annotation without ordering in 0.3.0; 0.3.1 fixed it and added the regression test.
3. **Retrieval profiles as data with evidence fields** (`drishti`). Every built-in profile cites the A/B that justified it. Anyone can define a profile and re-run `bench/ab.sh` on their own data.
4. **The finding:** high-recall machinery (key expansion, observation digests) that lifts multi-session/aggregation questions **actively hurts knowledge-update questions** by surfacing superseded values ("$350k mortgage" instead of the current "$400k"). A zero-token per-type router — recall path for "how many / summarise", precision path for everything else — kept the +10.3 on multi-session and removed the −9 to −13 knowledge-update tax.

**Number.** Multi-session 0.359 → 0.462 (+10.3, McNemar p=0.046, n=78); knowledge-update 0.833 → 0.846 (+1.3, was −5.1 before routing). Temporal-reasoning +17.6 from the observation stack on n=200.

**Caveat.** Oracle (evidence-only) split, DeepSeek reader and judge, per-type n of 30–78. The deltas are transferable; the absolute levels are not. The full-haystack run is exactly what I want the residency's credits for.

### A3. "mem0 reports 93–94% on LongMemEval. You report 68.7% on an easier split. Why would anyone choose you?"

**Core.** Decompose "quality delivered per cost spent" honestly:

> value = P(correct | question) × (how much correctness matters for this workload) − [tokens × price + infrastructure + operations + verification cost + lock-in]

For a support bot at a large SaaS company with an SRE team, the left term dominates — pay for the platform. For the *majority of agents that will exist* — personal agents, coding agents, on-device assistants, robots, air-gapped or regulated deployments — the right term dominates: nobody is standing up Postgres + Qdrant + a cloud account for a memory that holds 20k facts. And on the categories those agents actually hit (single-session recall, knowledge updates), the gap is small.

**Numbers.**
- Vendor headline vs independent: mem0 self-reports 93.4–94.4% on LongMemEval; an independent evaluation (vectorize.io, March 2026) measured **49.0%** under the same benchmark name. That 45-point spread *is my argument* — the number you cannot reproduce is not the number you will get.
- SMRITI single-session-user is 94.4% on oracle — competitive with everyone on the category most real queries fall into.
- Cost: ~1,600 tokens per answer vs mem0's own ~6,900 per retrieval. A frontier reader + judge over 500 questions costs ~$2.50 on SMRITI. Graph memory on mem0 is behind the $249/month Pro tier; the graph is free here.
- Infra: mem0 self-host = Docker + Postgres + Qdrant; Zep = Neo4j (community edition deprecated); GBrain = Postgres/pgvector (PGLite for local); Hindsight = Postgres 14+. SMRITI = `pip install`, one file.

**Caveat.** I refuse to claim parity on full-haystack until I have run it with a fixed judge. That is the honest position and the 30-day milestone.

### A4. "mem0 just shipped Dream — supersession, merge, synthesis. Doesn't that erase your differentiator?"

**Core.** It validates it. When the 50k-star incumbent adopts "mark superseded, never delete, keep history" — the exact design I shipped in 0.1.0 — the design argument is settled. What remains different:

| | mem0 Dream | SMRITI badha |
|---|---|---|
| When | Supersede/merge at add; synthesis weekly (Pro) / daily (Enterprise), off the request path | At write, in the main path, every plan (there is one plan: Apache-2.0) |
| Cost | Synthesis gated behind $249/mo Pro | Deterministic `(subject, predicate)` supersession = 0 tokens |
| Visibility | `latest_only=true` flag; superseded badged | Validity window printed *into the context* with dates; CURRENT-first ordering |
| Where it runs | Their cloud | Your file |

Their own blog states the problem plainly: "the median active project carries a few hundred memories that duplicate or contradict other memories." That is the failure mode I designed around from day one.

**Caveat.** Update the README: the line "knowledge updates leave stale facts competing with fresh ones" about mem0 is now partially outdated. Say so before they do.

### A5. "GBrain: Garry Tan, ~20k stars, zero-LLM extraction, 146k pages in production. Why not just use that?"

**Core.** GBrain is a *personal brain for one operator* — markdown is the source of truth, you author the skills, the typed edges (`works_at`, `invested_in`) are regex/string rules. That is a great design for that operator. It is not an embeddable memory *library*:
- Needs Postgres + pgvector (PGLite WASM for local), Bun, and OpenClaw/Hermes as the agent.
- No as-of-date validity model — pages have "compiled truth + timeline", which is human-readable history, not machine-queryable validity windows.
- Its published retrieval numbers are on its own 240-page BrainBench (P@5 49.1%, R@5 97.9%) and LongMemEval **R@5** — retrieval recall, not answer accuracy.

What I took from it: zero-LLM wiring is right for the common case — my `(subject, predicate)` supersession is the same instinct applied to time.

### A6. "Hindsight holds SOTA on BEAM 10M (64.1%) and posts 94.6% on LongMemEval, with 40+ integrations. Isn't that the serious product here?"

**Core.** Yes — for multi-tenant, service-shaped memory, Hindsight is the serious product and I say so in the README's honesty section. My scale envelope explicitly says "not yet suited to multi-million-row, high-concurrency multi-tenant serving." I do not compete for that buyer.

The design kinship is real: Hindsight's TEMPR (semantic + BM25 + graph + temporal, RRF, cross-encoder) and SMRITI's four channels + RRF + optional reranker are the same architecture. Their observation/mental-model paradigm is what I adapted as the observation stack — and then *measured* that observations must be recall-profile-only, or they launder stale values (A2).

Difference in one line: Hindsight is memory-as-a-service (Postgres, Docker/Helm, managed cloud). SMRITI is memory-as-a-file. Different operator, different threat model, different cost curve.

**Caveat.** Note: the landscape page in this repo says Hindsight was "misidentified" — that is wrong. Hindsight is Vectorize's product (MIT, Dec 2025, ~12.8k stars). Fix the page.

### A7. "Graphify?"

Different category. Graphify (Karpathy's `/raw` folder workflow) builds a deterministic knowledge graph *over a folder of files* — codebases, papers, notes — for structure queries and GraphRAG export. It is not a conversational memory layer with a write path. The idea worth crediting: every edge tagged EXTRACTED / INFERRED / AMBIGUOUS — an honest audit trail. That is the same instinct as SMRITI's provenance-rich packing and "enumerate, don't assert."

### A8. "Zep / Graphiti has the bi-temporal model already."

Right model, wrong infrastructure. Zep's LongMemEval number (71.2%, GPT-4o) and ~1.6k tokens/retrieval show the temporal graph works and is token-efficient — but it requires Neo4j, the community edition is deprecated, and advanced features are cloud-only. SMRITI's synthesis line: *keep Zep's temporal model and GBrain's entity graph, drop the database tax; keep mem0's extraction discipline, add supersession.*

### A9. "Why one SQLite file? Isn't that a toy?"

**Core.** SQLite is the most deployed database in the world (every phone, browser, plane) because it has no server. The file *is* the security boundary, the backup unit, the migration unit, and the tenancy unit: one agent, one file. Zero-infra is not a limitation for the target workloads; it is the reason those workloads can have memory at all.

**Numbers (measured, `bench/scale.py`, 256-dim, external agent run).** Warm query 3.2 ms at 12.5k rows, 29.4 ms at 125k, 78.4 ms at 312k; ~50k rows/sec ingest; needle retrieval correct at every size. WAL + busy-timeout; six real parallel connections on a cold file pass the concurrency tests.

**Caveat.** The vector channel is an exact O(N) numpy scan. Roadmap #2 is int8/binary quantization in pure numpy (10–30× headroom, zero new deps; Mnemosyne's MIB result re-derived on my principles), then `sqlite-vec` as the optional ANN tier. That is on the 30-day list.

### A10. (Shyamal / Soumyadeep) "Your significance is p=0.046 on n=78 and p≈0.095 on n=200. Convince me this isn't noise."

**Core.** Say the exact things: McNemar on discordant pairs (paired design, same questions, only the feature flag differs); 29 discordant of 200, 19 helped / 10 hurt; z≈1.67. I wrote "very likely real, not yet proven" in BENCHMARKS.md and refused to round up. The routed result on the multi-session slice is the one that cleared 0.05.

Also name the weaknesses of the protocol before they do: LLM-as-judge (DeepSeek), oracle split, single seed, per-type n small, `single-session-preference` regressed −6.7 (open-ended, judge-sensitive). Then: *this is why the harness ships in the box and why the 30-day milestone is the full-haystack run under a fixed judge with the credits you are offering.*

### A11. "What did you learn that the incumbents' blog posts don't say?"

1. Recall and precision are different products. Summaries help "how many concerts" and hurt "what is my current mortgage." Route or pay the tax.
2. Annotation without ordering is not enough — the model anchors on the first fact it reads. Found by an external audit, fixed in 0.3.1.
3. Erasure must be a *different operation* from correction, and must not be reachable from untrusted content — `erase_*` is deliberately not exposed via MCP.
4. Idempotent, atomic ingestion matters more than any retrieval trick once agents retry.

### A12. "Why the Sanskrit? Isn't that branding?"

Two rules keep it honest: code stays English; no forced poetry — if a component has no honest Sanskrit fit it gets an English name. The terms earned their place because the classical meaning *is* the engineering meaning: **anubhava → samskara → smriti** (experience leaves impressions; recollection arises from impressions) is literally the write path and encodes the argument for retrieving over *both* facts and raw episodes. **Badha** (sublation — the snake is invalidated by seeing the rope, without erasing that the snake-cognition occurred) is supersession, precisely. It also says something true about where this is built: India worked out a technical vocabulary for memory two millennia before vector databases. Terry Winograd will enjoy this; do not lead with it for the VCs.

### A13. "Who uses it today?"

Be truthful. Shipped: 0.1.0 → 0.3.2 in July 2026, 85 offline tests, MCP server with six typed tools, two external agent-run audits that found real bugs (fixed and regression-tested), enterprise module (39 tests: tri-temporal as-of, lineage, receipts, retention/holds, verified packs), landing site, launch film. Not yet: PyPI release, full-haystack numbers, named external users. The residency is where the second list gets crossed off. Do not inflate.

### A14. "Is this a company or a library?"

**Core.** Today it is a kernel. The commercial shape (ROADMAP-ENTERPRISE.md v2) is: core stays Apache-2.0, everything included; monetise *operational assurance* for teams that must run memory inside their own boundary — regulated deployment profiles, signed releases/SBOM, LTS, evidence-review, and a served profile only if ≥2 design partners pull for it. Price per deployment, not per seat. The wedge nobody else occupies: an **embedded, offline-capable kernel whose temporal state and retrieval evidence are legible enough to verify** — receipts binding the exact packed-context digest.

**Caveat.** I would rather say "I don't know if this is a venture-scale company yet; I know it is a correct component, and the residency's job is to find the first three teams who need it badly" than pitch a TAM.

### A15. "What would make you wrong?"

- If a same-judge full-haystack run shows SMRITI >15 points behind mem0-OSS on knowledge-update or temporal reasoning, the "quality per cost" claim fails for anything but toy workloads.
- If quantization cannot get sub-100 ms at 1M rows, the envelope is a ceiling not a tier.
- If no on-device / edge / regulated team wants memory-as-a-file after 30 days of asking, the ownership thesis is wrong.

Having kill criteria is the strongest signal of seriousness you can give an evals person and a VC in the same sentence.

---

## 3. Section B — The 30 days: what I will do for the product and the reach

### B1. The one measurable milestone (their application Q8; say it verbatim)

> **By 15 October I will publish the first same-protocol comparison of agent memory systems — SMRITI vs mem0 (OSS) vs Zep/Graphiti — on full-haystack LongMemEval_S and LoCoMo, with one fixed judge, one fixed reader, and cost per correct answer (tokens, dollars, infrastructure) reported alongside accuracy. Every run reproducible from `bench/` with one command. Target: SMRITI within 10 points of the best open system on overall accuracy at ≤¼ the tokens per answer and zero infrastructure — or I publish the loss.**

Supporting deliverables that make it real:

| # | Deliverable | Why | Proof at Demo Day |
|---|---|---|---|
| 1 | Full-haystack LongMemEval_S + LoCoMo, fixed judge, lite and full modes | Removes the "oracle split" caveat forever | Per-type table + JSONL, live |
| 2 | mem0-OSS and Graphiti adapters in `bench/` | Same judge, same reader, same split | One command runs all three |
| 3 | **Cost-per-correct-answer** metric in the harness | Turns "quality per rupee" from a slogan into a chart | The chart |
| 4 | int8 / binary quantization (pure numpy) | Lifts envelope from ~300k to ~1M+ rows, no new deps | `bench/scale.py` before/after |
| 5 | PyPI release `smriti-agents` 0.4.0 | Removes install friction | `pip install smriti-agents` on stage |
| 6 | Adapters: Claude Code, Cursor, Hermes/OpenClaw | Where agents actually run | Live memory across a session |
| 7 | 3–5 design-partner conversations (on-device / edge / regulated) | Tests the ownership thesis | Named or anonymised learnings |

### B2. Week by week

- **Week 1 (15–21 Sep): protocol before results.** Freeze judge, reader, splits, prompts; write the protocol doc *first* and ask Shyamal/Soumyadeep to tear it apart. Build mem0-OSS and Graphiti adapters. Start quantization branch. PyPI dry run.
- **Week 2 (22–28 Sep): run everything.** Full-haystack runs on Anthropic/Fireworks credits (this is what the $10k Anthropic credit is for — a frontier judge over ~3–4k question-runs). Publish interim per-type tables, including losses. Quantization A/B gated on recall.
- **Week 3 (29 Sep–5 Oct): fix what the numbers say.** Most likely temporal-reasoning and multi-session on the hard split. Ship 0.4.0. Land the three adapters. Second round of external audit (the same agent-run audit process that caught the 0.3.0 bugs).
- **Week 4 (6–15 Oct): make it legible.** Cost-per-correct-answer chart, reproducibility README, one-command repro of the entire comparison. Show HN / X launch with the launch film. Demo Day artifact: live A/B on stage with a running cost meter.

### B3. Reach — how the work travels

- **Distribution through agents, not marketing:** MCP is already there; Hermes/OpenClaw/Claude Code/Cursor adapters put SMRITI where the agents live. GBrain's two-agent coupling shows why adapters are the growth loop.
- **The comparison is the content.** Nobody has published a same-judge, cost-included comparison across memory systems. That post writes itself and is defensible because everything reproduces.
- **The cohort is the first market.** Robotics and hardware residents have agents that must remember without a cloud round-trip. Offer to be the memory layer for two of their demos. Ask Atharva/Markov what an on-robot memory needs.
- **Design partners via mentors:** Abhishek (Cloudflare — SQLite at the edge), Div (AGI Inc — long-running agents), Hemant/Harshita (intros to portfolio companies running agents on-prem).
- **India-built, on purpose.** The nomenclature is not decoration; it is a claim about where foundational AI infrastructure can come from. That is Variance's thesis too.

### B4. How I will use the credits (be specific — they asked)

Anthropic $10k → fixed-judge runs (judge is the expensive part: ~3 systems × 2 benchmarks × 2 modes × ~1,000 questions). Fireworks/others → cheap open-weight readers so the comparison is not frontier-model-flattered. AWS/Azure → the one place I *do* need infrastructure: standing up mem0's Postgres+Qdrant and Zep's Neo4j so the cost comparison includes their real infra bill.

---

## 4. Section C — What I want out of this residency (say this clearly when asked)

1. **A month of undistracted, full-time work on one milestone** — the full-protocol comparison — in a room where "show what changed" is the norm.
2. **Evaluation rigor from people who have done it at the frontier.** Fifteen minutes of Shyamal Anadkat or Soumyadeep Bakshi tearing apart my protocol *before* I run it is worth more than any compute.
3. **Compute I cannot otherwise afford for the judge runs.** ~$10k of frontier-judge inference is the gate between "oracle-split delta" and "publishable number."
4. **My first three design partners** for memory-as-a-file: one edge/robotics, one coding-agent, one regulated/on-prem. Introductions through mentors and the cohort.
5. **Pressure-testing the company question** with Hemant, Harshita, Rajeev, Danielle: is a verifiable embedded kernel a venture business, an open-core support business, or a component that should be donated to a larger project? I want a real answer, not encouragement.
6. **Peers who build hard things without a server.** A robotics founder who has to make memory work on a Jetson will see problems in SMRITI that no web developer will.
7. **A public artifact by 16 October** — the comparison and the 0.4.0 release — that makes SMRITI the reference point for "cheap, honest, verifiable agent memory" in the same way the harness is already the reference point for "run it yourself."

What I am *not* asking for: equity discussions, a pivot to hosted memory, or a polished pitch. The house is for the work.

---

## 5. Section D — Questions to ask them

1. Of the 14 residents, how many are software/AI infra vs hardware? How do you make the software people useful to the hardware people?
2. How do mentor sessions actually work — office hours, or pulled in when a resident is blocked? Can I book Shyamal in week 1, before I run anything?
3. What did the World Models hackathons teach you about what a 30-day sprint can and cannot produce?
4. Is there appetite among the robotics residents for an on-device memory layer? Can I run a mini-workshop in the house?
5. What does a *bad* Demo Day look like to you? (Their answer tells you exactly what they are grading.)
6. After 16 October — what does The Residency do with the cohort?

---

## 6. Section E — Traps, cheat sheet, and repo fixes before the interview

### Do not say
- "We beat mem0." You have not run the same protocol. Say "on quality per cost for these workloads, and I'll have the same-judge numbers by 15 Oct."
- "Facts are never lost." Say "corrections are never lost; erasure is a separate, owner-initiated operation."
- "Compliance-ready" or "tamper-proof." The enterprise docs deliberately say "produces evidence supporting a customer's governance implementation" and "checksummed unless customer-key signed."
- "It scales." Say the envelope: excellent to tens of thousands, acceptable to low hundreds of thousands, not yet multi-million multi-tenant.
- The "~49% at 50k sessions" decay figure from the landscape page unless you can cite it live; use mem0's own Dream blog line about "a few hundred duplicating or contradicting memories per median project" instead.

### Numbers to have cold

| Item | Value | Source |
|---|---|---|
| Core size / deps / tests | ~2.5k lines · stdlib + numpy · 85 offline tests (+39 enterprise) | repo |
| Tokens per answer | ~1,600 | BENCHMARKS / README |
| Cost of 500-question frontier reader+judge run | ~$2.50 | README |
| Multi-session lift (routed) | 0.359 → 0.462, +10.3, McNemar p=0.046, n=78 | BENCHMARKS.md |
| Knowledge-update after routing | 0.833 → 0.846 (+1.3; was −5.1) | BENCHMARKS.md |
| Observation stack, n=200 | overall +4.8 (p≈0.095); temporal-reasoning +17.6; preference −6.7 | BENCHMARKS.md |
| Oracle overall / per type (n=300, full) | 68.7% · SS-user 94.4 · SS-asst 74.1 · SS-pref 36.7 · KU 79.6 · TR 74.1 · MS 38.9 | landscape page |
| Scale (256-dim) | 3.2 ms @ 12.5k · 29.4 ms @ 125k · 78.4 ms @ 312k rows · ~50k rows/s ingest | BENCHMARKS.md |
| Full-context baseline | 60.2% LongMemEval, GPT-4o | LongMemEval / Zep report |
| mem0 | self-reported 93.4–94.4% LME; independent 49.0% (vectorize.io, Mar 2026); ~6.9k tokens/retrieval; graph + Dream synthesis behind $249/mo Pro; self-host = Docker + Postgres + Qdrant | mem0 blog/docs, third-party |
| Zep/Graphiti | 71.2% LME (GPT-4o); ~1.6k tokens; Neo4j; community edition deprecated | Zep report, third-party |
| GBrain | released 5 Apr 2026; ~14–21k stars; Postgres/pgvector or PGLite; zero-LLM typed edges; P@5 49.1 / R@5 97.9 on BrainBench | vectorize.io, viewport |
| Hindsight (Vectorize) | Dec 2025; ~12.8k stars; BEAM 10M 64.1% (SOTA); LME 94.6%; Postgres 14+; 40+ integrations | vectorize.io |

### Fix in the repo before they open it (30 minutes)
1. README honesty section cites "mem0's ~49%" as the vendor number — it is the *independent* number; mem0's own claim is 93–94%. Say both, attributed.
2. README's mem0 row ("knowledge updates leave stale facts competing") — add "(mem0 added background supersession via Dream in 2026; synthesis is Pro-tier)".
3. `smriti-landscape.html` "Hindsight misidentified" bullet is wrong — Hindsight is Vectorize's memory product. Remove the bullet.
4. Make sure `pip install -e . && pytest` is green on a clean machine the night before. They will try it.
