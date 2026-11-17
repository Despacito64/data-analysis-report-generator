# HANDOFF.md: current task and continuation

Updated: 2026-11-17 by Cursor

## Current task
M7 Task 1 is done (D-035): recovery counters and no-progress stops are wired in `assess_recovery()`. Next is Task 2: call `invalidate_evidence()` when evidence is invalidated, then `validate_findings()` before the user-facing answer. Task 3 is `evaluation/recovery_suite/`. Do not start M8. Do not mark M7 closed.

## State
- Branch: `shivam`, based on `main` at `be78cab` plus this session's evaluation artifacts and doc updates. Not committed.
- `CONTRACT_VERSION` remains `0.1.0`.
- No application config change. `config.yaml` `per_call_timeout_s` stays `60`. The full run used that default.
- Model: `qwen3:4b` pulled locally. Ollama `0.23.3`. GPU: NVIDIA GeForce GTX 1650, 4 GB. `ollama ps` reported `100% GPU`, about 3.6 GB.
- Smoke: `evaluation/results/m6-shivam-smoke/` — q03 passed in about 40 s.
- Full run: `uv run python evaluation/run_agent_eval.py --mode real --model qwen3:4b --run-id m6-shivam-full`
  - `score_complete: true`
  - Agent 13/20 correct (0.650). Baseline 20/20 on the same questions (template-keyed ceiling).
  - Failures: q01 `no_score_shaped_answer`; q06, q07, q08, q11, q12, q20 `incorrect_answer`.
  - No timeout and no `not_run` on the full run. Wall time about 13 minutes. Warm-up about 1.8 s.
- M7 libraries from the previous session remain: claim validator, invalidation, failure classification, and `validation/recovery.py` (`decide_recovery` is already used by graph routing). `detect_no_progress`, `invalidate_evidence`, and `validate_findings` are not wired through the live agent path. `evaluation/recovery_suite/` does not exist.
- Pytest and Ruff were not re-run in this session. Last recorded suite is still `uv run pytest -q` — 258 passed (2026-11-16).

## Next steps
1. Wire no-progress detection into the graph and stop with an explicit partial or failed status.
2. Call dependent-evidence invalidation when evidence is invalidated, then run `validate_findings()` before the user-facing result is accepted.
3. Add `evaluation/recovery_suite/`, separate from the frozen benchmark questions.
4. Re-run `uv run pytest -q` and Ruff before claiming M7 progress.

## Open questions
- Dataset redistribution approval remains as recorded in D-007.
- Whether the 13/20 misses should be fixed inside M7 or left as measured M6 results is an owner choice. Do not retune prompts against the frozen eval set.

## How to run
Validation and tests:
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`

Evaluation:
- `uv run python evaluation/run_agent_eval.py --mode real --model qwen3:4b --run-id m6-shivam-full`
- Resume with `--resume m6-shivam-full` only for a new partial run. This run is already complete.
