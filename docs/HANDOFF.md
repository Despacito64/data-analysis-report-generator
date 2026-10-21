# HANDOFF.md: current task and continuation

Updated: 2026-10-21 by Antigravity

## Current task
M1, steps 3 and 4: profiler (physical type, semantic type, missing counts, exact duplicates, date coverage, descriptive statistics) and dataset hash / transformation version (see `docs/MODULES.md`, section M1).

## State of the repository
- Python 3.12.8, uv, ruff, pytest. Dependencies: pandas, openpyxl, pydantic, langgraph, plotly, streamlit, duckdb.
- `src/da_agent/contracts/`: all Pydantic v2 models matching `docs/CONTRACTS.md` (CONTRACT_VERSION 0.1.0).
- `src/da_agent/core/`: `config.py` (YAML loader, typed Budgets, InputLimitsConfig) and `trace.py` (RunTraceWriter, JSONL traces in `runs/<run_id>/`).
- `src/da_agent/data/`:
  - `registry.py`: benchmark dataset registered (D-007) and SHA-256 verification.
  - `loader.py`: configurable CSV parsing (delimiter, encoding, date format), openpyxl sheet selection, `data_only` XLSX loading, input limits validation, and domain exception hierarchy (`DataLoadError`, `InvalidExtensionError`, `EmptyDataError`, `CorruptFileError`, `FileLimitExceededError`, `InvalidSheetError`).
- `tests/fixtures/`:
  - `valid_sample.csv` and `valid_sample.xlsx` (identical paired datasets with mixed dates, postal code numeric identifiers, missing values, duplicates).
  - `valid_sample_expected.json` (hand-computed expected missing counts, duplicate counts, row/col counts, postal codes, sales sum).
  - `multi_sheet.xlsx` and `multi_sheet_expected.json`.
  - `formula.xlsx` (openpyxl `data_only` test).
  - Negative edge case fixtures: `empty.csv`, `corrupt.xlsx`, `wrong_extension.txt`.
- `tests/`: 47 tests (contracts, trace, dataset registry, import rules, loader). All 47 passed, ruff clean.

## M0 status
- M0 is closed except for the deferred local model spike (D-006).
- D-006 MUST be resolved before M5 starts. M1 to M4 do not need an LLM.

## What was just finished
- Generated test fixtures in `tests/fixtures/` with hand-computed expected metrics in JSON files.
- Added comprehensive loader test suite in `tests/unit/test_loader.py` covering format parity, input checks, sheet selection, encoding/delimiter configuration, and limit rejections.
- Implemented `src/da_agent/data/loader.py` with fail-visibly input validation against `config.yaml` limits.
- Cleaned and formatted repository code to pass `ruff check` and `ruff format --check`.

## Exact next steps
1. Write profiler tests from the M1 exit gate: profile matches hand calculations (`valid_sample_expected.json`), semantic types properly distinguish identifiers from measures, duplicate counts match, date coverage detected, and `DatasetProfile` serializes to JSON.
2. Implement `src/da_agent/data/profiler.py` and dataset hash / transformation version.
3. Run `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`.
4. Close M1 exit gate.

## Open questions for the owner
- Which model route for M5: LM Studio, llama.cpp, or a hosted free-tier API? (D-006)
- Does the Sample Superstore license allow keeping the CSV in the repository? (D-007)
- The registered benchmark CSV has 22 columns (`csvbase_row_id` prepended). Check header in M1 profiler session and verify in D-007.

## Gotchas and warnings
- Numeric identifiers such as postal codes must be classified as `identifier`, never `numeric_measure`.
- `validation` must never import `tools`; pass metadata as `ToolSpec`.
- The oracle (`evaluation/oracle.py`) must be written in a separate session that has not read `src/da_agent/tools/`.
- Do not start M5 before D-006 is resolved.

## How to run things
- Sync dependencies: `uv sync`
- Tests: `uv run pytest -v`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
