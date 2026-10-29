# HANDOFF.md: current task and continuation

Updated: 2026-10-29 by Antigravity

## Current task
Start Module M5: Question resolution and plan generation (FR04, FR13, FR14). Note: D-006 (candidate model choice) blocks planner execution; resolve model route with owner before implementing LLM planner nodes. See `docs/MODULES.md`, section M5.

## State of the repository
- Python 3.12.8, uv, ruff, pytest. Dependencies: pandas, openpyxl, pydantic, langgraph, plotly, streamlit, duckdb.
- `src/da_agent/contracts/`: all Pydantic v2 models matching `docs/CONTRACTS.md` (`CONTRACT_VERSION = "0.1.0"`).
- `src/da_agent/core/`: `config.py` (YAML loader, typed Budgets, InputLimitsConfig) and `trace.py` (RunTraceWriter, JSONL traces in `runs/<run_id>/`).
- `src/da_agent/data/`: `registry.py` (dataset registration and SHA-256 verification), `loader.py` (CSV/XLSX loading, input limits, BOM stripping, exception hierarchy), `profiler.py` (profiling, semantic types, date coverage, descriptive statistics, dataset hash).
- `src/da_agent/tools/`:
  - `errors.py`: `ToolError` domain exception wrapping `FailureClass.INVALID_ARGS` or `FailureClass.EMPTY_RESULT`.
  - `models.py`: Strongly-typed Pydantic v2 argument and result models for all 8 analytical tools, plus `ToolResultEnvelope[T]`, `canonical_dumps`, and `normalize_canonical_value`.
  - `pandas_tools.py`: `filter_data`, `group_aggregate`, `rank`, `period_compare`.
  - `statistics.py`: `trend`, `segment_contribution`, `correlation`, `detect_anomalies_iqr`.
  - `charts.py`: Plotly chart builders consuming typed tool results only, rejecting raw DataFrames, with units in labels.
  - `registry.py`: Allowlisted immutable `DEFAULT_REGISTRY` of 8 tools; `export_tool_specs()` generating `ToolSpec` models with schemas and no data values.
  - `executor.py`: `execute_task()` running tasks deterministically, enforcing `Budgets.per_call_timeout_s`, logging tool calls, failures, and `EvidenceRecord`s to `RunTraceWriter`, and storing full canonical results alongside records.
- `src/da_agent/validation/`:
  - `args.py`: `validate_task_args()` enforcing schema, column existence, semantic types, and date coverage bounds against `DatasetProfile`.
  - `results.py`: `validate_tool_result()` enforcing output schemas and per-tool numerical invariants without re-calling tools.
- `tests/`: 128 unit tests across import rules, contracts, dataset registry, loader, profiler, trace writer, tool errors & canonical serialization, pandas tools, statistics tools, chart builders, tool registry, argument validation, numerical invariants validation, and task executor. All 128 passed, ruff clean, ruff format clean.

## M0, M1, M2 & M3 status
- M0 is closed except for the deferred local model spike (D-006).
- M1 exit gate has PASSED: both formats load, invalid inputs fail clearly, profile counts match hand calculations, identical profile metrics across CSV and XLSX, profile serializes to JSON.
- M2 exit gate has PASSED: all analytical tools implemented as pure functions, handling all required edge cases.
- M3 exit gate has PASSED: nothing outside the allowlisted registry can run; every executed task leaves either an evidence record or a classified failure (and a trace entry); per-tool invariants enforce mathematical properties; tool specs exported from registry without data values.

## What was just finished
- Implemented `src/da_agent/validation/args.py`: untrusted planner input validation against tool schemas and `DatasetProfile`.
- Implemented `src/da_agent/validation/results.py`: result schema checking and per-tool numerical invariants for all 8 tools.
- Implemented `src/da_agent/tools/registry.py`: immutable `ToolRegistry` and `export_tool_specs()`.
- Implemented `src/da_agent/tools/executor.py`: task executor with timeout enforcement, `args_hash` generation, bounded LLM summary creation, canonical result storage, and audit logging.
- Extended `tests/test_import_rules.py` verifying Layer 5 tools imports Layer 4 validation while Layer 4 validation never imports tools.
- Added comprehensive unit tests in `tests/unit/validation/` and `tests/unit/tools/`:
  - `test_args_validation.py`: R01-R08 rejection cases (unknown tool, malformed args, extra args, missing column, wrong metric type, wrong date type, out-of-bounds period, text grouping).
  - `test_results_validation.py`: schema check and deliberate corruption tests for all 20 numerical invariants.
  - `test_registry.py`: registry lookup, immutability, and `ToolSpec` export verification.
  - `test_executor.py`: task execution, deterministic `args_hash`, timeout mapping to `TRANSIENT`, unexpected exception mapping to `SCHEMA_VIOLATION`, bounded summaries, and trace writer logging.
- Recorded D-019 in `docs/DECISIONS.md`.

## Exact next steps
1. Resolve D-006 with the owner: model choice/route (Ollama, LM Studio, llama.cpp, or hosted API) before starting M5 LLM planner nodes.
2. Review `docs/MODULES.md` section M5: Question resolution and plan generation (FR04, FR13, FR14).
3. Build in M5:
   - Resolver: question and profile to `ResolvedQuestion`.
   - Ambiguity rule: if metric or period cannot be resolved, record an explicit assumption or request clarification.
   - Answerability check: decline absent columns or excluded methods (forecasting, causal claims) with factual reason.
   - Planner prompt: resolved question, profile summary, and `ToolSpec` list in; typed plan out.
   - Plan validator: tool names exist in registry, columns exist, args type-check, graph is acyclic, at least one ready task.
4. Write test table of 15 to 20 phrasings and invalid plan rejections in `tests/unit/agent/test_resolver.py` and `test_planner.py` before implementation.

## Open questions for the owner
- Which model route for M5: LM Studio, llama.cpp, or a hosted free-tier API? (D-006, must be resolved before M5).
- Does the Sample Superstore license allow keeping the CSV in the repository? (D-007).

## Gotchas and warnings
- Numeric identifiers such as postal codes must be classified as `identifier`, never `numeric_measure`.
- `validation` must never import `tools`; tool metadata passes as `ToolSpec`.
- The oracle (`evaluation/oracle.py`) must be written in a separate session that has not read `src/da_agent/tools/`.
- Expected answers must never appear in any prompt given to the agent, including recovery prompts.
- Do not start M5 before D-006 is resolved.

## How to run things
- Sync dependencies: `uv sync`
- Tests: `uv run pytest -v`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
