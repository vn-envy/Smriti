from bench import public_retrieval_gbrain_semantic as semantic
from pathlib import Path
import pytest


def test_semantic_score_maps_opaque_documents_and_reports_mrr():
    hits = [
        {"document_slug": "bench/public-a", "session_id": "s1", "score": 2.0},
        {"document_slug": "bench/public-b", "session_id": "s1", "score": 1.0},
        {"document_slug": "bench/public-c", "session_id": "s2", "score": 0.5},
    ]
    score = semantic._score_hits(hits, ["s1", "s2"], False)
    assert score["returned_session_ids"] == ["s1", "s2"]
    assert score["recall_at_k"] == 1.0
    assert score["reciprocal_rank"] == 1.0


def test_semantic_abs_scoring_has_no_answerable_denominator():
    score = semantic._score_hits(
        [{"document_slug": "bench/public-a", "session_id": "s1", "score": 1.0}],
        ["s1"], True,
    )
    assert score["relevant_session_ids"] == []
    assert score["recall_at_k"] is None
    assert score["reciprocal_rank"] is None


def test_semantic_configuration_is_pinned_and_separate_from_lexical():
    assert semantic.DEFAULT_EMBED_MODEL == "ollama:nomic-embed-text:v1.5"
    assert semantic.DEFAULT_EMBED_DIMENSIONS == 768
    assert semantic.DEFAULT_OLLAMA_BASE_URL == "http://localhost:11436/v1"
    assert "semantic" in semantic.GbrainSemanticPersistent.label


def test_semantic_worker_has_real_embed_and_hybrid_fail_closed():
    worker_path = Path(semantic.__file__).with_name("gbrain_public_semantic_worker.ts")
    source = worker_path.read_text(encoding="utf-8")
    assert "importFromContent" in source
    assert "hybridSearch" in source
    assert "dimensionProbe" in source
    assert "meta?.vector_enabled !== true" in source
    assert "vector_arm_failed" in source
    assert "engine.getStats" in source
    assert "embedded_count" in source
    assert "queryEmbedFn:" not in source
    assert "queryEmbedFn =" not in source
    assert "noEmbed: true" not in source


def test_semantic_worker_supports_separate_analyze_maintenance_operation():
    worker_path = Path(semantic.__file__).with_name("gbrain_public_semantic_worker.ts")
    source = worker_path.read_text(encoding="utf-8")
    assert "op === 'analyze'" in source
    assert "engine.executeRaw('ANALYZE')" in source


def test_growth_semantic_adapter_batches_imports_and_requires_measured_nomic(monkeypatch):
    from bench import growth

    class FakeWorker:
        def __init__(self, **kwargs):
            assert kwargs["embed_model"] == "ollama:nomic-embed-text:v1.5"
            assert kwargs["embed_dimensions"] == 768
            self.root = "/tmp/fake-gbrain-semantic"
            self.db_path = self.root + "/db"
            self.startup_ms = 12.5
            self.ready_metadata = {
                "embedding_model": "ollama:nomic-embed-text:v1.5",
                "embedding_dimensions": 768,
                "measured_embedding_dimensions": 768,
                "ollama_base_url": "http://localhost:11436/v1",
            }
            self.page_count = 0
            self.requests = []

        def _request(self, message):
            self.requests.append(message)
            if message["op"] == "put_many":
                docs = message["documents"]
                self.page_count += len(docs)
                return {
                    "ok": True,
                    "imported": len(docs),
                    "skipped": 0,
                    "page_count": self.page_count,
                    "statuses": [{"id": d["id"], "status": "imported"} for d in docs],
                    "vector_stats": {"embedded_count": self.page_count, "chunk_count": self.page_count},
                }
            if message["op"] == "analyze":
                return {"ok": True, "maintenance_ms": 4.0}
            raise AssertionError(message)

        def _stop(self):
            return None

        def _start(self):
            return 13.0

        def close(self):
            return None

    monkeypatch.setattr(growth, "GbrainSemanticPersistent", FakeWorker)
    adapter = growth.GbrainSemanticGrowth()
    docs = [growth.doc(index) for index in range(205)]
    adapter.add_many(docs, expected_count=205)
    assert [len(request["documents"]) for request in adapter.worker.requests] == [100, 100, 5]
    assert len(adapter.last_batch_result["statuses"]) == 205
    assert adapter.effective_embedder["model"] == "nomic-embed-text:v1.5"
    assert adapter.effective_embedder["measured_embedding_dims"] == 768
    assert adapter.effective_embedder["endpoint"] == "http://localhost:11436"
    assert adapter.effective_embedder["endpoint_api_path"] == "/v1"
    assert adapter.local_cost_verified is True
    assert adapter.analyze() == 4.0


def test_growth_cost_is_unknown_for_non_loopback_ollama_endpoint():
    from bench import growth

    assert growth._is_verified_loopback_ollama("http://127.0.0.1:11436/v1") is True
    assert growth._is_verified_loopback_ollama("http://remote.example:11436/v1") is False


def test_growth_cli_exposes_separate_semantic_adapter():
    from pathlib import Path
    from bench import growth

    source = Path(growth.__file__).read_text(encoding="utf-8")
    assert '"gbrain-nomic"' in source
    assert "process-restart cold query; semantic hybrid search" in source


def test_growth_chart_labels_keep_gbrain_semantic_separate_from_smriti():
    from bench import growth_charts

    report = {
        "track": {
            "adapter": "gbrain-nomic",
            "kind": "semantic",
            "configuration": "gbrain semantic / Ollama nomic",
        }
    }
    assert growth_charts._label(report) == "GBrain semantic / Ollama nomic / PGLite"
    assert growth_charts._short_label(report) == "GBrain semantic"
    assert growth_charts.TRACK_COLORS["gbrain-nomic"] != growth_charts.TRACK_COLORS["smriti-nomic"]


def test_semantic_worker_no_response_hits_deadline_and_kills(tmp_path, monkeypatch):
    fake_bun = tmp_path / "fake-bun-no-response"
    fake_bun.write_text("#!/bin/sh\nexec python3 -c 'import time; time.sleep(2)'\n")
    fake_bun.chmod(0o755)
    monkeypatch.setenv("BUN_BIN", str(fake_bun))
    monkeypatch.setenv("GBRAIN_ROOT", str(tmp_path))
    with pytest.raises(TimeoutError, match="timed out"):
        semantic.GbrainSemanticPersistent(_request_timeout_s=0.05)


def test_semantic_worker_partial_line_and_large_stderr_hit_deadline(tmp_path, monkeypatch):
    fake_bun = tmp_path / "fake-bun-partial"
    fake_bun.write_text(
        "#!/bin/sh\n"
        "exec python3 -c 'import sys,time; sys.stderr.write(\"x\"*200000); sys.stderr.flush(); "
        "sys.stdout.write(\"{\\\"ok\\\":true\"); sys.stdout.flush(); time.sleep(2)'\n"
    )
    fake_bun.chmod(0o755)
    monkeypatch.setenv("BUN_BIN", str(fake_bun))
    monkeypatch.setenv("GBRAIN_ROOT", str(tmp_path))
    with pytest.raises(TimeoutError, match="timed out"):
        semantic.GbrainSemanticPersistent(_request_timeout_s=0.05)
