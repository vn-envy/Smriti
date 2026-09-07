"""Offline regression tests for source-grounded extraction scopes."""

import json

from smriti import Fact, HashEmbedder, MockLLM, Smriti
from smriti.extraction import parse_facts, validate_fact_scopes
from smriti.mcp_server import SmritiMCP


def _facts(items):
    return parse_facts(json.dumps(items), "scope-test", "2025-03-10T12:00:00Z")


def test_scope_validation_rejects_typo_but_accepts_exact_and_location_contexts():
    turns = [{"role": "user", "content":
              "Leila switched from Sketch to Figma for project Cedar and worked in Mumbai."}]
    facts = _facts([
        {"statement": "Leila uses Figma for project Cedar", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "project:Cedar"},
        {"statement": "Leila switched from Sketch to Figma for project Cedar", "subject": "Leila",
         "predicate": "switched_from", "object": "Sketch", "scope": "project:Ceder"},
        {"statement": "Leila worked in Mumbai", "subject": "Leila",
         "predicate": "worked_in", "object": "Mumbai", "scope": "location:Mumbai"},
    ])
    valid, invalid = validate_fact_scopes(facts, turns)
    assert [fact.scope for fact in valid] == ["project:Cedar", "location:Mumbai"]
    assert len(invalid) == 1 and invalid[0]["scope"] == "project:Ceder"


def test_scope_validation_supports_multiword_quotes_and_rejects_date_scope_and_bleed():
    turns = [{"role": "user", "content":
              "For project 'North Star', Leila uses Figma. Separately, Leila prefers dark mode globally."}]
    facts = _facts([
        {"statement": "Leila uses Figma for project North Star", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "project:North Star"},
        {"statement": "Leila prefers dark mode globally", "subject": "Leila",
         "predicate": "prefers", "object": "dark mode", "scope": "project:North Star"},
        {"statement": "Leila uses Figma on 2025-03-10", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "date:2025-03-10"},
    ])
    valid, invalid = validate_fact_scopes(facts, turns)
    assert [fact.scope for fact in valid] == ["project:North Star"]
    assert {item["scope"] for item in invalid} == {"project:North Star", "date:2025-03-10"}


def test_scope_validation_requires_statement_context_for_other_person():
    turns = [{"role": "user", "content": "Leila lives in Kyoto. Omar lives in Nairobi."}]
    facts = _facts([
        {"statement": "Omar lives in Nairobi", "subject": "Omar",
         "predicate": "lives_in", "object": "Nairobi", "scope": "location:Nairobi"},
        {"statement": "Leila lives in Kyoto", "subject": "Leila",
         "predicate": "lives_in", "object": "Kyoto", "scope": "location:Nairobi"},
    ])
    valid, invalid = validate_fact_scopes(facts, turns)
    assert len(valid) == 1 and valid[0].subject == "Omar"
    assert len(invalid) == 1 and invalid[0]["subject"] == "Leila"


def test_memory_retries_one_invalid_scope_and_keeps_corrected_fact():
    source = "Leila switched from Sketch to Figma for project Cedar."
    invalid = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "switched_from",
        "object": "Sketch", "scope": "project:Ceder",
    }])
    corrected = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "switched_from",
        "object": "Sketch", "scope": "project:Cedar",
    }])
    llm = MockLLM([invalid, corrected])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        result = memory.add([{"role": "user", "content": source}],
                           session_id="retry-success", timestamp="2025-03-10T12:00:00Z")
        assert result["facts"] == 1
        assert llm.calls == 2
        assert memory.store.get_fact(1).scope == "project:Cedar"
        diagnostics = memory.last_extraction_diagnostics["scope_validation"]
        assert diagnostics["retry_used"] is True
        assert diagnostics["first_invalid"][0]["scope"] == "project:Ceder"
        assert diagnostics["second_invalid"] == []
        assert diagnostics["facts_dropped_after_retry"] == []
        assert result["scope_validation"]["outcome"] == "corrected"
        assert result["scope_validation"]["rejected_candidates"] == 0
    finally:
        memory.close()


def test_scope_retry_exhaustion_drops_invalid_scope_but_retains_raw_episode_and_valid_fact():
    source = "Leila uses Figma for project Cedar. Leila prefers dark mode globally."
    invalid = json.dumps([
        {"statement": "Leila uses Figma for project Cedar", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "project:Ceder"},
        {"statement": "Leila prefers dark mode globally", "subject": "Leila",
         "predicate": "prefers", "object": "dark mode", "scope": ""},
    ])
    llm = MockLLM([invalid, invalid])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        result = memory.add([{"role": "user", "content": source}],
                           session_id="retry-exhausted", timestamp="2025-03-10T12:00:00Z")
        assert result["facts"] == 1
        assert llm.calls == 2
        assert memory.store.similar_valid_facts("leila", "uses_tool", "project:Ceder") == []
        assert memory.store.similar_valid_facts("leila", "prefers", "")
        episode = memory.store.get_episode(1)
        assert episode is not None and episode.content == source
        diagnostics = memory.last_extraction_diagnostics["scope_validation"]
        assert diagnostics["retry_used"] is True
        assert diagnostics["second_invalid"][0]["scope"] == "project:Ceder"
        assert diagnostics["facts_dropped_after_retry"][0]["scope"] == "project:Ceder"
        assert result["scope_validation"]["outcome"] == "rejected"
        assert result["scope_validation"]["facts_dropped_after_retry"] == 1
    finally:
        memory.close()


