#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# A/B the two mem0-inspired, zero-dependency retrieval levers:
#   1. --stem              (FTS5 Porter stemmer — keyword normalization)
#   2. --semantic-entities (query -> entity-name embedding cosine match)
#
# Runs the SAME stratified questions four times so the only variables are the
# flags. Same questions => McNemar-comparable per-question flips across arms.
#
#   bash bench/ab_features.sh                      # all types, SAMPLE=40
#   SAMPLE=100 bash bench/ab_features.sh           # bigger, still stratified
#   QTYPE=multi-session bash bench/ab_features.sh  # focus the weakest gap
#   ARMS="base stem" bash bench/ab_features.sh     # subset of arms
#
# Defaults assume DeepSeek for the LLM + local Ollama embeddings; override via
# env (same vocabulary as ab.sh: PROVIDER, ANSWER_MODEL, DEEPSEEK_API_KEY, ...).
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
QTYPE="${QTYPE-}"           # focus one type, or empty for all types
LIMIT="${LIMIT:-40}"        # first-N (used when SAMPLE unset)
SAMPLE="${SAMPLE:-}"        # ~N spread across types (preferred for larger n)
MODE="${MODE:-full}"        # retrieval levers apply in both modes; full keeps
                            # extraction so the entity graph is populated
SEM_THRESHOLD="${SEM_THRESHOLD:-0.3}"
ARMS="${ARMS:-base stem semantic both}"

OUT_DIR="${OUT_DIR:-bench_results/abfeat_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$OUT_DIR"

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

# arm name -> extra flags
flags_for() {
  case "$1" in
    base)     echo "" ;;
    stem)     echo "--stem" ;;
    semantic) echo "--semantic-entities --semantic-threshold $SEM_THRESHOLD" ;;
    both)     echo "--stem --semantic-entities --semantic-threshold $SEM_THRESHOLD" ;;
    *) echo "" ;;
  esac
}

echo "A/B features: stem + semantic-entities on $BENCH/${QTYPE:-all} ($MODE, n<=${SAMPLE:-$LIMIT})"
echo "  arms: $ARMS"
echo "  provider: $PROVIDER/$ANSWER_MODEL  embedder: $EMBEDDER/$EMBED_MODEL"
echo "  results -> $OUT_DIR"
echo

for arm in $ARMS; do
  extra="$(flags_for "$arm")"
  echo "========== arm: $arm (${extra:-none}) =========="
  # shellcheck disable=SC2086
  $PYTHON -m bench.run "${COMMON[@]}" $extra --out "$OUT_DIR/$arm.json"
  echo
done

echo "========== COMPARE =========="
$PYTHON - "$OUT_DIR" $ARMS <<'PY'
import json, sys, os
out_dir, arms = sys.argv[1], sys.argv[2:]
rows = {}
for arm in arms:
    p = os.path.join(out_dir, f"{arm}.json")
    try:
        rows[arm] = json.load(open(p))["summary"]
    except Exception as e:
        print(f"  {arm:<10}: (missing/invalid: {e})")

base = rows.get(arms[0])
if not base:
    print("  no baseline arm found"); sys.exit(0)

# per-type + overall table
types = sorted(base.get("per_type", {}).keys())
hdr = f"  {'category':<28}" + "".join(f"{a:>12}" for a in arms) + "\n"
print(hdr)
for t in types + ["OVERALL"]:
    line = f"  {t:<28}"
    for a in arms:
        s = rows.get(a)
        if not s: line += f"{'--':>12}"; continue
        v = (s["accuracy"] if t == "OVERALL"
             else s.get("per_type", {}).get(t))
        line += f"{(v*100 if v is not None else 0):>11.1f}%" if v is not None else f"{'--':>12}"
    print(line)

print()
print("  deltas vs baseline (percentage points):")
for a in arms[1:]:
    s = rows.get(a)
    if not s: continue
    d = (s["accuracy"] - base["accuracy"]) * 100
    print(f"    {a:<10}: {d:+.1f} pp   ({base['accuracy']*100:.1f} -> {s['accuracy']*100:.1f})")

# per-question flips vs baseline (discordance), if question ids line up
def load_results(arm):
    p = os.path.join(out_dir, f"{arm}.json")
    try: return {r["question_id"]: r["correct"] for r in json.load(open(p))["results"]}
    except Exception: return {}

br = load_results(arms[0])
if br:
    print()
    print("  per-question discordance vs baseline:")
    for a in arms[1:]:
        ar = load_results(a)
        common = set(br) & set(ar)
        if not common: continue
        helped = sum(1 for q in common if not br[q] and ar[q])
        hurt   = sum(1 for q in common if br[q] and not ar[q])
        net = helped - hurt
        print(f"    {a:<10}: helped {helped:>3}  hurt {hurt:>3}  net {net:+d}  (n={len(common)})")
PY
echo
echo "(full per-question JSONL in $OUT_DIR/{base,stem,semantic,both}.json)"
