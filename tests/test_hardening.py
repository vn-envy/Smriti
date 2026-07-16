"""Hardening regression suite (0.3.0) — the production behaviors Sol's review
demanded receipts for: idempotent ingestion, owner-initiated erasure, entity
aliases, export/import round trips, secret redaction, WAL durability,
contradiction/knowledge-update handling, date parsing, multilingual content,
and noisy-haystack retrieval. All offline: HashEmbedder + MockLLM."""
import json

from smriti import Fact, HashEmbedder, MockLLM, Smriti
from smriti.memory import redact_secrets
from smriti.retrieval import extract_dates


def lite(**kw):
    return Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite", **kw)


def full(responses, **kw):
    return Smriti(path=":memory:", embedder=HashEmbedder(),
                  llm=MockLLM(responses), mode="full", **kw)


def fact_json(statement, subject, predicate, obj, entities, event_date=None):
    return json.dumps([{"statement": statement, "subject": subject,
                        "predicate": predicate, "object": obj,
                        "entities": entities, "event_date": event_date,
                        "kind": "profile"}])


# ------------------------------------------------------------- WAL / storage
def test_wal_mode_on_file_db(tmp_path):
    mem = Smriti(path=str(tmp_path / "m.db"), embedder=HashEmbedder(), mode="lite")
    mode = mem.store.db.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


def test_two_connections_same_file(tmp_path):
    p = str(tmp_path / "shared.db")
    a = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    b = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    a.add([{"role": "user", "content": "writer A stored the launch date."}],
          timestamp="2026-01-01T10:00:00Z")
    b.add([{"role": "user", "content": "writer B stored the venue address."}],
          timestamp="2026-01-01T11:00:00Z")
    assert b.stats()["episodes"] == 2  # B sees A's write through WAL


def test_reopen_after_close_preserves_memory(tmp_path):
    p = str(tmp_path / "durable.db")
    m1 = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    m1.add([{"role": "user", "content": "The vault code discussion happened at Begumpet."}],
           timestamp="2026-02-02T10:00:00Z")
    m1.store.db.close()
    m2 = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    hits = m2.search("Begumpet vault", k=3)
    assert any("Begumpet" in r.text for r in hits)


# ------------------------------------------------------- idempotent ingestion
def test_duplicate_session_is_deduped():
    mem = lite()
    msgs = [{"role": "user", "content": "I adopted a golden retriever named Bruno."}]
    first = mem.add(msgs, session_id="s1", timestamp="2026-03-01T10:00:00Z")
    replay = mem.add(msgs, session_id="s1", timestamp="2026-03-01T10:00:00Z")
    assert first["episodes"] == 1
    assert replay.get("deduped") is True and replay["episodes"] == 0
    assert mem.stats()["episodes"] == 1


def test_dedupe_respects_content_timestamp_and_session():
    mem = lite()
    msgs = [{"role": "user", "content": "same words"}]
    mem.add(msgs, session_id="s1", timestamp="2026-03-01T10:00:00Z")
    out2 = mem.add(msgs, session_id="s1", timestamp="2026-03-02T10:00:00Z")  # new ts
    out3 = mem.add(msgs, session_id="s2", timestamp="2026-03-01T10:00:00Z")  # new session
    assert not out2.get("deduped") and not out3.get("deduped")
    assert mem.stats()["episodes"] == 3


def test_dedupe_false_forces_reingest():
    mem = lite()
    msgs = [{"role": "user", "content": "repeat me"}]
    mem.add(msgs, session_id="s1", timestamp="2026-03-01T10:00:00Z")
    forced = mem.add(msgs, session_id="s1", timestamp="2026-03-01T10:00:00Z", dedupe=False)
    assert forced["episodes"] == 1
    assert mem.stats()["episodes"] == 2


# ----------------------------------------------------------------- erasure
def test_erase_session_cascades_and_spares_others():
    mem = full([
        fact_json("The user lives in Hyderabad.", "user", "lives_in", "Hyderabad", ["Hyderabad"]),
        fact_json("The user plays veena.", "user", "plays", "veena", ["veena"]),
    ])
    mem.add([{"role": "user", "content": "I live in Hyderabad."}],
            session_id="keep", timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "I play the veena."}],
            session_id="erase-me", timestamp="2026-01-02T10:00:00Z")
    out = mem.erase_session("erase-me")
    assert out["episodes"] == 1 and out["facts"] == 1
    s = mem.stats()
    assert s["episodes"] == 1 and s["facts"] == 1
    # erased content is gone from every channel
    assert not any("veena" in r.text for r in mem.search("veena", k=10))
    assert mem.store.fts_search("veena", "fact") == []
    assert mem.store.fts_search("veena", "episode") == []
    # the surviving session still answers
    assert any("Hyderabad" in r.text for r in mem.search("where does the user live?", k=5))


