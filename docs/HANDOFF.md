# HANDOFF.md: current task and continuation

Updated: 2026-11-19 by Antigravity

## Current task
**D-050**: Conducted no-replan ablation study and multi-model spike on frozen benchmark; generated visual presentation charts in `scripts/charts/` and documented results in `docs/EXPERIMENTS_SUMMARY.md`. Ready for presentation deck and report synthesis.

## State
- Branch: `shivam`.
- `CONTRACT_VERSION` is `0.2.0`. Chat: `ChatThread` + `generate_plan_for_chat` + `augment_chat_plan`.
- Tests: `uv run pytest -q` — 320 passed.
- Linter: `uv run ruff check .` and `uv run ruff format . --check` clean.
- Main evaluation: 13/20 (65%) with `qwen3:4b` reference run.
- Ablation: 12/20 (60%) with replanning disabled (`max_repair_attempts=0`), proving dynamic replanning directly contributed +1 correct answer (q02).
- Model comparison: `qwen3:4b` (4/5, 80%) vs `qwen2.5:7b-instruct` (2/5, 40%) vs `qwen2.5:3b-instruct` (0/5, 0%).
- Charts: 7 PNGs + `summary_table.csv` saved in `scripts/charts/`.

## Next steps
1. Review generated PNG charts in `scripts/charts/` for the presentation slides.
2. Build/update slide deck (`scripts/build_review_ppt.py` / `docs/Evidence-Grounded-Dynamic-Planning.pptx`).
3. Complete final course project report incorporating experiment tables from `docs/EXPERIMENTS_SUMMARY.md`.

## Open questions
- Which slides in `build_review_ppt.py` should embed the new chart PNGs?

## How to run
- Charts generator: `uv run python scripts/generate_metrics_charts.py`
- Experiments runner: `bash scripts/run_experiments.sh`
- API: `uv run uvicorn api_main:app --reload --port 8000`
- UI: `cd frontend && npm run dev`
- Tests: `uv run pytest -q`
