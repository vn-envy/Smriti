"""Embedding providers. Zero third-party HTTP deps (stdlib urllib).

  * OllamaEmbedder      - local-first default (e.g. nomic-embed-text, bge-m3)
  * OpenAICompatEmbedder- any /v1/embeddings endpoint (vLLM, LM Studio, hosted)
  * HashEmbedder        - deterministic char-ngram hashing; offline tests/CI
"""
from __future__ import annotations

import hashlib
import http.client
import json
import math
import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional, Sequence


def _is_transient_network_error(exc: BaseException) -> bool:
    """Reject permanent TLS failures while accepting urllib transport errors."""
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, (ssl.SSLError, ssl.CertificateError)):
            return False
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, socket.timeout,
                            http.client.RemoteDisconnected))


def _post_json(url: str, payload: dict, headers: Optional[dict] = None,
               timeout: int = 120, retries: int = 2,
               on_attempt: Optional[Callable[[], None]] = None) -> dict:
    """POST JSON with bounded retry on transient transport/server errors.

    Hosted endpoints occasionally drop a connection or stall (socket.timeout);
    a single such blip should not abandon a long benchmark or ingest run, so we
    retry with linear backoff before giving up. HTTP 429 and 5xx responses are
    also retryable; authentication, validation, malformed JSON, and other HTTP
    errors fail immediately. ``on_attempt`` is called once per actual request.
    """
    data = json.dumps(payload).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        # Some providers (e.g. Groq behind Cloudflare) reject the default
        # "Python-urllib/x.y" User-Agent with HTTP 403. Send an explicit one,
        # versioned from the package so it can't drift (lazy import: avoids
        # a circular import at package-init time).
        from . import __version__ as _v
        req.add_header("User-Agent", f"smriti/{_v}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        if on_attempt is not None:
            on_attempt()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if (exc.code == 429 or 500 <= exc.code <= 599) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            if _is_transient_network_error(exc) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except (TimeoutError, ConnectionError, socket.timeout,
                http.client.RemoteDisconnected) as exc:
            if _is_transient_network_error(exc) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
        except json.JSONDecodeError:
            raise
    raise AssertionError("unreachable")  # pragma: no cover


class HashEmbedder:
    """Deterministic, dependency-free embedder for tests and lite mode.

    Character n-gram hashing into a fixed-dim space. Not semantically smart,
    but stable, fast, and good enough to exercise the full pipeline offline.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            t = text.lower()
            for n in (3, 4):
                for i in range(max(0, len(t) - n + 1)):
                    h = int.from_bytes(
                        hashlib.blake2b(t[i:i + n].encode(), digest_size=4).digest(), "big"
                    )
                    vec[h % self.dim] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OllamaEmbedder:
    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        texts = [t[:4000] for t in texts]
        try:
            resp = _post_json(f"{self.base_url}/api/embed", {"model": self.model, "input": list(texts)})
            return resp["embeddings"]
        except Exception:
            # older Ollama versions: one prompt per call
            return [
                _post_json(f"{self.base_url}/api/embeddings", {"model": self.model, "prompt": t})["embedding"]
                for t in texts
            ]


class OpenAICompatEmbedder:
    def __init__(self, model: str, base_url: str, api_key: str = ""):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = _post_json(
            f"{self.base_url}/embeddings",
            {"model": self.model, "input": [t[:6000] for t in texts]},
            headers,
        )
        data = sorted(resp["data"], key=lambda d: d.get("index", 0))
        return [d["embedding"] for d in data]
