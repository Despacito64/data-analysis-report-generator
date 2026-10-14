# HANDOFF.md: current task and continuation

Updated: 2026-10-14 by antigravity

## Current task
M0 Foundations and contracts:
- Completed: project skeleton with `uv`, typed contracts with `CONTRACT_VERSION = "0.1.0"`, `config.yaml` and loader, JSONL `RunTraceWriter`, dataset registration and SHA-256 verification (D-007), import layering test.
- Remaining in M0: local model spike and candidate choice (D-006).

## State of the repository
- `pyproject.toml` and `.venv` created with Python 3.12.8, uv, ruff, pytest, pandas, openpyxl, pydantic, langgraph, plotly, streamlit, duckdb.
- `src/da_agent/contracts/`: all Pydantic v2 data models matching `docs/CONTRACTS.md`.
- `src/da_agent/core/`: `config.py` (YAML config loader with typed `Budgets`) and `trace.py` (`RunTraceWriter` recording events and reports to `runs/<run_id>/`).
- `src/da_agent/data/`: `registry.py` with `Sample-Superstore.csv` registered benchmark and SHA-256 verification.
- `tests/`: 27 tests in `test_contracts.py`, `test_trace.py`, `test_dataset_registry.py`, and `test_import_rules.py`.
- Tests status: 27 passed in 0.23s (`uv run pytest`).
- Linter status: 0 errors (`uv run ruff check .` and `uv run ruff format --check .`).

## What was just finished
- Implemented `pyproject.toml` and synchronized dependencies via `uv sync`.
- Implemented `src/da_agent/contracts/models.py` and `__init__.py`.
- Implemented `config.yaml` and `src/da_agent/core/config.py`.
- Implemented `src/da_agent/core/trace.py` for full run-trace recording and round-trip replay.
- Registered benchmark dataset `Sample-Superstore.csv` with SHA-256 `dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c`.
- Implemented architectural import rule test enforcing layer constraints.
- Ran tests and linters, fixing all issues.

## Exact next steps
1. Address D-006 (Model spike): Owner to confirm local model runtime (Ollama, llama.cpp, vLLM, or LM Studio) and candidate models available on the machine.
2. Run model spike (10 sample prompts for valid-JSON rate, tool-name accuracy, latency) to finalize model choice in `config.yaml` and `DECISIONS.md`.
3. Verify M0 exit gate pass criteria, then proceed to M1 (Data layer: loader, checks, profiler, hash).

## Open questions for the owner
- Which local model runtime is installed or preferred on your machine (e.g. Ollama, llama.cpp, LM Studio)? Which local model weights are already downloaded?

## Gotchas and warnings
- `Sample-Superstore.csv` has 9,994 data rows (+ 1 header row) and 22 columns; use the registered SHA-256 hash `dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c`.
- `validation` package must never import `tools` directly; pass metadata as `ToolSpec`.
- Oracle (`evaluation/oracle.py`) must be implemented in a dedicated clean session that does not read `da_agent.tools`.

## How to run things
- Install/sync dependencies: `uv sync`
- Run test suite: `uv run pytest -v`
- Run linter: `uv run ruff check .`
- Run format check: `uv run ruff format --check .`
