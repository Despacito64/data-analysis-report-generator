#!/usr/bin/env bash
# run_experiments.sh — kick off all ablation + model spike runs, then generate charts
# Usage:  bash scripts/run_experiments.sh
# Requires: Ollama running with qwen3:4b, qwen2.5:3b-instruct, qwen2.5:7b-instruct
set -euo pipefail
cd "$(dirname "$0")/.."

RESULTS_DIR="evaluation/results"
CHARTS_DIR="scripts/charts"
mkdir -p "$CHARTS_DIR"

TS=$(date +%Y%m%d%H%M%S)

# ── 0. Quick smoke check ──────────────────────────────────────────────────────
echo "[0/4] Checking environment..."
uv run python -c "from da_agent.pipeline import run_agent; print('  imports ok')"
curl -sf http://localhost:11434/api/tags > /dev/null && echo "  ollama ok" || { echo "ERROR: Ollama not running. Start it with: ollama serve"; exit 1; }
ollama list

# ── 1. Base charts from existing M10 data (instant, no Ollama) ───────────────
echo ""
echo "[1/4] Generating base charts from M10 reference run..."
uv run python scripts/generate_metrics_charts.py
echo "  Done. Charts in $CHARTS_DIR/"

# ── 2. Reduced-budget run with repair cap 0 (NOT a no-replan ablation; see D-050) ──────────────────
echo ""
echo "[2/4] Running reduced-budget repair-cap-0 run (replanning stays on; see D-050)..."
echo "      This will take ~10-20 minutes on GPU..."
ABLATION_ID="ablation-no-replan-${TS}"
uv run python evaluation/run_agent_eval.py \
  --run-id "$ABLATION_ID" \
  --max-repair-attempts 0 \
  --max-llm-calls-per-question 4 \
  --per-call-timeout-s 60 \
  --per-question-budget-s 180 \
  --repeats 1 \
  --mode real \
  2>&1 | tee "${RESULTS_DIR}/ablation-no-replan.log"
echo "  Ablation done. Run ID: $ABLATION_ID"

# ── 3. Model spike: qwen2.5-instruct variants (5 questions each) ─────────────
echo ""
echo "[3/4] Running model spike (5 representative questions per model)..."
SPIKE_QS="q03,q06,q09,q13,q17"

echo "  Running qwen2.5:3b-instruct..."
SPIKE_3B_ID="model-spike-qwen25-3b-instruct-${TS}"
uv run python evaluation/run_agent_eval.py \
  --run-id "$SPIKE_3B_ID" \
  --model "qwen2.5:3b-instruct" \
  --questions "$SPIKE_QS" \
  --per-call-timeout-s 60 \
  --per-question-budget-s 180 \
  --repeats 1 \
  --mode real \
  2>&1 | tee "${RESULTS_DIR}/spike-3b-instruct.log"
echo "  3b-instruct done."

echo "  Running qwen2.5:7b-instruct..."
SPIKE_7B_ID="model-spike-qwen25-7b-instruct-${TS}"
uv run python evaluation/run_agent_eval.py \
  --run-id "$SPIKE_7B_ID" \
  --model "qwen2.5:7b-instruct" \
  --questions "$SPIKE_QS" \
  --per-call-timeout-s 60 \
  --per-question-budget-s 180 \
  --repeats 1 \
  --mode real \
  2>&1 | tee "${RESULTS_DIR}/spike-7b-instruct.log"
echo "  7b-instruct done."

# ── 4. Regenerate all charts with ablation + spike data ──────────────────────
echo ""
echo "[4/4] Regenerating all charts with new experiment data..."
uv run python scripts/generate_metrics_charts.py \
  --ablation-json "${RESULTS_DIR}/${ABLATION_ID}/agent_eval.json" \
  --spike-3b      "${RESULTS_DIR}/${SPIKE_3B_ID}/agent_eval.json" \
  --spike-7b      "${RESULTS_DIR}/${SPIKE_7B_ID}/agent_eval.json"

echo ""
echo "============================================================"
echo " All experiments complete."
echo " Charts:    $CHARTS_DIR/"
echo " Ablation:  ${RESULTS_DIR}/${ABLATION_ID}/agent_eval.json"
echo " Spike 3b:  ${RESULTS_DIR}/${SPIKE_3B_ID}/agent_eval.json"
echo " Spike 7b:  ${RESULTS_DIR}/${SPIKE_7B_ID}/agent_eval.json"
echo "============================================================"
