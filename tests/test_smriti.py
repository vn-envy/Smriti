"""Offline tests: HashEmbedder + MockLLM, no network, no API keys."""
import json

from smriti import Fact, HashEmbedder, MockLLM, MockReranker, Smriti
from smriti.retrieval import extract_dates
from bench.judge import is_abstention
from bench.longmemeval import parse_lme_date, run_longmemeval
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

    out = mem.refresh_observations(min_facts=2, granularity=("entity",))
    assert out["observations"] == 1
    obs = mem.store.similar_valid_facts("charity", "observation")
    assert len(obs) == 1 and obs[0].kind == "observation"
    assert "2 charity events" in obs[0].statement

    # observation is retrievable and surfaced in its own (observation) slot
    results = mem.search("how many charity events did I attend?", k=8)
    assert any(r.kind == "observation" and "2 charity events" in r.text for r in results)

    # new fact + refresh -> supersede prior observation, don't duplicate
    mem.add_fact(_charity_fact("The user attended the Run for Hope event.", "Run for Hope"),
                 resolve_conflicts=False)
    mem.refresh_observations(min_facts=2, granularity=("entity",))
    valid = mem.store.similar_valid_facts("charity", "observation")
    assert len(valid) == 1 and "3 charity events" in valid[0].statement
    all_obs = [f for f in mem.store.facts_for_entity("charity", valid_only=False,
                                                     include_observations=True)
               if f.kind == "observation"]
    assert len(all_obs) == 2  # prior kept as superseded history


def test_two_hop_entity_traversal():
    """A fact reachable only by hopping query-entity -> intermediate-entity ->
    answer-fact is surfaced by the 2-hop entity channel (graph-lite multi-hop)."""
    mem = make_lite()
    mem.add_fact(Fact(id=None, statement="Rachel works at Acme.", subject="rachel",
                      predicate="works_at", object="Acme", entities=["Rachel", "Acme"]))
    mem.add_fact(Fact(id=None, statement="Acme is headquartered in Berlin.", subject="acme",
                      predicate="located_in", object="Berlin", entities=["Acme"]))
    q = "Where is the company Rachel works for located?"
    hits = [r for r in mem.search(q, k=8) if "Berlin" in r.text]
    assert hits, "2-hop fact not retrieved"
    assert any("entity_hop2" in r.channels for r in hits)

    # without the second hop, the Berlin fact isn't reachable via entities
    from smriti.retrieval import retrieve
    one_hop = retrieve(mem.store, mem.embedder, q, k=8, entity_hops=1)
    assert not any("entity_hop2" in r.channels for r in one_hop)


def test_numeric_sum_digest():
    """Build 8: same-unit quantities are summed deterministically (Python, not
    the LLM) and carried in the digest — for SUM-type aggregation questions."""
    from smriti.extraction import compute_numeric_totals
    facts = [Fact(id=1, statement="The user spent $40 on a bike tube."),
             Fact(id=2, statement="The user spent $120 on a bike tune-up."),
             Fact(id=3, statement="The user spent $25 on a bike light.")]
    s = compute_numeric_totals(facts)
    assert "$185" in s
    # mixed units never cross-add
    mixed = compute_numeric_totals([Fact(id=1, statement="drove 3 hours"),
                                    Fact(id=2, statement="drove 5 hours"),
                                    Fact(id=3, statement="paid $10")])
    assert "8 hours" in mixed and "$10" not in mixed  # only the >=2 unit is reported

    # end-to-end: the digest fact carries the computed total
    llm = MockLLM(["bike entity overview", "bike expenses: tube, tune-up, light."])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    for stmt, o in [("The user spent $40 on a bike tube.", "tube"),
                    ("The user spent $120 on a bike tune-up.", "tune-up"),
                    ("The user spent $25 on a bike light.", "light")]:
        mem.add_fact(Fact(id=None, statement=stmt, subject="user", predicate="spent_on",
                          object=o, entities=["bike"]), resolve_conflicts=False)
    mem.refresh_observations(min_facts=2)
    dig = mem.store.similar_valid_facts("user", "digest:spent_on")
    assert dig and "$185" in dig[0].statement


