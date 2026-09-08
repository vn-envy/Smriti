import io
import json
import urllib.error

import pytest

import smriti.embedder as embedder_module
from smriti import HashEmbedder, MockLLM, Smriti


class ShortBatchEmbedder(HashEmbedder):
    def embed(self, texts):
        vectors = super().embed(texts)
        return vectors[:1]


class RepairableEmbedder(HashEmbedder):
    def __init__(self):
        super().__init__()
        self.short = True

    def embed(self, texts):
        vectors = super().embed(texts)
        return vectors[:1] if self.short else vectors


class ExtraVectorEmbedder(HashEmbedder):
    def embed(self, texts):
        return super().embed(texts) + [[0.0] * self.dim]


class NullVectorEmbedder(HashEmbedder):
    def embed(self, texts):
        return [None for _ in texts]


def test_episode_cardinality_failure_does_not_claim_ingest_and_retry_is_clean(tmp_path):
    path = str(tmp_path / "memory.db")
    embedder = RepairableEmbedder()
    broken = Smriti(path=path, embedder=embedder, mode="lite")
    messages = [{"role": "user", "content": "one"}, {"role": "user", "content": "two"}]
    with pytest.raises(ValueError, match="episode embedder returned 1 vectors for 2 texts"):
        broken.add(messages, session_id="s1", timestamp="2026-09-07T00:00:00Z")
    assert broken.stats()["episodes"] == 0
    assert broken.store.db.execute("SELECT count(*) FROM ingest_log").fetchone()[0] == 0
    embedder.short = False
    result = broken.add(messages, session_id="s1", timestamp="2026-09-07T00:00:00Z")
    assert result["episodes"] == 2
    broken.close()


def test_fact_batch_cardinality_failure_happens_before_transaction():
    extraction = json.dumps([
        {"statement": "The user likes tea.", "subject": "user", "predicate": "likes", "object": "tea"},
        {"statement": "The user likes coffee.", "subject": "user", "predicate": "likes", "object": "coffee"},
    ])
    mem = Smriti(path=":memory:", embedder=ShortBatchEmbedder(), llm=MockLLM([extraction]), mode="full")
    with pytest.raises(ValueError, match="fact embedder returned 1 vectors for 2 texts"):
        mem.add([{"role": "user", "content": "I like tea and coffee."}], session_id="s1")
    assert mem.stats()["episodes"] == 0
    assert mem.stats()["facts"] == 0


@pytest.mark.parametrize(
    ("bad_embedder", "message"),
    [
        (ExtraVectorEmbedder(), "episode embedder returned 3 vectors for 2 texts"),
        (NullVectorEmbedder(), "episode embedder returned a null vector"),
    ],
)
def test_extra_or_null_vectors_are_rejected_without_writes(bad_embedder, message):
    mem = Smriti(path=":memory:", embedder=bad_embedder, mode="lite")
    with pytest.raises(ValueError, match=message):
        mem.add([{"role": "user", "content": "one"}, {"role": "user", "content": "two"}], session_id="s1")
    assert mem.stats()["episodes"] == 0
    assert mem.store.db.execute("SELECT count(*) FROM ingest_log").fetchone()[0] == 0


def _http_error(code):
    return urllib.error.HTTPError("http://ollama.test/api/embed", code, "injected", {}, io.BytesIO(b"{}"))


def test_ollama_only_uses_legacy_fallback_for_unsupported_endpoint(monkeypatch):
    calls = []

    def fake_post(url, payload):
        calls.append(url)
        if url.endswith("/api/embed"):
            raise _http_error(401)
        return {"embedding": [1.0]}

    monkeypatch.setattr(embedder_module, "_post_json", fake_post)
    with pytest.raises(urllib.error.HTTPError):
        embedder_module.OllamaEmbedder(base_url="http://ollama.test").embed(["x"])
    assert calls == ["http://ollama.test/api/embed"]


def test_ollama_legacy_fallback_is_limited_to_404(monkeypatch):
    calls = []

    def fake_post(url, payload):
        calls.append(url)
        if url.endswith("/api/embed"):
            raise _http_error(404)
        return {"embedding": [1.0]}

    monkeypatch.setattr(embedder_module, "_post_json", fake_post)
    assert embedder_module.OllamaEmbedder(base_url="http://ollama.test").embed(["x"]) == [[1.0]]
    assert calls == ["http://ollama.test/api/embed", "http://ollama.test/api/embeddings"]
