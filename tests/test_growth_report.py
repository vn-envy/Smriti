import json

from bench import growth_report


def artifact(adapter="smriti-nomic"):
    return {
        "schema_version": 2,
        "status": "complete",
        "adapter": adapter,
        "configuration": adapter,
        "effective_embedder": {
            "provider": "ollama",
            "model": "nomic-embed-text:v1.5",
            "configured_embedding_dims": 768,
            "measured_embedding_dims": 768,
            "endpoint": "http://127.0.0.1:11436",
        },
        "model_cost": {"observed_paid_api_usd": 0},
        "checkpoints": [{
            "documents": 100,
            "incremental_ingest_ms": 10.0,
            "timed_query_samples": 1,
            "timed_queries": [{
                "query": "passport renewal appointment",
                "returned_ids": ["n0000000", "n0000001"],
                "per_hit_relevance": [True, False],
                "relevant_ids": ["n0000000"],
            }],
            "warm_nonempty_results": 1,
            "warm_queries_with_relevant_result": 1,
            "warm_query_ms_p50": 1.0,
            "warm_query_ms_p95": 2.0,
            "storage_bytes": 100,
        }],
    }


def write_artifact(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(json.dumps(value))
    return str(path)


def test_malformed_checkpoint_types_are_reported_without_sort_type_error(tmp_path):
    value = artifact()
    value["checkpoints"].append({"documents": None})
    result = growth_report.summarize(write_artifact(tmp_path, "bad.json", value))
    assert result["validity"]["headline_valid"] is False
    assert any("positive integer" in error for error in result["validity"]["errors"])


def test_missing_ingest_is_invalid_and_cumulative_unknown(tmp_path):
    value = artifact()
    del value["checkpoints"][0]["incremental_ingest_ms"]
    result = growth_report.summarize(write_artifact(tmp_path, "missing.json", value))
    assert result["validity"]["headline_valid"] is False
    assert result["checkpoint_table"][0]["cumulative_ingest_ms"] is None


def test_semantic_parity_requires_complete_effective_config(tmp_path):
    first = artifact("smriti-nomic")
    second = artifact("mem0")
    second["effective_embedder"]["endpoint"] = None
    result = growth_report.combine([
        write_artifact(tmp_path, "smriti.json", first),
        write_artifact(tmp_path, "mem0.json", second),
    ])
    assert result["semantic_parity"]["matched_effective_config_verified"] is False


def test_semantic_parity_accepts_two_distinct_matching_adapters(tmp_path):
    result = growth_report.combine([
        write_artifact(tmp_path, "smriti.json", artifact("smriti-nomic")),
        write_artifact(tmp_path, "mem0.json", artifact("mem0")),
    ])
    assert result["semantic_parity"]["matched_effective_config_verified"] is True
