#!/usr/bin/env python3
"""Offline control-flow QA for ``bench/hindsight_comparative.py``.

This test replaces both the Hindsight client and HTTP helper before importing
the runner.  It exercises artifact persistence, ownership-aware cleanup,
completeness, and optional version handling without contacting any service or
model.  The output JSON is a QA record, never comparative benchmark evidence.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = ROOT / "bench" / "hindsight_comparative.py"
OUTPUT = ROOT / "audit" / "2026-09-05" / "raw" / "hindsight-comparative-harness-qa.json"


class FakeHindsight:
    scenario = "success"
    instances: list["FakeHindsight"] = []

    def __init__(self, **_kwargs):
        self.retains = 0
        self.recalls = 0
        self.deletes = 0
        self.closed = False
        type(self).instances.append(self)
        if type(self).scenario == "config_missing":
            self.get_bank_config = None

    def create_bank(self, **kwargs):
        if type(self).scenario == "create_failure":
            return None
        return {"bank_id": kwargs["bank_id"]}

    def retain(self, **kwargs):
        self.retains += 1
        if type(self).scenario == "midretain" and self.retains == 5:
            raise RuntimeError("injected retain failure")
        if type(self).scenario == "none_retain" and self.retains == 5:
            return None
        return {"source_id": kwargs["document_id"], "ok": True}

    def recall(self, **_kwargs):
        self.recalls += 1
        return {"results": [{"text": "[SOURCE_DOCUMENT_ID=d01] diagnostic only"}]}

    def get_bank_config(self, _bank_id):
        if type(self).scenario == "config_failure":
            raise RuntimeError("injected bank config failure")
        return {
            "bank_id": _bank_id,
            "config": {
                # This mirrors HindsightConfig's v0.9.2 flat response shape.
                "llm_provider": "ollama",
                "llm_model": "qwen3:8b",
                "llm_base_url": "http://user:secret@127.0.0.1:11436/v1?token=hidden",
                "retain_llm_model": "qwen3:8b",
                "embeddings_provider": "ollama",
                "retain_extraction_mode": "guided",
                "retain_chunk_size": 800,
                "retain_structured_chunk_size": 1200,
                "enable_observations": False,
                "enable_temporal_retrieval": True,
                "enable_graph_retrieval": True,
                "enable_reranking": False,
                "llm_api_key": "never persist",
                "database_url": "postgres://user:secret@example/db?password=hidden",
            },
            "overrides": {"retain_chunk_size": 900},
        }

    def delete_bank(self, bank_id):
        self.deletes += 1
        if type(self).scenario == "cleanup_failure":
            raise RuntimeError("injected cleanup failure")
        return {"deleted": bank_id}

    def close(self):
        self.closed = True
        if type(self).scenario == "close_failure":
            raise RuntimeError("injected close failure")


def load_runner():
    # The runner's HTTP functions are patched before invocation.  Installing a
    # fake module keeps this QA independent of the optional httpx dependency.
    fake_httpx = types.ModuleType("httpx")
    fake_httpx.get = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("offline QA attempted an HTTP call"))
    sys.modules["httpx"] = fake_httpx
    spec = importlib.util.spec_from_file_location("hindsight_comparative", RUNNER_PATH)
    runner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(runner)
    fake_client_module = types.ModuleType("hindsight_client")
    fake_client_module.Hindsight = FakeHindsight
    sys.modules["hindsight_client"] = fake_client_module
    return runner


def main() -> int:
    runner = load_runner()
    real_dataset = runner.load_dataset()
    temp_root = Path(tempfile.mkdtemp(prefix="hindsight-comparative-harness-qa-"))
    results = []

    def run_case(name, scenario, *, dataset=None, version_ok=True):
        FakeHindsight.scenario = scenario
        FakeHindsight.instances.clear()
        runner.OUTPUT = temp_root / f"{name}.json"
        runner.load_dataset = (lambda dataset=dataset: dataset) if dataset is not None \
            else (lambda: real_dataset)

        def fake_get(path):
            if path == "/version" and not version_ok:
                raise RuntimeError("injected 404")
            return {"status": "ok", "path": path}

        runner._get_json = fake_get
        runner.metrics_snapshot = lambda: {"selected_lines": [], "raw_text": ""}
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = runner.main()
        report = json.loads(runner.OUTPUT.read_text())
        instance = FakeHindsight.instances[-1]
        result = {
            "case": name,
            "exit_code": exit_code,
            "status": report.get("status"),
            "progress": report.get("progress"),
            "completeness": report.get("completeness"),
            "failure_count": report.get("failure_count"),
            "warnings": report.get("warnings", []),
            "observed_config": report.get("config", {}).get("observed_server_configuration"),
            "delete_calls": instance.deletes,
            "closed": instance.closed,
            "artifact": str(runner.OUTPUT),
        }
        results.append(result)
        return report, instance

    report, instance = run_case("success", "success")
    assert report["status"] == "ok" and report["completeness"]["complete"]
    assert instance.deletes == 1
    observed = report["config"]["observed_server_configuration"]
    assert observed["config"]["llm_provider"] == "ollama"
    assert observed["config"]["llm_model"] == "qwen3:8b"
    assert observed["config"]["llm_base_url"] == "http://127.0.0.1:11436/v1"
    assert observed["config"]["retain_chunk_size"] == 800
    assert observed["config"]["enable_temporal_retrieval"] is True
    assert observed["overrides"]["retain_chunk_size"] == 900
    assert "secret" not in json.dumps(observed).casefold()
    assert "api_key" not in json.dumps(observed).casefold()

    report, instance = run_case("create-failure", "create_failure")
    assert report["status"] == "blocked_create_bank" and instance.deletes == 0

    report, instance = run_case("midretain-failure", "midretain")
    assert report["status"] == "completed_with_failures"
    assert report["progress"]["retains_completed"] == 19 and instance.deletes == 1

    malformed = {
        "name": "malformed", "license": "CC0-1.0",
        "documents": [{"timestamp": "2024-01-01T00:00:00Z", "text": "missing id"}],
        "queries": [{"id": "q01", "query": "x", "relevant": []}],
    }
    report, instance = run_case("malformed-document", "success", dataset=malformed)
    assert report["status"] == "completed_with_failures"
    assert report["runner_error"]["type"] == "KeyError" and instance.deletes == 1

    report, instance = run_case("close-failure", "close_failure")
    assert report["status"] == "completed_with_failures"
    assert "client_close_error" in report and instance.deletes == 1

    report, instance = run_case("cleanup-failure", "cleanup_failure")
    assert report["status"] == "completed_with_failures"
    assert any(item["name"] == "delete_bank" and not item["ok"]
               for item in report["steps"])
    assert instance.deletes == 1

    report, instance = run_case("none-retain-response", "none_retain")
    assert report["status"] == "completed_with_failures"
    assert report["progress"]["retains_completed"] == 19
    assert report["incomplete_units"] >= 1 and instance.deletes == 1

    report, instance = run_case("version-404-warning", "success", version_ok=False)
    assert report["status"] == "ok"
    assert any("version endpoint unavailable" in item for item in report["warnings"])
    assert instance.deletes == 1

    report, instance = run_case("bank-config-missing", "config_missing")
    assert report["status"] == "ok" and report["config"]["observed_server_configuration"] is None
    assert any("bank config endpoint unavailable" in item for item in report["warnings"])
    assert instance.deletes == 1

    report, instance = run_case("bank-config-failure", "config_failure")
    assert report["status"] == "ok" and report["config"]["observed_server_configuration"] is None
    assert any("bank config endpoint unavailable" in item for item in report["warnings"])
    assert instance.deletes == 1

    qa = {
        "probe": "hindsight_comparative_harness_control_flow_qa",
        "runner": str(RUNNER_PATH),
        "network_calls": 0,
        "model_calls": 0,
        "benchmark_evidence": False,
        "cases": results,
        "notes": [
            "Hindsight client and HTTP helper were isolated fakes in this process.",
            "The records test control flow and artifact handling only; they are not benchmark evidence.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(qa, indent=2) + "\n")
    print(json.dumps(qa, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
