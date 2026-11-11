# HANDOFF.md: current task and continuation

Updated: 2026-11-11 by Copilot

## Current task
Module M6 (Dynamic Planning Agent) is implemented and its Phase 4 exit gate passed. `CONTRACT_VERSION` remains `0.1.0`. The next module is M7 (Feedback and evidence validation).

## State of the repository
- M0-M6 gates are recorded as passed in `docs/PROGRESS.md`.
- The full test suite passed in this session: `uv run pytest -q` (212 passed).
- Repository lint and format checks passed: `uv run ruff check .`; `uv run ruff format --check .` (77 files clean).
- The baseline's prior recorded evaluation is 20/20; this is a baseline/oracle sanity check, not evidence that the dynamic agent outperforms it.
- M5 planning evaluation after the `group_aggregate` and `rank` schema-description fixes is recorded as 20/20 valid in `evaluation/results/plan_eval_m5.json`.
- Candidate model evidence and model choice are documented in D-025 (`qwen3:4b` primary, `qwen3:8b` fallback). This session did not rerun live Ollama evaluations; it resumed at M6 Step 3 as requested.
- All contracts remain unchanged; no HTML/report, Streamlit, PDF, final scoring comparison, or M7 validation work was started.

## What was completed for M6
- Added typed shared state and deterministic DAG execution using the M3 tool executor, including references, dependency skipping, per-tool timeout, tool-call bounds, and trace events.
- Added fixed LangGraph orchestration for resolution, validated planning, execution, inspection, bounded failure repair, result-driven follow-up, and finalization.
- Kept injected LLM and trace dependencies in node closures and declared all graph routing keys in `AgentState`.
- Accepted revisions increment plan versions, record changed task IDs and a factual failure/evidence trigger, and are traced.
- Reused earlier task evidence only when task arguments and dependencies remain unchanged through the full dependency chain. Revised-plan evidence IDs are versioned; version-1 IDs remain compatible.
- Exposed the dynamic run through `pipeline.run_agent()`.
- Added tests for executor DAG cases, stale-dependent-evidence prevention, graph success/repair/exhaustion/revisions, pipeline wiring, trace events, and M6 import isolation.
- D-025 through D-027 record the model evidence, executor design, and M6 orchestration/revision decisions.

## Scope reconciliation
- Phase 4 in `docs/implementation_plan.docx` defines M6 as the dynamic control loop; oracle scoring and baseline comparison belong to the later M10 evaluation runner. The task prompt's request to score and compare during M6 is therefore deferred to M10.
- M6 uses only concise tool-result summaries; the oracle is never imported or sent to the agent. The broader M7 feedback/claim validation suite, M8 reports, and M9 UI remain out of scope.
- D-025's evidence covers the previously recorded candidate model spike and mock plan evaluation. If the owner intended the separate 20-question × 3-run live planner evaluation for each candidate model as an M6 gate, that run was not repeated in this continuation.

## Exact next steps
1. Begin M7 only: implement bounded feedback/evidence validation and claim validation per `docs/MODULES.md`.
2. Do not start reports, UI, or final frozen comparisons before their module.

## Open questions
- Dataset redistribution: confirm whether the Sample Superstore license allows retaining the CSV in the repository (D-007).
- Confirm whether the live planner-evaluation run noted above is required before M7; current M6 orchestration checks are green.

## Gotchas
- `evaluation/oracle.py` must not import tool, agent, validation, or report modules.
- The planner and M6 dynamic-agent functions must not accept benchmark `question_id`; benchmark IDs and oracle answers must not be used as few-shot prompts.
- Future contract changes require owner approval, a decision record, and a version bump; do not change contracts silently.

## How to run
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Baseline evaluation: `uv run python evaluation/run_eval.py`
- Plan evaluation: `uv run python evaluation/run_plan_eval.py` (mock by default; live Ollama with `--mode real --model <name>`)
