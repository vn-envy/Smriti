# Paired LongMemEval-S QA preflight (s6)

Exploratory six-question preflight only; no statistical significance or leaderboard interpretation.

- Same six selected IDs and budgets: **yes** (1,000-character chunks, 16,000-character sessions, k=5).
- Smriti: **4/6** failure-inclusive accuracy; Mem0: **3/6**.
- Answerable: Smriti **2/4**, Mem0 **1/4**.
- `_abs`: **2/2** heuristic `is_abstention` matches for both adapters; this is not Qwen judge scoring.
- Operational failures: **0/6** for both adapters.

| Question | Type | Smriti | Mem0 |
|---|---|---:|---:|
| `e47becba` | single-session-user | pass | pass |
| `0862e8bf_abs` | single-session-user | pass | pass |
| `0a995998` | multi-session | fail | fail |
| `88432d0a_abs` | multi-session | pass | pass |
| `8a2466db` | single-session-preference | fail | fail |
| `gpt4_59149c77` | temporal-reasoning | pass | fail |

Full questions, gold answers, reader hypotheses, retrieved contexts, judge outputs, token usage, and errors are preserved in the paired raw artifacts:
[public-qa-smriti-s6.json](public-qa-smriti-s6.json) and [public-qa-mem0-s6.json](public-qa-mem0-s6.json).
