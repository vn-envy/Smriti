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

from smriti import LLM, HashEmbedder, OllamaEmbedder, OpenAICompatEmbedder, Smriti
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
    p.add_argument("--out", default="bench_results.json")
    args = p.parse_args()

    def mk_llm(model):
        return LLM(model=model, base_url=args.base_url, api_key=args.api_key,
                   provider=args.provider)

    answer_llm = mk_llm(args.answer_model)
    judge_llm = mk_llm(args.judge_model or args.answer_model)
    memory_llm = mk_llm(args.memory_model or args.answer_model) if args.mode == "full" else None
    embedder = build_embedder(args)

    def memory_factory():
        return Smriti(path=":memory:", embedder=embedder, llm=memory_llm, mode=args.mode)

    if args.bench == "longmemeval":
        data = load_longmemeval(args.data)
        summary = run_longmemeval(data, answer_llm, judge_llm, memory_factory,
                                  limit=args.limit, k=args.k,
                                  char_budget=args.char_budget, out_path=args.out,
                                  sample=args.sample)
    else:
        data = load_locomo(args.data)
        summary = run_locomo(data, answer_llm, judge_llm, memory_factory,
                             limit_questions=args.limit, k=args.k,
                             char_budget=args.char_budget, out_path=args.out,
                             sample=args.sample)

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nFull per-question results written to {args.out}")


if __name__ == "__main__":
    main()
