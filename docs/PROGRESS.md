# PROGRESS.md: what is done and what is pending

## M6 Completion Plan (owner-approved Steps 5-8 expansion)
- Preserve completed M6 Steps 1-4: model evidence, DAG executor, bounded replanning, LangGraph orchestration, and typed pipeline wiring.
- Synthesize a typed user-facing result containing answer text, key numbers, evidence references, assumptions, failures, and status.
- Derive every numeric claim from successful tool evidence; reject unsupported narrative numbers, use a grounded template, and trace the fallback.
- Keep declined/failed outcomes well-formed and record the structured final result in the run trace.
- Add evaluation-only answer extraction from tool evidence and reuse the M4 scorer.
- Run all 20 frozen questions through `run_agent()` with the chosen local Ollama model; keep question IDs and oracle data out of agent code and prompts.
- Compare against the fixed baseline using accuracy, plan validity, repair/replan rates, tool-call counts, latency, failures, and per-question outcomes.
- Report repeated-run variance when feasible and label the baseline's template-keyed ceiling accurately.
- Extend architecture/prompt-leakage tests without weakening existing import rules or frozen benchmark data.
- Preserve `CONTRACT_VERSION = "0.1.0"` and defer broader M7 feedback/validation, M8 reports, M9 UI, and other M10 experiments.
- Exit gates: complete tests and Ruff checks, real-model benchmark artifacts, honest score comparison, traceable answers, and updated decisions/handoff.

Last updated: 2026-11-12 by Copilot. Run and record every gate before marking it passed.
Build order: M0, M1, M2, M3, M5, M4, M6, M7, M8, M9, M10.

## Module checklist

- [x] M0 Foundations and contracts
  - [x] project and dependencies  - [x] contracts  - [x] config.yaml  - [x] run-trace writer  - [x] dataset registered (D-007)  - [x] model spike and choice (D-006, D-023) - [x] import-rule test
  - [x] GATE passed
- [x] M1 Data layer: loader, checks, profiler, hash. Steps 1-4 done. GATE passed: [x]
- [x] M2 Analytical tools: filter, group, rank, period compare, trend, contribution, correlation, anomaly, charts. GATE passed: [x]
- [x] M3 Registry and executor. GATE passed: [x]
- [x] M5 Resolver and planner. GATE passed: [x]
- [x] M4 Baseline, oracle, scorer, question files. GATE passed: [x]
- [ ] M6 Dynamic agent. GATE passed: [ ]
- [ ] M7 Feedback and evidence validation. GATE passed: [ ]
- [ ] M8 Reports and rendering. GATE passed: [ ]
- [ ] M9 Streamlit interface and follow-ups. GATE passed: [ ]
- [ ] M10 Frozen experiments and documentation. GATE passed: [ ]

M6 owner-approved Steps 5-8: answer synthesis, evaluation harness, architecture checks, documentation, and local test gates are complete. This continuation adds per-stage/LLM/tool timing, question budgets and caps, resumable attempts, model diagnostics, and timeout-aware reporting. The real-agent gate remains open: the complete 60-second run timed out on all 20 questions; an owner-approved 180-second rerun stopped after q09, with q03/q04 producing answers and repeated planner timeouts on other completed questions. See D-030, D-031, and the current handoff.

## Requirement status

| ID | Status | Evidence (test or file) |
| --- | --- | --- |
| FR01 | passed | `src/da_agent/data/loader.py`, `tests/unit/test_loader.py` |
| FR02 | passed | `src/da_agent/data/profiler.py`, `tests/unit/test_profiler.py` |
| FR03 | passed | `src/da_agent/data/profiler.py`, `src/da_agent/data/registry.py`, `tests/unit/test_profiler.py` |
| FR04 | passed | `src/da_agent/agent/planner.py`, `src/da_agent/validation/plan_check.py`, `tests/unit/agent/test_planner.py` |
| FR05 | passed | `src/da_agent/tools/`, `src/da_agent/validation/`, `tests/unit/tools/`, `tests/unit/validation/` |
| FR07 (recording side) | passed | `src/da_agent/tools/executor.py`, `tests/unit/tools/test_executor.py` |
| FR11 (baseline setup) | passed | `src/da_agent/agent/baseline.py`, `evaluation/run_eval.py`, `tests/unit/agent/test_baseline.py` |
| FR13 | passed | `src/da_agent/agent/resolver.py`, `tests/unit/agent/test_resolver.py` |
| FR14 | passed | `src/da_agent/agent/resolver.py`, `tests/unit/agent/test_resolver.py` |
| FR06 | passed | `src/da_agent/agent/graph.py`, `tests/unit/agent/test_graph.py` |
| FR08 (control-side revision) | passed | `src/da_agent/agent/planner.py`, `tests/unit/agent/test_graph.py::test_graph_revises_after_observing_successful_result` |
| FR15 | passed | `src/da_agent/core/trace.py`, `src/da_agent/agent/graph.py`, `tests/unit/agent/test_graph.py` |
| FR07 (claim validation), FR08 (feedback validation), FR09, FR10, FR12 | not started | Deferred to M7-M9 |
| NFR1 to NFR3 | not started | |

