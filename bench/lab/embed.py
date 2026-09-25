"""Embedders for the lab: the in-process ONNX model behind a persistent cache.

Repeated A/B runs embed the same turns thousands of times; caching by
sha1(model, text) makes every run after the first CPU-cheap and guarantees
that all systems in a comparison see bit-identical vectors.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from typing import List, Sequence

import numpy as np

DEFAULT_MODEL_DIR = os.environ.get("SMRITI_LAB_ONNX", "/home/user/data/minilm/onnx")
DEFAULT_CACHE = os.environ.get("SMRITI_LAB_EMBCACHE", "/home/user/data/embcache.sqlite")


class CachedEmbedder:
    """Wrap any ``embed(texts)`` embedder with an on-disk vector cache."""

    def __init__(self, inner, cache_path: str = DEFAULT_CACHE):
        self.inner = inner
        self.model = getattr(inner, "model", type(inner).__name__)
        self.dim = getattr(inner, "dim", None)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(cache_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS v(k TEXT PRIMARY KEY, e BLOB)")
        self.hits = 0
        self.misses = 0

    def _key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}\x00{text}".encode()).hexdigest()

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        keys = [self._key(t) for t in texts]
        found = {}
        with self._lock:
            for i in range(0, len(keys), 500):
                chunk = keys[i:i + 500]
                q = ",".join("?" * len(chunk))
                for k, e in self.db.execute(f"SELECT k, e FROM v WHERE k IN ({q})", chunk):
                    found[k] = e
        missing = [i for i, k in enumerate(keys) if k not in found]
        self.hits += len(keys) - len(missing)
        self.misses += len(missing)
        if missing:
            uniq = list(dict.fromkeys(texts[i] for i in missing))
            vecs = self.inner.embed(uniq)
            by_text = {t: np.asarray(v, dtype=np.float32).tobytes() for t, v in zip(uniq, vecs)}
            with self._lock:
                self.db.executemany("INSERT OR REPLACE INTO v(k, e) VALUES(?, ?)",
                                    [(self._key(t), b) for t, b in by_text.items()])
                self.db.commit()
            for i in missing:
                found[keys[i]] = by_text[texts[i]]
        return [np.frombuffer(found[k], dtype=np.float32).tolist() for k in keys]

    def embed_np(self, texts: Sequence[str]) -> np.ndarray:
        return np.asarray(self.embed(texts), dtype=np.float32)


_SHARED = None


def lab_embedder() -> CachedEmbedder:
    global _SHARED
    if _SHARED is None:
        try:
            from smriti.onnx_embedder import OnnxEmbedder
        except ImportError:
            # Baseline worktrees predate the in-process embedder; load the
            # module from this checkout so every arm shares identical vectors.
            import importlib.util
            path = os.path.join(os.path.dirname(__file__), "..", "..", "smriti",
                                "onnx_embedder.py")
            spec = importlib.util.spec_from_file_location("_lab_onnx_embedder", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            OnnxEmbedder = mod.OnnxEmbedder
        _SHARED = CachedEmbedder(OnnxEmbedder(DEFAULT_MODEL_DIR, model="all-MiniLM-L6-v2",
                                              batch_size=32))
    return _SHARED
