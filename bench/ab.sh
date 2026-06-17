#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# A/B one feature flag on a focused slice and print the accuracy delta.
# Runs the SAME questions twice — once baseline, once with the treatment flag —
# so the only variable is the feature under test.
#
#   bash bench/ab.sh                 # --observations on multi-session (oracle, full)
#   TREATMENT=--iterative bash bench/ab.sh
#   QTYPE=temporal-reasoning TREATMENT=--iterative bash bench/ab.sh
#   LIMIT=60 bash bench/ab.sh
#
# Defaults assume DeepSeek for the LLM + local Ollama embeddings; override via env.
# ---------------------------------------------------------------------------
set -euo pipefail

PYTHON="${PYTHON:-python3}"
PROVIDER="${PROVIDER:-deepseek}"
API_KEY="${API_KEY:-${DEEPSEEK_API_KEY:-}}"
ANSWER_MODEL="${ANSWER_MODEL:-deepseek-v4-flash}"
JUDGE_MODEL="${JUDGE_MODEL:-$ANSWER_MODEL}"
MEMORY_MODEL="${MEMORY_MODEL:-$ANSWER_MODEL}"
EMBEDDER="${EMBEDDER:-ollama}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"

BENCH="${BENCH:-longmemeval}"
DATA="${DATA:-data/longmemeval_oracle.json}"
QTYPE="${QTYPE-multi-session}"           # LongMemEval question type to focus (QTYPE= clears it -> all types)
LIMIT="${LIMIT:-40}"                      # first-N (used when SAMPLE unset)
SAMPLE="${SAMPLE:-}"                      # ~N spread across types (preferred for larger n)
MODE="${MODE:-full}"                      # observations need full mode
BASELINE="${BASELINE:-}"                 # flags applied to BOTH arms (isolate a marginal change)
TREATMENT="${TREATMENT:---observations}" # the extra flag(s) measured (added to BASELINE)

OUT_DIR="${OUT_DIR:-bench_results/ab_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT_DIR"

# SAMPLE (stratified) takes precedence over LIMIT (first-N) when set
if [ -n "$SAMPLE" ]; then
    SEL=(--sample "$SAMPLE")
else
    SEL=(--limit "$LIMIT")
fi

COMMON=(--bench "$BENCH" --data "$DATA" --mode "$MODE" "${SEL[@]}"
        --provider "$PROVIDER" --api-key "$API_KEY"
        --answer-model "$ANSWER_MODEL" --judge-model "$JUDGE_MODEL"
        --memory-model "$MEMORY_MODEL"
        --embedder "$EMBEDDER" --embed-model "$EMBED_MODEL")
if [ "$BENCH" = "longmemeval" ] && [ -n "$QTYPE" ]; then
    COMMON+=(--question-type "$QTYPE")
fi

echo "A/B: '$TREATMENT' on $BENCH/${QTYPE:-all} ($MODE, n<=$LIMIT) via $PROVIDER/$ANSWER_MODEL"
echo "  results -> $OUT_DIR"

echo; echo "========== A: baseline (${BASELINE:-none}) =========="
# shellcheck disable=SC2086
$PYTHON -m bench.run "${COMMON[@]}" $BASELINE --out "$OUT_DIR/base.json"

echo; echo "========== B: + $TREATMENT =========="
# shellcheck disable=SC2086
$PYTHON -m bench.run "${COMMON[@]}" $BASELINE $TREATMENT --out "$OUT_DIR/treat.json"

echo; echo "========== RESULT =========="
$PYTHON - "$OUT_DIR/base.json" "$OUT_DIR/treat.json" "$TREATMENT" <<'PY'
import json, sys
base = json.load(open(sys.argv[1]))["summary"]
treat = json.load(open(sys.argv[2]))["summary"]
flag = sys.argv[3]
b, t = base["accuracy"], treat["accuracy"]
print(f"  baseline        : {b:.4f}  (n={base['n']})")
print(f"  {flag:<16}: {t:.4f}  (n={treat['n']})")
print(f"  delta           : {t-b:+.4f}  ({(t-b)*100:+.1f} pts)")
PY
echo; echo "(full per-question JSONL in $OUT_DIR/{base,treat}.json)"
