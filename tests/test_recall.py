"""Evidence-first recall (smriti.recall) and temporal grounding (smriti.temporal)."""
import re
from datetime import date

import pytest

from smriti import HashEmbedder, Smriti
from smriti.recall import (RecallConfig, addresses_assistant, alternatives, excerpt,
                           query_terms, speaker_of)
from smriti.temporal import annotate, find_mentions, query_window
from smriti.types import Episode

ANCHOR = "2023-05-08T10:00:00Z"  # a Monday


# ---------------------------------------------------------------- temporal
@pytest.mark.parametrize("text,label", [
    ("I went to a support group yesterday.", "yesterday [2023-05-07]"),
    ("We went camping last weekend.", "last weekend [2023-05-06..2023-05-07]"),
    ("I adopted a dog last Friday.", "last Friday [2023-05-05]"),
    ("It was 3 days ago.", "3 days ago [2023-05-05]"),
    ("I ran a race two weeks ago.", "two weeks ago [2023-04-24..2023-04-30]"),
    ("We moved a couple of months ago.", "a couple of months ago [2023-03]"),
    ("I start next month.", "next month [2023-06]"),
    ("the day before yesterday", "the day before yesterday [2023-05-06]"),
    ("I painted a lot last year.", "last year [2022]"),
])
def test_annotate_resolves_relative_dates(text, label):
    assert label in annotate(text, ANCHOR)


def test_annotate_leaves_ambiguous_and_absolute_text_alone():
    for text in ("See you on Friday.", "I recently moved.", "It happened in 2019."):
        assert annotate(text, ANCHOR) == text
    assert annotate("yesterday", None) == "yesterday"


def test_mentions_do_not_overlap_and_keep_order():
    ms = find_mentions("the day before yesterday and yesterday", ANCHOR)
    assert [m.phrase for m in ms] == ["the day before yesterday", "yesterday"]


def test_last_weekend_on_a_weekend_anchor_is_the_previous_one():
    sat = "2023-05-13"
    m = find_mentions("last weekend", sat)[0]
    assert (m.first, m.last) == (date(2023, 5, 6), date(2023, 5, 7))


def test_query_window_variants():
    assert query_window("What did I do last weekend?", ANCHOR) == (date(2023, 5, 6), date(2023, 5, 7))
    assert query_window("What happened in March?", ANCHOR) == (date(2023, 3, 1), date(2023, 3, 31))
    assert query_window("What did I buy on 2023-04-02?", ANCHOR) == (date(2023, 4, 2), date(2023, 4, 2))
    assert query_window("What did I do in May 2023?", None) == (date(2023, 5, 1), date(2023, 5, 31))
    lo, hi = query_window("books I read in the past two months", ANCHOR)
    assert hi == date(2023, 5, 8) and (hi - lo).days == 62
    assert query_window("When did Caroline go?", ANCHOR) is None


# --------------------------------------------------------------- helpers
def test_query_terms_drop_filler():
    terms = query_terms("Can you remind me what the dentist address was?")
    assert terms == ["dentist", "address"]
    assert query_terms("the") == ["the"]  # stopword-only queries fall back


def test_addresses_assistant():
    assert addresses_assistant("What did you recommend for my trip?")
    assert addresses_assistant("In our previous chat, what was the recipe?")
    assert addresses_assistant("Remind me of that dessert shop we talked about last time?")
    assert addresses_assistant("Looking back at our previous chess game, what move did you make?")
    assert not addresses_assistant("Can you tell me where I live?")


def test_alternatives_only_for_ordering_questions():
    assert alternatives("Which did I do first, the pottery class or the yoga retreat?") == \
        ["the pottery class", "the yoga retreat"]
    assert alternatives("Do I prefer tea or coffee?") == []


def test_speaker_of_role_and_prefix():
    assert speaker_of(Episode(1, "s", "Caroline", "hi", None)) == "caroline"
    assert speaker_of(Episode(1, "s", "user", "Melanie: I painted.", None)) == "melanie"
    assert speaker_of(Episode(1, "s", "user", "no prefix here", None)) is None


def test_excerpt_keeps_the_answer_sentence_not_the_prefix():
    filler = " ".join(f"Sentence number {i} is filler about nothing." for i in range(40))
    text = filler + " The rotation for Admon on Sunday is the 8am to 4pm shift."
    out = excerpt(text, "What was the rotation for Admon on a Sunday?", 400)
    assert "Admon on Sunday" in out and len(out) <= 420
    assert excerpt("short text", "anything", 400) == "short text"


# ------------------------------------------------------------ end-to-end
def _mem(**kw):
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", **kw)
    mem.add([{"role": "user", "content": "I live in Hyderabad with my cat Pixel."},
             {"role": "assistant", "content": "Hyderabad is lovely. " * 30}],
            session_id="s1", timestamp="2023-01-10T10:00:00Z")
    mem.add([{"role": "user", "content": "I went to a pottery class yesterday and made a bowl."}],
            session_id="s2", timestamp="2023-05-08T10:00:00Z")
    long_turn = ("Here is the plan. " * 120) + "Your dentist appointment is at Begumpet clinic."
    mem.add([{"role": "user", "content": "Where is my dentist appointment?"},
             {"role": "assistant", "content": long_turn}],
            session_id="s3", timestamp="2023-06-01T10:00:00Z")
    return mem


