"""Summarize growth artifacts without inventing measurements.

The input artifacts are deliberately kept separate from this derived report.
Missing target checkpoints remain ``null`` and partial/legacy inputs are
identified in the validity section instead of being promoted to headline data.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


TARGETS = (3000, 9000, 36500)
QUERIES = {
    "passport renewal appointment": 0,
    "doctor knee recommendation": 1,
    "project launch date": 2,
    "invoice due date": 3,
    "emergency contact": 4,
}


def _number(value: Any) -> int | float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        return None
    return value


def _synthetic_relevant(query: Any, identifier: Any) -> bool:
    if not isinstance(query, str) or query not in QUERIES or not isinstance(identifier, str):
        return False
    digits = "".join(character for character in identifier if character.isdigit())
    return bool(digits) and int(digits) % len(QUERIES) == QUERIES[query]


def _track_kind(data: dict[str, Any]) -> str:
    adapter = str(data.get("adapter", ""))
    configuration = str(data.get("configuration", ""))
    return "lexical" if adapter == "gbrain" or "lexical" in configuration.lower() else "semantic"


def _effective_embedder(data: dict[str, Any]) -> dict[str, Any] | None:
    value = data.get("effective_embedder")
    if isinstance(value, dict):
        return {
            "provider": value.get("provider"),
            "model": value.get("model"),
            "configured_embedding_dims": value.get("configured_embedding_dims", value.get("embedding_dims")),
            "measured_embedding_dims": value.get("measured_embedding_dims"),
            "endpoint": value.get("endpoint", value.get("ollama_base_url")),
        }
    return None


def _validity(data: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    status = data.get("status")
    if data.get("schema_version") != 2:
        errors.append("schema_version is not 2")
    if status not in {"complete", "partial", "blocked"}:
        errors.append("artifact has no explicit complete/partial/blocked status")
        status = "legacy_unspecified"
    rows = data.get("checkpoints")
    if not isinstance(rows, list):
        errors.append("checkpoints is not a list")
        rows = []
    docs: list[int] = []
    for index, row in enumerate(rows):
        value = row.get("documents") if isinstance(row, dict) else None
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(f"checkpoint {index} documents is not a positive integer")
        else:
            docs.append(value)
    if len(docs) != len(set(docs)) or docs != sorted(docs):
        errors.append("checkpoint documents are not unique, positive, and increasing")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"checkpoint {index} is not an object")
            continue
        sample_count = row.get("timed_query_samples")
        if not isinstance(sample_count, int) or sample_count <= 0:
            errors.append(f"checkpoint {index} has no positive timed sample count")
        for field in ("incremental_ingest_ms", "warm_query_ms_p50", "warm_query_ms_p95", "storage_bytes"):
            value = _number(row.get(field))
            if value is None or value < 0:
                errors.append(f"checkpoint {index} is missing a finite nonnegative {field}")
        timed = row.get("timed_queries")
        if not isinstance(timed, list):
            errors.append(f"checkpoint {index} lacks per-query returned-ID details")
            timed = []
        if isinstance(sample_count, int) and len(timed) != sample_count:
            errors.append(f"checkpoint {index} timed query detail count does not match sample count")
        observed_nonempty = 0
        observed_relevant = 0
        for query_index, detail in enumerate(timed):
            if not isinstance(detail, dict):
                errors.append(f"checkpoint {index} query {query_index} is not an object")
                continue
            returned = detail.get("returned_ids")
            per_hit = detail.get("per_hit_relevance")
            relevant = detail.get("relevant_ids")
            if not isinstance(returned, list) or not returned:
                errors.append(f"checkpoint {index} query {query_index} returned no IDs")
                continue
            if not isinstance(per_hit, list) or len(per_hit) != len(returned):
                errors.append(f"checkpoint {index} query {query_index} relevance length mismatches returned IDs")
                continue
            if not isinstance(relevant, list):
                errors.append(f"checkpoint {index} query {query_index} has invalid relevant IDs")
                continue
            recomputed = [_synthetic_relevant(detail.get("query"), identifier) for identifier in returned]
            if per_hit != recomputed:
                errors.append(f"checkpoint {index} query {query_index} relevance does not match synthetic topic buckets")
            expected_ids = [identifier for identifier, is_relevant in zip(returned, recomputed) if is_relevant]
            if relevant != expected_ids:
                errors.append(f"checkpoint {index} query {query_index} relevant IDs are inconsistent")
            observed_nonempty += 1
            observed_relevant += bool(expected_ids)
        if isinstance(sample_count, int):
            if row.get("warm_nonempty_results") != observed_nonempty:
                errors.append(f"checkpoint {index} nonempty count does not match query details")
            if row.get("warm_queries_with_relevant_result") != observed_relevant:
                errors.append(f"checkpoint {index} relevant-query count does not match query details")
        if data.get("adapter") == "gbrain":
            for field in ("gbrain_ingest_statuses", "gbrain_update_statuses"):
                if row.get(field) is None:
                    warnings.append(f"checkpoint {index} lacks {field}")
    headline_valid = not errors and status == "complete"
    return {
        "status": status,
        "headline_valid": headline_valid,
        "errors": errors,
        "warnings": warnings,
        "completed_checkpoints": docs,
    }


def _checkpoint_row(data: dict[str, Any], row: dict[str, Any], cumulative_ingest: float | None, cumulative_maintenance: float | None) -> dict[str, Any]:
    return {
        "track": data.get("adapter"),
        "track_kind": _track_kind(data),
        "configuration": data.get("configuration"),
        "documents": row.get("documents"),
        "timed_query_samples": row.get("timed_query_samples"),
        "incremental_ingest_ms": row.get("incremental_ingest_ms"),
        "cumulative_ingest_ms": round(cumulative_ingest, 3) if cumulative_ingest is not None else None,
        "same_payload_update_ms": row.get("same_payload_update_ms"),
        "cold_query_boundary": row.get("cold_query_boundary"),
        "process_restart_startup_ms": row.get("process_restart_startup_ms"),
        "first_query_after_ingest_ms": row.get("first_query_after_ingest_ms"),
        "cold_query_after_restart_ms": row.get("cold_query_after_restart_ms"),
        "warm_query_ms_p50": row.get("warm_query_ms_p50"),
        "warm_query_ms_p95": row.get("warm_query_ms_p95"),
        "storage_bytes": row.get("storage_bytes"),
        "storage_mb": row.get("storage_mb"),
        "gbrain_analyze_maintenance_ms": row.get("gbrain_analyze_maintenance_ms"),
        "cumulative_gbrain_analyze_maintenance_ms": round(cumulative_maintenance, 3) if cumulative_maintenance is not None else None,
    }


def summarize(path: str) -> dict[str, Any]:
    source = Path(path)
    data = json.loads(source.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{source} must contain a JSON object")
    validity = _validity(data)
    rows = data.get("checkpoints", [])
    cumulative_ingest: float | None = 0.0
    maintenance_values: list[float] = []
    maintenance_known = True
    checkpoint_rows: list[dict[str, Any]] = []
    by_documents: dict[int, dict[str, Any]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        ingest = _number(row.get("incremental_ingest_ms"))
        if cumulative_ingest is not None and ingest is not None and ingest >= 0:
            cumulative_ingest += float(ingest)
        else:
            cumulative_ingest = None
        maintenance = _number(row.get("gbrain_analyze_maintenance_ms"))
        if maintenance is not None:
            maintenance_values.append(float(maintenance))
        elif data.get("gbrain_analyze"):
            maintenance_known = False
        cumulative_maintenance = sum(maintenance_values) if maintenance_values and maintenance_known else None
        normalized = _checkpoint_row(data, row, cumulative_ingest, cumulative_maintenance)
        checkpoint_rows.append(normalized)
        if isinstance(row.get("documents"), int):
            by_documents[row["documents"]] = normalized
    target_rows = []
    for target in TARGETS:
        row = by_documents.get(target)
        target_rows.append({
            "track": data.get("adapter"),
            "track_kind": _track_kind(data),
            "target_documents": target,
            "measured": row is not None,
            "headline_valid": bool(row is not None and validity["headline_valid"]),
            "checkpoint": row,
            "bound": "measured" if row is not None else "not_measured",
        })
    model_cost = data.get("model_cost") if isinstance(data.get("model_cost"), dict) else {}
    return {
        "schema_version": 1,
        "source": str(source),
        "track": {
            "adapter": data.get("adapter"),
            "kind": _track_kind(data),
            "configuration": data.get("configuration"),
            "effective_embedder": _effective_embedder(data),
            "gbrain_analyze": bool(data.get("gbrain_analyze", False)),
            "model_cost": {
                "observed_paid_api_usd": model_cost.get("observed_paid_api_usd"),
                "hardware_electricity_cost_usd": model_cost.get("hardware_electricity_cost_usd"),
                "note": model_cost.get("note"),
            },
        },
        "validity": validity,
        "checkpoint_table": checkpoint_rows,
        "target_mapping": target_rows,
    }


def _semantic_parity(reports: list[dict[str, Any]]) -> dict[str, Any]:
    semantic = [report for report in reports if report["track"]["kind"] == "semantic"]
    configs = [report["track"].get("effective_embedder") for report in semantic]
    adapters = [report["track"]["adapter"] for report in semantic]
    comparable = len(set(adapters)) >= 2 and len(configs) >= 2 and all(
        config is not None
        and all(config.get(key) not in (None, "") for key in ("provider", "model", "endpoint"))
        and isinstance(config.get("configured_embedding_dims"), (int, float))
        and config["configured_embedding_dims"] > 0
        and isinstance(config.get("measured_embedding_dims"), (int, float))
        and config["measured_embedding_dims"] > 0
        for config in configs
    )
    if comparable:
        comparable = len({(c.get("provider"), c.get("model"), c.get("measured_embedding_dims"), c.get("configured_embedding_dims"), c.get("endpoint")) for c in configs}) == 1
    return {
        "semantic_tracks": [report["track"]["adapter"] for report in semantic],
        "matched_effective_config_verified": comparable,
        "note": "Semantic speed comparison requires equal effective provider/model/configured and measured dimensions; lexical GBrain remains separate." if not comparable else "Effective semantic embedder configuration matches across semantic tracks.",
    }


def combine(paths: list[str]) -> dict[str, Any]:
    reports = [summarize(path) for path in paths]
    return {
        "schema_version": 1,
        "reports": reports,
        "semantic_parity": _semantic_parity(reports),
        "cost_scope": {
            "semantic_tracks": "Local model/API paid cost is reported from each artifact; unknown remains null. Hardware/electricity is not measured.",
            "lexical_tracks": "GBrain no-embedding route is separate and has no embedding API cost; hardware/electricity remains unmeasured.",
            "managed_pricing": "Managed subscription projections are outside these measured local artifacts.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", nargs=3, metavar="ARTIFACT", required=True, help="three raw growth JSON artifacts: semantic Smriti, semantic Mem0, lexical GBrain")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = combine(args.input)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