def test_erase_session_allows_reingest_after_erasure():
    mem = lite()
    msgs = [{"role": "user", "content": "ephemeral note"}]
    mem.add(msgs, session_id="s1", timestamp="2026-04-01T10:00:00Z")
    mem.erase_session("s1")
    again = mem.add(msgs, session_id="s1", timestamp="2026-04-01T10:00:00Z")
    assert not again.get("deduped")  # erasure also clears the ingest log
    assert mem.stats()["episodes"] == 1


def test_erase_entity_removes_facts_keeps_episodes():
    mem = full([fact_json("Rachel works at Acme.", "rachel", "works_at", "Acme",
                          ["Rachel", "Acme"])])
    mem.add([{"role": "user", "content": "Rachel works at Acme now."}],
            session_id="s1", timestamp="2026-01-05T10:00:00Z")
    out = mem.erase_entity("Rachel")
    assert out["facts"] == 1
    assert mem.stats()["facts"] == 0
    assert mem.stats()["episodes"] == 1  # transcript untouched by design


def test_erase_superseding_fact_clears_dangling_pointer():
    mem = full([
        fact_json("The user lives in Hyderabad.", "user", "lives_in", "Hyderabad",
                  ["Hyderabad"]),
        fact_json("The user lives in Bengaluru.", "user", "lives_in", "Bengaluru",
                  ["Bengaluru"], event_date="2026-06-01"),
    ])
    mem.add([{"role": "user", "content": "I live in Hyderabad."}],
            session_id="a", timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "I moved to Bengaluru."}],
            session_id="b", timestamp="2026-06-02T10:00:00Z")
    mem.erase_session("b")  # erase the SUPERSEDING session
    rows = mem.store.db.execute(
        "SELECT superseded_by FROM facts WHERE invalid_at IS NOT NULL").fetchall()
    assert all(r[0] is None for r in rows)  # no dangling pointers


# ------------------------------------------------------------------ aliases
def test_alias_read_time_resolution():
    mem = full([fact_json("Rachel works at Acme.", "rachel", "works_at", "Acme",
                          ["Rachel"])])
    mem.add([{"role": "user", "content": "Rachel works at Acme."}],
            timestamp="2026-01-01T10:00:00Z")
    mem.add_alias("Rachel Smith", "Rachel")
    hits = mem.search("what does rachel smith do?", k=5, profile="relations")
    assert any("Acme" in r.text and r.kind == "fact" for r in hits)


def test_alias_write_time_canonicalization():
    mem = lite()
    mem.add_alias("bob's startup", "acme")
    fid = mem.add_fact(Fact(id=None, statement="Acme raised a seed round.",
                            subject="acme", predicate="raised", object="seed",
                            entities=["Bob's Startup"]), resolve_conflicts=False)
    assert fid is not None
    assert mem.store.facts_for_entity("acme")  # linked under canonical
    assert not mem.store.facts_for_entity("bob's startup")


def test_alias_chain_flattens():
    mem = lite()
    mem.add_alias("rachel smith", "rachel")
    mem.add_alias("rae", "rachel smith")   # chains to rachel smith -> rachel
    assert mem.store.resolve_entity("rae") == "rachel"


# ------------------------------------------------------------ export/import
def test_export_import_roundtrip_preserves_supersession(tmp_path):
    mem = full([
        fact_json("The user lives in Hyderabad.", "user", "lives_in", "Hyderabad",
                  ["Hyderabad"]),
        fact_json("The user lives in Bengaluru.", "user", "lives_in", "Bengaluru",
                  ["Bengaluru"], event_date="2026-06-01"),
    ])
    mem.add([{"role": "user", "content": "I live in Hyderabad."}],
            timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "I moved to Bengaluru."}],
            timestamp="2026-06-02T10:00:00Z")
    path = str(tmp_path / "backup.json")
    out = mem.export_json(path)
    assert out["facts"] == 2

    fresh = lite()
    fresh.import_json(path)
    assert fresh.stats()["facts"] == 2 and fresh.stats()["episodes"] == 2
    ctx = fresh.context("where do I live?")
    assert "SUPERSEDED" in ctx and "CURRENT" in ctx and "Bengaluru" in ctx
    # embeddings survived: vector channel works without re-embedding
    assert fresh.search("which city is home?", k=5)