Update this table as modules pass their gates, naming the test or artifact.

## Session log (append only, newest at the bottom)

Format: `YYYY-MM-DD | tool | module | what was done | tests run and result | commit`

2026-10-14 | owner | setup | project memory files created | n/a | n/a
2026-10-14 | antigravity | M0 | project setup, contracts, config, trace writer, dataset registry, tests | uv run pytest: 27 passed | c81fa80
2026-10-14 | Copilot | repo push | inspected GitHub destination; push blocked pending owner sign-in/access verification (no remote configured; no push performed) | no tests run (docs/status only) | local handoff commit
2026-10-21 | antigravity | M1 | test fixtures and data loader with configurable parsing and input checks | uv run pytest: 47 passed | 71797c1
2026-10-21 | antigravity | M1 | addressed fixture gaps (junk date parse failures, missing-value rule and na_values) | uv run pytest: 49 passed | 24365ae
2026-10-21 | antigravity | M1 | profiler, semantic types, date coverage, descriptive stats, hash (M1 gate passed) | uv run pytest: 54 passed | fa108b5
2026-10-29 | antigravity | M2 | deterministic analytical tools (filter, group, rank, period compare, trend, contribution, correlation, anomalies, charts), ToolError, canonical envelope, edge cases (M2 gate passed) | uv run pytest: 95 passed | 81f4320
2026-10-29 | antigravity | M3 | tool registry allowlist, argument validation, numerical invariants, task executor with timeout & trace, ToolSpec export (M3 gate passed) | uv run pytest: 128 passed | 8d0becf
2026-10-29 | copilot | M0 | added Ollama model-spike runner and focused tests; real model run blocked until benchmark questions exist (D-006 still open) | uv run pytest -q: 134 passed; ruff check/format passed | pending
2026-10-29 | copilot | M0 | executed temporary 10-question Ollama smoke spike; recorded 90 runs in evaluation/results/model_spike.csv (schema-valid 1.000 across models) | focused tests 6 passed; smoke run completed | pending
2026-11-01 | copilot | M0 | fixed Ollama JSON-string tool argument parsing and removed the broken implicit missing-question default | focused tests 8 passed; full pytest 139 passed | pending
2026-11-06 | antigravity | M4 | 20 frozen benchmark questions, standalone oracle, model spike prompt fix, fixed baseline templates, scorer, and eval harness (M4 gate passed) | uv run pytest: 143 passed; ruff clean; run_eval: 20/20 (1.000) | 353b04c
2026-11-06 | antigravity | M0/M5 | full 20-question benchmark model spike across qwen3:4b, qwen3:8b, llama3.1:8b (180 runs); resolved D-006 with D-023 selecting qwen3:4b (M0 gate passed) | uv run pytest -q: 143 passed; ruff clean; spike: qwen3:4b cleared bar (86.7% valid, 93.3% tool sel) | pending
2026-11-11 | antigravity | M5 | resolver, planner with bounded repair, DAG validator, pipeline entry, benchmark eval harness (M5 gate passed) | uv run pytest -q: 190 passed; ruff clean; run_plan_eval: 90% validity | pending
2026-11-11 | Copilot | M6 | local model evidence and DAG executor (D-025/D-026); fixed LangGraph orchestration, bounded failure repair and result-driven revisions, revision-safe evidence reuse, pipeline entry; deferred scoring/comparison to M10 per Phase 4 | uv run pytest -q: 212 passed; uv run ruff check . clean; uv run ruff format --check . clean | e066882
2026-11-11 | Copilot | M6 Step 4 | added explicit validate_repair/replan stages, graph node-sequence trace events, decline/no-LLM branch test, typed AgentResult and positional pipeline signature | uv run pytest -q: 213 passed; uv run ruff check . clean; uv run ruff format --check . clean | 5aa65e4
2026-11-12 | Copilot | M6 Steps 5-8 | added evidence-grounded answers, pipeline integration, scoring/comparison harness, prompt/import checks, D-029/D-030 and handoff; complete qwen3:4b run timed out at 60 seconds; approved 180-second partial run reached q09 but remained too slow | uv run pytest -q: 225 passed; uv run ruff check . and format --check clean; 60-second real eval 0/20 plans, baseline 20/20; longer partial run q03/q04 answered, other completed requests timed out | pending
2026-11-12 | Copilot | M6 diagnostics/resumability | added stage and per-call timing, bounded question/overall budgets, distinct repair/LLM caps, per-attempt persistence, resume/subset CLI, warm-up/model diagnostics, and timeout-aware reports; M6 remains open and no real-model run was made | uv run pytest -q: 232 passed; uv run ruff check . clean; uv run ruff format --check . clean | pending
