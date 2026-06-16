"""SMRITI quickstart — runs fully offline (HashEmbedder + MockLLM).

Swap in real components for production:

    from smriti import Smriti, LLM, OllamaEmbedder
    mem = Smriti(path="memory.db",
                 embedder=OllamaEmbedder("nomic-embed-text"),
                 llm=LLM("qwen3:14b", provider="ollama"))
"""
import json

from smriti import HashEmbedder, MockLLM, Smriti

e1 = json.dumps([
    {"statement": "The user lives in Hyderabad.", "subject": "user",
     "predicate": "lives_in", "object": "Hyderabad", "entities": ["Hyderabad"],
     "event_date": None, "kind": "profile"},
    {"statement": "The user is building SigmaFlow, a reliability middleware for agent pipelines.",
     "subject": "user", "predicate": "founded", "object": "SigmaFlow",
     "entities": ["SigmaFlow"], "event_date": None, "kind": "knowledge"},
])
e2 = json.dumps([
    {"statement": "The user lives in Bengaluru.", "subject": "user",
     "predicate": "lives_in", "object": "Bengaluru", "entities": ["Bengaluru"],
     "event_date": "2026-06-01", "kind": "profile"},
])

mem = Smriti(embedder=HashEmbedder(), llm=MockLLM([e1, e2]), mode="full")

mem.add([{"role": "user", "content": "I live in Hyderabad and I'm building SigmaFlow."}],
        timestamp="2026-01-15T10:00:00Z")
mem.add([{"role": "user", "content": "Update: I moved to Bengaluru on June 1st."}],
        timestamp="2026-06-02T10:00:00Z")

print("stats:", mem.stats())
print("\n--- search: 'where does the user live?' ---")
for r in mem.search("where does the user live?", k=4):
    print(f"  [{r.kind}] {r.text}  (channels: {','.join(sorted(set(r.channels)))})")

print("\n--- packed context (what the answering model sees) ---")
print(mem.context("where does the user live?"))
