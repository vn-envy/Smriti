"""LLM-as-judge — *nyaya* (न्याय, the school of logic and right judgment).

Follows the LongMemEval evaluation protocol:
binary correct/incorrect against the gold answer, with special handling
for abstention — *mauna* (मौन, knowing when silence is the right answer) —
on questions (ids ending in "_abs" must be declined)."""
from __future__ import annotations

import re

JUDGE_SYSTEM = """You are grading a memory-augmented assistant. Given a question, the gold answer, and the assistant's response, decide whether the response is correct.
- The response is correct if it contains the gold answer's key information, even with extra wording.
- Numeric/date answers must match in substance.
- Output ONLY "yes" or "no"."""

ABSTAIN_MARKERS = [
    "don't have", "do not have", "no information", "not enough information",
    "i don't know", "i do not know", "wasn't mentioned", "was not mentioned",
    "no record", "cannot find", "can't find", "never mentioned", "unable to find",
    "not mentioned", "no memory of",
]


def is_abstention(response: str) -> bool:
    r = response.lower()
    return any(m in r for m in ABSTAIN_MARKERS)


def judge(judge_llm, question: str, gold: str, hypothesis: str,
          question_id: str = "") -> bool:
    if question_id.endswith("_abs"):
        return is_abstention(hypothesis)
    prompt = (f"Question: {question}\n"
              f"Gold answer: {gold}\n"
              f"Assistant response: {hypothesis}\n"
              f"Correct?")
    raw = judge_llm.complete(
        [{"role": "system", "content": JUDGE_SYSTEM},
         {"role": "user", "content": prompt}],
        max_tokens=8,
    )
    return bool(re.search(r"\byes\b", raw.lower()))
