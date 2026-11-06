# HANDOFF.md: current task and continuation

Updated: 2026-11-06 by Antigravity

## Current task
D-006 is resolved by D-023 through empirical model spike evaluation across all 20 benchmark questions. Primary candidate model `qwen3:4b` is selected and configured, with `qwen3:8b` as fallback. All M0-M4 gates have passed. The next task is Module M5 (Question resolution and plan generation).

## State of the repository
- Modules M0, M1, M2, M3, and M4 gates have passed.
- Model Spike (D-006 / D-023): Fully evaluated across all 20 benchmark questions (`evaluation/benchmark/questions.json`) for `qwen3:4b`, `qwen3:8b`, and `llama3.1:8b` (3 runs each, 180 total runs, temperature 0.0, seed 42) using the M4 prompt with injected column names and semantic types from `DatasetProfile`.
  - `qwen3:4b`: 86.67% valid tool call rate, 93.33% correct tool selection, 86.67% correct argument rate, 80.56% task argument accuracy, 0.0% schema failures, 45.11s mean latency (median 23.79s), 9.29 TPS. Exceeds the minimum bar (≥85% valid tool calls, ≥70% correct tool selection).
  - `qwen3:8b` (fallback): 75.00% valid tool calls, 91.67% correct tool selection, 29.85s mean latency, 6.19 TPS.
  - `llama3.1:8b`: 55.00% valid tool calls, 81.67% correct tool selection, 24.11s mean latency, 6.28 TPS.
  - Results stored in `evaluation/results/model_spike_m5.json` and `evaluation/results/model_spike_m5.csv`.
- Configuration: `config.yaml` updated with `model.name: "qwen3:4b"`.
- Benchmark & Oracle: 20 frozen questions (`evaluation/benchmark/questions.json`) and independent ground-truth oracle (`evaluation/benchmark/oracle.json`, `evaluation/oracle.py`).
- M4 Baseline: 20/20 benchmark questions pass (1.000 accuracy) via `evaluation/run_eval.py`.
- Test Suite: 143 passed tests. Ruff check and format clean.

## What was just finished
- Updated `evaluation/model_spike.py` with planning validity metrics (`valid_tool_call`, `correct_tool_selection`, `correct_argument`, task-level argument accuracy, latency, and schema failure rate), incremental checkpointing, and resume support.
- Executed full 180-run spike across all 20 benchmark questions and all 3 candidate models.
- Recorded empirical findings and decision D-023 selecting `qwen3:4b` with fallback `qwen3:8b` in `docs/DECISIONS.md`.
- Updated D-006 status to Resolved and marked M0 gate as passed in `docs/PROGRESS.md`.
- Updated `config.yaml` with the chosen model.

## Exact next steps
1. Begin Module M5: Question resolution and plan generation.
   - Implement `src/da_agent/agent/resolver.py`: resolves question + profile to `ResolvedQuestion`.
   - Implement ambiguity rules and answerability checks.
   - Implement `src/da_agent/agent/planner.py`: prompt with resolved question, profile summary, and `ToolSpec` list returning typed `Plan`.
   - Implement `src/da_agent/validation/plan.py`: validates tool names exist in registry, columns exist, arguments pass `validate_task_args`, graph is acyclic, and at least one task is ready.
   - Write unit tests from M5 exit gate in `tests/unit/agent/test_resolver.py`, `test_planner.py`, and `tests/unit/validation/test_plan.py`.

## Open questions for the owner
- Dataset redistribution: Does the Sample Superstore license allow keeping the CSV in the repository? (D-007.)

## Gotchas and warnings
- `evaluation/oracle.py` must never import `da_agent.tools`, `da_agent.agent`, `da_agent.validation`, or `da_agent.reports` (automated AST test enforces this).
- Expected oracle answers must never appear in any planner or resolver prompt.
- `qwen3:4b` may occasionally generate cyclic self-dependencies in complex multi-step questions (seen in `q02` in spike); the M5 plan validator must detect this and provide clear feedback for repair.

## How to run things
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Run model spike: `uv run python evaluation/model_spike.py --questions evaluation/benchmark/questions.json`
- Run baseline evaluation against oracle: `uv run python evaluation/run_eval.py`
