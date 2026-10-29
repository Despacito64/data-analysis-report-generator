# HANDOFF.md: current task and continuation

Updated: 2026-10-29 by Antigravity

## Current task
Start Module M3: Tool registry and executor (FR05, FR07). See `docs/MODULES.md`, section M3.

## State of the repository
- Python 3.12.8, uv, ruff, pytest. Dependencies: pandas, openpyxl, pydantic, langgraph, plotly, streamlit, duckdb.
- `src/da_agent/contracts/`: all Pydantic v2 models matching `docs/CONTRACTS.md` (`CONTRACT_VERSION = "0.1.0"`).
- `src/da_agent/core/`: `config.py` (YAML loader, typed Budgets, InputLimitsConfig) and `trace.py` (RunTraceWriter, JSONL traces in `runs/<run_id>/`).
- `src/da_agent/data/`: `registry.py` (dataset registration and SHA-256 verification), `loader.py` (CSV/XLSX loading, input limits, BOM stripping, exception hierarchy), `profiler.py` (profiling, semantic types, date coverage, descriptive statistics, dataset hash).
- `src/da_agent/tools/`:
  - `errors.py`: `ToolError` domain exception wrapping `FailureClass.INVALID_ARGS` or `FailureClass.EMPTY_RESULT`, with JSON-serializable factual context and derived recoverability.
  - `models.py`: Strongly-typed Pydantic v2 argument and result models for all 8 tools, plus `ToolResultEnvelope[T]`, `canonical_dumps`, and `normalize_canonical_value` (sorted keys, NaN/inf to None, -0.0 to 0.0, exact float precision without display rounding).
  - `pandas_tools.py`: `filter_data`, `group_aggregate`, `rank`, `period_compare`.
  - `statistics.py`: `trend`, `segment_contribution`, `correlation`, `detect_anomalies_iqr`.
  - `charts.py`: Plotly chart builders consuming typed tool results only, rejecting raw DataFrames, and adding units to labels.
- `tests/`: 95 unit tests across import rules, contracts, dataset registry, loader, profiler, trace writer, tool errors & canonical serialization envelope, pandas tools, statistics tools, and chart builders. All 95 passed, ruff clean, ruff format clean.

## M0, M1 & M2 status
- M0 is closed except for the deferred local model spike (D-006).
- M1 exit gate has PASSED: both formats load, invalid inputs fail clearly, profile counts match hand calculations, identical profile metrics across CSV and XLSX, profile serializes to JSON.
- M2 exit gate has PASSED: all fixtures pass, every successful call returns reproducible metadata (`tool_name`, `args`, `input_row_count`, `result`), edge cases fully handled and tested (ranking competition ties, all-missing sums returning None, period compare absent/missing/zero states, zero-denominator growth undefined reason, negative base growth, segment contribution 1e-9 tolerance and independent total, correlation constant column, IQR zero-IQR caveat and output truncation, chart builders rejecting raw DataFrames).

## What was just finished
- Implemented `src/da_agent/tools/errors.py`, `src/da_agent/tools/models.py`, `src/da_agent/tools/pandas_tools.py`, `src/da_agent/tools/statistics.py`, and `src/da_agent/tools/charts.py`.
- Exported all public tool functions and models in `src/da_agent/tools/__init__.py`.
- Added Layer 5 import rule check in `tests/test_import_rules.py` verifying `src/da_agent/tools/` imports only allowed layers (contracts, core, data).
- Added comprehensive unit tests in `tests/unit/tools/`:
  - `test_errors_and_envelope.py`: recoverability, JSON-serializable context, canonical JSON serialization byte parity.
  - `test_pandas_tools.py`: filter, group_aggregate, rank, period_compare, trend, segment_contribution with all edge-case table scenarios.
  - `test_statistics.py`: bivariate correlation and detect_anomalies_iqr with documented limitations.
  - `test_charts.py`: Plotly chart builders rejecting raw DataFrames, checking trace types and axis units.
- Recorded D-018 in `docs/DECISIONS.md`.

## Exact next steps
1. Review `docs/MODULES.md` section M3: Tool registry and executor.
2. In M3:
   - Allowlisted registry: tool name to function, args model, result schema, invariants.
   - Argument validation against profile: columns exist, types fit, periods within coverage.
   - Result validation: schema and per-tool numerical invariants (e.g. contribution reconciliation, ranking bounds).
   - Executor: runs one task, creates an `EvidenceRecord`, returns evidence or classified `Failure`.
   - `ToolSpec` export generated from the registry, used by planner prompt.
3. Write unit tests in `tests/unit/` for registry, validation against profile, invariant checks, and executor before implementation.
4. Run full test suite and linter.

## Open questions for the owner
- Which model route for M5: LM Studio, llama.cpp, or a hosted free-tier API? (D-006, must be resolved before M5).
- Does the Sample Superstore license allow keeping the CSV in the repository? (D-007).

## Gotchas and warnings
- Numeric identifiers such as postal codes must be classified as `identifier`, never `numeric_measure`.
- `validation` must never import `tools`; pass metadata as `ToolSpec`.
- The oracle (`evaluation/oracle.py`) must be written in a separate session that has not read `src/da_agent/tools/`.
- Tools do NOT create EvidenceRecords or perform argument-vs-profile validation; that is strictly M3's responsibility.
- Do not start M5 before D-006 is resolved.

## How to run things
- Sync dependencies: `uv sync`
- Tests: `uv run pytest -v`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