def test_import_refuses_nonempty_store(tmp_path):
    mem = lite()
    mem.add([{"role": "user", "content": "seed"}], timestamp="2026-01-01T00:00:00Z")
    path = str(tmp_path / "x.json")
    mem.export_json(path)
    try:
        mem.import_json(path)
        assert False, "expected ValueError on non-empty import target"
    except ValueError:
        pass


# ---------------------------------------------------------------- redaction
def test_redact_patterns():
    s = redact_secrets("key sk-abcdefghijklmnop1234 and ghp_ABCDEFGHIJKLMNOPQRSTuvwx "
                       "and AKIAABCDEFGHIJKLMNOP and password: hunter2secret")
    assert "sk-abcdefghijklmnop1234" not in s
    assert "ghp_" not in s and "AKIA" not in s and "hunter2secret" not in s
    assert s.count("[REDACTED]") >= 4


def test_redaction_applies_before_persistence():
    mem = lite(redact=True)
    mem.add([{"role": "user", "content": "my api_key = sk-verysecretkey12345678 ok"}],
            timestamp="2026-01-01T10:00:00Z")
    rows = mem.store.db.execute("SELECT content FROM episodes").fetchall()
    assert all("sk-verysecretkey12345678" not in r[0] for r in rows)
    assert any("[REDACTED]" in r[0] for r in rows)


def test_redaction_off_by_default():
    mem = lite()
    mem.add([{"role": "user", "content": "the word token: abc123xyz789 stays"}],
            timestamp="2026-01-01T10:00:00Z")
    rows = mem.store.db.execute("SELECT content FROM episodes").fetchall()
    assert any("abc123xyz789" in r[0] for r in rows)


# ------------------------------------------- contradictions / updates / dates
def test_contradiction_annotated_not_silently_resolved():
    mem = full([
        fact_json("The user is vegetarian.", "user", "diet", "vegetarian", []),
        fact_json("The user eats chicken.", "user", "diet", "chicken", []),
    ])
    mem.add([{"role": "user", "content": "I'm vegetarian."}],
            timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "Had chicken for dinner."}],
            timestamp="2026-03-01T10:00:00Z")
    ctx = mem.context("what is the user's diet?")
    # key-collision supersession: old value visible as history, new as current
    assert "SUPERSEDED" in ctx and "CURRENT" in ctx


def test_extract_dates_variants():
    assert extract_dates("we met on 2026-03-05") == ["2026-03-05"]
    # day-precise parse ranks first; the month-level fallback may follow
    assert extract_dates("we met on 5 March 2026")[0] == "2026-03-05"
    assert extract_dates("we met on March 5, 2026")[0] == "2026-03-05"
    assert extract_dates("back in March 2026 sometime") == ["2026-03-15"]
    assert extract_dates("no dates here") == []


# ------------------------------------------------------------- multilingual
def test_devanagari_content_is_searchable_lexically():
    mem = lite()
    mem.add([{"role": "user", "content": "मैं बेंगलुरु में रहता हूँ और वीणा बजाता हूँ"}],
            timestamp="2026-01-01T10:00:00Z")
    hits = mem.store.fts_search("बेंगलुरु", "episode")
    assert hits, "unicode tokens must reach FTS5 (the \\w+ fix)"
    results = mem.search("वीणा", k=3)
    assert any("वीणा" in r.text for r in results)


# ------------------------------------------------------------ noisy haystack
def test_needle_survives_noisy_typo_haystack():
    mem = lite()
    for i in range(30):
        mem.add([{"role": "user", "content":
                  f"random chatter #{i}: weathr updates, recipies, lorem ipsum blah"}],
                timestamp=f"2026-01-{(i % 27) + 1:02d}T10:00:00Z")
    mem.add([{"role": "user", "content":
              "IMPORTANT: the notary appointment is at Koramangala office, counter 4."}],
            timestamp="2026-02-01T10:00:00Z")
    hits = mem.search("where is my notary appointment?", k=5)
    assert any("Koramangala" in r.text for r in hits)
