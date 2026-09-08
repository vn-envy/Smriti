"""Read-only diagnostics for an existing SMRITI SQLite store."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from . import __version__


def inspect_database(path: str) -> dict:
    resolved = Path(path).expanduser().resolve()
    report = {"smriti_version": __version__, "database": str(resolved), "ok": False}
    if not resolved.is_file():
        report["error"] = "database file does not exist"
        return report
    db = None
    try:
        db = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        required = {"episodes", "facts", "entities", "entity_aliases", "ingest_log",
                    "episodes_fts", "facts_fts", "fact_keys_fts"}
        missing = sorted(required - tables)
        counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ("episodes", "facts", "entities") if table in tables}
        dimensions = {}
        inconsistent = []
        for table in ("episodes", "facts"):
            if table not in tables:
                continue
            sizes = [r[0] for r in db.execute(
                f"SELECT DISTINCT length(emb) FROM {table} WHERE emb IS NOT NULL")]
            dimensions[table] = sorted(size // 4 for size in sizes)
            if any(size % 4 for size in sizes) or len(sizes) > 1:
                inconsistent.append(table)
        populated_dimensions = {dims[0] for dims in dimensions.values() if dims}
        if len(populated_dimensions) > 1:
            inconsistent.append("facts/episodes")
        identity = None
        if "metadata" in tables:
            row = db.execute(
                "SELECT value FROM metadata WHERE key='embedder_identity'"
            ).fetchone()
            identity = row[0] if row else None
        has_vectors = any(dimensions.values())
        if identity:
            compatibility = "tracked"
        elif has_vectors:
            compatibility = "legacy-untracked; explicit adoption required before opening"
        else:
            compatibility = "empty-untracked"
        report.update(
            integrity=integrity,
            journal_mode=db.execute("PRAGMA journal_mode").fetchone()[0],
            missing_tables=missing,
            counts=counts,
            embedding_dimensions=dimensions,
            embedder_identity=identity,
            embedder_compatibility=compatibility,
            guidance=[
                "HashEmbedder is deterministic lexical hashing, not a semantic embedding model.",
                "Full-mode extraction quality depends on the configured model; validate it on representative conversations.",
            ],
        )
        report["ok"] = integrity == "ok" and not missing and not inconsistent
        if inconsistent:
            report["inconsistent_embeddings"] = inconsistent
    except sqlite3.Error as exc:
        report["error"] = str(exc)
    finally:
        if db is not None:
            db.close()
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check a SMRITI database without modifying it")
    parser.add_argument("--db", required=True, help="path to an existing SMRITI SQLite database")
    args = parser.parse_args(argv)
    report = inspect_database(os.path.abspath(args.db))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
