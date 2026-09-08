"""Focused tests for bounded provider HTTP retry and accounting policy."""

import io
import json
import ssl
import urllib.error

import pytest

import smriti.embedder as embedder
import smriti.llm as llm_module


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "http://provider.test", code, "injected", {}, io.BytesIO(b"{}")
    )


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_post_json_does_not_retry_permanent_http_errors(monkeypatch, status):
    calls = {"http": 0, "reported": 0}

    def fail(req, timeout=0):
        calls["http"] += 1
        raise _http_error(status)

    monkeypatch.setattr(embedder.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.HTTPError) as caught:
        embedder._post_json(
            "http://provider.test", {}, retries=2,
            on_attempt=lambda: calls.__setitem__("reported", calls["reported"] + 1),
        )
    assert caught.value.code == status
    assert calls == {"http": 1, "reported": 1}


@pytest.mark.parametrize("status", [429, 500, 503])
def test_post_json_retries_retryable_http_errors(monkeypatch, status):
    calls = {"http": 0, "reported": 0}

    def flaky(req, timeout=0):
        calls["http"] += 1
        if calls["http"] < 3:
            raise _http_error(status)
        return _Response(b'{"ok": true}')

    monkeypatch.setattr(embedder.time, "sleep", lambda *_: None)
    monkeypatch.setattr(embedder.urllib.request, "urlopen", flaky)
    out = embedder._post_json(
        "http://provider.test", {}, retries=2,
        on_attempt=lambda: calls.__setitem__("reported", calls["reported"] + 1),
    )
    assert out == {"ok": True}
    assert calls == {"http": 3, "reported": 3}


def test_post_json_reports_actual_attempts_when_retry_exhausts(monkeypatch):
    calls = {"http": 0, "reported": 0}

    def fail(req, timeout=0):
        calls["http"] += 1
        raise urllib.error.URLError("connection reset")

    monkeypatch.setattr(embedder.time, "sleep", lambda *_: None)
    monkeypatch.setattr(embedder.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.URLError):
        embedder._post_json(
            "http://provider.test", {}, retries=2,
            on_attempt=lambda: calls.__setitem__("reported", calls["reported"] + 1),
        )
    assert calls == {"http": 3, "reported": 3}


def test_post_json_does_not_retry_malformed_json(monkeypatch):
    calls = {"http": 0, "reported": 0}

    def malformed(req, timeout=0):
        calls["http"] += 1
        return _Response(b"not json")

    monkeypatch.setattr(embedder.urllib.request, "urlopen", malformed)
    with pytest.raises(json.JSONDecodeError):
        embedder._post_json(
            "http://provider.test", {}, retries=2,
            on_attempt=lambda: calls.__setitem__("reported", calls["reported"] + 1),
        )
    assert calls == {"http": 1, "reported": 1}


def test_post_json_does_not_retry_tls_certificate_failure(monkeypatch):
    calls = {"http": 0}

    def fail(req, timeout=0):
        calls["http"] += 1
        raise urllib.error.URLError(ssl.SSLCertVerificationError("untrusted"))

    monkeypatch.setattr(embedder.time, "sleep", lambda *_: None)
    monkeypatch.setattr(embedder.urllib.request, "urlopen", fail)
    with pytest.raises(urllib.error.URLError):
        embedder._post_json("http://provider.test", {}, retries=2)
    assert calls["http"] == 1


def test_llm_keeps_logical_attempts_and_counts_http_retries(monkeypatch):
    client = llm_module.LLM("model")
    calls = {"http": 0}

    def flaky(req, timeout=0):
        calls["http"] += 1
        if calls["http"] == 1:
            raise urllib.error.URLError(ConnectionResetError("temporary"))
        return _Response(
            b'{"choices":[{"message":{"content":"ok"}}],'
            b'"usage":{"prompt_tokens":4,"completion_tokens":2}}'
        )

    monkeypatch.setattr(embedder.time, "sleep", lambda *_: None)
    monkeypatch.setattr(embedder.urllib.request, "urlopen", flaky)
    assert client.complete([]) == "ok"
    assert client.attempts == 1  # compatibility: logical completions
    assert client.http_attempts == 2
    assert client.calls == 1
    assert (client.tokens_in, client.tokens_out) == (4, 2)


@pytest.mark.parametrize("status", [400, 422])
def test_llm_json_mode_fallback_is_one_explicit_second_request(monkeypatch, status):
    client = llm_module.LLM("model")
    requests = []

    def respond(url, payload, headers, **kwargs):
        kwargs["on_attempt"]()
        requests.append(payload.copy())
        if len(requests) == 1:
            raise _http_error(status)
        return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setattr(llm_module, "_post_json", respond)
    assert client.complete([], json_mode=True) == "{}"
    assert client.attempts == 2
    assert client.http_attempts == 2
    assert client.calls == 1
    assert "response_format" in requests[0]
    assert "response_format" not in requests[1]


def test_llm_permanent_http_error_has_no_success_or_usage(monkeypatch):
    client = llm_module.LLM("model")

    def fail(url, payload, headers, **kwargs):
        kwargs["on_attempt"]()
        raise _http_error(401)

    monkeypatch.setattr(llm_module, "_post_json", fail)
    with pytest.raises(urllib.error.HTTPError):
        client.complete([])
    assert client.attempts == 1
    assert client.http_attempts == 1
    assert client.calls == 0
    assert client.usage_missing == 0
    assert (client.tokens_in, client.tokens_out) == (0, 0)
