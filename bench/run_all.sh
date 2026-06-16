#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# SMRITI "benchmarks first" — one-shot pass.
#   download datasets -> scale smoke test -> lite oracle -> full s -> LoCoMo
#
# Everything below is configurable with environment variables. Defaults are
# fully local (Ollama). Run from the repo root:  bash bench/run_all.sh
#
# Examples:
#   bash bench/run_all.sh                                  # local Ollama, defaults
#   LIMIT=20 bash bench/run_all.sh                         # quick, cheap pass
#   PROVIDER=groq API_KEY=$GROQ_API_KEY \
#     ANSWER_MODEL=llama-3.3-70b-versatile \
#     bash bench/run_all.sh                                # hosted answer/judge
# ---------------------------------------------------------------------------
set -euo pipefail

# --- configuration (override via env) --------------------------------------
PYTHON="${PYTHON:-python3}"                     # interpreter (python3 on macOS)
PROVIDER="${PROVIDER:-ollama}"                 # ollama | groq | openrouter | openai
API_KEY="${API_KEY:-}"                          # required for hosted providers
ANSWER_MODEL="${ANSWER_MODEL:-qwen3:14b}"       # model that answers questions
JUDGE_MODEL="${JUDGE_MODEL:-$ANSWER_MODEL}"     # FIXED judge across all runs
MEMORY_MODEL="${MEMORY_MODEL:-$ANSWER_MODEL}"   # extraction/consolidation (full mode)
EMBEDDER="${EMBEDDER:-ollama}"                  # ollama | openai | hash
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
LIMIT="${LIMIT:-50}"                            # FIRST N questions (one type — quick but skewed)
SAMPLE="${SAMPLE:-}"                             # ~N questions spread EVENLY across types (preferred)
FEATURES="${FEATURES:-}"                         # extra retrieval flags for FULL-mode steps,
                                                 # e.g. "--observations" or "--observations --iterative"
DATA_DIR="${DATA_DIR:-data}"
OUT_DIR="${OUT_DIR:-bench_results/$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$OUT_DIR"

# SAMPLE (stratified) takes precedence over LIMIT (first-N) when set
if [ -n "$SAMPLE" ]; then
    SEL=(--sample "$SAMPLE")
else
    SEL=(--limit "$LIMIT")
fi

# common args reused by every run.py invocation
COMMON=(--provider "$PROVIDER" --api-key "$API_KEY"
        --answer-model "$ANSWER_MODEL" --judge-model "$JUDGE_MODEL"
        --embedder "$EMBEDDER" --embed-model "$EMBED_MODEL" "${SEL[@]}")

step() { printf '\n========== %s ==========\n' "$1"; }

echo "SMRITI benchmark pass"
echo "  provider=$PROVIDER  answer=$ANSWER_MODEL  judge=$JUDGE_MODEL  memory=$MEMORY_MODEL"
echo "  embedder=$EMBEDDER/$EMBED_MODEL  selection=${SEL[*]}  features=${FEATURES:-none}"
echo "  results -> $OUT_DIR"

# --- 1. datasets -----------------------------------------------------------
step "1/5  download datasets"
$PYTHON -m bench.download longmemeval_oracle longmemeval_s locomo --out "$DATA_DIR"

# --- 2. scale smoke test (no models, no data) ------------------------------
step "2/5  scale harness (latency, synthetic — validates infra before spending tokens)"
$PYTHON -m bench.scale | tee "$OUT_DIR/scale.txt"

# --- 3. lite mode, oracle split (fast sanity pass) -------------------------
step "3/5  lite mode — longmemeval_oracle"
$PYTHON -m bench.run --bench longmemeval --data "$DATA_DIR/longmemeval_oracle.json" \
    --mode lite "${COMMON[@]}" --out "$OUT_DIR/lme_oracle_lite.json"

# --- 4. full mode, longmemeval_s (the comparable number) -------------------
# shellcheck disable=SC2086
step "4/5  full mode — longmemeval_s"
$PYTHON -m bench.run --bench longmemeval --data "$DATA_DIR/longmemeval_s_cleaned.json" \
    --mode full --memory-model "$MEMORY_MODEL" "${COMMON[@]}" $FEATURES \
    --out "$OUT_DIR/lme_s_full.json"

# --- 5. LoCoMo, full mode --------------------------------------------------
# shellcheck disable=SC2086
step "5/5  full mode — LoCoMo"
$PYTHON -m bench.run --bench locomo --data "$DATA_DIR/locomo10.json" \
    --mode full --memory-model "$MEMORY_MODEL" "${COMMON[@]}" $FEATURES \
    --out "$OUT_DIR/locomo_full.json"

# --- summary ---------------------------------------------------------------
step "DONE"
echo "All results written under $OUT_DIR/:"
ls -1 "$OUT_DIR"
echo
echo "Headline accuracy per run:"
for f in "$OUT_DIR"/*.json; do
    $PYTHON -c "import json,sys; d=json.load(open(sys.argv[1])); s=d.get('summary',d); print(f\"  {sys.argv[1].split('/')[-1]:<22} {s.get('benchmark','?'):<12} acc={s.get('accuracy','?')}  n={s.get('n','?')}\")" "$f" 2>/dev/null || true
done
