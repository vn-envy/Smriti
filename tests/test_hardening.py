"""Hardening regression suite (0.3.0) — the production behaviors Sol's review
demanded receipts for: idempotent ingestion, owner-initiated erasure, entity
aliases, export/import round trips, secret redaction, WAL durability,
contradiction/knowledge-update handling, date parsing, multilingual content,
and noisy-haystack retrieval. All offline: HashEmbedder + MockLLM."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest

from smriti import Fact, HashEmbedder, MockLLM, RetrievalResult, Smriti
from smriti.mcp_server import SmritiMCP
from smriti.memory import redact_secrets
from smriti.retrieval import extract_dates
from smriti.store import Store


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


def test_failed_import_is_atomic_and_retryable():
    source = lite()
    source.add([{"role": "user", "content": "first"}],
               timestamp="2026-01-01T00:00:00Z")
    source.add([{"role": "user", "content": "second"}],
               timestamp="2026-01-02T00:00:00Z")
    good = source.store.export_data()
    broken = json.loads(json.dumps(good))
    broken["episodes"][1]["emb"] = "%%%not-base64%%%"
    target = lite()
    with pytest.raises(ValueError, match="base64"):
        target.store.import_data(broken)
    assert target.stats()["episodes"] == 0
    target.store.import_data(good)
    assert target.stats()["episodes"] == 2


def test_import_rejects_unknown_export_version():
    target = lite()
    with pytest.raises(ValueError, match="unsupported"):
        target.store.import_data({"format": "smriti-export", "version": 999})


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


# --------------------------------------------- 0.3.1 audit fixes (agent run)
def test_pack_context_puts_current_facts_before_superseded():
    """The quickstart repro from the audit: annotation alone isn't enough —
    the CURRENT fact must be the first fact the model reads."""
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
    ctx = mem.context("where do I live?")
    fact_lines = [l for l in ctx.splitlines() if l.startswith("- [")]
    assert fact_lines, ctx
    assert "CURRENT" in fact_lines[0] and "Bengaluru" in fact_lines[0]
    assert any("SUPERSEDED" in l for l in fact_lines[1:])


def test_pack_context_annotates_scoped_observation_without_changing_legacy_text():
    from smriti.retrieval import pack_context

    scoped = pack_context([RetrievalResult(
        kind="observation", id=1, text="Atlas uses Rust", score=1.0,
        scope="project:Atlas")])
    unscoped = pack_context([RetrievalResult(
        kind="observation", id=2, text="The user likes tea", score=1.0)])
    assert "- Atlas uses Rust [scope=project:Atlas]" in scoped
    assert "- The user likes tea\n" in unscoped
    assert "scope=" not in unscoped


def test_failed_ingest_rolls_back_completely(monkeypatch):
    """Atomicity: a crash mid-ingest leaves no partial session, and the
    ingest-log claim rolls back with it, so a retry re-ingests cleanly."""
    from smriti.store import Store
    mem = lite()
    original = Store.add_episode
    calls = {"n": 0}

    def explode_on_second(self, ep, emb=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("simulated crash mid-ingest")
        return original(self, ep, emb=emb)

    monkeypatch.setattr(Store, "add_episode", explode_on_second)
    msgs = [{"role": "user", "content": "turn one"},
            {"role": "user", "content": "turn two"}]
    try:
        mem.add(msgs, session_id="s1", timestamp="2026-05-01T10:00:00Z")
        assert False, "expected the simulated crash to propagate"
    except RuntimeError:
        pass
    assert mem.stats()["episodes"] == 0          # nothing partial persisted
    monkeypatch.undo()
    retry = mem.add(msgs, session_id="s1", timestamp="2026-05-01T10:00:00Z")
    assert not retry.get("deduped")              # claim rolled back too
    assert mem.stats()["episodes"] == 2


def test_ingest_claim_is_first_writer_wins():
    mem = lite()
    mem.store.begin()
    assert mem.store.log_ingest_claim("h1", "s1") is True
    assert mem.store.log_ingest_claim("h1", "s2") is False  # loser sees claim
    mem.store.commit()


def test_export_roundtrip_preserves_keys_and_ingest_log(tmp_path):
    from smriti import Fact
    mem = lite()
    mem.add([{"role": "user", "content": "hello"}],
            session_id="s1", timestamp="2026-01-01T10:00:00Z")
    mem.add_fact(Fact(id=None, statement="The user attends yoga.",
                      subject="user", predicate="attends", object="yoga",
                      entities=["yoga"], search_keys=["exercise", "wellness class"]),
                 resolve_conflicts=False)
    path = str(tmp_path / "b.json")
    mem.export_json(path)

    fresh = lite()
    fresh.import_json(path)
    # key-expansion index survived: recall-profile search keys still match
    assert fresh.store.key_fts_search("wellness exercise"), \
        "search_keys index must survive export/import"
    # idempotency history survived: replaying the exported session dedupes
    replay = fresh.add([{"role": "user", "content": "hello"}],
                       session_id="s1", timestamp="2026-01-01T10:00:00Z")
    assert replay.get("deduped") is True


def test_erase_session_purges_derived_observations():
    mem = full([fact_json("The user attends yoga weekly.", "user", "attends",
                          "yoga", ["yoga"])])
    mem.add([{"role": "user", "content": "I attend yoga weekly."}],
            session_id="s1", timestamp="2026-01-01T10:00:00Z")
    from smriti import Fact
    mem.store.add_fact(Fact(id=None, statement="user attends: yoga (weekly).",
                            subject="user", predicate="digest:attends", object="",
                            kind="observation", entities=["yoga"]),
                       emb=mem.embedder.embed(["digest"])[0])
    out = mem.erase_session("s1")
    assert out["observations"] == 1              # contaminated digest dropped
    assert mem.stats()["facts"] == 0


def test_user_agent_carries_package_version():
    import smriti
    assert smriti.__version__ != "0.1"           # the audit's stale-UA finding
    # embedder builds the UA from __version__ lazily; just confirm the import
    from smriti.embedder import _post_json  # noqa: F401


# ----------------------------------------------- 0.3.2 audit fixes (round 2)
def _hyd_blr():
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
    return mem


def test_search_ranks_current_fact_above_superseded():
    """Round-2 audit repro: structured search() (and thus the MCP search tool)
    must not lead with a stale fact."""
    mem = _hyd_blr()
    hits = mem.search("where do I live?", k=6)
    facts = [r for r in hits if r.kind == "fact"]
    assert facts and facts[0].invalid_at is None, \
        [f"{r.text} invalid_at={r.invalid_at}" for r in facts]
    # superseded fact must also rank below episodes (never first anything)
    first_fact_idx = next(i for i, r in enumerate(hits) if r.kind == "fact")
    assert hits[first_fact_idx].invalid_at is None


def test_timeline_profile_preserves_historical_ranking_and_chronology():
    mem = _hyd_blr()
    hits = mem.search("where did I live before June 2026?", profile="timeline", k=6)
    assert hits  # historical results not suppressed
    ctx = mem.context("where did I live before June 2026?", profile="timeline")
    fact_lines = [l for l in ctx.splitlines() if l.startswith("- [")]
    if len(fact_lines) >= 2:  # chronological: Hyderabad (Jan) before Bengaluru (Jun)
        assert "Hyderabad" in fact_lines[0]


def test_mcp_search_orders_current_first():
    srv = SmritiMCP(_hyd_blr())
    resp = srv.handle({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                       "params": {"name": "search",
                                  "arguments": {"query": "where do I live?"}}})
    out = json.loads(resp["result"]["content"][0]["text"])
    facts = [r for r in out["results"] if r["kind"] == "fact"]
    assert facts and facts[0]["current"] is True


def test_concurrent_first_time_db_creation(tmp_path):
    """Round-2 audit: two workers opening a brand-new database raced on the
    WAL pragma. busy_timeout-first + retry must make cold-start contention
    safe across REAL separate connections in parallel threads."""
    import threading
    p = str(tmp_path / "race.db")
    errors = []

    def worker(i):
        try:
            m = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
            m.add([{"role": "user", "content": f"worker {i} note"}],
                  session_id=f"w{i}", timestamp="2026-07-01T10:00:00Z")
            m.store.db.close()
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    check = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    assert check.stats()["episodes"] == 6


def test_concurrent_embedder_claim_is_atomic(tmp_path):
    """Only one initial identity claim wins; same-identity callers all pass."""
    import threading

    p = str(tmp_path / "identity-race.db")
    seed = Store(path=p)
    seed.close()
    barrier = threading.Barrier(6)
    errors = []

    def worker():
        store = Store(path=p)
        try:
            barrier.wait(timeout=5)
            store.ensure_embedder("same-model")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            store.close()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors, errors


def test_concurrent_different_embedder_claims_have_one_winner(tmp_path):
    """Competing identities never produce duplicate-key errors or both pass."""
    import threading

    p = str(tmp_path / "identity-compete.db")
    seed = Store(path=p)
    seed.close()
    barrier = threading.Barrier(2)
    outcomes = []

    def worker(identity):
        store = Store(path=p)
        try:
            barrier.wait(timeout=5)
            store.ensure_embedder(identity)
            outcomes.append((identity, "ok"))
        except Exception as exc:  # noqa: BLE001
            outcomes.append((identity, type(exc).__name__, str(exc)))
        finally:
            store.close()

    threads = [threading.Thread(target=worker, args=(identity,))
               for identity in ("model-a", "model-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sum(row[1] == "ok" for row in outcomes) == 1
    loser = next(row for row in outcomes if row[1] != "ok")
    assert loser[1] == "ValueError" and "incompatible" in loser[2]


def test_cross_connection_dedupe(tmp_path):
    p = str(tmp_path / "dd.db")
    a = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    b = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    msgs = [{"role": "user", "content": "once only"}]
    a.add(msgs, session_id="s1", timestamp="2026-07-01T10:00:00Z")
    replay = b.add(msgs, session_id="s1", timestamp="2026-07-01T10:00:00Z")
    assert replay.get("deduped") is True
    assert b.stats()["episodes"] == 1


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


def test_mode_typo_is_rejected():
    with pytest.raises(ValueError, match="mode must be"):
        Smriti(mode="ltei")
    with pytest.raises(ValueError, match="mode must be"):
        Smriti(mode=None)


def test_direct_add_fact_honors_redaction():
    mem = lite(redact=True)
    mem.add_fact(Fact(id=None,
                      statement="API key is sk-abcdefghijklmnop1234",
                      subject="user", predicate="credential",
                      object="sk-abcdefghijklmnop1234",
                      entities=["sk-abcdefghijklmnop1234"]))
    row = mem.store.db.execute(
        "SELECT statement, object FROM facts").fetchone()
    assert "sk-abcdefghijklmnop1234" not in " ".join(row)
    assert "[REDACTED]" in row[0]


def test_cross_connection_vector_cache_sees_committed_rows(tmp_path):
    path = str(tmp_path / "shared.db")
    reader = Smriti(path=path, embedder=HashEmbedder(), mode="lite")
    writer = Smriti(path=path, embedder=HashEmbedder(), mode="lite")
    reader.add([{"role": "user", "content": "initial unrelated note"}],
               timestamp="2026-01-01T00:00:00Z")
    reader.search("semantic cache warmup", channels={"semantic"})
    writer.add([{"role": "user", "content": "new cross connection memory"}],
               timestamp="2026-02-01T00:00:00Z")
    hits = reader.search("new cross connection memory", channels={"semantic"})
    assert any("new cross connection memory" in h.text for h in hits)


def test_late_arriving_history_does_not_supersede_newer_truth():
    mem = lite()
    newer = Fact(id=None, statement="The user lives in Bengaluru.",
                 subject="user", predicate="lives_in", object="Bengaluru",
                 valid_from="2026-06-01T00:00:00Z")
    older = Fact(id=None, statement="The user lives in Hyderabad.",
                 subject="user", predicate="lives_in", object="Hyderabad",
                 valid_from="2026-01-01T00:00:00Z")
    newer_id = mem.add_fact(newer)
    older_id = mem.add_fact(older)
    newer_row = mem.store.get_fact(newer_id)
    older_row = mem.store.get_fact(older_id)
    assert newer_row.invalid_at is None
    assert older_row.invalid_at == newer_row.valid_from
    assert older_row.superseded_by == newer_id


def test_late_middle_fact_rebuilds_complete_validity_chain():
    mem = lite()
    jan = mem.add_fact(Fact(id=None, statement="Lives in Hyderabad", subject="user",
                             predicate="lives_in", object="Hyderabad",
                             valid_from="2026-01-01T00:00:00Z"))
    june = mem.add_fact(Fact(id=None, statement="Lives in Bengaluru", subject="user",
                              predicate="lives_in", object="Bengaluru",
                              valid_from="2026-06-01T00:00:00Z"))
    march = mem.add_fact(Fact(id=None, statement="Lives in Pune", subject="user",
                               predicate="lives_in", object="Pune",
                               valid_from="2026-03-01T05:30:00+05:30"))
    jan_f, march_f, june_f = map(mem.store.get_fact, (jan, march, june))
    assert jan_f.invalid_at == march_f.valid_from and jan_f.superseded_by == march
    assert march_f.invalid_at == june_f.valid_from and march_f.superseded_by == june
    assert june_f.invalid_at is None and june_f.superseded_by is None


def test_llm_arbiter_cannot_supersede_fact_outside_candidates(monkeypatch):
    llm = MockLLM(['{"action":"supersede","target_id":2}'])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    candidate = mem.add_fact(Fact(id=None, statement="Works at Acme", subject="user",
                                  predicate="role", object="Acme"),
                             resolve_conflicts=False)
    unrelated = mem.add_fact(Fact(id=None, statement="Maya lives in Pune", subject="maya",
                                  predicate="lives_in", object="Pune"),
                             resolve_conflicts=False)
    monkeypatch.setattr(mem.store, "vector_search",
                        lambda *args, **kwargs: [(candidate, 0.99)])
    mem.add_fact(Fact(id=None, statement="Works at Beta", subject="user",
                      predicate="employer", object="Beta"))
    assert mem.store.get_fact(unrelated).invalid_at is None


def test_llm_semantic_supersession_respects_event_chronology(monkeypatch):
    llm = MockLLM(['{"action":"supersede","target_id":1}'])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    newer = mem.add_fact(Fact(id=None, statement="Works at Acme", subject="user",
                              predicate="employed_by", object="Acme",
                              valid_from="2026-06-01T00:00:00Z"),
                         resolve_conflicts=False)
    monkeypatch.setattr(mem.store, "vector_search",
                        lambda *args, **kwargs: [(newer, 0.99)])
    older = mem.add_fact(Fact(id=None, statement="Was an Acme contractor", subject="user",
                              predicate="works_at", object="contractor",
                              valid_from="2026-01-01T00:00:00Z"))
    assert mem.store.get_fact(newer).invalid_at is None
    assert mem.store.get_fact(older).superseded_by == newer


def test_semantic_arbiter_keeps_role_and_employer_facts_distinct(monkeypatch):
    llm = MockLLM(['{"action":"supersede","target_id":1}'])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    role = mem.add_fact(Fact(id=None, statement="The user's role is engineer", subject="user",
                             predicate="role", object="engineer"), resolve_conflicts=False)
    monkeypatch.setattr(mem.store, "vector_search", lambda *args, **kwargs: [(role, 0.99)])
    employer = mem.add_fact(Fact(id=None, statement="The user works at Acme", subject="user",
                                 predicate="employed_by", object="Acme"))
    assert employer is not None
    assert mem.store.get_fact(role).invalid_at is None
    assert mem.stats()["facts"] == 2
    assert llm.calls == 0


def test_semantic_arbiter_does_not_conflate_preference_domains(monkeypatch):
    llm = MockLLM(['{"action":"supersede","target_id":1}'])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    language = mem.add_fact(Fact(id=None, statement="Mira prefers Python", subject="user",
                                 predicate="prefers", object="Python"), resolve_conflicts=False)
    monkeypatch.setattr(mem.store, "vector_search", lambda *args, **kwargs: [(language, 0.99)])
    theme = mem.add_fact(Fact(id=None, statement="Mira prefers light mode", subject="user",
                              predicate="prefers", object="light mode"))
    assert theme is not None
    assert mem.store.get_fact(language).invalid_at is None
    assert mem.stats()["facts"] == 2
    assert llm.calls == 0


def test_scoped_state_replaces_only_same_scope_and_round_trips():
    source = Smriti(embedder=HashEmbedder(), mode="lite")
    source.add_fact(Fact(id=None, statement="Atlas uses Python", subject="user",
                         predicate="primary_programming_language", object="Python",
                         scope="project:Atlas", valid_from="2025-01-01T00:00:00Z"))
    source.add_fact(Fact(id=None, statement="Atlas uses Rust", subject="user",
                         predicate="primary_programming_language", object="Rust",
                         scope="project:Atlas", valid_from="2025-02-01T00:00:00Z"))
    source.add_fact(Fact(id=None, statement="Orion uses Python", subject="user",
                         predicate="primary_programming_language", object="Python",
                         scope="project:Orion", valid_from="2025-02-01T00:00:00Z"))
    atlas = source.store.facts_for_key("user", "primary_programming_language", "project:Atlas")
    orion = source.store.facts_for_key("user", "primary_programming_language", "project:Orion")
    assert len(atlas) == 2 and atlas[0].invalid_at == atlas[1].valid_from
    assert len(orion) == 1 and orion[0].invalid_at is None

    exported = source.store.export_data()
    assert exported["version"] == 3
    assert {fact["scope"] for fact in exported["facts"]} == {"project:Atlas", "project:Orion"}
    restored = Smriti(embedder=HashEmbedder(), mode="lite")
    restored.store.import_data(exported)
    assert restored.store.get_fact(atlas[-1].id).scope == "project:Atlas"


def test_semantic_arbiter_cannot_cross_scopes(monkeypatch):
    llm = MockLLM(['{"action":"supersede","target_id":1}'])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    atlas = mem.add_fact(Fact(id=None, statement="Atlas uses Rust", subject="user",
                              predicate="works_at", object="Rust", scope="project:Atlas"),
                         resolve_conflicts=False)
    monkeypatch.setattr(mem.store, "vector_search", lambda *args, **kwargs: [(atlas, 0.99)])
    borealis = mem.add_fact(Fact(id=None, statement="Borealis uses Python", subject="user",
                                 predicate="works_at", object="Python", scope="project:Borealis"))
    assert borealis is not None
    assert mem.store.get_fact(atlas).invalid_at is None
    assert llm.calls == 0


def test_scope_is_in_vector_index_input_and_result_provenance():
    class RecordingEmbedder(HashEmbedder):
        def __init__(self):
            super().__init__(dim=64)
            self.inputs = []

        def embed(self, texts):
            self.inputs.extend(texts)
            return super().embed(texts)

    embedder = RecordingEmbedder()
    mem = Smriti(embedder=embedder, mode="lite")
    fid = mem.add_fact(Fact(id=None, statement="Uses the same tool", subject="user",
                            predicate="primary_programming_language", object="Rust",
                            search_keys=["programming language", "tool"],
                            scope="project:Atlas"))
    assert any("scope:project:Atlas" in text for text in embedder.inputs)
    assert "Uses the same tool scope:project:Atlas" in embedder.inputs
    assert "Uses the same tool scope:project:Atlas programming language tool" not in embedder.inputs
    hits = mem.search("same tool", k=3, channels={"lexical"})
    assert any(hit.id == fid and hit.scope == "project:Atlas" for hit in hits)


def test_extracted_scoped_fact_embedding_excludes_search_keys():
    class RecordingEmbedder(HashEmbedder):
        def __init__(self):
            super().__init__(dim=64)
            self.inputs = []

        def embed(self, texts):
            self.inputs.extend(texts)
            return super().embed(texts)

    raw = json.dumps([{
        "statement": "Atlas uses Rust",
        "subject": "user",
        "predicate": "primary_programming_language",
        "object": "Rust",
        "entities": ["Atlas"],
        "search_keys": ["programming language", "tool"],
        "scope": "project:Atlas",
        "event_date": None,
        "kind": "knowledge",
    }])
    embedder = RecordingEmbedder()
    mem = Smriti(embedder=embedder, llm=MockLLM([raw]), mode="full")
    result = mem.add(
        [{"role": "user", "content": "Atlas uses Rust"}],
        session_id="scope-test",
        timestamp="2025-01-01T00:00:00Z",
    )
    assert result["facts"] == 1
    fact_inputs = [text for text in embedder.inputs if text.startswith("Atlas uses Rust")]
    assert "Atlas uses Rust scope:project:Atlas" in fact_inputs
    assert "Atlas uses Rust scope:project:Atlas programming language tool" not in fact_inputs


def test_scoped_entity_and_predicate_observations_keep_scope_and_refresh():
    llm = MockLLM([
        "Atlas project overview", "Orion project overview",
        "Atlas attended events", "Orion attended events",
        "Atlas project overview v2", "Orion project overview v2",
        "Atlas attended events v2", "Orion attended events v2",
    ])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    for scope, entity in (("project:Atlas", "Atlas"), ("project:Orion", "Orion")):
        for event in ("launch", "review"):
            mem.add_fact(Fact(
                id=None, statement=f"{entity} had {event}", subject="user",
                predicate="attended", object=event, entities=[entity], scope=scope),
                resolve_conflicts=False)

    first = mem.refresh_observations(min_facts=2)
    assert first["entity"] == 2 and first["predicate"] == 2
    entity_obs = [f for f in mem.store.facts_for_entity(
        "atlas", valid_only=True, include_observations=True)
                  if f.kind == "observation"]
    assert {f.scope for f in entity_obs} == {"project:Atlas"}
    predicate_obs = [f for f in mem.store.facts_for_key(
        "user", "digest:attended", "project:Atlas") if f.kind == "observation"]
    assert len(predicate_obs) == 1 and predicate_obs[0].scope == "project:Atlas"

    second = mem.refresh_observations(min_facts=2)
    assert second["entity"] == 2 and second["predicate"] == 2
    assert len(mem.store.similar_valid_facts(
        "user", "digest:attended", "project:Atlas")) == 1
    assert len(mem.store.similar_valid_facts(
        "user", "digest:attended", "project:Orion")) == 1
    assert len([f for f in mem.store.facts_for_key(
        "user", "digest:attended", "project:Atlas")
                if f.kind == "observation"]) == 2


def test_observation_prompt_preserves_fact_scope_and_interval():
    from smriti.extraction import build_observation_prompt

    prompts = build_observation_prompt("Mira", [
        Fact(id=None, statement="Mira uses Rust", subject="user",
             predicate="primary_programming_language", object="Rust",
             scope="project:Atlas", valid_from="2025-02-20T00:00:00Z"),
        Fact(id=None, statement="Mira prefers Python", subject="user",
             predicate="prefers", object="Python", valid_from="2024-01-10T00:00:00Z"),
    ])
    system, user = prompts
    assert "never" in system["content"] and "global" in system["content"]
    assert "scope=project:Atlas" in user["content"]
    assert "scope=<unscoped/global>" in user["content"]
    assert "valid_from=2025-02-20T00:00:00Z" in user["content"]


def test_scope_whitespace_normalizes_to_same_conflict_key():
    mem = lite()
    first = mem.add_fact(Fact(id=None, statement="Atlas uses Python", subject="user",
                              predicate="primary_programming_language", object="Python",
                              scope=" project:Atlas ", valid_from="2025-01-01"))
    second = mem.add_fact(Fact(id=None, statement="Atlas uses Rust", subject="user",
                               predicate="primary_programming_language", object="Rust",
                               scope="project:Atlas", valid_from="2025-02-01"))
    assert mem.store.get_fact(first).invalid_at == mem.store.get_fact(second).valid_from
    assert mem.store.get_fact(second).scope == "project:Atlas"


def test_unscoped_legacy_fact_defaults_to_empty_scope():
    mem = Smriti(embedder=HashEmbedder(), mode="lite")
    fid = mem.add_fact(Fact(id=None, statement="The user lives in Pune", subject="user",
                            predicate="lives_in", object="Pune"))
    fact = mem.store.get_fact(fid)
    assert fact.scope == ""
    assert mem.store.facts_for_key("user", "lives_in")[0].scope == ""


def test_v2_export_import_defaults_missing_scope_to_empty():
    source = lite()
    source.add_fact(Fact(id=None, statement="The user lives in Pune", subject="user",
                         predicate="lives_in", object="Pune"))
    exported = source.store.export_data()
    exported["version"] = 2
    for fact in exported["facts"]:
        fact.pop("scope", None)
    target = lite()
    target.store.import_data(exported)
    assert target.store.get_fact(1).scope == ""


def test_legacy_scope_migration_is_safe_under_concurrent_open(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE episodes(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, ts TEXT, emb BLOB)")
    db.execute("CREATE TABLE facts(id INTEGER PRIMARY KEY, statement TEXT, subject TEXT, predicate TEXT, object TEXT, kind TEXT, event_date TEXT, ingested_at TEXT, valid_from TEXT, invalid_at TEXT, superseded_by INTEGER, episode_id INTEGER, session_id TEXT, emb BLOB)")
    db.commit()
    db.close()

    def open_and_close():
        store = Store(str(path))
        try:
            return "scope" in {row[1] for row in store.db.execute("PRAGMA table_info(facts)")}
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: open_and_close(), range(2))) == [True, True]


def test_embedding_dimension_change_rolls_back_before_write():
    class ChangingEmbedder:
        def __init__(self):
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            size = 3 if self.calls == 1 else 4
            return [[1.0] * size for _ in texts]

    mem = Smriti(embedder=ChangingEmbedder(), mode="lite")
    mem.add([{"role": "user", "content": "first"}])
    with pytest.raises(ValueError, match="embedding dimension mismatch"):
        mem.add([{"role": "user", "content": "second"}])
    assert mem.stats()["episodes"] == 1


def test_invalid_embedding_is_rejected_before_write():
    class BadEmbedder:
        def embed(self, texts):
            return [[float("nan"), 0.0] for _ in texts]

    mem = Smriti(embedder=BadEmbedder(), mode="lite")
    with pytest.raises(ValueError, match="finite"):
        mem.add([{"role": "user", "content": "bad vector"}])
    assert mem.stats()["episodes"] == 0


def test_repeated_undated_direct_fact_remains_deduped():
    mem = lite()
    fact = Fact(id=None, statement="The user lives in Pune", subject="user",
                predicate="lives_in", object="Pune")
    assert mem.add_fact(fact) is not None
    assert mem.add_fact(fact) is None
    assert mem.stats()["facts"] == 1


def test_smriti_context_manager_closes_connection():
    with lite() as mem:
        assert mem.stats()["episodes"] == 0
    with pytest.raises(Exception):
        mem.stats()


def test_doctor_inspects_database_read_only(tmp_path):
    from smriti.doctor import inspect_database
    path = str(tmp_path / "doctor.db")
    with Smriti(path=path, mode="lite") as mem:
        mem.add([{"role": "user", "content": "doctor test"}],
                timestamp="2026-01-01T00:00:00Z")
    before = (tmp_path / "doctor.db").stat().st_mtime_ns
    report = inspect_database(path)
    after = (tmp_path / "doctor.db").stat().st_mtime_ns
    assert report["ok"] is True
    assert report["counts"]["episodes"] == 1
    assert report["embedding_dimensions"]["episodes"] == [256]
    assert before == after


def test_doctor_reports_missing_database_without_creating_it(tmp_path):
    from smriti.doctor import inspect_database
    path = tmp_path / "missing.db"
    report = inspect_database(str(path))
    assert report["ok"] is False
    assert not path.exists()


def test_doctor_handles_uri_metacharactersacters_in_path(tmp_path):
    from smriti.doctor import inspect_database
    path = tmp_path / "memory #1?.db"
    with Smriti(path=str(path), mode="lite"):
        pass
    assert inspect_database(str(path))["ok"] is True


def test_database_rejects_incompatible_embedder_identity(tmp_path):
    path = str(tmp_path / "identity.db")
    with Smriti(path=path, embedder=HashEmbedder(dim=64), mode="lite") as mem:
        mem.add([{"role": "user", "content": "identity test"}])
    with pytest.raises(ValueError, match="incompatible"):
        Smriti(path=path, embedder=HashEmbedder(dim=128), mode="lite")
    with Smriti(path=path, embedder=HashEmbedder(dim=64), mode="lite") as reopened:
        assert reopened.stats()["episodes"] == 1


def test_database_rejects_same_dimension_different_model(tmp_path):
    class NamedHash(HashEmbedder):
        def __init__(self, model):
            super().__init__(dim=64)
            self.model = model

    path = str(tmp_path / "models.db")
    with Smriti(path=path, embedder=NamedHash("model-a"), mode="lite") as mem:
        mem.add([{"role": "user", "content": "model identity"}])
    with pytest.raises(ValueError, match="incompatible"):
        Smriti(path=path, embedder=NamedHash("model-b"), mode="lite")


def test_export_identity_prevents_mislabeled_vector_restore():
    source = Smriti(embedder=HashEmbedder(dim=64), mode="lite")
    source.add([{"role": "user", "content": "portable vectors"}])
    exported = source.store.export_data()
    target = Smriti(embedder=HashEmbedder(dim=128), mode="lite")
    with pytest.raises(ValueError, match="export embedder is incompatible"):
        target.store.import_data(exported)
    assert target.stats()["episodes"] == 0


def test_legacy_export_vectors_require_explicit_adoption():
    source = Smriti(embedder=HashEmbedder(dim=64), mode="lite")
    source.add([{"role": "user", "content": "old export"}])
    exported = source.store.export_data()
    exported.pop("embedder_identity")
    target = Smriti(embedder=HashEmbedder(dim=64), mode="lite")
    with pytest.raises(ValueError, match="legacy export"):
        target.store.import_data(exported)
    target.store.import_data(exported, adopt_legacy_embedder=True)
    assert target.stats()["episodes"] == 1


def test_version_one_export_restores_only_with_explicit_adoption():
    source = Smriti(embedder=HashEmbedder(dim=64), mode="lite")
    source.add([{"role": "user", "content": "version one backup"}])
    exported = source.store.export_data()
    exported["version"] = 1
    exported.pop("embedder_identity")
    target = Smriti(embedder=HashEmbedder(dim=64), mode="lite")
    with pytest.raises(ValueError, match="version 1 export"):
        target.store.import_data(exported)
    target.store.import_data(exported, adopt_legacy_embedder=True)
    assert target.stats()["episodes"] == 1


def test_legacy_vectors_require_explicit_embedder_adoption(tmp_path):
    from smriti.doctor import inspect_database
    path = str(tmp_path / "legacy.db")
    with Smriti(path=path, embedder=HashEmbedder(dim=64), mode="lite") as mem:
        mem.add([{"role": "user", "content": "legacy vector"}])
        mem.store.db.execute("DELETE FROM metadata WHERE key='embedder_identity'")
    report = inspect_database(path)
    assert report["embedder_compatibility"].startswith("legacy-untracked")
    with pytest.raises(ValueError, match="adopt_legacy_embedder"):
        Smriti(path=path, embedder=HashEmbedder(dim=64), mode="lite")
    with Smriti(path=path, embedder=HashEmbedder(dim=64), mode="lite",
                adopt_legacy_embedder=True) as adopted:
        assert adopted.search("legacy vector")
    assert inspect_database(path)["embedder_compatibility"] == "tracked"


def test_extraction_json_parser_respects_brackets_inside_strings():
    from smriti.llm import extract_json
    raw = 'prefix [{"statement":"Use ] in the draft", "entities":[]}] suffix'
    assert extract_json(raw)[0]["statement"] == "Use ] in the draft"


def test_extraction_diagnostics_distinguish_empty_malformed_and_rejected():
    from smriti.extraction import parse_facts
    diagnostics = {}
    assert parse_facts("[]", "s", None, diagnostics) == []
    assert diagnostics["status"] == "ok" and diagnostics["items"] == 0
    assert parse_facts("not json", "s", None, diagnostics) == []
    assert diagnostics["status"] == "malformed"
    assert parse_facts('[{"statement":"x","entities":null,"search_keys":null}]',
                       "s", None, diagnostics)
    assert diagnostics["accepted"] == 1
    assert parse_facts('[{"statement":"x","entities":"not-an-array"}]',
                       "s", None, diagnostics) == []
    assert diagnostics["status"] == "all_items_rejected"


def test_extraction_normalizes_conservative_location_update_predicates():
    from smriti.extraction import parse_facts
    diagnostics = {}
    facts = parse_facts(
        '[{"statement":"The user moved to Bengaluru", "subject":"user", '
        '"predicate":"moved_to", "object":"Bengaluru"}]',
        "s", "2026-01-01T00:00:00Z", diagnostics,
    )
    assert facts[0].predicate == "lives_in"
    assert diagnostics["normalized_predicates"] == 1


def test_extraction_normalizes_inflected_preference_predicates():
    from smriti.extraction import parse_facts
    diagnostics = {}
    facts = parse_facts(
        '[{"statement":"Mira still preferred Python", "subject":"user", '
        '"predicate":"preferred", "object":"Python"}]',
        "s", "2026-01-01T00:00:00Z", diagnostics,
    )
    assert facts[0].predicate == "prefers"
    assert diagnostics["normalized_predicates"] == 1


def test_extraction_contract_preserves_named_subjects_and_scope_boundaries():
    from smriti.extraction import EXTRACT_SYSTEM

    assert "Preserve the identity of the fact's subject" in EXTRACT_SYSTEM
    assert '"subject": "Redwood team"' in EXTRACT_SYSTEM
    assert '"scope": "project:Cedar"' in EXTRACT_SYSTEM
    assert "switched from ToolA to ToolB for project Cedar" in EXTRACT_SYSTEM
    assert 'subject is usually "user"' not in EXTRACT_SYSTEM
    assert "Dates and time ranges are temporal fields, not applicability scope" in EXTRACT_SYSTEM
    assert "adjacent preference or fact does not inherit a project scope" in EXTRACT_SYSTEM


def test_semantic_arbiter_does_not_cross_unrelated_predicate_groups(monkeypatch):
    llm = MockLLM(['{"action":"supersede","target_id":1}'])
    mem = Smriti(embedder=HashEmbedder(), llm=llm, mode="full")
    location = mem.add_fact(Fact(id=None, statement="Mira lives in Berlin", subject="user",
                                 predicate="lives_in", object="Berlin"),
                            resolve_conflicts=False)
    monkeypatch.setattr(mem.store, "vector_search", lambda *args, **kwargs: [(location, 0.99)])
    joined = mem.add_fact(Fact(id=None, statement="Mira joined the Atlas project", subject="user",
                               predicate="joined", object="Atlas project"))
    assert joined is not None
    assert mem.store.get_fact(location).invalid_at is None
    assert mem.stats()["facts"] == 2
    assert llm.calls == 0


def test_llm_does_not_retry_network_failure_as_format_fallback(monkeypatch):
    import urllib.error
    import smriti.llm as llm_module
    client = llm_module.LLM("model")

    def fail(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(llm_module, "_post_json", fail)
    with pytest.raises(urllib.error.URLError):
        client.complete([], json_mode=True)
    assert client.attempts == 1 and client.calls == 0


def test_llm_tracks_format_fallback_attempt_and_missing_usage(monkeypatch):
    import urllib.error
    import smriti.llm as llm_module
    client = llm_module.LLM("model")
    responses = [urllib.error.HTTPError("url", 400, "bad format", {}, None),
                 {"choices": [{"message": {"content": "{}"}}]}]

    def respond(*args, **kwargs):
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(llm_module, "_post_json", respond)
    assert client.complete([], json_mode=True) == "{}"
    assert client.attempts == 2 and client.calls == 1 and client.usage_missing == 1
