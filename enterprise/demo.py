"""SMRITI Enterprise — end-to-end walkthrough. Fully offline, no keys.

    python demo.py

Shows: tri-temporal as-of belief, exact lineage, evidence receipts with
tamper detection, legal hold beating erasure, egress fail-closed, and a
verified knowledge pack mounted read-only into federated retrieval.
"""
import json
import os
import tempfile

from smriti import Fact, HashEmbedder, MockLLM
from smriti_enterprise import (EgressError, EnterpriseSmriti, HeldError,
                               HMACSigner, PackError, SidecarSQLiteSink,
                               open_pack, retrieve_multi, verify_pack)


def fj(stmt, subj, pred, obj, ents, ed=None):
    return json.dumps([{"statement": stmt, "subject": subj, "predicate": pred,
                        "object": obj, "entities": ents, "event_date": ed,
                        "kind": "profile"}])


def rule(t):
    print(f"\n\033[1m{t}\033[0m\n" + "─" * 66)


tmp = tempfile.mkdtemp(prefix="smriti-demo-")
key = b"customer-held-audit-key"
signer = HMACSigner(key, key_id="demo-key-1")
sink = SidecarSQLiteSink(os.path.join(tmp, "memory.audit.db"), signer=signer,
                         checkpoint_every=3)

llm = MockLLM([
    fj("The user lives in Hyderabad.", "user", "lives_in", "Hyderabad", ["Hyderabad"]),
    fj("The user lives in Bengaluru.", "user", "lives_in", "Bengaluru",
       ["Bengaluru"], "2026-06-01"),
])
mem = EnterpriseSmriti(os.path.join(tmp, "memory.db"), profile="regulated",
                       sink=sink, signer=signer, embedder=HashEmbedder(),
                       llm=llm, mode="full")

rule("1 · Ingest — the world changes in June, we learn about it in July")
mem.add([{"role": "user", "content": "I live in Hyderabad."}],
        session_id="s-jan", timestamp="2026-01-01T10:00:00Z")
mem.add([{"role": "user", "content": "Oh, I moved to Bengaluru back on June 1."}],
        session_id="s-jul", timestamp="2026-07-10T10:00:00Z")
print(f"store_id      : {mem.store.store_id[:16]}…")
print(f"schema        : v{mem.store.enterprise_schema_version}")
print(f"stats         : {mem.stats()}")

rule("2 · Tri-temporal — world time and knowledge time are independent")
row = mem.store.db.execute(
    "SELECT invalid_at, withdrawn_at FROM facts WHERE object='Hyderabad'").fetchone()
print(f"world: valid until   {row[0]}   (the move happened)")
print(f"known: withdrawn at  {row[1]}   (we found out)")
print(f"believed on 2026-03-01 : {[f.object for f in mem.facts_asof(known='2026-03-01T00:00:00Z')]}")
print(f"believed today         : {[f.object for f in mem.facts_asof()]}")
print("→ late-arriving corrections no longer rewrite what we believed then")

rule("3 · Lineage — exact parents, not heuristics")
from smriti_enterprise import parents_of
fid = mem.store.db.execute(
    "SELECT id FROM facts WHERE object='Bengaluru'").fetchone()[0]
print(f"fact {fid} derives from: {parents_of(mem.store, 'fact', fid)}")

rule("4 · Evidence receipt — binds the exact packed context")
ctx = mem.context("where do I live?", correlation_id="req-4f2a")
r = mem.last_receipt
print(f"op={r['op']}  correlation={r['correlation_id']}  profile={r['versions']['profile']}")
print(f"query_digest   : {r['body']['query_digest'][:32]}…")
print(f"context_digest : {r['body']['context_digest'][:32]}…  ({r['body']['context_chars']} chars)")
print(f"first ctx line : {ctx.splitlines()[1] if len(ctx.splitlines()) > 1 else ctx[:60]}")
print("→ plaintext is never stored in the receipt; digests bind it")

rule("5 · Audit integrity — chain + customer-key checkpoints")
for q in ("where do I live?", "what city?", "current address"):
    mem.context(q)
print(f"verify (correct key) : {mem.verify_audit()}")
print(f"verify (wrong key)   : {sink.verify(signer=HMACSigner(b'attacker'))}")

rule("6 · Legal hold beats erasure")
hid = mem.place_hold("session", "s-jan", reason="litigation-2026-114",
                     authority="legal@corp")
try:
    mem.erase_session("s-jan")
except HeldError as e:
    print(f"erase refused  : {e}")
mem.release_hold(hid)
print(f"after release  : {mem.erase_session('s-jan')}")

rule("7 · Profiles fail closed")
try:
    from smriti import OllamaEmbedder
    EnterpriseSmriti(":memory:", profile="local",
                     embedder=OllamaEmbedder(base_url="http://api.example.com"),
                     mode="lite")
except EgressError as e:
    print(f"local profile  : {e}")
print(f"data flow      : {json.dumps(mem.describe_data_flow()['embedder'])}")

rule("8 · Verified knowledge pack + federation")
org_src = EnterpriseSmriti(os.path.join(tmp, "orgsrc.db"), profile="local",
                           embedder=HashEmbedder(), mode="lite")
org_src.add([{"role": "user", "content":
              "Company policy: expense reports are due on the 5th of each month."}],
            timestamp="2026-01-01T10:00:00Z")
org_src.signer = signer
pack_path = os.path.join(tmp, "org-handbook.pack.db")
m = org_src.build_pack(pack_path, name="org-handbook",
                       embedder_fingerprint="hash-256")
print(f"pack built     : {m['name']}  sha256={m['sha256'][:16]}…  signed={'signature' in m}")
print(f"verify         : ok ({verify_pack(pack_path, signer=signer)['store_id'][:12]}…)")

org, _ = open_pack(pack_path, signer=signer, expected_embedder="hash-256")
hits = retrieve_multi([("personal", mem.store), ("org", org)], mem.embedder,
                      "when are expense reports due?", k=4)
for h in hits[:2]:
    print(f"  [{h.kind}] {h.text[:52]}…  channels={[c for c in h.channels if c.startswith('store:')]}")

try:
    org.db.execute("DELETE FROM episodes")
except Exception as e:  # noqa: BLE001
    print(f"pack write     : refused ({type(e).__name__}) — read-only mount")

with open(pack_path, "ab") as fh:
    fh.write(b"tamper")
try:
    verify_pack(pack_path, signer=signer)
except PackError as e:
    print(f"tampered pack  : {e}")

print(f"\n\033[1mdemo files:\033[0m {tmp}")
