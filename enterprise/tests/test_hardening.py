"""Regressions for fail-closed enterprise policy and evidence behavior."""
import json

import pytest

from smriti import Fact, HashEmbedder, OllamaEmbedder
from smriti_enterprise import (EgressError, EnterpriseSmriti, HMACSigner,
                               HeldError, PackError, SidecarSQLiteSink,
                               build_pack, open_pack, retrieve_multi, verify_chain)


def lite(**kw):
    kw.setdefault("embedder", HashEmbedder())
    kw.setdefault("mode", "lite")
    return EnterpriseSmriti(":memory:", **kw)


def fact(statement="The user knows Alice.", entity="alice"):
    return Fact(id=None, statement=statement, subject="user", predicate="knows",
                object="Alice", entities=[entity])


def test_remote_team_adapter_requires_allowlist():
    with pytest.raises(EgressError, match="requires an allowlist"):
        EnterpriseSmriti(":memory:", profile="team", mode="lite",
                         embedder=OllamaEmbedder(base_url="https://api.example.com"))


def test_local_redaction_cannot_be_disabled():
    mem = lite(redact=False)
    assert mem.redact is True


def test_direct_fact_write_rejects_invalid_origin():
    mem = lite()
    with pytest.raises(ValueError, match="invalid origin"):
        mem.add_fact(fact(), origin="tenant-admin", resolve_conflicts=False)


def test_regulated_profile_requires_same_configured_signer(tmp_path):
    signer = HMACSigner(b"customer-key", key_id="customer")
    sink = SidecarSQLiteSink(str(tmp_path / "audit.db"), signer=signer)
    with pytest.raises(ValueError, match="same receipt signer"):
        lite(profile="regulated", sink=sink,
             signer=HMACSigner(b"customer-key", key_id="customer"))


def test_receipt_verification_rejects_noninitial_sequence():
    body = json.dumps({"op": "read"}, sort_keys=True, separators=(",", ":"))
    from smriti_enterprise import digest
    h = digest(body)
    out = verify_chain([(7, body, h, "", None)])
    assert out["ok"] is False


def test_hmac_verification_binds_algorithm_and_key_id():
    signer = HMACSigner(b"key", key_id="expected")
    sig = signer.sign(b"payload")
    sig["key_id"] = "other"
    assert signer.verify(b"payload", sig) is False


def test_missing_required_checkpoint_is_a_verification_failure(tmp_path):
    signer = HMACSigner(b"key", key_id="expected")
    sink = SidecarSQLiteSink(str(tmp_path / "audit.db"), signer=signer,
                             checkpoint_every=2)
    sink.append({"op": "one"})
    sink.append({"op": "two"})
    sink.db.execute("UPDATE receipts SET checkpoint=NULL WHERE seq=2")
    assert sink.verify()["ok"] is False


def test_expired_entity_hold_does_not_block_session_erasure():
    mem = lite()
    mem.add_fact(fact(), resolve_conflicts=False)
    mem.store.db.execute("UPDATE facts SET session_id='s1'")
    mem.place_hold("entity", "alice", reason="short", authority="legal",
                   expires_at="2000-01-01T00:00:00Z")
    assert mem.erase_session("s1")["facts"] == 1


def test_overlapping_entity_hold_remains_effective_after_one_release():
    mem = lite()
    mem.add_fact(fact(), resolve_conflicts=False)
    mem.store.db.execute("UPDATE facts SET session_id='s1'")
    first = mem.place_hold("entity", "alice", reason="case-a", authority="legal")
    mem.place_hold("entity", "alice", reason="case-b", authority="legal")
    assert mem.release_hold(first)
    with pytest.raises(HeldError):
        mem.erase_session("s1")


def test_expected_embedder_rejects_pack_with_undeclared_fingerprint(tmp_path):
    mem = lite()
    pack = str(tmp_path / "pack.db")
    build_pack(mem.store.db, pack, name="org")
    with pytest.raises(PackError, match="embedder mismatch"):
        open_pack(pack, expected_embedder="hash-256")


def test_federation_rejects_duplicate_provenance_names():
    mem = lite()
    with pytest.raises(ValueError, match="unique"):
        retrieve_multi([("tenant", mem.store), ("tenant", mem.store)],
                       mem.embedder, "query")


def test_late_middle_fact_preserves_prior_known_world_interval():
    mem = lite()

    def learn(obj, valid_from, known_at):
        f = Fact(None, f"The user lives in {obj}.", "user", "lives_in", obj,
                 valid_from=valid_from)
        mem.store._knowledge_time = known_at
        try:
            fid = mem.add_fact(f)
        finally:
            mem.store._knowledge_time = None
        mem.store.db.execute("UPDATE facts SET recorded_at=? WHERE id=?",
                             (known_at, fid))

    learn("Hyderabad", "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z")
    learn("Bengaluru", "2026-06-01T00:00:00Z", "2026-07-01T00:00:00Z")
    learn("Pune", "2026-03-01T00:00:00Z", "2026-08-01T00:00:00Z")

    july = mem.facts_asof(world="2026-05-01T00:00:00Z",
                          known="2026-07-15T00:00:00Z")
    september = mem.facts_asof(world="2026-05-01T00:00:00Z",
                               known="2026-09-01T00:00:00Z")
    assert [f.object for f in july] == ["Hyderabad"]
    assert july[0].invalid_at == "2026-06-01T00:00:00Z"
    assert [f.object for f in september] == ["Pune"]
    assert september[0].invalid_at == "2026-06-01T00:00:00Z"


def test_enterprise_json_backup_fails_with_lossless_alternatives(tmp_path):
    mem = lite()
    with pytest.raises(RuntimeError, match=r"snapshot.*build_pack"):
        mem.export_json(str(tmp_path / "unsafe.json"))
    with pytest.raises(RuntimeError, match=r"snapshot.*verify_pack/open_pack"):
        mem.import_json(str(tmp_path / "unsafe.json"))


def test_erasure_removes_fact_validity_history():
    mem = lite()
    fid = mem.add_fact(fact(), resolve_conflicts=False)
    mem.store._record_validity(fid)
    mem.store.db.execute("UPDATE facts SET session_id='erase-me' WHERE id=?", (fid,))
    assert mem.erase_session("erase-me")["facts"] == 1
    assert mem.store.db.execute(
        "SELECT COUNT(*) FROM fact_validity_history WHERE fact_id=?", (fid,)
    ).fetchone()[0] == 0


def test_schema_one_store_migrates_with_current_state_backfill(tmp_path):
    path = str(tmp_path / "legacy-enterprise.db")
    mem = EnterpriseSmriti(path, embedder=HashEmbedder(), mode="lite")
    fid = mem.add_fact(fact(), resolve_conflicts=False)
    mem.store.db.execute("DROP TABLE fact_validity_history")
    mem.store.db.execute("PRAGMA user_version=1")
    mem.store.db.close()

    reopened = EnterpriseSmriti(path, embedder=HashEmbedder(), mode="lite")
    row = reopened.store.db.execute(
        "SELECT invalid_at, known_at FROM fact_validity_history WHERE fact_id=?",
        (fid,)).fetchone()
    assert row is not None and row[1]
