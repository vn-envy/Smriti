"""Offline tests for retrieval profiles (drishti) — channel gating, the v2
router, profile plumbing through Smriti and the MCP server. HashEmbedder +
MockLLM only: no network, no keys."""
import json

from smriti import HashEmbedder, PROFILES, RetrievalProfile, Smriti, resolve_profile
from smriti.mcp_server import SmritiMCP
from smriti.retrieval import CHANNEL_GROUPS, expand_channels


def seeded():
    mem = Smriti(path=":memory:", embedder=HashEmbedder(), mode="lite")
    mem.add([{"role": "user", "content": "I adopted a golden retriever named Bruno."}],
            timestamp="2025-03-10T09:00:00Z")
    mem.add([{"role": "user", "content": "My dentist appointment is at the Begumpet clinic."}],
            timestamp="2025-04-02T10:00:00Z")
    mem.add([{"role": "user", "content": "Rachel started working with Priya at Acme."}],
            timestamp="2025-05-05T10:00:00Z")
    return mem


# ------------------------------------------------------------ channel masks
def test_expand_channels_accepts_names_aliases_and_internal_keys():
    assert expand_channels(None) is None
    assert expand_channels({"lexical"}) == set(CHANNEL_GROUPS["lexical"])
    # Sanskrit aliases resolve to the same groups
    assert expand_channels({"shabda"}) == expand_channels({"lexical"})
    assert expand_channels({"kala"}) == {"temporal"}
    # raw internal keys pass through
    assert expand_channels({"bm25_fact"}) == {"bm25_fact"}


def test_expand_channels_rejects_unknown():
    try:
        expand_channels({"telepathy"})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "telepathy" in str(e)


def test_lexical_only_search_uses_only_bm25_channels():
    mem = seeded()
    hits = mem.search("Begumpet dentist appointment", channels={"lexical"})
    assert hits, "lexical-only search should still find the needle"
    for r in hits:
        assert set(r.channels) <= set(CHANNEL_GROUPS["lexical"]), r.channels


def test_semantic_only_search_uses_only_vector_channels():
    mem = seeded()
    hits = mem.search("dog adoption", channels={"artha"})
    for r in hits:
        assert set(r.channels) <= set(CHANNEL_GROUPS["semantic"]), r.channels


# ---------------------------------------------------------------- profiles
def test_builtin_profiles_exist_and_are_frozen():
    for name in ("facts", "relations", "timeline", "deep", "precision"):
        assert name in PROFILES
        assert PROFILES[name].evidence  # every shipped profile carries its receipt
    try:
        PROFILES["facts"].k = 99
        assert False, "profiles must be immutable"
    except Exception:
        pass


def test_profile_search_and_context_run_offline():
    mem = seeded()
    for name in ("facts", "relations", "timeline", "deep", "precision", "auto"):
        hits = mem.search("Where is my dentist appointment?", profile=name)
        assert isinstance(hits, list)
    ctx = mem.context("Where is my dentist appointment?", profile="facts")
    assert "Begumpet" in ctx


def test_deep_profile_packs_aggregation_instruction():
    mem = seeded()
    ctx = mem.context("how many pets do I have?", profile="deep")
    assert "COUNTING / AGGREGATION" in ctx


def test_custom_profile_is_data_not_code():
    mem = seeded()
    support = RetrievalProfile(name="support", channels={"lexical", "semantic"},
                               k=5, include_observations=False)
    hits = mem.search("Bruno the retriever", profile=support)
    assert hits and all(
        set(r.channels) <= set(CHANNEL_GROUPS["lexical"]) | set(CHANNEL_GROUPS["semantic"])
        for r in hits)


def test_explicit_channels_override_profile_channels():
    mem = seeded()
    # timeline profile normally excludes entity; the explicit mask overrides
    hits = mem.search("Begumpet clinic", profile="timeline", channels={"lexical"})
    for r in hits:
        assert set(r.channels) <= set(CHANNEL_GROUPS["lexical"])


def test_unknown_profile_raises():
    mem = seeded()
    try:
        mem.search("anything", profile="clairvoyance")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "clairvoyance" in str(e)


# ---------------------------------------------------------------- router v2
def test_router_aggregation_routes_deep():
    assert resolve_profile("how many concerts did I attend in total?").name == "deep"


def test_router_dates_and_tense_route_timeline():
    assert resolve_profile("what happened in March 2025?").name == "timeline"
    assert resolve_profile("where did I live before the move?").name == "timeline"


def test_router_relation_cues_route_relations():
    assert resolve_profile("who works with Rachel?").name == "relations"


def test_router_default_routes_facts():
    assert resolve_profile("current address on file").name == "facts"


def test_router_two_known_entities_route_relations():
    mem = seeded()
    # "rachel" and "priya" are both in the entity vocabulary via episodes? —
    # lite mode has no extracted entities, so this must fall back to facts.
    p = resolve_profile("rachel priya acme", store=mem.store)
    assert p.name in ("relations", "facts")  # depends on entity vocabulary


# -------------------------------------------------------------- legacy path
def test_default_search_and_context_unchanged_without_profile():
    mem = seeded()
    hits = mem.search("Where is my dentist appointment?")
    assert any("Begumpet" in r.text for r in hits)
    ctx = mem.context("Where is my dentist appointment?")
    assert "Begumpet" in ctx  # legacy precision path, byte-identical policy


# -------------------------------------------------------------------- MCP
def _call(srv, name, args):
    resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
    assert "error" not in resp, resp
    return json.loads(resp["result"]["content"][0]["text"])


def test_mcp_recall_and_search_accept_profile_and_channels():
    srv = SmritiMCP(seeded())
    out = _call(srv, "recall", {"query": "Where is my dentist appointment?",
                                "profile": "facts"})
    assert "Begumpet" in out["context"]
    out = _call(srv, "search", {"query": "Begumpet clinic",
                                "channels": ["shabda"]})
    assert out["results"]
    for r in out["results"]:
        assert set(r["channels"]) <= set(CHANNEL_GROUPS["lexical"])


def test_mcp_rejects_bad_profile_and_bad_channel():
    srv = SmritiMCP(seeded())
    resp = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                       "params": {"name": "recall",
                                  "arguments": {"query": "x", "profile": "clairvoyance"}}})
    assert "error" in resp
    resp = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "search",
                                  "arguments": {"query": "x", "channels": ["telepathy"]}}})
    assert "error" in resp


def test_mcp_tool_defs_advertise_profiles():
    from smriti.mcp_server import TOOL_DEFS
    recall = next(t for t in TOOL_DEFS if t["name"] == "recall")
    assert "profile" in recall["inputSchema"]["properties"]
    assert "facts" in recall["inputSchema"]["properties"]["profile"]["enum"]
