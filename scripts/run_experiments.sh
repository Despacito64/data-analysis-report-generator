#!/usr/bin/env bash
# run_experiments.sh: reproduce the runs reported in the paper, then regenerate the charts.
# Usage:  bash scripts/run_experiments.sh
# Requires: Ollama running with qwen3:4b-instruct, qwen2.5:3b-instruct, qwen2.5:7b-instruct, llama3.2:3b
# One run per question, default budgets, replanning on except for the second run. About 3 hours on a GTX 1650.
set -euo pipefail
cd "$(dirname "$0")/.."

RESULTS_DIR="evaluation/results"
TS=$(date +%Y%m%d)

run() {  # run <run id> <model> [extra options]
  local id="$1" model="$2"
  shift 2
  uv run python evaluation/run_agent_eval.py --run-id "$id" --model "$model" --repeats 1 --mode real "$@" \
    2>&1 | tee "${RESULTS_DIR}/${id}.nohup.log"
}

echo "[1/5] Main run, replanning on"
run "main-${TS}" "qwen3:4b-instruct"
echo "[2/5] Same run with replanning off"
run "noreplan-${TS}" "qwen3:4b-instruct" --max-replans 0
echo "[3/5] qwen2.5:3b-instruct"
run "spike-qwen25-3b-${TS}" "qwen2.5:3b-instruct"
echo "[4/5] qwen2.5:7b-instruct"
run "spike-qwen25-7b-${TS}" "qwen2.5:7b-instruct"
echo "[5/5] llama3.2:3b"
run "spike-llama32-3b-${TS}" "llama3.2:3b"

echo "Regenerating charts"
uv run python scripts/generate_metrics_charts.py \
  --eval-json "${RESULTS_DIR}/main-${TS}/agent_eval.json" \
  --ablation-json "${RESULTS_DIR}/noreplan-${TS}/agent_eval.json" \
  --spike-3b "${RESULTS_DIR}/spike-qwen25-3b-${TS}/agent_eval.json" \
  --spike-7b "${RESULTS_DIR}/spike-qwen25-7b-${TS}/agent_eval.json" \
  --spike-llama "${RESULTS_DIR}/spike-llama32-3b-${TS}/agent_eval.json"
echo "Done."
