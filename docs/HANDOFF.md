# HANDOFF.md: current task and continuation

Updated: 2026-11-12 by Copilot

## Current task
Complete the owner-approved M6 Steps 5-8: evidence-grounded answers, evaluation and baseline comparison, architecture hygiene, and documentation. The implementation and local checks are complete. The real-agent benchmark gate is blocked pending a timeout/hardware decision. `CONTRACT_VERSION` remains `0.1.0`.

## State
- M6 Steps 1-4 remain committed in `e066882`, `5aa65e4`, and `067242a`.
- M6 Steps 5-8 implementation and real-evaluation artifacts are in commit `2d27aea`.
- Current full suite: `uv run pytest -q` — 225 passed.
- Ruff: `uv run ruff check .` — clean; `uv run ruff format --check .` — 81 files clean.
- D-029 records the owner's explicit override of D-027's prior M10 scoring deferral. No shared contracts changed.
- New answer synthesis is in `src/da_agent/agent/answer.py`; `pipeline.run_agent()` returns that typed result.
- Evaluation code is in `evaluation/run_agent_eval.py`; reports are saved in `evaluation/results/m6_qwen3-4b/`.

## Real-model benchmark result and blocker
- The real harness attempted all 20 questions once with local `qwen3:4b`.
- 0/20 plans were valid; 0 tool calls; all 20 planning calls ended in `FailureClass.TRANSIENT` with `LLM inference error: timed out` at the configured 60-second timeout.
- The fixed baseline scored 20/20 (1.000); its result is a template-keyed ceiling, not a fair competitor.
- The simple `ollama run qwen3:4b` check succeeded, but the longer planner requests exceeded the configured timeout.
- JSON/Markdown report: `evaluation/results/m6_qwen3-4b/agent_eval.json` and `agent_eval.md`. Per-run traces exist under `runs/agent_eval_*` and are gitignored.
- Owner approved 180 seconds per planner call for a local rerun. `evaluation/run_agent_eval.py` now has an evaluation-only `--per-call-timeout-s` option; the application default remains 60 seconds.
- The longer-timeout rerun stopped before completing the benchmark: q01-q09 have traces, q03 and q04 returned answered results with tool evidence, q01, q02, and q05-q08 failed from planner timeouts, and q09 has no final event. q10-q20 were not run. No summary report was generated in `evaluation/results/m6_qwen3-4b-timeout180/`.
- The existing complete 60-second report is still 0/20 agent plans and 20/20 baseline; it is a genuine failed attempt, not a passed dynamic-agent evaluation.
- Do not claim the real-model exit gate passed. A future complete run needs a faster local inference environment or a different approved approach; increasing timeout to 180 seconds alone was insufficient.
- The earlier real planner/model-selection evidence remains recorded in D-025.

## What changed in this continuation
- Added typed answer synthesis with evidence references, key numbers, ambiguity assumptions, declined/failed outcomes, narrative number-grounding checks, fallback tracing, and a concise final-answer trace event.
- Integrated synthesis into the pipeline result.
- Added evidence-to-score extraction, M4 scorer reuse, repeat-aware metrics and baseline comparison, JSON/Markdown output, and a prompt/import architecture check.
- Corrected trailing punctuation handling in narrative numeric validation.
- Full suite increased from 213 to 225 passing tests; Ruff checks pass.

## Next steps
1. Keep M6's real-agent evaluation gate open.
2. With owner direction, rerun on an environment that can finish full planner requests within the approved timeout.
3. Generate and verify all-20 scored outputs and complete traces before closing M6.
4. Do not start M7 until this M6 extension is closed.

## Open questions
- D-030: 180-second timeout was approved but still insufficient on this host; a complete real-agent benchmark remains pending.
- Dataset redistribution approval remains as recorded in D-007.

## How to run
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run python evaluation/run_agent_eval.py --model qwen3:4b --repeats 1 --results-dir evaluation/results/m6_qwen3-4b`
- `uv run python evaluation/run_plan_eval.py --mode real --model qwen3:4b`
