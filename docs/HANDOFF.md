# HANDOFF.md: current task and continuation

Updated: 2026-10-21 by owner

## Current task
M1, steps 1 and 2: test fixtures first, then the loader (see docs/MODULES.md, section M1).
Do not write the profiler or dataset hash code yet. That is a separate follow-up session.

## State of the repository
- Branch `master` is clean and pushed to `origin`: https://github.com/Despacito64/data-analysis-report-generator.git. Latest commit: `f7fa8b5 (HEAD -> main, origin/main, origin/HEAD) Defer M0 model spike; start M1`.
- Python 3.12.8, uv, ruff, pytest. Dependencies: pandas, openpyxl, pydantic, langgraph, plotly, streamlit, duckdb.
- `src/da_agent/contracts/`: all Pydantic v2 models matching docs/CONTRACTS.md (CONTRACT_VERSION 0.1.0).
- `src/da_agent/core/`: `config.py` (YAML loader, typed Budgets) and `trace.py` (RunTraceWriter, JSONL traces in `runs/<run_id>/`).
- `src/da_agent/data/`: `registry.py` with Sample-Superstore.csv registered (D-007) and SHA-256 verification. No loader or profiler yet.
- `tests/`: 27 tests (contracts, trace, dataset registry, import rules). 27 passed, ruff clean at the last M0 run.
- `Sample-Superstore.csv` is tracked in git.

## M0 status
- M0 is NOT fully closed. Done: project setup, contracts, config, trace writer, dataset registration, import-rule test.
- Deferred: local model spike (D-006). Ollama could not be downloaded because of network issues. M1 to M4 need no LLM.
- D-006 MUST be resolved before M5 starts. Options: another local runtime (LM Studio, llama.cpp) or a hosted free-tier API. A hosted API needs a new decision entry. `scripts/model_spike.py` can test any Ollama-served model when one is available.

## What was just finished
- Pushed the repository to GitHub without force.
- Recorded the model-spike deferral.

## Exact next steps
1. Write fixtures in `tests/fixtures/`: small CSV and XLSX files with hand-computed expected values (missing counts, duplicate rows, dates in more than one format, numeric identifiers such as postal codes), plus an empty file, a corrupt XLSX and a wrong-extension file.
2. Write the M1 loader tests from the exit gate: both formats load, every invalid input fails clearly, the same data as CSV and XLSX gives identical data.
3. Implement `src/da_agent/data/loader.py`: configurable CSV parsing (delimiter, encoding, date format), Excel sheet selection, `data_only` XLSX loading, input checks using limits from `config.yaml`, clear error messages.
4. Run pytest, ruff check and ruff format --check. Show exact commands and output. Commit and push.
5. Next session: profiler and dataset hash (M1 steps 3 and 4).

## Open questions for the owner
- Which model route for M5: LM Studio, llama.cpp, or a hosted free-tier API? (D-006)
- Does the Sample Superstore license allow keeping the CSV in the repository? The file is already tracked; check the source's terms and record the answer in D-007.
- The registered CSV has 22 columns, but Sample Superstore is usually described as having 21. Check the header in the M1 profiler session and note the extra column in D-007.

## Gotchas and warnings
- The dataset has 9,994 data rows and 22 columns with SHA-256 `dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c`. Counts are facts about this registered file only. Do not assume them for other files.
- `validation` must never import `tools`; pass metadata as `ToolSpec`.
- The oracle (`evaluation/oracle.py`) must be written in a separate session that has not read `src/da_agent/tools/`.
- Do not force-push. Do not start M5 before D-006 is resolved.

## How to run things
- Sync dependencies: `uv sync`
- Tests: `uv run pytest -v`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`