"""Offline invariants for opt-in session-diverse retrieval."""

import pytest

from smriti import HashEmbedder, PROFILES, RetrievalProfile, Smriti
from smriti.retrieval import pack_context, retrieve
from smriti.types import Episode, Fact


class _Store:
    def __init__(self, episodes=(), facts=()):
        self.episodes = {episode.id: episode for episode in episodes}
        self.facts = {fact.id: fact for fact in facts}
        self.episode_lookups = 0

    def fts_search(self, query, table, limit):
        if table == "episode":
            return [(identifier, 1.0) for identifier in self.episodes][:limit]
        return [(identifier, 1.0) for identifier in self.facts][:limit]

    def get_episode(self, identifier):
        self.episode_lookups += 1
        return self.episodes.get(identifier)

    def get_fact(self, identifier):
        return self.facts.get(identifier)


class _Reranker:
    def rerank(self, query, texts):
        # Preserve candidate order while making the scores explicit.
        return [1.0 - index / 10 for index, _ in enumerate(texts)]


def _episodes(*session_ids):
    return [Episode(index + 1, session_id, "user", f"episode {index + 1}",
                    f"2026-0{index + 1}-01T10:00:00Z")
            for index, session_id in enumerate(session_ids)]


def test_session_diversity_replaces_duplicate_episode_only_and_keeps_facts():
    store = _Store(
        episodes=_episodes("s1", "s1", "s2"),
        facts=[
            Fact(10, "current fact", valid_from="2026-01-01"),
            Fact(11, "old fact", valid_from="2025-01-01", invalid_at="2026-01-01"),
            Fact(12, "summary", kind="observation"),
        ],
    )
    baseline = retrieve(store, None, "q", k=4, channels={"lexical"},
                        include_observations=True)
    diverse = retrieve(store, None, "q", k=4, channels={"lexical"},
                       include_observations=True, session_diverse=True)

    assert [result.id for result in baseline if result.kind == "observation"] == [12]
    assert [result.id for result in diverse if result.kind == "observation"] == [12]
    assert [result.id for result in baseline if result.kind != "observation"] == [10, 1, 2, 11]
    assert [result.id for result in diverse if result.kind != "observation"] == [10, 1, 3, 11]
    assert {result.id for result in diverse if result.kind == "fact"} == {10, 11}
    assert diverse[1].id == 10  # current fact remains ahead of superseded fact


def test_session_diversity_is_deterministic_on_ties_and_keeps_missing_sessions_distinct():
    orphan_episodes = [
        Episode(1, "", "user", "same orphan content", "2026-01-01T10:00:00Z"),
        Episode(2, "", "user", "same orphan content", "2026-02-01T10:00:00Z"),
        Episode(3, "s2", "user", "episode 3", "2026-03-01T10:00:00Z"),
    ]
    store = _Store(episodes=orphan_episodes)
    results = retrieve(store, None, "q", k=2, channels={"lexical"},
                       include_observations=False, session_diverse=True)
    assert [result.id for result in results] == [1, 2]

    repeated = _Store(episodes=_episodes("s1", "s1", "s2"))
    results = retrieve(repeated, None, "q", k=2, channels={"lexical"},
                       include_observations=False, session_diverse=True)
    assert [result.id for result in results] == [1, 3]


def test_session_diversity_restores_reranked_order_after_replacement():
    store = _Store(episodes=_episodes("s1", "s1", "s2", "s3"))
    results = retrieve(store, None, "q", k=3, channels={"lexical"},
                       include_observations=False, reranker=_Reranker(),
                       rerank_top=3, session_diverse=True, session_overfetch=2)
    assert [result.id for result in results] == [1, 3, 4]


def test_session_diversity_applies_after_reranking_and_bounds_candidate_scan():
    store = _Store(episodes=_episodes("s1", "s1", "s2", "s3", "s4"))
    results = retrieve(store, None, "q", k=2, channels={"lexical"},
                       include_observations=False, reranker=_Reranker(),
                       rerank_top=2,
                       session_diverse=True, session_overfetch=2)
    assert [result.id for result in results] == [1, 3]
    assert all("rerank" in result.channels for result in results)
    assert store.episode_lookups == 4  # min(5, k * overfetch)


def test_session_overfetch_must_be_positive_when_enabled():
    store = _Store(episodes=_episodes("s1", "s2"))
    with pytest.raises(ValueError, match="positive integer"):
        retrieve(store, None, "q", k=2, channels={"lexical"},
                 session_diverse=True, session_overfetch=0)


def test_context_preserves_episode_timestamps_and_budget_after_selection():
    store = _Store(episodes=_episodes("s1", "s1", "s2"))
    results = retrieve(store, None, "q", k=2, channels={"lexical"},
                       include_observations=False, session_diverse=True)
    context = pack_context(results, char_budget=200)
    assert "[2026-01-01]" in context and "[2026-03-01]" in context
    assert len(context) <= 200


def test_custom_profile_can_enable_session_diversity_without_changing_builtins():
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")
    profile = RetrievalProfile(name="ablation", channels={"lexical"}, k=2,
                               session_diverse=True, session_overfetch=2)
    assert all(not built_in.session_diverse for built_in in PROFILES.values())
    assert profile.session_diverse and profile.session_overfetch == 2
    assert mem.search("q", profile=profile) == []


def test_iterative_paths_reject_session_diversity_before_retrieval():
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")
    with pytest.raises(ValueError, match="not supported by iterative retrieval"):
        mem.search_iterative("q", session_diverse=True)
    with pytest.raises(ValueError, match="not supported by iterative retrieval"):
        mem.context_iterative("q", session_diverse=True)
