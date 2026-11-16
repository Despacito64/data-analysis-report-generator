# HANDOFF.md: current task and continuation

Updated: 2026-11-16 by Antigravity

## Current task
M7 Session 1 — numeric claim validator (`src/da_agent/validation/claims.py`) implemented and verified using mock mode and fixtures only. M7 is in progress (claim validator done). Do NOT mark M6 or M7 closed: M6's all-20 real-model scoring gate remains open (D-030/D-031), and M7 has remaining sessions.

## State
- `CONTRACT_VERSION` remains `0.1.0`.
- Full suite: `uv run pytest -q` — 243 passed (baseline before this task: 232).
- Ruff: `uv run ruff check .` — clean; `uv run ruff format --check .` — 85 files clean.
- Layer 4 claim validator implemented in `src/da_agent/validation/claims.py`:
  - Typed extraction: `extract_numeric_claims` extracts plain numbers, thousands separators, currency amounts, percentages, signed changes, ratios, and values with units into `ExtractedNumericClaim` models with text spans, decimal digits, and unit/currency/percentage flags.
  - Context filtering: ignores non-claim numbers including dates, years in context, ordinals, alphanumeric IDs, list numbering, and quoted identifiers/postal codes.
  - Tolerance and rounding: `match_claim_to_evidence` applies configurable `rtol` (default 0.001), `atol` (default 0.01), rounding to claim's stated decimal precision ($d < 4$), and percentage-fraction scaling ($\times 100$).
  - Cheap recomputation: recomputes pairwise sums, differences, shares, and percentage changes from unique evidence numbers in the same evidence record (capped to top 25 values).
  - Status classification: `supported`, `recomputed` (with derivation formula recorded), `ambiguous` (multiple distinct paths/derivations), and `unsupported` (missing/invalid evidence or no match).
  - Finding validation: `validate_findings` processes finding statements and `numeric_claims`, rejecting or dropping unsupported claims according to `FindingDropPolicy` (`drop_finding` by default, or `remove_claim`).
  - Trace auditing: logs additive optional `"claim_validation"` event to `RunTraceWriter`.
- Config: added `ClaimValidationConfig` and `FindingDropPolicy` to `src/da_agent/core/config.py` and `config.yaml`.
- Refactoring (Step 0 overlap audit): `src/da_agent/agent/answer.py` refactored to reuse Layer 4 `extract_evidence_numbers` and `normalize_claim_number`, eliminating duplication while keeping all 232 baseline tests passing.
- Import layering: `tests/test_import_rules.py` extended to verify Layer 4 never imports tools/agent/reports/pipeline/evaluation, and verified `claims.py` contains no benchmark question leakage.
- New decision D-032 accepted in `docs/DECISIONS.md`.

## Next steps (M7 remaining items)
1. Failure classification & recovery context: implement failure classifier mapping tool and execution errors into typed `Failure` contracts with factual context (never expected answers).
2. Bounded recovery & no-progress detection: enforce retry and replan limits, allowing identical retries only for transient errors, and detecting no-progress loops.
3. Dependent-evidence invalidation: ensure invalidating an evidence record cascades to dependent tasks, findings, and derived claims.
4. Controlled-failure suite: build `evaluation/recovery_suite/` separate from frozen benchmark questions to test each failure class and claim tampering.
5. In parallel (when local Ollama host is available): complete or resume the M6 real-model evaluation benchmark run across all 20 frozen questions to close the M6 exit gate.

## Open questions
- Real-model evaluation on CPU host remains bounded and resumable via `evaluation/run_agent_eval.py` per D-030 and D-031; gate remains open until all 20 questions are scored with a real model.
- Dataset redistribution approval remains as recorded in D-007.

## How to run
Validation and tests:
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest tests/unit/validation/test_claims.py`
- `uv run pytest tests/test_import_rules.py`

Evaluation mock mode:
- `uv run python evaluation/run_agent_eval.py --mode mock --questions q03`
