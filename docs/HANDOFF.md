# HANDOFF.md: current task and continuation

Updated: 2026-11-11 by Antigravity

## Current task
Module M5 (Question resolution and plan generation) is complete and its exit gate has passed. All contracts remain frozen at `CONTRACT_VERSION = "0.1.0"`. The next task is Module M6 (Dynamic planning agent).

## State of the repository
- Modules M0, M1, M2, M3, M4, and M5 gates have passed.
- Test Suite: 190 passed tests (up from 143 baseline, +47 tests across resolver, plan validator, planner bounded repair, and AST rules).
- Linter & Formatter: `uv run ruff check .` and `uv run ruff format --check .` both completely clean.
- Baseline Benchmark: 20/20 (1.000 accuracy) via `evaluation/run_eval.py`. Note: baseline 20/20 is an oracle sanity check and comparison ceiling, not a dynamic finding; the dynamic agent's performance in M6 will be measured against it.
- M5 Plan Evaluation (`evaluation/run_plan_eval.py`):
  - Total questions: 20
  - Valid plans: 18/20 (90.0% validity rate)
  - Repaired plans: 2/20 (10.0% repair rate)
  - Tool sequence matches against baseline templates: 18/20 (90.0% match rate)
  - Failures: 2/20 (`q03`: argument schema mismatch for `group_aggregate`, `q08`: schema mismatch for `rank`)
  - Results stored in `evaluation/results/plan_eval_m5.json`.

## What was just finished
- Step 1: Question resolution in `src/da_agent/agent/resolver.py`: maps user natural language to real columns using fuzzy and alias matching strictly against `DatasetProfile`. Declines out-of-scope requests (forecasting, causal attribution, machine learning) and nonexistent data concepts with explicit `decline_reason`, and records assumptions for ambiguous queries.
- Step 2: Plan generation in `src/da_agent/agent/planner.py`: local LLM client interface (`LLMClient` protocol, `OllamaClient`, and `MockLLMClient`). Formats system prompt with registered `ToolSpec` definitions, dataset column names and semantic types, max-step cap (default 5), and 3 non-benchmark few-shot examples.
- Step 3: Plan validation in `src/da_agent/validation/plan_check.py`: Layer 4 module enforcing DAG bounds (max steps, unique IDs, dependency references, topological cycle detection, ready task presence), delegating argument validation to `validate_task_args`. Supports single-turn bounded repair feeding validation errors back to the LLM.
- Step 4: Pipeline entry point in `src/da_agent/pipeline.py`: added `plan_question()` alongside `run_baseline()`, writing all raw LLM responses, validation errors, repair attempts, and final plan to `RunTraceWriter`.
- Step 5: Evaluation in `evaluation/run_plan_eval.py`: benchmark evaluation harness running all 20 questions, logging traces, and calculating plan validity, repair rate, and sequence matches.
- AST Independence Guards: enforced that `planner.py` never imports `evaluation.oracle` or `da_agent.agent.baseline` and never receives `question_id`.
- Recorded Decision D-024 in `docs/DECISIONS.md`.

## Exact next steps
1. Begin Module M6: Dynamic planning agent (FR04, FR06, FR08, FR15).
   - Implement shared state: resolved question, task graph, plan version, evidence store, failures, budgets, status.
   - Implement fixed LangGraph control graph nodes: resolve, plan, select ready task, validate and execute (via M3 executor), inspect, revise or finalize.
   - Implement plan versioning: each revision increments `plan_version` and logs `PlanRevision` with trigger evidence.
   - Enforce bounded execution and dynamic replanning on intermediate results or recoverable failures.
   - Stop before M7.

## Open questions for the owner
- Dataset redistribution: Does the Sample Superstore license allow keeping the CSV in the repository? (D-007.)

## Gotchas and warnings
- `evaluation/oracle.py` must never import `da_agent.tools`, `da_agent.agent`, `da_agent.validation`, or `da_agent.reports` (automated AST test enforces this).
- Planner must never see question IDs and never import oracle or baseline templates (automated AST test enforces this).
- No contracts were modified (`CONTRACT_VERSION` = 0.1.0). Any future contract change requires owner approval and a decision record.

## How to run things
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Run baseline evaluation against oracle: `uv run python evaluation/run_eval.py`
- Run M5 plan evaluation harness: `uv run python evaluation/run_plan_eval.py`
