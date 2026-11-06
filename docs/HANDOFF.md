# HANDOFF.md: current task and continuation

Updated: 2026-11-06 by Antigravity

## Current task
Module M4 (Fixed baseline and evaluation foundation) is completed and verified. The next task is M5 (Question resolution and plan generation), pending selection of candidate local model for D-006.

## State of the repository
- Modules M0, M1, M2, M3, and M4 gates have passed.
- Benchmark: 20 frozen Sample Superstore questions (`evaluation/benchmark/questions.json`) covering all 8 analytical tools and multi-step tasks.
- Oracle: Independent ground truth generator (`evaluation/benchmark/build_oracle.py`) and cached answers (`evaluation/benchmark/oracle.json`), exposed via `evaluation/oracle.py` without importing `da_agent` analytical packages (enforced via AST test).
- M4 Baseline: Deterministic fixed-workflow baseline implemented in `src/da_agent/agent/baseline.py` and exposed via `src/da_agent/pipeline.py:run_baseline`.
- Evaluation Harness: `evaluation/scorer.py` and `evaluation/run_eval.py` execute the baseline and score answers against the oracle (20/20 passed, 1.000 accuracy, status "complete").
- Model Spike (Step 2): Root cause of low `valid_tool_call` diagnosed and fixed in `evaluation/model_spike.py` by injecting registered column names and semantic types from `DatasetProfile` into the system prompt. Smoke-tested on q01 where `qwen3:4b` achieved 3/3 (100%) valid tool calls.

## What was just finished
- Step 1: Created `evaluation/benchmark/questions.json`, `evaluation/benchmark/build_oracle.py`, `evaluation/benchmark/oracle.json`, and schema/independence tests in `tests/unit/evaluation/test_benchmark_schema.py`.
- Step 2: Diagnosed low `valid_tool_call` in `evaluation/model_spike.py`, added column name & semantic type prompt injection, and smoke tested.
- Step 3: Implemented `src/da_agent/agent/baseline.py`, `src/da_agent/pipeline.py`, `evaluation/oracle.py`, `evaluation/scorer.py`, `evaluation/run_eval.py`, `tests/unit/agent/test_baseline.py`, and `tests/unit/evaluation/test_scorer.py`.
- Full test suite verified: 143 tests passed in 18.84s (`uv run pytest -q`). `ruff check` and `ruff format` clean.

## Exact next steps
1. Complete model selection for D-006 based on model spike evaluation.
2. Begin Module M5: Question resolution and plan generation (`src/da_agent/agent/resolver.py`, `planner.py`, `validation/plan.py`).

## Open questions for the owner
- Model selection for D-006: With column injection in place, `qwen3:4b` produces valid tool calls with fast latency; should `qwen3:4b` or `qwen3:8b` be selected for M5 planner?
- Dataset redistribution: Does the Sample Superstore license allow keeping the CSV in the repository? (D-007.)

## Gotchas and warnings
- `evaluation/oracle.py` must never import `da_agent.tools`, `da_agent.agent`, `da_agent.validation`, or `da_agent.reports` (automated test enforces this).
- Expected oracle answers must never appear in any agent or planner prompt.
- Do not modify M0 contracts without an approved decision in `DECISIONS.md`.

## How to run things
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Run baseline evaluation against oracle: `uv run python evaluation/run_eval.py`