def test_default_context_is_evidence_first_and_grouped_by_session():
    mem = _mem()
    ctx = mem.context("When did I go to the pottery class?", now="2023-06-02")
    assert "CONVERSATION EVIDENCE" in ctx
    assert "[Session 2023-05-08 Mon]" in ctx
    assert "yesterday [2023-05-07]" in ctx          # resolved relative date
    assert "(Current date: 2023-06-02 Fri)" in ctx
    stamps = re.findall(r"\[Session (\d{4}-\d{2}-\d{2})", ctx)
    assert stamps == sorted(stamps)                  # chronological sessions


def test_long_turn_keeps_answer_via_query_focused_excerpt():
    mem = _mem()
    ctx = mem.context("Where is my dentist appointment clinic?", char_budget=3000)
    assert "Begumpet" in ctx
    assert len(ctx) <= 3000


def test_budget_is_respected():
    mem = _mem()
    for budget in (400, 1200, 9000):
        assert len(mem.context("pottery class", char_budget=budget)) <= budget


def test_fusion_engine_remains_available_and_unchanged():
    legacy = _mem(read_engine="fusion")
    ctx = legacy.context("Where do I live?")
    assert "RAW CONVERSATION EVIDENCE" in ctx
    with pytest.raises(ValueError):
        _mem(read_engine="bogus")


def test_search_returns_ranked_episodes_with_internal_channel_names():
    mem = _mem()
    hits = mem.search("pottery class bowl", k=3)
    assert hits and hits[0].kind == "episode" and "pottery" in hits[0].text
    assert set(hits[0].channels) <= {"bm25_episode", "vec_episode", "temporal", "rerank"}


def test_time_window_prior_prefers_turns_in_the_window():
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")
    mem.add([{"role": "user", "content": "I baked sourdough bread."}], session_id="a",
            timestamp="2023-02-11T10:00:00Z")
    mem.add([{"role": "user", "content": "I baked banana bread."}], session_id="b",
            timestamp="2023-05-06T10:00:00Z")
    hits = mem.search("What bread did I bake last weekend?", now="2023-05-08", k=2)
    assert "banana" in hits[0].text
    assert "temporal" in hits[0].channels


def test_assistant_turns_are_softened_unless_addressed():
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")
    mem.add([{"role": "user", "content": "My favourite hiking trail is Kedarkantha."},
             {"role": "assistant", "content": "Kedarkantha hiking trail is a great favourite."}],
            session_id="h", timestamp="2023-01-01T00:00:00Z")
    user_first = mem.search("my favourite hiking trail", k=2)
    assert user_first[0].role == "user"
    asked = mem.search("which hiking trail did you recommend as a favourite?", k=2)
    assert {h.role for h in asked} == {"user", "assistant"}


def test_contextual_embeddings_keep_stored_text():
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite",
                 contextual_embeddings=100)
    mem.add([{"role": "user", "content": "Did you paint that?"},
             {"role": "user", "content": "Yes, a lake sunrise."}], session_id="p")
    rows = [r[0] for r in mem.store.db.execute("SELECT content FROM episodes ORDER BY id")]
    assert rows == ["Did you paint that?", "Yes, a lake sunrise."]


def test_recall_config_overrides_are_immutable_copies():
    base = RecallConfig()
    tuned = base.with_overrides(depth=10)
    assert base.depth != 10 and tuned.depth == 10


def test_onnx_embedder_reports_missing_model(tmp_path):
    pytest.importorskip("onnxruntime")
    pytest.importorskip("tokenizers")
    from smriti.onnx_embedder import OnnxEmbedder
    with pytest.raises(FileNotFoundError):
        OnnxEmbedder(str(tmp_path))


def test_iterative_context_uses_evidence_packing_and_follow_up():
    from smriti import MockLLM
    llm = MockLLM(["[]", "[]", "Priya's research field"])
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add([{"role": "user", "content": "My mentor is Priya."}], session_id="a",
            timestamp="2023-01-01T00:00:00Z")
    mem.add([{"role": "user", "content": "Priya researches coral reef ecology."}], session_id="b",
            timestamp="2023-02-01T00:00:00Z")
    ctx = mem.context_iterative("What is my mentor's research field?", k=1)
    assert "CONVERSATION EVIDENCE" in ctx
    assert "coral reef" in ctx


@pytest.mark.parametrize("layout", ["chrono", "relevance", "top"])
def test_layouts_render_within_budget(layout):
    from smriti import RetrievalProfile
    mem = _mem()
    prof = RetrievalProfile(name="evidence", engine="evidence",
                            recall=RecallConfig(layout=layout))
    ctx = mem.context("pottery class bowl", profile=prof, char_budget=2500)
    assert "pottery" in ctx and len(ctx) <= 2500
    if layout == "top":
        assert "MOST RELEVANT EXCERPTS" in ctx