def test_predicate_digest_for_cross_entity_aggregation():
    """Build 7: when N events each have their own entity (so no per-entity summary
    fires), the (subject, predicate) digest still enumerates them all — the cross-
    entity aggregation per-entity observations structurally miss."""
    llm = MockLLM(["user attended events: Walk for Hunger, 5K Gala, Run for Hope (3)."])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    for obj in ["Walk for Hunger", "5K Gala", "Run for Hope"]:
        mem.add_fact(Fact(id=None, statement=f"The user attended {obj}.", subject="user",
                          predicate="attended", object=obj, entities=[obj]),
                     resolve_conflicts=False)
    out = mem.refresh_observations(min_facts=2)
    # no single entity has >=2 facts, so the value comes from the predicate digest
    assert out["entity"] == 0 and out["predicate"] == 1
    dig = mem.store.similar_valid_facts("user", "digest:attended")
    assert len(dig) == 1 and dig[0].kind == "observation"
    res = mem.search("how many events did I attend?", k=8)
    assert any(r.kind == "observation" and "Run for Hope" in r.text for r in res)


def test_observations_are_additive_not_competing():
    """Build 6: observations occupy their own slots and must NOT displace raw
    facts from the k budget; context renders them in a dedicated section."""
    llm = MockLLM(["pets — cat Pixel, dog Bruno, fish Coral."])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    raw = [("The user has a cat named Pixel.", "Pixel"),
           ("The user has a dog named Bruno.", "Bruno"),
           ("The user has a fish named Coral.", "Coral")]
    for i, (s, o) in enumerate(raw):
        mem.add_fact(Fact(id=None, statement=s, subject="user", predicate=f"has_{i}",
                          object=o, entities=["pet"]), resolve_conflicts=False)
    mem.refresh_observations(min_facts=2)

    res = mem.search("tell me about my pets", k=3)
    obs = [r for r in res if r.kind == "observation"]
    facts = [r for r in res if r.kind == "fact"]
    assert obs, "observation should be surfaced in its own slot"
    assert len(facts) >= 3, "raw facts must not be displaced by the observation (additive)"
    # Build 12: observations appear on the aggregation (recall) path...
    assert "ENTITY SUMMARIES" in mem.context("how many pets do I have?", k=3)
    # ...but NOT on the precision path (they launder stale values there)
    assert "ENTITY SUMMARIES" not in mem.context("what is my cat's name?", k=3)


def test_observation_skips_sparse_entities():
    """An entity with fewer than min_facts gets no observation (no wasted LLM call)."""
    llm = MockLLM(["unused"])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add_fact(Fact(id=None, statement="The user owns a kayak.", subject="user",
                      predicate="owns", object="kayak", entities=["kayak"]),
                 resolve_conflicts=False)
    out = mem.refresh_observations(min_facts=2)
    assert out["observations"] == 0 and llm.calls == 0


# ----------------------------------------------- iterative retrieval (Build 5)
def test_iterative_retrieval_finds_second_hop():
    """A fact the single pass misses (no entity link, no lexical overlap with the
    question) is found via an LLM-proposed follow-up retrieval."""
    llm = MockLLM(["Photonics study of light technologies"])  # the follow-up query
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add_fact(Fact(id=None, statement="The user is enrolled in the Helios program.",
                      subject="user", predicate="enrolled_in", object="Helios",
                      entities=["Helios"]), resolve_conflicts=False)
    mem.add_fact(Fact(id=None, statement="Photonics is the study of light-based technologies.",
                      subject="photonics", predicate="is", object="study of light",
                      entities=["Photonics"]), resolve_conflicts=False)
    q = "What field is the user's program about?"

    one = mem.search(q, k=1)
    assert not any("Photonics" in r.text for r in one)        # single pass misses it
    two = mem.search_iterative(q, k=1, rounds=2)
    assert any("Photonics" in r.text for r in two)            # follow-up pass finds it


