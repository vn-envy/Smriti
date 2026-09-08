from bench import public_retrieval_ablation as ablation
from types import SimpleNamespace


def _item(qid, qtype):
    return {
        "question_id": qid,
        "question_type": qtype,
        "question": "Where?",
        "haystack_dates": ["2024/01/01"],
        "haystack_session_ids": ["session-1"],
        "haystack_sessions": [[{"role": "user", "content": "A fact."}]],
        "answer_session_ids": ["session-1"],
    }


def test_heldout_sampler_excludes_prior_ids_and_is_stable():
    items = [_item(f"q{i}", "type-a" if i % 2 == 0 else "type-b") for i in range(6)]
    first = ablation.stratified_sample_excluding(items, 3, {"q0", "q1"})
    second = ablation.stratified_sample_excluding(items, 3, {"q0", "q1"})
    assert [item["question_id"] for item in first] == ["q2", "q3", "q4"]
    assert [item["question_id"] for item in second] == [item["question_id"] for item in first]


def test_score_hits_uses_opaque_episode_mapping_and_separates_abs():
    hits = [{"result_id": 9, "kind": "episode", "episode_id": 9,
             "session_id": "session-9", "score": 0.5},
            {"result_id": 10, "kind": "episode", "episode_id": 10,
             "session_id": "session-9", "score": 0.4}]
    score = ablation._score_hits(hits, ["session-9", "session-other"], False)
    assert score["returned_episode_ids"] == [9, 10]
    assert score["returned_session_ids"] == ["session-9"]
    assert score["covered_relevant_session_ids"] == ["session-9"]
    assert score["recall_at_k"] == 0.5
    absent = ablation._score_hits(hits, ["session-9"], True)
    assert absent["relevant_session_ids"] == []
    assert absent["recall_at_k"] is None


def test_run_reports_mrr_and_separates_cleanup_failures(monkeypatch):
    class FakeEmbedder:
        def __init__(self, model, base_url):
            pass

        def embed(self, texts):
            return [[0.0] * 768 for _ in texts]

    class FakeMemory:
        def __init__(self, **kwargs):
            self.store = self

        def add(self, messages, session_id, timestamp):
            pass

        def search(self, query, k, session_diverse=False, session_overfetch=3):
            return [SimpleNamespace(id=1, kind="episode", score=1.0)]

        def get_episode(self, result_id):
            return SimpleNamespace(session_id="session-1")

        def close(self):
            raise RuntimeError("cleanup failed")

    monkeypatch.setattr(ablation, "OllamaEmbedder", FakeEmbedder)
    monkeypatch.setattr(ablation, "Smriti", FakeMemory)
    data = [_item("q1", "type-a")]
    result = ablation.run_ablation(
        data, b"data", sample=1, k=1, session_char_budget=100,
        chunk_char_budget=20, overfetch=3,
        embed_model=ablation.DEFAULT_EMBED_MODEL,
        base_url="http://localhost", excluded_ids=set(),
        exclusion_sources=[], verbose=False)
    assert result["status"] == "partial"
    assert result["failure_records"] == []
    assert len(result["cleanup_failure_records"]) == 1
    assert result["summary"]["cleanup_failures"] == 1
    assert result["summary"]["default"]["mean_reciprocal_rank"] == 1.0
