"""No-network checks for the matched public answer/judge wrapper."""

import bench.qa_comparison as qa


class _Episode:
    def __init__(self, session_id, content, ts):
        self.session_id = session_id
        self.content = content
        self.ts = ts


class _Hit:
    def __init__(self, ident, text):
        self.id = ident
        self.text = text


class _Store:
    def __init__(self, hits, episodes):
        self.hits = hits
        self.episodes = episodes

    def get_episode(self, ident):
        return self.episodes.get(ident)


class _Adapter:
    instances = 0
    fail_first_add = False

    def __init__(self, embedder):
        self.index = type(self).instances
        type(self).instances += 1
        self.rows = []
        self.closed = False
        self.memory = self
        self.store = _Store([], {})

    def add(self, row):
        if self.fail_first_add and self.index == 0:
            raise RuntimeError("ingest failure")
        self.rows.append(row)

    def search(self, query, k=5):
        return self.store.hits[:k]

    def close(self):
        self.closed = True


class _Answer:
    model = "qwen3:8b"
    base_url = "http://127.0.0.1:11436/v1"
    calls = attempts = tokens_in = tokens_out = usage_missing = 0

    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    def complete(self, messages, max_tokens):
        self.prompts.append(messages)
        self.calls += 1
        return next(self.responses)


class _Judge(_Answer):
    def complete(self, messages, max_tokens):
        self.calls += 1
        return "yes"


def _item(qid="q1", qtype="single", unanswerable=False):
    return {"sample_id": "sample-1", "question_id": qid,
            "question_type": qtype, "question": "What happened?",
            "gold": "later", "unanswerable": unanswerable,
            "rows": [
                {"session_id": "answer_session_1", "timestamp": "2024-01-01",
                 "chunk_index": 0, "text": "old chunk"},
                {"session_id": "answer_session_1", "timestamp": "2024-02-02",
                 "chunk_index": 1, "text": "later chunk"},
            ]}


def test_context_uses_opaque_labels_and_exact_later_chunk(monkeypatch):
    adapter = _Adapter(None)
    adapter.store = _Store(
        [_Hit(2, "later chunk")],
        {2: _Episode("answer_session_1", "later chunk", "2024-02-02")},
    )
    monkeypatch.setattr(qa, "SmritiAdapter", _Adapter)
    _Adapter.instances = 0
    _Adapter.fail_first_add = False
    # The class instance created by run_comparison needs the injected hit.
    original_init = _Adapter.__init__
    def init_with_hit(self, embedder):
        original_init(self, embedder)
        self.store = adapter.store
    monkeypatch.setattr(_Adapter, "__init__", init_with_hit)

    answer = _Answer(["later"])
    result = qa.run_comparison([_item()], b"dataset", "smriti", answer,
                               _Judge([]), sample=1, k=1,
                               context_char_budget=60, verbose=False)
    prompt = answer.prompts[0][1]["content"]
    assert "answer_session_1" not in prompt
    assert "source-0001" in prompt and "2024-02-02" in prompt
    assert result["results"][0]["question"] == "What happened?"
    assert result["results"][0]["gold"] == "later"
    assert result["results"][0]["reader_context"] in prompt
    assert result["results"][0]["retrieved_rows"] == [{
        "source_label": "source-0001", "session_id": "answer_session_1",
        "chunk_index": 1, "timestamp": "2024-02-02", "match": "exact",
    }]


def test_failures_cleanup_and_abs_denominator_are_explicit(monkeypatch):
    monkeypatch.setattr(qa, "SmritiAdapter", _Adapter)
    _Adapter.instances = 0
    _Adapter.fail_first_add = True
    data = [_item("q1"), _item("q2_abs", qtype="adversarial", unanswerable=True)]
    result = qa.run_comparison(
        data, b"dataset", "smriti", _Answer(["I don't have enough information"]),
        _Judge([]), sample=2, k=3, session_char_budget=100,
        chunk_char_budget=40, context_char_budget=77, verbose=False,
    )
    assert result["summary"]["requested"] == 2
    assert result["summary"]["completed"] == 1
    assert result["summary"]["failures"] == 1
    assert result["summary"]["correct"] == 1
    assert result["summary"]["accuracy"] == 0.5
    assert result["results"][0]["errors"][0]["stage"] == "ingest"
    assert result["results"][1]["correct"] is True
    assert all(row["ok"] for row in result["cleanup"])
    assert result["provenance"]["budgets"]["context_char_budget"] == 77
    assert result["provenance"]["memory"]["mode"] == "lite"


def test_matched_route_rejects_invalid_budgets_and_embed_model():
    answer = _Answer(["answer"])
    judge = _Judge([])
    data = [_item()]
    try:
        qa.run_comparison(data, b"dataset", "smriti", answer, judge,
                          sample=1, k=0, verbose=False)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("non-positive k must be rejected")
    try:
        qa.run_comparison(data, b"dataset", "smriti", answer, judge,
                          sample=1, embed_model="other", verbose=False)
    except ValueError as exc:
        assert "embed model" in str(exc)
    else:
        raise AssertionError("unmatched embed model must be rejected")


def test_sampling_reserves_an_abstention_stratum_when_sample_allows():
    items = [_item("q1"), _item("q2"), _item("q3_abs", qtype="single", unanswerable=True)]
    selected = qa.stratified_answerable_sample(items, 2)
    assert [item["question_id"] for item in selected] == ["q1", "q3_abs"]


def test_judge_sanity_retains_failed_raw_verdict():
    class BadJudge:
        extra_body = {"reasoning_effort": "none", "think": False}

        def complete(self, messages, max_tokens):
            return "maybe, with reasoning"

    sanity = qa.judge_sanity_check(BadJudge())
    assert sanity["status"] == "failed"
    assert sanity["checks"][0]["raw"] == "maybe, with reasoning"
    assert sanity["error"]["stage"] == "judge_sanity"
