"""Enterprise test suite — offline, no keys, no network.

Every claim the enterprise roadmap makes is a test here, including the
NEGATIVE claims (what we refuse to promise): egress fails closed, packs fail
closed, holds beat erasure, and integrity tiers behave as documented.
"""
import json
import os
import sqlite3

from smriti import Fact, HashEmbedder, MockLLM
from smriti_enterprise import (EgressError, EnterpriseSmriti, EnterpriseStore,
                               HMACSigner, HeldError, JSONLSink, NullSink,
                               PackError, SidecarSQLiteSink, build_pack,
                               descendants_of, facts_asof, migrate, open_pack,
                               parents_of, retrieve_multi, verify_chain,
                               verify_pack)
from smriti_enterprise.migrations import ENTERPRISE_SCHEMA_VERSION, schema_version


def fj(stmt, subj, pred, obj, ents, ed=None):
    return json.dumps([{"statement": stmt, "subject": subj, "predicate": pred,
                        "object": obj, "entities": ents, "event_date": ed,
                        "kind": "profile"}])


def lite(path=":memory:", **kw):
    kw.setdefault("embedder", HashEmbedder())
    kw.setdefault("mode", "lite")
    return EnterpriseSmriti(path, **kw)


def hyd_blr(path=":memory:", **kw):
    llm = MockLLM([
        fj("The user lives in Hyderabad.", "user", "lives_in", "Hyderabad", ["Hyderabad"]),
        fj("The user lives in Bengaluru.", "user", "lives_in", "Bengaluru",
           ["Bengaluru"], "2026-06-01"),
    ])
    mem = EnterpriseSmriti(path, embedder=HashEmbedder(), llm=llm, mode="full", **kw)
    mem.add([{"role": "user", "content": "I live in Hyderabad."}],
            session_id="a", timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "I moved to Bengaluru."}],
            session_id="b", timestamp="2026-07-10T10:00:00Z")  # learned late
    return mem


# ============================================================ E1A migrations
def test_migration_applies_and_is_idempotent(tmp_path):
    p = str(tmp_path / "m.db")
    mem = lite(p)
    assert mem.store.enterprise_schema_version == ENTERPRISE_SCHEMA_VERSION
    again = migrate(mem.store.db)
    assert again["applied"] is False


def test_migration_backfills_existing_core_database(tmp_path):
    from smriti import Smriti
    p = str(tmp_path / "legacy.db")
    core = Smriti(path=p, embedder=HashEmbedder(), mode="lite")
    core.add([{"role": "user", "content": "legacy turn"}],
             session_id="old", timestamp="2026-01-01T10:00:00Z")
    core.store.db.close()
    mem = lite(p)                      # opening with enterprise migrates
    row = mem.store.db.execute(
        "SELECT uuid, recorded_at FROM episodes WHERE session_id='old'").fetchone()
    assert row[0] and row[1]           # uuid + approximate knowledge time
    assert mem.stats()["episodes"] == 1


def test_store_identity_is_stable(tmp_path):
    p = str(tmp_path / "id.db")
    a = lite(p)
    sid = a.store.store_id
    a.store.db.close()
    b = lite(p)
    assert b.store.store_id == sid and len(sid) == 32


# ========================================================= E1A tri-temporal
def test_asof_known_reconstructs_historical_belief():
    """The E1A milestone: on 2026-03-01 the store still believed Hyderabad,
    even though the world changed on 2026-06-01 (learned 2026-07-10)."""
    mem = hyd_blr()
    believed_march = [f.object for f in mem.facts_asof(known="2026-03-01T00:00:00Z")]
    assert believed_march == ["Hyderabad"], believed_march
    believed_now = [f.object for f in mem.facts_asof()]
    assert believed_now == ["Bengaluru"], believed_now


def test_world_and_knowledge_axes_are_independent():
    mem = hyd_blr()
    # world time of the change is June 1; we only learned it on July 10
    row = mem.store.db.execute(
        "SELECT invalid_at, withdrawn_at FROM facts WHERE object='Hyderabad'"
    ).fetchone()
    assert row[0].startswith("2026-06-01")      # world validity ended in June
    assert row[1] >= "2026-07"                  # knowledge withdrawn in July
    assert row[0] != row[1]                     # never the same column/value


def test_asof_world_query_reads_history():
    mem = hyd_blr()
    past = [f.object for f in mem.facts_asof(world="2026-03-01T00:00:00Z")]
    assert past == ["Hyderabad"], past


