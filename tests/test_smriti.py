"""Offline tests: HashEmbedder + MockLLM, no network, no API keys."""
import json

from smriti import Fact, HashEmbedder, MockLLM, Smriti
from smriti.retrieval import extract_dates
from bench.judge import is_abstention
from bench.longmemeval import parse_lme_date
from bench.locomo import iter_sessions, parse_locomo_date


def make_lite():
    return Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")


# ------------------------------------------------------------------- ingest
def test_lite_ingest_and_stats():
    mem = make_lite()
    out = mem.add(
        [{"role": "user", "content": "I adopted a golden retriever named Bruno."},
         {"role": "assistant", "content": "Congrats on adopting Bruno!"}],
        timestamp="2025-03-10T09:00:00Z",
    )
    assert out["episodes"] == 2
    s = mem.stats()
    assert s["episodes"] == 2 and s["mode"] == "lite"


def test_needle_retrieval_among_distractors():
    mem = make_lite()
    distractors = [
        "Can you explain how transformers use attention?",
        "Write me a haiku about monsoon rains.",
        "What is the capital of Australia?",
        "Help me debug a python segfault in my service.",
        "Summarize the plot of a famous detective novel.",
    ]
    for i, d in enumerate(distractors):
        mem.add([{"role": "user", "content": d}], timestamp=f"2025-01-0{i+1}T10:00:00Z")
    mem.add([{"role": "user", "content": "My passport number renewal appointment is at the Begumpet office on Friday."}],
            timestamp="2025-02-01T10:00:00Z")
    results = mem.search("Where is my passport renewal appointment?", k=3)
    assert results, "expected hits"
    assert any("Begumpet" in r.text for r in results)


# -------------------------------------------------------------- full mode
def test_full_mode_extracts_facts():
    extraction = json.dumps([{
        "statement": "The user lives in Hyderabad.",
        "subject": "user", "predicate": "lives_in", "object": "Hyderabad",
        "entities": ["Hyderabad"], "event_date": None, "kind": "profile",
    }])
    llm = MockLLM([extraction])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    out = mem.add([{"role": "user", "content": "btw I live in Hyderabad"}],
                  timestamp="2025-05-01T10:00:00Z")
    assert out["facts"] == 1
    assert mem.stats()["valid_facts"] == 1
    results = mem.search("Which city does the user live in?", k=5)
    assert any(r.kind == "fact" and "Hyderabad" in r.text for r in results)


def test_supersession_on_knowledge_update():
    """'lives in Hyderabad' then 'moved to Bengaluru' -> old fact superseded, not deleted."""
    e1 = json.dumps([{"statement": "The user lives in Hyderabad.", "subject": "user",
                      "predicate": "lives_in", "object": "Hyderabad",
                      "entities": ["Hyderabad"], "event_date": None, "kind": "profile"}])
    e2 = json.dumps([{"statement": "The user lives in Bengaluru.", "subject": "user",
                      "predicate": "lives_in", "object": "Bengaluru",
                      "entities": ["Bengaluru"], "event_date": "2025-06-01", "kind": "profile"}])
    llm = MockLLM([e1, e2])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add([{"role": "user", "content": "I live in Hyderabad"}], timestamp="2025-01-01T00:00:00Z")
    mem.add([{"role": "user", "content": "I just moved to Bengaluru"}], timestamp="2025-06-01T00:00:00Z")

    s = mem.stats()
    assert s["facts"] == 2 and s["valid_facts"] == 1  # history preserved

    old = mem.store.get_fact(1)
    new = mem.store.get_fact(2)
    assert old.invalid_at is not None and old.superseded_by == new.id
    assert new.invalid_at is None

    ctx = mem.context("Where does the user live?")
    assert "CURRENT" in ctx and "SUPERSEDED" in ctx
    assert "Bengaluru" in ctx and "Hyderabad" in ctx


def test_duplicate_facts_are_skipped():
    e = json.dumps([{"statement": "The user owns a Mac Studio.", "subject": "user",
                     "predicate": "owns", "object": "Mac Studio",
                     "entities": ["Mac Studio"], "event_date": None, "kind": "profile"}])
    llm = MockLLM([e, e])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add([{"role": "user", "content": "I own a Mac Studio"}])
    mem.add([{"role": "user", "content": "as I said, I own a Mac Studio"}])
    assert mem.stats()["facts"] == 1


def test_entity_channel():
    mem = make_lite()
    mem.add_fact(Fact(id=None, statement="The user's startup SigmaFlow is a reliability middleware.",
                      subject="user", predicate="founded", object="SigmaFlow",
                      entities=["SigmaFlow"]))
    results = mem.search("tell me about SigmaFlow", k=5)
    assert any("SigmaFlow" in r.text and "entity" in r.channels for r in results)


