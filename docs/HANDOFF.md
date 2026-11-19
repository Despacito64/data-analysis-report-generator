# HANDOFF.md: current task and continuation

Updated: 2026-11-19 by Claude Code

## Current task
**D-050**: Ran a reduced-budget repair-cap-0 comparison and a partial model spike, diagnosed the M10 failures, corrected earlier docs; generated visual presentation charts in `scripts/charts/` and documented results in `docs/EXPERIMENTS_SUMMARY.md`. Ready for presentation deck and report synthesis.

## State
- Branch: `shivam`.
- `CONTRACT_VERSION` is `0.2.0`. Chat: `ChatThread` + `generate_plan_for_chat` + `augment_chat_plan`.
- Tests: `uv run pytest -q` — 320 passed.
- Linter: `uv run ruff check .` and `uv run ruff format . --check` clean.
- Main evaluation: 13/20 (65%) with `qwen3:4b` reference run.
- Final-code runs (2026-11-20): R1 `final-code-frozen-real-20261119` 12/20, 36/60 attempts, 258 LLM calls, 93 min. R2 `clean-ablation-max-replans-0-20261119` (`--max-replans 0`, nothing else changed) 12/20, 36/60, 118 calls, 61 min: replanning changed cost, not accuracy. Ceiling check (`scripts/ceiling_check.py`): only 12/20 are passable through the scoring path; the agent passes all 12 in 3/3 repeats. q02 regressed vs R0 (13/20) because of `augment_chat_plan`. The earlier reduced-budget run is not a clean ablation.
- M10 failure diagnosis (traces): tools ran `ok` in all 7 failures. `rank` ranks rows and has no aggregation argument (q06-q08, q20); q01 plan was filter-only; q11 lacked the 2017 restriction; q12 is a direction-label mismatch with the oracle.
- Partial model spike (5 questions, 1 repeat, both new runs stopped early): `qwen2.5:3b-instruct` 0 passed, `qwen2.5:7b-instruct` 2 passed; the `qwen3:4b` 4-of-5 figure is from the 3-repeat reference run. Not like-for-like; no ranking claimed.
- Charts: 7 PNGs + `summary_table.csv` saved in `scripts/charts/`.

## Next steps
1. Review `docs/Technical-Review-Deck.pptx` (23 slides, built on the askMNIT template). Fill the bracketed items: second presenter name and ID (slide 1), individual contribution (slide 21), and insert the demo recording or screenshots (slide 6).
2. Corrections to earlier docs are in the working tree (README, DEVELOPER_GUIDE, EXPERIMENTS_SUMMARY, DECISIONS D-049/D-050, charts); commit and push when the owner agrees.
3. Optional: run a clean ablation with `max_replans=0` (the eval CLI has no flag for it yet; it is in `config.yaml` budgets).
4. Complete the written report using `docs/EXPERIMENTS_SUMMARY.md`.

## Open questions
- Presenter names and IDs, individual contributions, and the demo recording are not known to the repo; the deck marks them in brackets.
- `docs/M10_RESULTS.md` still says q01 failed "answer extraction"; the diagnosis (D-050) shows a filter-only plan. Update it if the owner approves editing that file.

## How to run
- Deck: `uv run --with python-pptx python scripts/build_technical_ppt.py --template "<path>/askMNIT_SmritiStyle.pptx" --out docs/Technical-Review-Deck.pptx` (python-pptx is not a project dependency)
- Charts generator: `uv run python scripts/generate_metrics_charts.py`
- Experiments runner: `bash scripts/run_experiments.sh`
- API: `uv run uvicorn api_main:app --reload --port 8000`
- UI: `cd frontend && npm run dev`
- Tests: `uv run pytest -q`