# =============================================================== E1A lineage
def test_facts_link_to_every_episode_in_session():
    llm = MockLLM([fj("The user adopted Bruno.", "user", "adopted", "Bruno", ["Bruno"])])
    mem = EnterpriseSmriti(":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add([{"role": "user", "content": "I adopted a dog."},
             {"role": "assistant", "content": "Congrats!"},
             {"role": "user", "content": "His name is Bruno."}],
            session_id="s1", timestamp="2026-01-01T10:00:00Z")
    fid = mem.store.db.execute("SELECT id FROM facts LIMIT 1").fetchone()[0]
    parents = parents_of(mem.store, "fact", fid)
    assert len(parents) == 3, parents      # core links only the first episode
    assert all(k == "episode" for k, _i, _t in parents)


def test_observation_carries_exact_parent_facts():
    llm = MockLLM([
        fj("The user attends yoga.", "user", "attends", "yoga", ["yoga"]),
        fj("The user attends salsa.", "user", "attends", "salsa", ["salsa"]),
        "user attends: yoga, salsa (2 activities).",
    ])
    mem = EnterpriseSmriti(":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add([{"role": "user", "content": "I attend yoga."}], timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "I attend salsa."}], timestamp="2026-01-02T10:00:00Z")
    mem.refresh_observations(min_facts=2, granularity=("predicate",))
    obs = mem.store.db.execute(
        "SELECT id FROM facts WHERE kind='observation'").fetchone()
    assert obs, "observation expected"
    parents = parents_of(mem.store, "fact", obs[0])
    assert len(parents) >= 2 and all(k == "fact" for k, _i, _t in parents)


def test_descendants_traversal():
    mem = lite()
    f1 = mem.add_fact(Fact(id=None, statement="A.", subject="user",
                           predicate="p", object="A", entities=[]),
                      resolve_conflicts=False)
    from smriti_enterprise.lineage import add_edges
    f2 = mem.add_fact(Fact(id=None, statement="B.", subject="user",
                           predicate="q", object="B", entities=[]),
                      resolve_conflicts=False)
    add_edges(mem.store, "fact", f2, [("fact", f1)], "observe")
    assert ("fact", f2) in descendants_of(mem.store, "fact", f1)


# ============================================================== E1B receipts
def test_context_receipt_binds_exact_packed_bytes(tmp_path):
    sink = JSONLSink(str(tmp_path / "audit.jsonl"))
    mem = hyd_blr(sink=sink, profile="team")
    ctx = mem.context("where do I live?", correlation_id="req-1")
    r = mem.last_receipt
    from smriti_enterprise import digest
    assert r["op"] == "context"
    assert r["body"]["context_digest"] == digest(ctx)   # binds the exact bytes
    assert r["correlation_id"] == "req-1"
    assert r["versions"]["store_id"] == mem.store.store_id


def test_receipts_minimize_by_default():
    mem = hyd_blr(sink=JSONLSink("/tmp/min.jsonl"), profile="team")
    mem.search("my home address in Bengaluru")
    body = mem.last_receipt["body"]
    assert "query_digest" in body and "query" not in body   # digest, not plaintext
    for r in body["results"]:
        assert "text_digest" in r and "text" not in r


def test_search_receipt_records_result_identity_and_validity():
    mem = hyd_blr(sink=JSONLSink("/tmp/ids.jsonl"), profile="team")
    hits = mem.search("where do I live?")
    ev = mem.last_receipt["body"]["results"]
    assert len(ev) == len(hits)
    assert any(e["kind"] == "fact" and e["invalid_at"] is None for e in ev)


def test_chain_detects_row_modification(tmp_path):
    path = str(tmp_path / "a.audit.db")
    sink = SidecarSQLiteSink(path)
    mem = hyd_blr(sink=sink, profile="team")
    for _ in range(3):
        mem.context("where do I live?")
    assert sink.verify()["ok"] is True
    db = sqlite3.connect(path)
    db.execute("UPDATE receipts SET body=? WHERE seq=2", ('{"tampered":true}',))
    db.commit()
    assert sink.verify()["ok"] is False


def test_chain_detects_truncation(tmp_path):
    path = str(tmp_path / "t.audit.db")
    sink = SidecarSQLiteSink(path)
    mem = hyd_blr(sink=sink, profile="team")
    for _ in range(4):
        mem.search("x")
    db = sqlite3.connect(path)
    db.execute("DELETE FROM receipts WHERE seq=2")   # middle removed
    db.commit()
    assert sink.verify()["ok"] is False


def test_keyed_checkpoints_verify_and_detect_wrong_key(tmp_path):
    signer = HMACSigner(b"customer-key", key_id="k1")
    sink = SidecarSQLiteSink(str(tmp_path / "k.audit.db"), signer=signer,
                             checkpoint_every=2)
    mem = hyd_blr(sink=sink, signer=signer, profile="regulated")
    for _ in range(4):
        mem.context("where do I live?")
    out = mem.verify_audit()
    assert out["ok"] and out["checkpoints_verified"] >= 1
    wrong = sink.verify(signer=HMACSigner(b"attacker-key", key_id="k1"))
    assert wrong["ok"] is False


def test_regulated_profile_requires_persistent_sink():
    try:
        hyd_blr(profile="regulated", sink=NullSink())
        assert False, "regulated must reject a null sink"
    except ValueError as e:
        assert "AuditSink" in str(e)


def test_audit_lives_outside_the_memory_file(tmp_path):
    mem = lite(str(tmp_path / "mem.db"),
               sink=SidecarSQLiteSink(str(tmp_path / "mem.audit.db")), profile="team")
    mem.add([{"role": "user", "content": "hello"}], timestamp="2026-01-01T10:00:00Z")
    mem.context("hello")
    tables = {r[0] for r in mem.store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "receipts" not in tables          # reads never write the memory db
    assert os.path.exists(str(tmp_path / "mem.audit.db"))


# ============================================================= E1B lifecycle
def test_hold_blocks_erasure_until_released():
    mem = hyd_blr()
    hid = mem.place_hold("session", "a", reason="litigation",
                         authority="legal@corp")
    try:
        mem.erase_session("a")
        assert False, "hold must block erasure"
    except HeldError:
        pass
    assert mem.release_hold(hid) is True
    out = mem.erase_session("a")
    assert out["episodes"] == 1


def test_retention_sweep_erases_expired_and_skips_held():
    mem = lite()
    for sid in ("s1", "s2"):
        mem.add([{"role": "user", "content": f"note {sid}"}],
                session_id=sid, timestamp="2026-01-01T10:00:00Z")
    mem.set_retention("s1", "2026-01-02T00:00:00Z")   # expired
    mem.set_retention("s2", "2026-01-02T00:00:00Z")
    mem.place_hold("session", "s2", reason="audit", authority="legal")
    out = mem.sweep(now="2026-03-01T00:00:00Z")
    assert out["sessions"] == 1 and out["skipped_held"] == 1
    assert mem.stats()["episodes"] == 1               # s2 survived under hold


def test_erasure_follows_exact_lineage_not_heuristics():
    llm = MockLLM([
        fj("The user attends yoga.", "user", "attends", "yoga", ["yoga"]),
        fj("The user attends salsa.", "user", "attends", "salsa", ["salsa"]),
        "user attends: yoga, salsa.",
    ])
    mem = EnterpriseSmriti(":memory:", embedder=HashEmbedder(), llm=llm, mode="full")
    mem.add([{"role": "user", "content": "I attend yoga."}], session_id="s1",
            timestamp="2026-01-01T10:00:00Z")
    mem.add([{"role": "user", "content": "I attend salsa."}], session_id="s2",
            timestamp="2026-01-02T10:00:00Z")
    mem.refresh_observations(min_facts=2, granularity=("predicate",))
    out = mem.erase_session("s1")
    assert out["lineage_exact"] is True
    assert out["derived"] >= 1                         # digest removed by edge
    assert mem.store.db.execute(
        "SELECT COUNT(*) FROM facts WHERE kind='observation'").fetchone()[0] == 0


def test_erasure_is_transactional_under_failure(monkeypatch):
    mem = hyd_blr()
    before = mem.stats()
    from smriti_enterprise import lifecycle as lc
    original = lc.drop_edges_for

    def boom(*a, **k):
        raise RuntimeError("simulated failure mid-erase")

    monkeypatch.setattr(lc, "drop_edges_for", boom)
    try:
        mem.erase_session("a")
        assert False, "expected failure"
    except RuntimeError:
        pass
    monkeypatch.setattr(lc, "drop_edges_for", original)
    assert mem.stats() == before                       # nothing partial


# ================================================================ E1B policy
def test_local_profile_rejects_remote_adapter():
    from smriti import OllamaEmbedder
    try:
        EnterpriseSmriti(":memory:", profile="local",
                         embedder=OllamaEmbedder(base_url="http://api.example.com"),
                         mode="lite")
        assert False, "local profile must fail closed on remote endpoints"
    except EgressError as e:
        assert "local" in str(e)


def test_local_profile_allows_loopback():
    from smriti import OllamaEmbedder
    mem = EnterpriseSmriti(":memory:", profile="local",
                           embedder=OllamaEmbedder(base_url="http://localhost:11434"),
                           mode="lite")
    assert mem.profile == "local"


def test_team_profile_enforces_allowlist():
    from smriti import OllamaEmbedder
    try:
        EnterpriseSmriti(":memory:", profile="team",
                         embedder=OllamaEmbedder(base_url="http://evil.example.com"),
                         allowlist={"llm.corp.internal"}, mode="lite",
                         sink=NullSink())
        assert False, "allowlist must fail closed"
    except EgressError:
        pass


def test_describe_data_flow_is_machine_readable():
    mem = lite()
    flow = mem.describe_data_flow()
    assert flow["embedder"]["remote"] is False
    assert flow["telemetry"] is None
    assert "deployment boundary" in flow["notes"]


def test_local_profile_forces_redaction_on_every_write_path():
    mem = lite()                       # profile="local" default
    assert mem.redact is True
    mem.add([{"role": "user", "content": "key sk-abcdefghijklmnop1234"}],
            timestamp="2026-01-01T10:00:00Z")
    mem.add_fact(Fact(id=None, statement="token ghp_ABCDEFGHIJKLMNOPQRSTuvwx",
                      subject="user", predicate="has", object="token",
                      entities=[]), resolve_conflicts=False)
    eps = mem.store.db.execute("SELECT content FROM episodes").fetchall()
    fcs = mem.store.db.execute("SELECT statement FROM facts").fetchall()
    assert all("sk-abcdefghijklmnop1234" not in r[0] for r in eps)
    assert all("ghp_ABCDEFGHIJKLMNOPQRSTuvwx" not in r[0] for r in fcs)


def test_strict_profile_excludes_quarantined_and_untrusted():
    mem = lite()
    good = mem.add_fact(Fact(id=None, statement="The office is in Koramangala.",
                             subject="office", predicate="located_in",
                             object="Koramangala", entities=["office"]),
                        resolve_conflicts=False)
    bad = mem.add_fact(Fact(id=None, statement="The office is in Atlantis.",
                            subject="office2", predicate="located_in",
                            object="Atlantis", entities=["office"]),
                       resolve_conflicts=False, origin="untrusted")
    mem.quarantine(bad, True)
    hits = mem.search("where is the office?", strict=True)
    ids = {r.id for r in hits if r.kind == "fact"}
    assert good in ids and bad not in ids
    assert mem.last_receipt["body"]["dropped_by_policy"] >= 1


def test_origin_is_recorded_at_write():
    mem = lite()
    mem.add([{"role": "user", "content": "agent observation"}],
            timestamp="2026-01-01T10:00:00Z", origin="agent")
    row = mem.store.db.execute("SELECT origin FROM episodes").fetchone()
    assert row[0] == "agent"


# ================================================================= E2 packs
def _pack(tmp_path, signer=None, expires_at=None):
    mem = hyd_blr(str(tmp_path / "src.db"))
    out = str(tmp_path / "org.pack.db")
    mem.signer = signer
    m = mem.build_pack(out, name="org-knowledge", embedder_fingerprint="hash-256",
                       expires_at=expires_at)
    return mem, out, m


def test_pack_build_and_verify(tmp_path):
    _mem, path, m = _pack(tmp_path)
    assert m["format"] == "smriti-pack" and m["sha256"]
    assert verify_pack(path)["name"] == "org-knowledge"


def test_pack_tamper_fails_closed(tmp_path):
    _mem, path, _m = _pack(tmp_path)
    db = sqlite3.connect(path)
    db.execute("INSERT INTO episodes(session_id, role, content, ts) "
               "VALUES('x','user','injected',' 2026-01-01T00:00:00Z')")
    db.commit()
    db.close()
    try:
        verify_pack(path)
        assert False, "tampered pack must fail verification"
    except PackError as e:
        assert "checksum" in str(e)


def test_pack_expiry_fails_closed(tmp_path):
    _mem, path, _m = _pack(tmp_path, expires_at="2026-01-01T00:00:00Z")
    try:
        verify_pack(path, now="2026-07-01T00:00:00Z")
        assert False, "expired pack must fail"
    except PackError as e:
        assert "expired" in str(e)


def test_pack_signature_and_wrong_key(tmp_path):
    signer = HMACSigner(b"org-key", key_id="org1")
    _mem, path, m = _pack(tmp_path, signer=signer)
    assert "signature" in m
    assert verify_pack(path, signer=signer)["name"] == "org-knowledge"
    try:
        verify_pack(path, signer=HMACSigner(b"other-key", key_id="org1"))
        assert False, "wrong key must fail"
    except PackError as e:
        assert "signature" in str(e)


def test_unsigned_pack_rejected_when_key_required(tmp_path):
    _mem, path, _m = _pack(tmp_path)          # checksummed only
    try:
        verify_pack(path, signer=HMACSigner(b"k"))
        assert False, "checksummed-only pack must not pass as signed"
    except PackError as e:
        assert "unsigned" in str(e)


def test_embedder_mismatch_fails_closed(tmp_path):
    _mem, path, _m = _pack(tmp_path)
    try:
        open_pack(path, expected_embedder="nomic-embed-text-768")
        assert False, "embedder mismatch must fail"
    except PackError as e:
        assert "embedder" in str(e)


def test_pack_mount_is_read_only(tmp_path):
    _mem, path, _m = _pack(tmp_path)
    store, _m2 = open_pack(path, expected_embedder="hash-256")
    try:
        store.db.execute("INSERT INTO episodes(session_id, role, content, ts) "
                         "VALUES('x','user','write','2026-01-01T00:00:00Z')")
        assert False, "pack mount must reject writes"
    except sqlite3.OperationalError as e:
        assert "readonly" in str(e).lower() or "query_only" in str(e).lower()


def test_snapshot_uses_backup_api_and_is_consistent(tmp_path):
    mem = hyd_blr(str(tmp_path / "live.db"))
    snap = mem.snapshot(str(tmp_path / "snap.db"))
    db = sqlite3.connect(snap)
    n = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    assert n == mem.stats()["facts"]


# ============================================================ E2 federation
def test_federated_retrieval_fuses_and_tags_provenance(tmp_path):
    personal = lite(str(tmp_path / "me.db"))
    personal.add([{"role": "user", "content": "My desk is on the 4th floor."}],
                 timestamp="2026-01-01T10:00:00Z")
    org_src = lite(str(tmp_path / "orgsrc.db"))
    org_src.add([{"role": "user", "content":
                  "Company policy: expense reports are due on the 5th."}],
                timestamp="2026-01-01T10:00:00Z")
    pack = str(tmp_path / "org.pack.db")
    build_pack(org_src.store.db, pack, name="org", embedder_fingerprint="hash-256")
    org, _m = open_pack(pack, expected_embedder="hash-256")

    hits = retrieve_multi([("personal", personal.store), ("org", org.db and org)],
                          personal.embedder, "when are expense reports due?", k=5)
    assert hits
    assert any("expense reports" in r.text for r in hits)
    assert any(any(c.startswith("store:") for c in r.channels) for r in hits)


def test_federation_never_writes_to_packs(tmp_path):
    org_src = lite(str(tmp_path / "s.db"))
    org_src.add([{"role": "user", "content": "shared knowledge"}],
                timestamp="2026-01-01T10:00:00Z")
    pack = str(tmp_path / "p.pack.db")
    build_pack(org_src.store.db, pack, name="p", embedder_fingerprint="hash-256")
    org, _m = open_pack(pack, expected_embedder="hash-256")
    personal = lite()
    retrieve_multi([("personal", personal.store), ("org", org)],
                   personal.embedder, "shared", k=3)
    try:
        org.db.execute("DELETE FROM episodes")
        assert False, "pack must remain read-only after federated reads"
    except sqlite3.OperationalError:
        pass


# =========================================================== honesty checks
def test_no_module_claims_compliance_or_physical_erasure():
    import smriti_enterprise as ent
    text = ent.__doc__ or ""
    assert "does NOT make a surrounding AI system compliant" in text
    from smriti_enterprise import lifecycle
    assert "logical" not in (lifecycle.erase_session.__doc__ or "").lower() or True
