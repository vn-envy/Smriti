"""Build a real pre-scope enterprise pack, then mount it with current code.

The producer is isolated by running from ``SMRITI_PRE_SCOPE_SOURCE`` so the
historical imports cannot accidentally resolve to the current checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def main() -> None:
    source = Path(os.environ.get("SMRITI_PRE_SCOPE_SOURCE", "/private/tmp/smriti-pre-scope-source"))
    work = Path(os.environ.get("SMRITI_PRESCOPE_WORK", "/private/tmp/smriti-pre-scope-compat"))
    work.mkdir(parents=True, exist_ok=True)
    for stale in (work / "legacy.db", work / "legacy.pack.db",
                  work / "legacy.pack.db.manifest.json"):
        stale.unlink(missing_ok=True)
    old_script = work / "create_old.py"
    old_script.write_text("""import json, os\nfrom smriti import Fact, HashEmbedder\nfrom smriti_enterprise import EnterpriseSmriti\nroot = os.environ['SMRITI_PRESCOPE_WORK']\nmem = EnterpriseSmriti(os.path.join(root, 'legacy.db'), embedder=HashEmbedder(), mode='lite')\nfid = mem.add_fact(Fact(id=None, statement='The legacy source fact is retained.', subject='user', predicate='knows', object='legacy', entities=['legacy']), resolve_conflicts=False)\nmanifest = mem.build_pack(os.path.join(root, 'legacy.pack.db'), name='historical-prescope', embedder_fingerprint='hash-256')\nmem.close()\nprint(json.dumps({'fact_id': fid, 'manifest': manifest}))\n""", encoding="utf-8")
    env = dict(os.environ)
    env["SMRITI_PRESCOPE_WORK"] = str(work)
    env["PYTHONPATH"] = os.pathsep.join((str(source), str(source / "enterprise")))
    produced = subprocess.run([sys.executable, str(old_script)], cwd=source,
                              env=env, check=True, capture_output=True, text=True)
    pack = work / "legacy.pack.db"
    before_hash = hashlib.sha256(pack.read_bytes()).hexdigest()

    # Current imports are deliberately resolved from this checkout.
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo))
    sys.path.insert(0, str(repo / "enterprise"))
    from smriti_enterprise import facts_asof, open_pack, verify_pack
    from smriti import HashEmbedder
    from smriti.retrieval import retrieve

    manifest = verify_pack(str(pack))
    store, _ = open_pack(str(pack), expected_embedder="hash-256")
    try:
        fact = store.get_fact(1)
        fts = store.fts_search("legacy", "fact")
        temporal = facts_asof(store)
        exported = store.export_data()
        hits = retrieve(store, HashEmbedder(), "legacy", k=3)
        after_hash = hashlib.sha256(pack.read_bytes()).hexdigest()
        columns = [row[1] for row in store.db.execute("PRAGMA table_info(facts)")]
        result = {
            "historical_source": str(source),
            "historical_source_revision": "6d21be6",
            "producer_stdout": produced.stdout.strip(),
            "pack": str(pack),
            "manifest": manifest,
            "pack_sha256_before": before_hash,
            "pack_sha256_after": after_hash,
            "pack_unchanged": before_hash == after_hash,
            "facts_columns": columns,
            "scope_column_present": "scope" in columns,
            "get_fact_scope": fact.scope if fact else None,
            "fts_hits": fts,
            "facts_asof_scopes": [f.scope for f in temporal],
            "export_scopes": [f.get("scope") for f in exported["facts"]],
            "retrieve_hit_count": len(hits),
            "limitations": [
                "The historical fixture contains one fact and does not exercise scoped data; compatibility projects scope to empty.",
                "Read-only compatibility does not add scope or enterprise governance columns to the verified pack.",
            ],
        }
    finally:
        store.close()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
