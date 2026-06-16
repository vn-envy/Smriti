"""SMRITI - Structured Memory with Reflective Indexing and Temporal Inference.

A zero-infrastructure, local-first, Apache-2.0 memory layer for AI agents.
smriti (स्मृति): Sanskrit for "that which is remembered".
"""
from .embedder import HashEmbedder, OllamaEmbedder, OpenAICompatEmbedder
from .llm import LLM, MockLLM
from .memory import Smriti
from .types import Episode, Fact, RetrievalResult

__version__ = "0.1.0"
__all__ = [
    "Smriti", "Fact", "Episode", "RetrievalResult",
    "LLM", "MockLLM", "HashEmbedder", "OllamaEmbedder", "OpenAICompatEmbedder",
]
