"""In-process ONNX sentence embeddings — no server, no network, no torch.

``OllamaEmbedder`` needs a running Ollama daemon; ``HashEmbedder`` is offline
but not semantic. ``OnnxEmbedder`` closes that gap: it runs a sentence-
transformer exported to ONNX (for example ``all-MiniLM-L6-v2``) directly in
the Python process with ``onnxruntime`` + ``tokenizers``. Both are optional
extras (``pip install smriti-agents[onnx]``); the core stays stdlib + numpy.

The model directory must contain ``model.onnx`` and ``tokenizer.json`` (the
layout of the common sentence-transformers ONNX exports). Pooling is mean
over the attention mask followed by L2 normalization, matching
sentence-transformers' default for the MiniLM/mpnet families.
"""
from __future__ import annotations

import os
from typing import List, Optional, Sequence

try:  # numpy is a core dependency; keep the import style of store.py
    import numpy as np
except ImportError:  # pragma: no cover
    np = None


class OnnxEmbedder:
    """Local sentence embeddings from an ONNX export.

    ``model_dir`` holds ``model.onnx`` and ``tokenizer.json``. ``model`` is a
    stable, human-readable identity recorded in the database so vectors from
    a different model are never mixed silently (see ``Store.ensure_embedder``).
    """

    def __init__(self, model_dir: str, model: Optional[str] = None,
                 max_length: int = 256, batch_size: int = 32,
                 threads: Optional[int] = None):
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as exc:  # pragma: no cover - exercised by users
            raise ImportError(
                "OnnxEmbedder needs the optional extras: "
                "pip install onnxruntime tokenizers") from exc
        if np is None:  # pragma: no cover
            raise ImportError("OnnxEmbedder requires numpy")
        model_path = os.path.join(model_dir, "model.onnx")
        tok_path = os.path.join(model_dir, "tokenizer.json")
        for path in (model_path, tok_path):
            if not os.path.exists(path):
                raise FileNotFoundError(f"missing ONNX model file: {path}")
        self.model = model or os.path.basename(os.path.normpath(model_dir))
        self.max_length = int(max_length)
        self.batch_size = max(1, int(batch_size))
        self._tok = Tokenizer.from_file(tok_path)
        # Exported tokenizer.json files often pin fixed-length padding (for
        # example 128 tokens); padding is done here per batch instead, with
        # the true attention mask, so pad tokens never enter mean pooling.
        self._tok.no_padding()
        self._tok.enable_truncation(self.max_length)
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = int(threads)
        self._sess = ort.InferenceSession(model_path, opts,
                                          providers=["CPUExecutionProvider"])
        self._inputs = {i.name for i in self._sess.get_inputs()}
        self.dim = int(self._sess.get_outputs()[0].shape[-1])

    def _run(self, texts: Sequence[str]) -> "np.ndarray":
        encs = self._tok.encode_batch(list(texts))
        width = max(1, max(len(e.ids) for e in encs))
        ids = np.zeros((len(encs), width), dtype=np.int64)
        mask = np.zeros((len(encs), width), dtype=np.int64)
        for row, enc in enumerate(encs):
            ids[row, :len(enc.ids)] = enc.ids
            mask[row, :len(enc.ids)] = enc.attention_mask
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._inputs:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self._sess.run(None, feed)[0]
        weights = mask[..., None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return pooled / norms

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        texts = [(t or " ")[:8000] for t in texts]
        if not texts:
            return []
        # Length-sorted batches minimize padding (a large CPU win for mixed
        # short/long turns); results are scattered back to input order.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out: List[Optional[List[float]]] = [None] * len(texts)
        for start in range(0, len(order), self.batch_size):
            idx = order[start:start + self.batch_size]
            vecs = self._run([texts[i] for i in idx])
            for i, v in zip(idx, vecs):
                out[i] = v.astype(np.float32).tolist()
        return out  # type: ignore[return-value]
