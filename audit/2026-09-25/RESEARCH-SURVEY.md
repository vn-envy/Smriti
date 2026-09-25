# Agent-memory research survey — what moves LongMemEval / LoCoMo (September 2026)

Compiled 2026-09-25 to choose the next Smriti experiments. **Sourcing caveat:**
the survey environment could not reach arXiv full texts, Hugging Face or most
vendor blogs; figures below come from search-result snippets and GitHub READMEs.
Treat every number as *reported*, and verify it before citing externally.

Labels: **S** = self-reported by the system's authors/vendor, **C** = run by a
competitor, **I** = independent. LongMemEval's official judge is GPT-4o;
vendors usually keep the judge and swap the reader. LoCoMo "J" scores mostly
come from Mem0's harness (gpt-4o-mini judge), which a public audit found
accepts many wrong-but-on-topic answers; ~6% of the LoCoMo answer key has
also been reported wrong. Cross-system comparisons with different readers and
judges are not like-for-like.

## Landscape

| System | Core idea | Reported results (reader) | LLM-free at query time? |
|---|---|---|---|
| LongMemEval paper (Wu et al., ICLR 2025) | Round-level keys, fact-augmented key expansion, time-aware query expansion, Chain-of-Note reading | Up to +11.4% temporal recall from time windows; +4% recall / +5% QA from fact keys; weak reading costs up to 10 pts even with perfect retrieval | Granularity + time windows: yes |
| Mem0 / Mem0g (2025) | LLM extraction with ADD/UPDATE/DELETE; optional graph | LoCoMo J 66.9 / 68.4 (gpt-4o-mini) S; full-context 72.9 in the same paper | Extraction needs an LLM |
| Mem0 "token-efficient" algorithm (2026) | Add-only extraction; semantic + lemmatized BM25 + entity fusion; LLM-free temporal intent; recency multiplier | LongMemEval 94.4 (top-200), LoCoMo 92.5, ~7K context tokens S | Query side yes |
| Zep / Graphiti | Bi-temporal knowledge graph; cosine + BM25 + BFS; RRF/MMR/cross-encoder rerankers | LongMemEval-S 71.2 (GPT-4o), 63.8 (4o-mini) S | Graph construction needs an LLM |
| Letta (MemGPT) | Agent-managed memory blocks, sleep-time agents | LoCoMo 74.0 with a filesystem + grep agent (4o-mini) S | No |
| Hindsight (Vectorize) | Four memory networks; semantic + BM25 + spreading activation + parsed-date filter, RRF, MiniLM cross-encoder with dates | LongMemEval-S 91.4 (Gemini-3 Pro), 83.6 (OSS-20B); LoCoMo 89.6 S | Retrieval almost LLM-free |
| Mastra Observational Memory | Observer/Reflector agents keep a dated observation log in context; no retrieval | 94.87 (gpt-5-mini), 84.23 (GPT-4o); its RAG baseline 80.05 mostly from timestamps + question date S | No |
| Supermemory | Atomic memories with document and event timestamps; typed update links | 81.6 (GPT-4o) – 85.2 (Gemini-3) S | Write-time LLM |
| Emergence AI | Match turns, retrieve sessions scored by NDCG of reranked turns, neighbour expansion | 82.4 "simple" (GPT-4o) S | Yes apart from the reader |
| MemMachine | Raw episodes + neighbour expansion | LongMemEval-S 93.0; depth +4.2, formatting +2.0, "user:" query prefix +1.4 in ablation S | Mostly |
| SmartSearch | Deterministic NER-weighted recall + cross-encoder/ColBERT fusion | LongMemEval-S 88.4, LoCoMo 93.5 S; **recall 98.6% but only 22.5% of gold evidence survived truncation without good ranking** | Yes |
| opsem / Nano-Memory / AgentIR / EdgeMem | BM25 + per-turn max-sim fusion; session = max over turns; skip dense when BM25 is confident; LLM-free hypergraph | e.g. LoCoMo Hit@1 fused 0.752 vs BM25 0.640; an off-the-shelf cross-encoder *lowered* Hit@1 by 6.9 S | Yes |
| EverMemOS / MemOS / Chronos / Agent Zero Memory | MemCells & scenes; memory-OS; event calendars with resolved date ranges | EverMemOS LoCoMo 93.05 (4.1-mini); Chronos 92.6 (GPT-4o); AZM 95.6 LME S | No (date-range idea is portable) |
| Nemori, SeCom, RMM, TiMem, LightMem, A-Mem, MIRIX, Memobase, LangMem | Episode segmentation, topic segments, RL rerankers, temporal trees, compression, Zettelkasten notes, multi-agent memory types, profile slots | LoCoMo 48–85, LongMemEval 64–77 across reports S/C | Mostly need a write-time LLM |
| HippoRAG 2 / RAPTOR | KG + Personalized PageRank; cluster-summary trees | Strong on multi-hop QA; tend to lose fine conversational detail | PPR cheap; construction needs NER/LLM |

