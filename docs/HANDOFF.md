# HANDOFF.md: current task and continuation

Updated: 2026-10-29 by Copilot

## Current task
Implement and run the deferred M0 local-model spike once the frozen Superstore benchmark questions and oracle answers exist. The M5 planner remains blocked by D-006.

## State of the repository
- M0 foundation/contracts, dataset registry, tools, registry/executor, argument/result validation, and tests are present.
- M1, M2, and M3 gates have passed.
- The benchmark question files and independent oracle are not yet present, so the spike has no real benchmark run to execute yet.

## What was just finished
- Added [evaluation/model_spike.py](evaluation/model_spike.py): fixed Ollama models, temperature 0, seed 42, three runs per question, bounded JSON retries, registered-tool argument validation, Ollama token metrics, CSV output, and per-model summary.
- Added focused unit coverage in [tests/unit/evaluation/test_model_spike.py](tests/unit/evaluation/test_model_spike.py).
- Verification in this session: `uv run pytest -q` passed 134 tests; `uv run ruff check .` and `uv run ruff format --check .` passed.

## Exact next steps
1. Add the development/evaluation Superstore question JSON and independent oracle answer source for M4.
2. Run the spike with Ollama available:
   `uv run python evaluation/model_spike.py --limit 10`
3. Record measured accuracy, schema-valid rate, tool validity, consistency, latency, and token speed in D-006, then choose the candidate local model.
4. Resolve D-006 before starting M5 planner implementation.

## Open questions for the owner
- Which model should be selected from the completed Ollama measurements? (D-006.)
- Does the Sample Superstore license allow keeping the CSV in the repository? (D-007.)

## Gotchas and warnings
- Do not run M5 until the spike identifies a model route or another approved route is recorded.
- Expected oracle answers must stay out of the LLM prompt.
- `evaluation/oracle.py` must remain independent of all `da_agent.tools`, agent, validation, and report code.

## How to run things
- Tests: `uv run pytest -q`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Spike: `uv run python evaluation/model_spike.py --limit 10`