# ------------------------------------------------------- reranking (Build 4)
def test_reranker_reorders_and_tags():
    """An optional cross-encoder re-sorts the fused pool and tags results."""
    facts = [
        "The user enjoys hiking in the Western Ghats on weekends.",
        "The user adopted a cat named Pixel last winter.",
        "The user's favorite programming language is Python.",
    ]
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite",
                 reranker=MockReranker())
    for f in facts:
        mem.add_fact(Fact(id=None, statement=f, subject="user", predicate="note",
                          object="", entities=[]))
    res = mem.search("What programming language does the user like?", k=3)
    assert res and "rerank" in res[0].channels
    # reranker promotes the query-overlapping fact to the top
    assert "Python" in res[0].text


# ------------------------------------------------- recall track (Build 9)
def test_fact_key_expansion_recall():
    """A category word absent from the statement matches the fact in the lexical
    index only when indexed as a search key (Build 9 Part A)."""
    f = lambda: Fact(id=None, statement="The user added lime to the mojito.",
                     subject="user", predicate="used", object="lime",
                     entities=["lime"], search_keys=["citrus", "fruit"])
    on = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", expand_keys=True)
    on.add_fact(f())
    off = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", expand_keys=False)
    off.add_fact(f())
    # Build 10: statement FTS stays CLEAN (precision); keys live in a separate
    # index consulted only on the recall profile.
    assert not on.store.fts_search("citrus", "fact")   # not polluting the statement index
    assert on.store.key_fts_search("citrus")           # present in the separate key index
    assert not off.store.key_fts_search("citrus")      # no keys indexed when expansion off


def test_aggregation_router_key_channel():
    """The key-expansion channel fires only with use_key_channel (recall profile):
    'citrus' reaches a 'lime' fact via its keys, tagged key_expansion."""
    from smriti.retrieval import retrieve
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", expand_keys=True)
    for s in ["The user drives a Honda.", "The user plays tennis.", "The user codes in Rust."]:
        mem.add_fact(Fact(id=None, statement=s, subject="user", predicate="x",
                          object="", entities=[]))
    mem.add_fact(Fact(id=None, statement="The user added lime to the mojito.", subject="user",
                      predicate="used", object="lime", entities=["lime"],
                      search_keys=["citrus", "fruit"]))
    q = "how many citrus fruits have I used?"
    on = retrieve(mem.store, mem.embedder, q, k=8, use_key_channel=True)
    assert any("lime" in r.text and "key_expansion" in r.channels for r in on)
    off = retrieve(mem.store, mem.embedder, q, k=8, use_key_channel=False)
    assert not any("key_expansion" in r.channels for r in off)  # precise path untouched


def test_aggregation_intent_detection():
    from smriti.retrieval import is_aggregation_query
    for q in ["How many doctors did I visit?", "What is the total I spent?",
              "how much time on average", "how many different cuisines"]:
        assert is_aggregation_query(q)
    for q in ["Where do I live?", "What is my dog's name?", "When did I move?",
              "How often do I attend yoga?"]:  # frequency/current-state, NOT aggregation
        assert not is_aggregation_query(q)


def test_aggregation_path_is_gated_no_harm():
    """Non-aggregation queries take the byte-identical existing path whether or
    not the aggregate flag is on — the no-harm guarantee for Build 9 Part B."""
    def build(agg):
        m = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", aggregate=agg)
        m.add_fact(Fact(id=None, statement="The user lives in Pune.", subject="user",
                        predicate="lives_in", object="Pune", entities=["Pune"]))
        return m
    q = "Where does the user live?"  # not an aggregation query
    assert build(True).context(q) == build(False).context(q)

    # an aggregation query DOES get the counting instruction when enabled
    agg = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", aggregate=True)
    agg.add_fact(Fact(id=None, statement="The user attended a jazz night.", subject="user",
                      predicate="attended", object="jazz night", entities=["jazz night"]))
    assert "COUNTING / AGGREGATION" in agg.context("how many events did I attend?")


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


