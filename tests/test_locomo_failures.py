"""Failure accounting and cleanup tests for the LoCoMo evaluation gate."""

import json

from bench.locomo import run_locomo


def _data(question_count=2):
    qa = [
        {"question": f"question {i}", "answer": "gold", "category": 1}
        for i in range(question_count)
    ]
    return [{
        "sample_id": "sample-explicit",
        "conversation": {
            "session_1": [{"speaker": "Mira", "text": "A note."}],
            "session_1_date_time": "1:00 pm on 8 May, 2023",
        },
        "qa": qa,
    }]


class _Memory:
    def __init__(self, fail_add=False, fail_close=False, fail_context=False):
        self.llm = None
        self.fail_add = fail_add
        self.fail_close = fail_close
        self.fail_context = fail_context
        self.closed = False

    def add(self, turns, session_id, timestamp):
        if self.fail_add:
            raise RuntimeError("ingest exploded")

    def context(self, question, k, char_budget):
        if self.fail_context:
            raise RuntimeError("retrieval exploded")
        return "memory"

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError("close exploded")


class _Answer:
    model = "answer-model"
    base_url = "http://localhost:11434/v1"

    def __init__(self, failures=()):
        self.failures = set(failures)
        self.calls = 0

    def complete(self, messages, max_tokens):
        call = self.calls
        self.calls += 1
        if call in self.failures:
            raise RuntimeError(f"answer failed {call}")
        return "hypothesis"


class _Judge:
    model = "judge-model"
    base_url = "http://localhost:11434/v1"

    def __init__(self, failures=()):
        self.failures = set(failures)
        self.calls = 0

    def complete(self, messages, max_tokens):
        call = self.calls
        self.calls += 1
        if call in self.failures:
            raise RuntimeError(f"judge failed {call}")
        return "yes"


def test_ingest_failure_keeps_each_selected_question_in_denominator_and_closes():
    memories = []

    def factory():
        mem = _Memory(fail_add=True)
        memories.append(mem)
        return mem

    out_path = "/private/tmp/locomo-failure-test.json"
    summary = run_locomo(_data(), _Answer(), _Judge(), factory,
                         verbose=False, out_path=out_path)
    report = json.load(open(out_path))
    assert summary["n"] == summary["selected_n"] == 2
    assert summary["errors"] == 2 and summary["accuracy"] == 0.0
    assert all(r["error"]["stage"] == "ingest" for r in report["results"])
    assert all(r["question_id"].startswith("sample-explicit-") for r in report["results"])
    assert memories[0].closed
    assert report["selection"]["selected_question_ids"] == [
        "sample-explicit-q0", "sample-explicit-q1"
    ]


def test_answer_and_judge_failures_are_raw_and_counted_separately():
    answer = _Answer(failures={0})
    judge = _Judge(failures={0})
    summary = run_locomo(_data(), answer, judge, _Memory,
                         verbose=False)
    assert summary["n"] == summary["selected_n"] == 2
    assert summary["errors"] == 2

    def factory():
        return _Memory()

    # Re-run to inspect each raw stage without relying on console output.
    report_path = "/private/tmp/locomo-answer-judge-failure.json"
    run_locomo(_data(), _Answer(failures={0}), _Judge(failures={0}),
               factory, verbose=False, out_path=report_path)
    captured = json.load(open(report_path))["results"]
    assert captured[0]["error"]["stage"] == "answer"
    assert captured[1]["error"]["stage"] == "judge"
    assert captured[1]["hypothesis"] == "hypothesis"
    assert all("traceback" in row["error"] for row in captured)


def test_cleanup_failure_is_reported_after_successful_question():
    mem = _Memory(fail_close=True)
    summary = run_locomo(_data(question_count=1), _Answer(), _Judge(),
                         lambda: mem, verbose=False)
    assert summary["n"] == 1 and summary["errors"] == 0
    assert summary["cleanup_errors"] == 1 and mem.closed


def test_retrieval_failure_has_its_own_stage():
    report_path = "/private/tmp/locomo-retrieval-failure.json"
    summary = run_locomo(_data(question_count=1), _Answer(), _Judge(),
                         lambda: _Memory(fail_context=True), verbose=False,
                         out_path=report_path)
    assert summary["n"] == summary["selected_n"] == 1
    assert summary["errors"] == 1
    assert json.load(open(report_path))["results"][0]["error"]["stage"] == "retrieval"
