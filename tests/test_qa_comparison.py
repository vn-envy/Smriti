"""No-network checks for the matched public answer/judge wrapper."""

import json

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


def test_progress_checkpoint_is_running_and_includes_errors_cleanup(monkeypatch, tmp_path):
    monkeypatch.setattr(qa, "SmritiAdapter", _Adapter)
    _Adapter.instances = 0
    _Adapter.fail_first_add = True
    progress = tmp_path / "progress.json"
    result = qa.run_comparison(
        [_item("q1"), _item("q2_abs", qtype="adversarial", unanswerable=True)],
        b"dataset", "smriti", _Answer(["I don't have enough information"]),
        _Judge([]), sample=2, k=3, verbose=False, progress_path=progress,
    )
    checkpoint = json.loads(progress.read_text())
    assert checkpoint["status"] == "running"
    assert "summary" not in checkpoint
    assert checkpoint["progress"] == {
        "processed_questions": 2, "requested_questions": 2,
        "failed_questions": 1, "cleanup_failures": 0,
        "last_question_id": "q2_abs",
    }
    assert checkpoint["results"][0]["errors"][0]["stage"] == "ingest"
    assert len(checkpoint["cleanup"]) == 2
    assert all(row["ok"] for row in checkpoint["cleanup"])
    assert result["summary"]["accuracy"] == 0.5
    assert not list(tmp_path.glob("*.tmp"))


def test_progress_checkpoint_survives_interruption(monkeypatch, tmp_path):
    class Abort(BaseException):
        pass

    class InterruptingAnswer(_Answer):
        def complete(self, messages, max_tokens):
            raise Abort("stop after first question")

    monkeypatch.setattr(qa, "SmritiAdapter", _Adapter)
    _Adapter.instances = 0
    _Adapter.fail_first_add = False
    progress = tmp_path / "interrupted.json"
    try:
        qa.run_comparison(
            [_item("q1")], b"dataset", "smriti", InterruptingAnswer([]),
            _Judge([]), sample=1, k=1, verbose=False, progress_path=progress,
        )
    except Abort:
        pass
    else:
        raise AssertionError("test must interrupt the comparison")
    checkpoint = json.loads(progress.read_text())
    assert checkpoint["status"] == "running"
    assert checkpoint["progress"]["processed_questions"] == 1
    assert checkpoint["results"][0]["errors"][0]["stage"] == "interrupted"
    assert checkpoint["cleanup"][0]["ok"] is True


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


def test_locomo_sampling_covers_conversations_within_each_category():
    items = []
    for conversation in range(10):
        for category, unanswerable in (("1", False), ("2", False),
                                       ("3", False), ("4", False), ("5", True)):
            item = _item(f"c{conversation}-{category}", qtype=category,
                         unanswerable=unanswerable)
            item["sample_id"] = f"conversation-{conversation}"
            items.append(item)
    selected = qa.stratified_answerable_sample(items, 50)
    assert len({item["sample_id"] for item in selected}) == 10
    assert {item["question_type"] for item in selected} == {"1", "2", "3", "4", "5"}
    assert all(sum(item["question_type"] == category for item in selected) == 10
               for category in ("1", "2", "3", "4", "5"))


def test_locomo_rows_preserve_speakers_image_caption_and_date():
    data = [{
        "sample_id": "conversation-a",
        "conversation": {
            "session_1_date_time": "1:56 pm on 8 May, 2023",
            "session_1": [
                {"speaker": "Caroline", "text": "hello"},
                {"speaker": "Bob", "text": "a photo", "blip_caption": "a dog"},
            ],
        },
        "qa": [{"question": "What happened?", "answer": "hello", "category": 4}],
    }]
    item = qa._locomo_questions(data, 1000, 1000)[0]
    assert item["question_id"] == "conversation-a-q0"
    assert item["rows"][0]["timestamp"] == "2023-05-08T00:00:00Z"
    assert item["rows"][0]["text"] == "Caroline: hello\nBob: a photo [shared an image: a dog]"


def test_locomo_category5_gold_is_not_sent_to_reader(monkeypatch):
    monkeypatch.setattr(qa, "SmritiAdapter", _Adapter)
    _Adapter.instances = 0
    _Adapter.fail_first_add = False
    answer = _Answer(["I don't have enough information."])
    item = _item("conversation-a-q0", qtype="5", unanswerable=True)
    item["gold"] = "self-care is important"
    result = qa.run_comparison([item], b"dataset", "smriti", answer,
                               _Judge([]), sample=1, k=1, verbose=False)
    prompt = answer.prompts[0][1]["content"]
    assert "self-care is important" not in prompt
    assert result["results"][0]["unanswerable"] is True
    assert result["summary"]["abstention_requested"] == 1
    assert result["summary"]["abstention_correct"] == 1
    assert result["summary"]["source_count"] == 1
    assert result["selection"]["sample_ids"] == ["sample-1"]


def test_judge_sanity_retains_failed_raw_verdict():
    class BadJudge:
        extra_body = {"reasoning_effort": "none", "think": False}

        def complete(self, messages, max_tokens):
            return "maybe, with reasoning"

    sanity = qa.judge_sanity_check(BadJudge())
    assert sanity["status"] == "failed"
    assert sanity["checks"][0]["raw"] == "maybe, with reasoning"
    assert sanity["error"]["stage"] == "judge_sanity"
