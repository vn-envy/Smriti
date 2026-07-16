"""SMRITI - Structured Memory with Reflective Indexing and Temporal Inference.

A zero-infrastructure, local-first, Apache-2.0 memory layer for AI agents.
smriti (स्मृति): Sanskrit for "that which is remembered".
"""
from .embedder import HashEmbedder, OllamaEmbedder, OpenAICompatEmbedder
from .llm import LLM, MockLLM
from .memory import Smriti, redact_secrets
from .profiles import PROFILES, RetrievalProfile, resolve as resolve_profile
from .rerank import HTTPReranker, MockReranker
from .types import Episode, Fact, RetrievalResult

__version__ = "0.3.1"
__all__ = [
    "Smriti", "Fact", "Episode", "RetrievalResult",
    "LLM", "MockLLM", "HashEmbedder", "OllamaEmbedder", "OpenAICompatEmbedder",
    "HTTPReranker", "MockReranker",
    "RetrievalProfile", "PROFILES", "resolve_profile", "redact_secrets",
]
