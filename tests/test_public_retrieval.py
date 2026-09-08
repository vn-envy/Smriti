import json

import pytest

from bench import public_retrieval as public


def item(qid="q1", qtype="single-session-user", sid="s1"):
    return {
        "question_id": qid,
        "question_type": qtype,
        "question": "Where?",
        "answer": "here",
        "haystack_dates": ["2023/01/01 00:00"],
        "haystack_session_ids": [sid],
        "haystack_sessions": [[{"role": "user", "content": "The answer is here."}]],
        "answer_session_ids": [sid],
    }


def test_stratified_sample_is_stable_and_touches_each_type():
    data = [item(str(i), qtype) for i, qtype in enumerate(("a", "a", "b", "b", "c"))]
    selected = public.stratified_sample(data, 3)
    assert [row["question_id"] for row in selected] == ["0", "2", "4"]
    assert [row["question_id"] for row in public.stratified_sample(data, 3)] == ["0", "2", "4"]


def test_parallel_arrays_are_rejected_before_indexing():
    broken = item()
    broken["haystack_dates"] = []
    with pytest.raises(public.DatasetError, match="mismatched"):
        public.iter_index_rows(broken, 100, 20)


def test_chunks_bound_payload_and_keep_session_id_out_of_text():
    row = item()
    row["haystack_sessions"] = [[{"role": "user", "content": "x" * 45}]]
    rows, stats = public.iter_index_rows(row, 40, 20)
    assert [len(r["text"]) for r in rows] == [20, 20]
    assert all("s1" not in r["text"] for r in rows)
    # The shared payload includes the ``user: `` role prefix (6 chars).
    assert stats["truncated_session_chars"] == 11
    assert stats["chunk_count"] == 2


def test_score_uses_dataset_labels_and_unique_session_mapping():
    score = public.score_retrieval(["wrong", "s1", "s1"], ["s1", "s2"], 5)
    assert score["returned"] == ["wrong", "s1"]
    assert score["relevant"] == ["s1", "s2"]
    assert score["recall_at_k"] == 0.5
    assert score["reciprocal_rank"] == 0.5


def test_abs_questions_use_separate_abstention_metric():
    score = public.score_retrieval(["evidence-session"], ["evidence-session"], 5,
                                   unanswerable=True)
    assert score["unanswerable"] is True
    assert score["relevant"] == []
    assert score["recall_at_k"] is None
    assert score["empty_retrieval_success"] is False
    assert public.is_unanswerable_item({"question_id": "gpt4_123_abs"}) is True


def test_mem0_config_isolated_and_uses_shared_ollama_endpoint(tmp_path):
    original = {
        "history_db_path": "/old/history.db",
        "embedder": {"provider": "ollama", "config": {"model": "nomic-embed-text:v1.5", "ollama_base_url": "old"}},
        "vector_store": {"provider": "qdrant", "config": {"path": "/old/qdrant", "collection_name": "old"}},
    }
    patched = public._patch_mem0_config(original, str(tmp_path), "http://127.0.0.1:11436")
    assert patched["history_db_path"] == str(tmp_path / "history.db")
    assert patched["vector_store"]["config"]["path"] == str(tmp_path / "qdrant")
    assert patched["vector_store"]["config"]["collection_name"].startswith("lme_")
    assert patched["embedder"]["config"]["ollama_base_url"] == "http://127.0.0.1:11436"
    assert original["history_db_path"] == "/old/history.db"


def test_run_keeps_failures_in_denominator_and_closes_adapter(monkeypatch, tmp_path):
    first = item("ok", "a", "session-ok")
    bad = item("bad", "b", "session-bad")
    bad["haystack_dates"] = []
    closed = []

    class FakeAdapter:
        def __init__(self, embedder):
            self.rows = []

        def add(self, row):
            self.rows.append(row)

        def search(self, query, k):
            return [self.rows[0]["session_id"]]

        def close(self):
            closed.append(True)

    monkeypatch.setattr(public, "SmritiAdapter", FakeAdapter)
    raw = json.dumps([first, bad]).encode()
    result = public.run([first, bad], raw, "smriti", sample=2, k=5,
                        embed_model=public.DEFAULT_EMBED_MODEL,
                        base_url="http://localhost", session_char_budget=100,
                        chunk_char_budget=50, temp_root=str(tmp_path), verbose=False)
    assert result["status"] == "partial"
    assert result["summary"]["requested"] == 2
    assert result["summary"]["completed"] == 1
    assert result["summary"]["failures"] == 1
    assert result["summary"]["failure_inclusive_denominator"] == 2
    assert result["summary"]["mean_recall_at_k"] == 0.5
    assert closed == [True]


def test_run_records_the_adapter_row_that_failed(monkeypatch, tmp_path):
    candidate = item("q-fail", "a", "session-first")
    candidate["haystack_sessions"].append([{"role": "assistant", "content": "second"}])
    candidate["haystack_dates"].append("2023/01/02 00:00")
    candidate["haystack_session_ids"].append("session-second")

    class FailingAdapter:
        def __init__(self, embedder):
            self.rows = []

        def add(self, row):
            if row["session_id"] == "session-second":
                raise ValueError("context limit")
            self.rows.append(row)

        def search(self, query, k):
            return [self.rows[0]["session_id"]]

        def close(self):
            pass

    monkeypatch.setattr(public, "SmritiAdapter", FailingAdapter)
    result = public.run([candidate], json.dumps([candidate]).encode(), "smriti",
                        sample=1, k=5, embed_model=public.DEFAULT_EMBED_MODEL,
                        base_url="http://localhost", session_char_budget=100,
                        chunk_char_budget=50, temp_root=str(tmp_path), verbose=False)
    assert result["failure_records"][0]["failed_row"] == {
        "session_id": "session-second", "chunk_index": 0, "text_chars": 17}


def test_oracle_filename_is_rejected(tmp_path):
    path = tmp_path / "longmemeval_oracle.json"
    path.write_text("[]")
    with pytest.raises(public.DatasetError, match="oracle"):
        public.load_dataset(str(path))