# ------------------------------------------------------- observations (Build 1)
def _charity_fact(stmt, obj):
    return Fact(id=None, statement=stmt, subject="user", predicate="attended",
                object=obj, entities=["charity"])


def test_observation_synthesis_and_supersession():
    """Per-entity observation summary is created, retrievable, and regenerating
    it supersedes the prior one (history preserved, never duplicated)."""
    llm = MockLLM([
        "The user attended 2 charity events: Walk for Hunger and the 5K Gala.",
        "The user attended 3 charity events: Walk for Hunger, the 5K Gala, and Run for Hope.",
    ])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add_fact(_charity_fact("The user attended the Walk for Hunger event.", "Walk for Hunger"),
                 resolve_conflicts=False)
    mem.add_fact(_charity_fact("The user attended the 5K Gala event.", "5K Gala"),
                 resolve_conflicts=False)

    out = mem.refresh_observations(min_facts=2)
    assert out["observations"] == 1
    obs = mem.store.similar_valid_facts("charity", "observation")
    assert len(obs) == 1 and obs[0].kind == "observation"
    assert "2 charity events" in obs[0].statement

    # observation is retrievable via the normal channels
    results = mem.search("how many charity events did I attend?", k=8)
    assert any(r.kind == "fact" and "2 charity events" in r.text for r in results)

    # new fact + refresh -> supersede prior observation, don't duplicate
    mem.add_fact(_charity_fact("The user attended the Run for Hope event.", "Run for Hope"),
                 resolve_conflicts=False)
    mem.refresh_observations(min_facts=2)
    valid = mem.store.similar_valid_facts("charity", "observation")
    assert len(valid) == 1 and "3 charity events" in valid[0].statement
    all_obs = [f for f in mem.store.facts_for_entity("charity", valid_only=False,
                                                     include_observations=True)
               if f.kind == "observation"]
    assert len(all_obs) == 2  # prior kept as superseded history


def test_observation_skips_sparse_entities():
    """An entity with fewer than min_facts gets no observation (no wasted LLM call)."""
    llm = MockLLM(["unused"])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add_fact(Fact(id=None, statement="The user owns a kayak.", subject="user",
                      predicate="owns", object="kayak", entities=["kayak"]),
                 resolve_conflicts=False)
    out = mem.refresh_observations(min_facts=2)
    assert out["observations"] == 0 and llm.calls == 0


# ---------------------------------------------------------------- temporal
def test_extract_dates_variants():
    assert "2024-03-12" in extract_dates("what happened on 2024-03-12?")
    assert "2024-03-12" in extract_dates("the trip on 12 March 2024")
    assert "2023-05-15" in extract_dates("back in May 2023 I think")


def test_lme_and_locomo_date_parsing():
    assert parse_lme_date("2023/05/30 (Tue) 23:40") == "2023-05-30T23:40:00Z"
    assert parse_locomo_date("1:56 pm on 8 May, 2023") == "2023-05-08T00:00:00Z"


def test_locomo_session_iteration():
    conv = {
        "speaker_a": "A", "speaker_b": "B",
        "session_1_date_time": "1:56 pm on 8 May, 2023",
        "session_1": [{"speaker": "A", "text": "hello"},
                      {"speaker": "B", "text": "hi", "blip_caption": "a dog photo"}],
        "session_2_date_time": "2 pm on 9 May, 2023",
        "session_2": [{"speaker": "A", "text": "bye"}],
    }
    sessions = list(iter_sessions(conv))
    assert len(sessions) == 2
    key, ts, turns = sessions[0]
    assert key == "session_1" and ts.startswith("2023-05-08") and len(turns) == 2
    assert "a dog photo" in turns[1]["content"]


def test_abstention_detection():
    assert is_abstention("I don't have enough information to answer that.")
    assert not is_abstention("Your sister lives in Pune.")


def test_persistence_roundtrip(tmp_path):
    db = str(tmp_path / "mem.db")
    mem = Smriti(path=db, embedder=HashEmbedder(), mode="lite")
    mem.add([{"role": "user", "content": "My UPI handle is neekhil@okaxis"}])
    del mem
    mem2 = Smriti(path=db, embedder=HashEmbedder(), mode="lite")
    results = mem2.search("what is my UPI handle?", k=3)
    assert any("okaxis" in r.text for r in results)


def test_sanskrit_mode_aliases():
    """laghu (lite) and purna (full) work as first-class mode names."""
    mem = Smriti(embedder=HashEmbedder(), mode="laghu")
    assert mem.mode == "lite"
    mem2 = Smriti(embedder=HashEmbedder(), llm=MockLLM(["[]"]), mode="purna")
    assert mem2.mode == "full"