def test_scope_retry_cannot_silently_globalize_rejected_candidate():
    source = "Leila uses Figma for project Cedar."
    invalid = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "uses_tool",
        "object": "Figma", "scope": "project:Ceder",
    }])
    erased_scope = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "uses_tool",
        "object": "Figma", "scope": "",
    }])
    llm = MockLLM([invalid, erased_scope])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        result = memory.add([{"role": "user", "content": source}],
                           session_id="retry-erases-scope", timestamp="2025-03-10T12:00:00Z")
        assert result["facts"] == 0
        assert result["scope_validation"]["outcome"] == "rejected"
        assert memory.store.facts_for_key("leila", "uses_tool", "") == []
        episode = memory.store.get_episode(1)
        assert episode is not None and episode.content == source
        diagnostics = memory.last_extraction_diagnostics["scope_validation"]
        assert diagnostics["second_invalid"][0]["reason"].startswith(
            "retry erased scope from an originally rejected candidate")
    finally:
        memory.close()


def test_scope_correction_keeps_valid_first_facts_if_retry_omits_them():
    source = "Leila uses Figma for project Cedar. Leila prefers dark mode globally."
    first = json.dumps([
        {"statement": "Leila uses Figma for project Cedar", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "project:Ceder"},
        {"statement": "Leila prefers dark mode globally", "subject": "Leila",
         "predicate": "prefers", "object": "dark mode", "scope": ""},
    ])
    retry_omits_valid_first_fact = json.dumps([{
        "statement": "Leila uses Figma for project Cedar", "subject": "Leila",
        "predicate": "uses_tool", "object": "Figma", "scope": "project:Cedar",
    }])
    llm = MockLLM([first, retry_omits_valid_first_fact])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        result = memory.add([{"role": "user", "content": source}],
                           session_id="retry-merge", timestamp="2025-03-10T12:00:00Z")
        assert result["facts"] == 2
        assert memory.store.similar_valid_facts("leila", "uses_tool", "project:Cedar")
        assert memory.store.similar_valid_facts("leila", "prefers", "")
    finally:
        memory.close()


def test_scope_correction_keeps_distinct_multivalued_facts():
    source = "Leila uses Figma for project Cedar. Leila prefers Python and tea globally."
    first = json.dumps([
        {"statement": "Leila uses Figma for project Cedar", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "project:Ceder"},
        {"statement": "Leila prefers Python globally", "subject": "Leila",
         "predicate": "prefers", "object": "Python", "scope": ""},
        {"statement": "Leila prefers tea globally", "subject": "Leila",
         "predicate": "prefers", "object": "tea", "scope": ""},
    ])
    retry_omits_tea = json.dumps([
        {"statement": "Leila uses Figma for project Cedar", "subject": "Leila",
         "predicate": "uses_tool", "object": "Figma", "scope": "project:Cedar"},
        {"statement": "Leila prefers Python globally", "subject": "Leila",
         "predicate": "prefers", "object": "Python", "scope": ""},
    ])
    llm = MockLLM([first, retry_omits_tea])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        result = memory.add([{"role": "user", "content": source}],
                           session_id="retry-multivalue", timestamp="2025-03-10T12:00:00Z")
        assert result["facts"] == 3
        assert memory.store.similar_valid_facts("leila", "prefers", "")
        assert {fact.object for fact in memory.store.facts_for_key("leila", "prefers", "")} == {"Python", "tea"}
    finally:
        memory.close()


def test_valid_unscoped_extraction_does_not_make_a_correction_call():
    source = "Leila prefers dark mode globally."
    valid = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "prefers",
        "object": "dark mode", "scope": "",
    }])
    llm = MockLLM([valid])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        memory.add([{"role": "user", "content": source}],
                   session_id="no-retry", timestamp="2025-03-10T12:00:00Z")
        assert llm.calls == 1
        assert memory.last_extraction_diagnostics["scope_validation"]["retry_used"] is False
    finally:
        memory.close()


def test_empty_or_malformed_scope_correction_is_not_reported_as_corrected():
    source = "Leila uses Figma for project Cedar."
    invalid = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "uses_tool",
        "object": "Figma", "scope": "project:Ceder",
    }])
    for retry in ("[]", "not JSON"):
        llm = MockLLM([invalid, retry])
        memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
        try:
            result = memory.add([{"role": "user", "content": source}],
                               session_id="retry-incomplete-" + str(len(retry)),
                               timestamp="2025-03-10T12:00:00Z")
            status = ("retry_parse_failed" if retry == "not JSON" else
                      "retry_completed")
            assert result["scope_validation"]["outcome"] == status
            assert result["scope_validation"]["unresolved_candidates"] == 1
            assert result["scope_validation"]["facts_dropped_after_retry"] == 1
            assert result["facts"] == 0
            assert memory.last_extraction_diagnostics["scope_validation"]["retry_status"] == status
        finally:
            memory.close()


def test_mcp_remember_surfaces_scope_validation_outcome_for_agent_callers():
    source = "Leila uses Figma for project Cedar."
    invalid = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "uses_tool",
        "object": "Figma", "scope": "project:Ceder",
    }])
    erased_scope = json.dumps([{
        "statement": source, "subject": "Leila", "predicate": "uses_tool",
        "object": "Figma", "scope": "",
    }])
    llm = MockLLM([invalid, erased_scope])
    memory = Smriti(path=":memory:", mode="full", llm=llm, embedder=HashEmbedder())
    try:
        result = SmritiMCP(memory).dispatch(
            "tools/call",
            {"name": "remember", "arguments": {
                "messages": [{"role": "user", "content": source}],
                "session_id": "mcp-scope-retry",
            }},
        )
        outcome = result["structuredContent"]["scope_validation"]
        assert outcome["outcome"] == "rejected"
        assert outcome["attempts"] == 2
        assert outcome["facts_dropped_after_retry"] == 1
        assert "not globalized" in outcome["warning"]
        assert "scope_validation" in result["content"][0]["text"]
    finally:
        memory.close()