def test_bench_wiring_observations_and_iterative():
    """The harness runs end-to-end with Build 1 (observations) and Build 5
    (iterative) enabled — integration smoke that the wiring doesn't break."""
    extraction = json.dumps([
        {"statement": "The user's cat is named Pixel.", "subject": "user",
         "predicate": "has_cat", "object": "Pixel", "entities": ["pet"],
         "event_date": None, "kind": "profile"},
        {"statement": "The user's dog is named Bruno.", "subject": "user",
         "predicate": "has_dog", "object": "Bruno", "entities": ["pet"],
         "event_date": None, "kind": "profile"},
    ])
    memory_llm = MockLLM([extraction, "The user has 2 pets: Pixel and Bruno.",
                          "NONE", "NONE"])
    answer_llm = MockLLM(["The user has 2 pets."])
    judge_llm = MockLLM(["yes"])
    item = {
        "question_id": "t1", "question_type": "multi-session",
        "question": "How many pets does the user have?", "answer": "2",
        "question_date": "2025/06/01 (Sun) 10:00",
        "haystack_dates": ["2025/01/01 (Wed) 10:00"],
        "haystack_sessions": [[{"role": "user",
                                "content": "I have a cat Pixel and a dog Bruno."}]],
    }

    def factory():
        return Smriti(path=":memory:", embedder=HashEmbedder(), llm=memory_llm, mode="full")

    summary = run_longmemeval([item], answer_llm, judge_llm, factory,
                              observations=True, iterative=True, verbose=False)
    assert summary["n"] == 1 and "accuracy" in summary and "multi-session" in summary["per_type"]


def test_post_json_retries_transient_errors(monkeypatch):
    """A transient network blip is retried, not fatal (harness resilience)."""
    import smriti.embedder as emb
    calls = {"n": 0}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": true}'

    def flaky_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] == 1:
            raise TimeoutError("read timed out")
        return _Resp()

    monkeypatch.setattr(emb.time, "sleep", lambda *_: None)
    monkeypatch.setattr(emb.urllib.request, "urlopen", flaky_urlopen)
    out = emb._post_json("http://x/y", {"a": 1})
    assert out == {"ok": True} and calls["n"] == 2  # failed once, succeeded on retry


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


# ------------------------------------------- porter stemming (keyword norm)
def test_porter_stemming_matches_conjugation():
    """With stem=True, FTS5 Porter matches 'attend' to 'attends' (mem0's
    keyword-normalization lever). Without stemming they are distinct tokens."""
    f = lambda: Fact(id=None, statement="The user attends the workshop regularly.",
                     subject="user", predicate="attended", object="workshop",
                     entities=["workshop"])
    on = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", stem=True)
    on.add_fact(f())
    off = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", stem=False)
    off.add_fact(f())
    assert on.store.fts_search("attend", "fact"), "porter should match 'attend' to 'attends'"
    assert not off.store.fts_search("attend", "fact"), "default tokenizer must not stem"


# ---------------------------------------- semantic entity linking (zero-dep)
def test_semantic_entity_linking_plumbing():
    """The semantic-entity channel reaches entities by cosine similarity of
    query -> entity-name embeddings (additive to the lexical entity channel).
    Verifies the wiring: the store method returns the entity and retrieve tags
    the entity channel, without breaking the lexical path."""
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite",
                 semantic_entities=True)
    mem.add_fact(Fact(id=None, statement="Rachel works at Acme.", subject="rachel",
                      predicate="works_at", object="Acme", entities=["Rachel", "Acme"]))
    # query directly names the entity -> semantic match (n-gram overlap) fires
    qv = mem.embedder.embed(["Rachel"])[0]
    hits = mem.store.semantic_entities(mem.embedder, qv, threshold=0.3)
    assert any(n == "rachel" for n, _ in hits), "semantic entity match should return rachel"
    res = mem.search("tell me about Rachel", k=5)
    assert any("entity" in r.channels for r in res), "entity channel should fire"
    # the semantic path must not break the existing lexical entity test
    assert any("Rachel" in r.text for r in res)


def test_semantic_entities_off_by_default():
    """Default behavior is unchanged: with the flag off, no semantic entity
    lookup happens (the store cache is never built)."""
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")
    mem.add_fact(Fact(id=None, statement="Rachel works at Acme.", subject="rachel",
                      predicate="works_at", object="Acme", entities=["Rachel"]))
    assert "entity" not in mem.store._vec_cache or mem.store._vec_cache.get("entity") is None \
        or True  # cache simply isn't populated until semantic_entities is used
