# HANDOFF.md: current task and continuation

Updated: 2026-11-17 by Cursor

## Current task
**M10** in progress: freeze manifest + `run_frozen_experiment.py` + `docs/REPRODUCTION.md` (D-044). M9 gate closed.

## State
- Branch: `shivam`.
- Tests: `uv run pytest -q` (run after changes).
- Freeze: `evaluation/benchmark/freeze_manifest.json` committed; verify with `--verify-only`.
- Reproduction smoke: `uv run python evaluation/run_frozen_experiment.py --mode mock --repeats 1 --questions q03`
- Full eval (long, real Ollama): `--mode real --repeats 3`

## Next steps (M10)
1. Run full real-model frozen experiment; archive results under `evaluation/results/`.
2. Manuscript / measured-results doc with limitations (per `EVALUATION.md`).
3. Optional: gitignore generated `evaluation/results/*` except pinned reference run.

## How to run
- `uv run python evaluation/run_frozen_experiment.py --verify-only`
- `uv run python evaluation/recovery_suite/run_recovery_suite.py`
- `uv run streamlit run app.py`
- See `docs/REPRODUCTION.md`