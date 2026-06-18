"""Benchmark CLI.

Examples (fully local, on a Mac Studio with Ollama):

  # download datasets first:  python -m bench.download --all
  python -m bench.run --bench longmemeval --data data/longmemeval_oracle.json \\
      --mode lite --limit 50 \\
      --answer-model qwen3:14b --judge-model qwen3:14b \\
      --embed-model nomic-embed-text

  # full mode (fact extraction + consolidation) via any OpenAI-compatible API
  python -m bench.run --bench longmemeval --data data/longmemeval_s_cleaned.json \\
      --mode full --provider groq --api-key $GROQ_API_KEY \\
      --memory-model llama-3.3-70b-versatile \\
      --answer-model llama-3.3-70b-versatile --judge-model llama-3.3-70b-versatile

  python -m bench.run --bench locomo --data data/locomo10.json --mode lite --limit 100
"""
from __future__ import annotations

import argparse
import json

from smriti import LLM, HashEmbedder, HTTPReranker, OllamaEmbedder, OpenAICompatEmbedder, Smriti
from smriti.llm import PRESETS

from .locomo import load_locomo, run_locomo
from .longmemeval import load_longmemeval, run_longmemeval


def build_embedder(args):
    if args.embedder == "hash":
        return HashEmbedder()
    if args.embedder == "ollama":
        return OllamaEmbedder(model=args.embed_model, base_url=args.embed_base_url or "http://localhost:11434")
    return OpenAICompatEmbedder(model=args.embed_model,
                                base_url=args.embed_base_url or PRESETS.get(args.provider, ""),
                                api_key=args.api_key)


def main():
    p = argparse.ArgumentParser(description="SMRITI benchmark runner")
    p.add_argument("--bench", choices=["longmemeval", "locomo"], required=True)
    p.add_argument("--data", required=True, help="path to dataset json")
    p.add_argument("--mode", choices=["lite", "full"], default="lite")
    p.add_argument("--limit", type=int, default=None, help="use the FIRST N questions (ordered by type)")
    p.add_argument("--sample", type=int, default=None,
                   help="use ~N questions spread EVENLY across question types (representative)")
    p.add_argument("--k", type=int, default=12, help="retrieval depth")
    p.add_argument("--char-budget", type=int, default=9000)
    p.add_argument("--provider", default="ollama", help="ollama|groq|openrouter|openai|deepseek or custom via --base-url")
    p.add_argument("--base-url", default="")
    p.add_argument("--api-key", default="")
    p.add_argument("--answer-model", default="qwen3:14b")
    p.add_argument("--judge-model", default="")
    p.add_argument("--memory-model", default="", help="extraction/consolidation model (full mode)")
    p.add_argument("--embedder", choices=["ollama", "openai", "hash"], default="ollama")
    p.add_argument("--embed-model", default="nomic-embed-text")
    p.add_argument("--embed-base-url", default="")
    # research-driven retrieval features (opt-in, so runs are A/B comparable)
    p.add_argument("--observations", action="store_true",
                   help="Build 1: synthesize per-entity observation summaries after ingest (full mode)")
    p.add_argument("--iterative", action="store_true",
                   help="Build 5: LLM-seeded second retrieval round for multi-hop (full mode)")
    p.add_argument("--key-expansion", action="store_true",
                   help="Build 9A: index fact-augmented search keys for recall (full mode)")
    p.add_argument("--aggregate", action="store_true",
                   help="Build 9B: high-recall enumerate-and-count path on aggregation queries")
    p.add_argument("--stem", action="store_true",
                   help="FTS5 Porter stemmer so conjugation variants match (keyword normalization)")
    p.add_argument("--semantic-entities", action="store_true",
                   help="Semantic entity linking: cosine-match query->entity-name embeddings (zero-dep)")
    p.add_argument("--semantic-threshold", type=float, default=0.3,
                   help="Cosine cutoff for the semantic-entity channel (default 0.3)")
    p.add_argument("--reranker-model", default="", help="Build 4: rerank model id")
    p.add_argument("--reranker-url", default="", help="Build 4: rerank endpoint base url (enables reranking)")
    p.add_argument("--reranker-key", default="")
    p.add_argument("--question-type", default="",
                   help="LongMemEval: restrict to one type, e.g. multi-session (focus a gap)")
    p.add_argument("--out", default="bench_results.json")
    args = p.parse_args()

    def mk_llm(model):
        return LLM(model=model, base_url=args.base_url, api_key=args.api_key,
                   provider=args.provider)

    answer_llm = mk_llm(args.answer_model)
    judge_llm = mk_llm(args.judge_model or args.answer_model)
    memory_llm = mk_llm(args.memory_model or args.answer_model) if args.mode == "full" else None
    embedder = build_embedder(args)
    reranker = (HTTPReranker(args.reranker_model, args.reranker_url, args.reranker_key)
                if args.reranker_url else None)

    def memory_factory():
        return Smriti(path=":memory:", embedder=embedder, llm=memory_llm,
                      mode=args.mode, reranker=reranker,
                      expand_keys=args.key_expansion, aggregate=args.aggregate,
                      stem=args.stem, semantic_entities=args.semantic_entities,
                      semantic_threshold=args.semantic_threshold)

    if args.bench == "longmemeval":
        data = load_longmemeval(args.data)
        summary = run_longmemeval(data, answer_llm, judge_llm, memory_factory,
                                  limit=args.limit, k=args.k,
                                  char_budget=args.char_budget, out_path=args.out,
                                  sample=args.sample, observations=args.observations,
                                  iterative=args.iterative,
                                  question_type=args.question_type or None)
    else:
        data = load_locomo(args.data)
        summary = run_locomo(data, answer_llm, judge_llm, memory_factory,
                             limit_questions=args.limit, k=args.k,
                             char_budget=args.char_budget, out_path=args.out,
                             sample=args.sample, observations=args.observations,
                             iterative=args.iterative)

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nFull per-question results written to {args.out}")


if __name__ == "__main__":
    main()