Independent cross-system studies found no architecture that wins everywhere;
reader strength moves scores 3–10 points on its own, and whether retrieval
credit goes to raw turns or derived facts changes rankings substantially.

## What consistently moves scores

1. Reader strength (and reading strategy).
2. Turn-level matching delivered with session context or neighbouring turns.
3. **Dates everywhere**: question date, session headers, resolved relative
   dates, date-window priors.
4. **Packing quality**: supporting evidence must actually survive into the
   final context — the SmartSearch "22.5% survival" finding.
5. Retrieval depth and coverage for multi-session / aggregation questions.

## Techniques ranked for Smriti (LLM-free, testable offline)

| # | Technique | Status in this change |
|---|---|---|
| 1 | Evidence-first, budget-adaptive packing; group by dated session, chronological | **Shipped** (`smriti/recall.py`) |
| 2 | Turn → session score roll-up | **Shipped** (`session_weight`) |
| 3 | Neighbour-turn windows | Implemented; budget is usually consumed by direct hits first (neutral in the lab) |
| 4 | Rule-based time handling: question date, resolved relative dates, soft window prior | **Shipped** (`smriti/temporal.py`, `time_boost`, `when_boost`) |
| 5 | Aggregation coverage caps | Tested; per-session caps hurt slightly, left off |
| 6 | Score-level (convex) fusion instead of RRF | **Shipped** — convex beat RRF on LoCoMo by 8 pts r@5; RRF was slightly better on LME-X |
| 7 | Knowledge-update ordering | Chronological sessions + "most recent statement wins" header |
| 8 | User-turn bias | **Shipped** (`assistant_prior`, lifted when the question addresses the assistant) |
| 9 | Question-type cues | Partly: assistant-addressed, "when", ordering alternatives, speaker names |
| 10 | Cross-encoder reranking | Supported via any `.rerank()`; no local model reachable to evaluate here |
| 11 | Pseudo-relevance feedback | Tested; lowered recall, left off |
| 12 | Entity graph / PPR | Not attempted in this round |
| 13 | Contextual (neighbour-aware) turn embeddings | **Opt-in** (`contextual_embeddings`): +2.3–2.6 r@5 on LoCoMo, neutral on LME-X |

Sources named in the table: LongMemEval (arXiv 2410.10813), Mem0 (2504.19413),
Zep (2501.13956), Hindsight (2512.12818), MemMachine (2604.04853), SmartSearch
(2603.15599), opsem (2606.04194), Nano-Memory (2604.11628), AgentIR
(2605.25092), EdgeMem (2609.05553), EverMemOS (2601.02163), MemOS (2507.03724),
Chronos (2603.16862), Nemori (2508.03341), SeCom (2502.05589), HippoRAG 2
(2502.14802), RAPTOR (2401.18059), Bruch et al. TOIS 2023 on fusion
(2210.11934), plus vendor pages for Mem0, Mastra, Supermemory, Emergence,
Letta and Backboard.
