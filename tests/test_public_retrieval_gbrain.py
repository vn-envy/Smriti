from bench.public_retrieval_gbrain import _score_hits
from bench import public_retrieval_gbrain as gbrain


def test_gbrain_lexical_score_maps_opaque_documents_to_sessions():
    hits = [
        {"document_slug": "bench/public-a", "session_id": "s1", "score": 2.0},
        {"document_slug": "bench/public-b", "session_id": "s1", "score": 1.0},
        {"document_slug": "bench/public-c", "session_id": "s2", "score": 0.5},
    ]
    score = _score_hits(hits, ["s1", "s2"], False)
    assert score["returned_session_ids"] == ["s1", "s2"]
    assert score["recall_at_k"] == 1.0
    assert score["reciprocal_rank"] == 1.0


def test_gbrain_abs_scoring_does_not_use_answer_labels():
    score = _score_hits(
        [{"document_slug": "bench/public-a", "session_id": "s1", "score": 1.0}],
        ["s1"], True,
    )
    assert score["relevant_session_ids"] == []
    assert score["recall_at_k"] is None


def test_gbrain_run_validates_budgets_before_starting_worker():
    try:
        gbrain.run([], b"", sample=1, k=0, session_char_budget=100,
                   chunk_char_budget=20)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("invalid k must fail before any worker starts")
