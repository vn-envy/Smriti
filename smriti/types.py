"""Core data types for SMRITI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Episode:
    """A single raw conversation turn (append-only, never mutated)."""
    id: Optional[int]
    session_id: str
    role: str
    content: str
    ts: Optional[str]  # ISO-8601 event time


@dataclass
class Fact:
    """An atomic, bi-temporal memory fact.

    valid_from / invalid_at  -> when the fact was true in the *world*
    ingested_at              -> when the system learned it
    A fact is never deleted; it is superseded (invalid_at set, superseded_by
    pointing at the newer fact). This preserves a full audit trail and lets
    retrieval answer "what was true as of <date>?" questions.
    """
    id: Optional[int]
    statement: str
    subject: str = ""
    predicate: str = ""
    object: str = ""
    kind: str = "knowledge"          # profile | preference | event | knowledge
    entities: List[str] = field(default_factory=list)
    event_date: Optional[str] = None  # explicit date mentioned in the fact
    ingested_at: Optional[str] = None
    valid_from: Optional[str] = None
    invalid_at: Optional[str] = None
    superseded_by: Optional[int] = None
    episode_id: Optional[int] = None
    session_id: Optional[str] = None


@dataclass
class RetrievalResult:
    """A fused retrieval hit from any channel."""
    kind: str           # "fact" | "episode"
    id: int
    text: str
    score: float
    ts: Optional[str] = None          # episode timestamp
    valid_from: Optional[str] = None  # fact validity window
    invalid_at: Optional[str] = None
    role: Optional[str] = None
    channels: List[str] = field(default_factory=list)
