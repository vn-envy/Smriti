#!/usr/bin/env bash
set -euo pipefail
python3 -m bench.comparative --adapter smriti-episodes --out audit/2026-09-05/benchmark-smriti.json
python3 -m bench.comparative --adapter lexical --out audit/2026-09-05/benchmark-lexical-control.json

# gbrain checkout must match benchmark-manifest.json.
GBRAIN_BENCH_CLI="${GBRAIN_BENCH_CLI:?point to pinned gbrain src/cli.ts}" \
  python3 -m bench.comparative --adapter gbrain --warmups 0 --repeats 1 \
  --out audit/2026-09-05/benchmark-gbrain.json

# Run with the Python environment and MEM0_BENCH_CONFIG documented in
# bench/COMPARATIVE.md. The benchmark refuses to invent a default configuration.
"${MEM0_BENCH_PYTHON:?point to isolated mem0 Python}" -m bench.comparative \
  --adapter mem0 --warmups 1 --repeats 3 \
  --out audit/2026-09-05/benchmark-mem0.json
