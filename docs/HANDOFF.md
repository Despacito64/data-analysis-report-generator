# HANDOFF.md: current task and continuation

Updated: 2026-10-21 by Antigravity

## Current task
Start Module M2: Deterministic analytical tools (filter, group and aggregate, rank, period compare, trend, segment contribution, correlation, anomaly detection, Plotly charts). See `docs/MODULES.md`, section M2.

## State of the repository
- Python 3.12.8, uv, ruff, pytest. Dependencies: pandas, openpyxl, pydantic, langgraph, plotly, streamlit, duckdb.
- `src/da_agent/contracts/`: all Pydantic v2 models matching `docs/CONTRACTS.md` (`CONTRACT_VERSION = "0.1.0"`).
- `src/da_agent/core/`: `config.py` (YAML loader, typed Budgets, InputLimitsConfig) and `trace.py` (RunTraceWriter, JSONL traces in `runs/<run_id>/`).
- `src/da_agent/data/`:
  - `registry.py`: benchmark dataset registered (D-007) and SHA-256 verification.
  - `loader.py`: configurable CSV parsing, openpyxl sheet selection, `data_only` XLSX loading, input limits validation, zero-width BOM stripping, and domain exception hierarchy (`DataLoadError`, `InvalidExtensionError`, `EmptyDataError`, `CorruptFileError`, `FileLimitExceededError`, `InvalidSheetError`).
  - `profiler.py`: `compute_profile`, `profile_file`, `compute_dataset_hash`, `infer_semantic_type`, producing validated `DatasetProfile` models. Correctly identifies numeric identifiers (postal codes) as `identifier`, dates with temporal bounds and parse failures, and computes `StatBlock` exclusively for numeric measures.
- `tests/fixtures/`:
  - `valid_sample.csv` and `valid_sample.xlsx` (identical paired datasets with mixed dates, junk unparseable date `not-a-date`, postal code numeric identifiers, missing values, duplicates).
  - `valid_sample_expected.json` (explicit missing value rules, hand-computed missing counts, duplicate counts, date coverage metrics with 1 parse failure, postal codes, sales sum).
  - `multi_sheet.xlsx` and `multi_sheet_expected.json`.
  - `formula.xlsx` (openpyxl `data_only` test).
  - Negative edge case fixtures: `empty.csv`, `corrupt.xlsx`, `wrong_extension.txt`.
- `tests/`: 54 tests across import rules, contracts, trace writer, dataset registry, loader, and profiler. All 54 passed, ruff clean.

## M0 & M1 status
- M0 is closed except for the deferred local model spike (D-006).
- M1 exit gate has PASSED: both formats load, invalid inputs fail clearly, profile counts match hand calculations, identical profile metrics across CSV and XLSX, profile serializes to JSON.

## What was just finished
- Implemented `src/da_agent/data/profiler.py` and exported public symbols in `src/da_agent/data/__init__.py`.
- Stripped zero-width BOM markers from column headers in `loader.py`.
- Added unit tests in `tests/unit/test_profiler.py` covering:
  - Exact missing counts matching `valid_sample_expected.json`.
  - Exact duplicate row counts.
  - Date coverage with parse failures (1 failure from `"not-a-date"`).
  - Semantic types ensuring postal codes and row IDs are `identifier`, never `numeric_measure`.
  - Descriptive statistics (`StatBlock`) generated only for numeric measures.
  - Parity between CSV and XLSX dataset profiles.
  - Clean JSON serialization / deserialization round-trip of `DatasetProfile`.
- Verified profiling against registered benchmark `Sample-Superstore.csv` (9,994 rows, 22 columns, SHA-256 verified).
- Recorded D-017 in `docs/DECISIONS.md`.

## Exact next steps
1. Review `docs/MODULES.md` section M2.
2. Design and write test fixtures and exit gate unit tests for analytical tools in `tests/unit/tools/`:
   - Filter tool (numeric ranges, category membership, date windows, null filters).
   - Group and aggregate tool (sum, mean, count, min, max, with edge case handling for all-missing sum).
3. Implement tools as pure functions in `src/da_agent/tools/`.
4. Run full test suite and linter.

## Open questions for the owner
- Which model route for M5: LM Studio, llama.cpp, or a hosted free-tier API? (D-006, must be resolved before M5).
- Does the Sample Superstore license allow keeping the CSV in the repository? (D-007).

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
