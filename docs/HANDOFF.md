# HANDOFF.md: current task and continuation

Updated: 2026-11-11 by Copilot

## Current task
M6 Step 4 (LangGraph orchestration and public pipeline contract) has been aligned with the user's explicit checklist and verified. M6 is complete; next module is M7. `CONTRACT_VERSION` remains `0.1.0`.

## State
- Prior M6 commit: `e066882`; this Step 4 alignment is committed separately (see progress session log).
- Full suite: `uv run pytest -q` — 213 passed.
- Repository Ruff: `uv run ruff check .` — clean; `uv run ruff format --check .` — 77 files clean.
- Focused Step 4 verification: `uv run pytest tests/unit/agent/test_graph.py tests/unit/test_pipeline.py tests/test_import_rules.py -q` — 23 passed.
- Live Ollama evaluation has not been run.

## What changed in this continuation
- `agent/graph.py` now has explicit `resolve`, `plan`, `validate_repair`, `execute`, `replan`, and `finalize` stages.
- Successful plan generation/repair is revalidated by `validate_repair` before execution. Failure and result-driven revisions route through one bounded replan stage.
- Every graph node writes start/end events to the run trace. Tests assert decline path invokes no LLM, validation failure finalizes, and execution recovery traces the expected stage order.
- `AgentState` includes a typed trace writer field.
- `pipeline.run_agent(question, dataset, config, client)` accepts free text without question IDs and returns typed `AgentResult`. Prior keyword injection options remain available.
- D-028 records these choices.

## Scope decisions
- Per Phase 4 of `docs/implementation_plan.docx`, oracle scoring/baseline comparison is M10; broader feedback/claim validation is M7. Neither was added here.
- No shared contract changes were made.

## Next steps
1. Begin M7 only after the owner confirms the live model-evaluation question if it is considered a prerequisite.

## Open questions
- Dataset redistribution approval remains as recorded in D-007.
- The prior handoff notes that live candidate model planner evaluation was not rerun in this continuation; resolve whether the owner considers it a prerequisite before M7.

## How to run
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python evaluation/run_plan_eval.py` (mock mode by default; live Ollama with `--mode real --model <name>`)
