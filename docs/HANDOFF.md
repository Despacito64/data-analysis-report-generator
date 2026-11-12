# HANDOFF.md: current task and continuation

Updated: 2026-11-12 by Copilot

## Current task
M6 real-model evaluation diagnostics and resumability. The harness changes are implemented and verified using mock-mode tests only. Do not mark M6 closed: the all-20 real-model scoring gate is still open, as recorded in D-030.

## State
- `CONTRACT_VERSION` remains `0.1.0`.
- No changes were made to the oracle, frozen benchmark questions, or fixed-workflow baseline.
- Full suite: `uv run pytest -q` — 232 passed (baseline before this task: 225).
- Ruff: `uv run ruff check .` — clean; `uv run ruff format --check .` — 82 files clean.
- No real-model benchmark was run for this task.
- Evaluation defaults in `config.yaml`: 300 seconds per question, 7200 seconds overall, 2 repair attempts, 8 LLM calls per question, thinking disabled, and Ollama `keep_alive: 10m`.
- Traces now include graph-stage durations, individual repair and tool durations, every LLM call's duration, budget/cap events, diagnostics, and warm-up status.
- Each attempt is persisted in `evaluation/results/<run_id>/attempts/<question_id>/`; merged question results are persisted in `evaluation/results/<run_id>/questions/`. Resume merges existing attempt files, including orphan attempts, and skips terminal results (`passed`, `failed`, `timeout`).
- JSON and Markdown summaries distinguish accuracy over all questions (timeouts/not-run count incorrect) from accuracy over completed questions. The score is marked incomplete while any question is `not_run`.
- Existing partial real-run artifacts and the timeout findings remain documented in D-030; they were not altered.

## Next steps
1. Run the new all-question real attempt below when the local Ollama host is available. The warm-up call is outside question budgets and benchmark timing.
2. If interrupted, resume the same run with the same model and limits. Terminal timeouts/failures are intentionally skipped; use a new run ID to retry them.
3. Inspect `evaluation/results/<run_id>/agent_eval.json`, `agent_eval.md`, per-question files, and `runs/` traces. Confirm every question has a terminal status and all 20 have been scored before closing M6.
4. Do not start M7 until M6's real-model gate is closed.

## Open questions
- The 180-second planner-call timeout previously approved in D-030 still did not finish the complete real benchmark on this host. The diagnosable, bounded run below is the next attempt; no real-model outcome is claimed yet.
- Dataset redistribution approval remains as recorded in D-007.

## How to run
Mock-only validation:
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python evaluation/run_agent_eval.py --mode mock --questions q03`

Next real-model attempt (not run in this task):
- `uv run python evaluation/run_agent_eval.py --model qwen3:4b --run-id m6-qwen3-4b-diag-20261112 --per-call-timeout-s 180 --per-question-budget-s 300 --overall-timeout-s 7200 --max-repair-attempts 2 --max-llm-calls-per-question 8 --no-thinking --keep-alive 10m`

Resume that run with:
- `uv run python evaluation/run_agent_eval.py --model qwen3:4b --resume m6-qwen3-4b-diag-20261112 --per-call-timeout-s 180 --per-question-budget-s 300 --overall-timeout-s 7200 --max-repair-attempts 2 --max-llm-calls-per-question 8 --no-thinking --keep-alive 10m`

Run a subset with `--questions q10,q11`; `--questions-file PATH` selects a different question file. Existing results marked terminal are skipped on resume. A new run ID is required to retry a terminal question.
