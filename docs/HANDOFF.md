# HANDOFF.md: current task and continuation

Updated: 2026-11-16 by Antigravity

## Current task
M7 Session 2 — dependent-evidence invalidation cascade (`src/da_agent/validation/invalidation.py`), failure classification with factual recovery context (`src/da_agent/validation/failures.py`), and stated-precision magnitude claim matching implemented and verified using mock mode and fixtures only. M7 is in progress (claim validator, invalidation, and failure classification done; no-progress detection and controlled-failure suite pending). Do NOT mark M6 or M7 closed: M6's all-20 real-model scoring gate remains open (D-030/D-031), and M7 has remaining items.

## State
- `CONTRACT_VERSION` remains `0.1.0`.
- Full suite: `uv run pytest -q` — 258 passed (baseline before this session: 243).
- Ruff: `uv run ruff check .` — clean; `uv run ruff format --check .` — 89 files clean.
- Step 0 Overlap Audit documented in `docs/DECISIONS.md` (D-033).
- Contracts (`src/da_agent/contracts/models.py` & `__init__.py`):
  - Added closed `RecoveryFailureClass` enum: `invalid_argument`, `unknown_column`, `type_mismatch`, `empty_result`, `invariant_violation`, `tool_timeout`, `transient_error`, `runtime_error`, `unsupported_operation`, `dependency_failure`, and `unknown` (safe default).
  - Added `RetryPolicy` enum: `retryable_identical` (strictly for `tool_timeout` and `transient_error`), `repairable`, and `terminal`.
  - Added `RecoveryContext` and `ClassifiedFailure` with `to_contract_failure()` conversion.
  - Added additive optional fields `failing_args` and `detailed_class` to `Failure`.
- Layer 4 failure classification (`src/da_agent/validation/failures.py`):
  - `classify_failure()`: centralized safe mapping of `ToolError`, `Failure`, exceptions, and execution outcomes to `ClassifiedFailure`. Never raises.
  - `render_recovery_context()`: produces structured factual context for planner recovery (valid columns, row counts, failing parameter, expected type, factual guidance) without oracle or benchmark leakage.
- Layer 4 dependent-evidence invalidation (`src/da_agent/validation/invalidation.py`):
  - `invalidate_evidence()`: deterministic BFS cascade invalidating root evidence, downstream DAG tasks (cancelled), downstream evidence records (`valid=False`, `invalidated_by=root_evidence_id`), and findings/claims linking to any invalidated record.
  - Diamond-shaped dependency deduplication and guaranteed termination on any finite DAG.
  - Preserves independent branches and unlinked evidence as valid.
  - Emits additive optional `"evidence_invalidation"` event to `RunTraceWriter`.
- Layer 4 claim validator updates (`src/da_agent/validation/claims.py`):
  - Stated-precision and magnitude matching: supports abbreviations ("$2.3M", "2.3 million") against raw evidence values (2,297,201) with precision-following tolerance ($d=1$ matches; $d=2$ with "$2.29M" rejected; "$2.30M" accepted).
  - Documented known limitation: right-number-wrong-field without semantic field binding (deferred to M8).
- Import rules & prompt leakage:
  - `tests/test_import_rules.py` extended to verify `failures.py` and `invalidation.py` have zero prohibited imports and zero benchmark question leakage.
- Decisions: D-033 accepted in `docs/DECISIONS.md`.

## Next steps (M7 remaining items)
1. Bounded recovery & no-progress detection: enforce retry and replan limits, allowing identical retries only for transient errors, and detecting no-progress loops (FR08).
2. Controlled-failure suite: build `evaluation/recovery_suite/` separate from frozen benchmark questions to test each failure class, recovery behavior, and claim tampering.
3. In parallel (when local Ollama host is available): complete or resume the M6 real-model evaluation benchmark run across all 20 frozen questions to close the M6 exit gate.

## Open questions
- Real-model evaluation on CPU host remains bounded and resumable via `evaluation/run_agent_eval.py` per D-030 and D-031; gate remains open until all 20 questions are scored with a real model.
- Dataset redistribution approval remains as recorded in D-007.

## How to run
Validation and tests:
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest tests/unit/validation/test_claims.py`
- `uv run pytest tests/unit/validation/test_invalidation.py`
- `uv run pytest tests/unit/validation/test_failures.py`
- `uv run pytest tests/test_import_rules.py`

Evaluation mock mode:
- `uv run python evaluation/run_agent_eval.py --mode mock --questions q03`
