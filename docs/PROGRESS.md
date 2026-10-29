# PROGRESS.md: what is done and what is pending

Last updated: 2026-10-29 by Antigravity. Tick items only after you ran the tests in the current session.
Build order: M0, M1, M2, M3, M5, M4, M6, M7, M8, M9, M10.

## Module checklist

- [ ] M0 Foundations and contracts
  - [x] project and dependencies  - [x] contracts  - [x] config.yaml  - [x] run-trace writer  - [x] dataset registered (D-007)  - [ ] model spike and choice (D-006) (deferred item: model spike, blocks M5) - [x] import-rule test
  - [ ] GATE passed
- [x] M1 Data layer: loader, checks, profiler, hash. Steps 1-4 done. GATE passed: [x]
- [x] M2 Analytical tools: filter, group, rank, period compare, trend, contribution, correlation, anomaly, charts. GATE passed: [x]
- [x] M3 Registry and executor. GATE passed: [x]
- [ ] M5 Resolver and planner. GATE passed: [ ]
- [ ] M4 Baseline, oracle, scorer, question files. GATE passed: [ ]
- [ ] M6 Dynamic agent. GATE passed: [ ]
- [ ] M7 Feedback and evidence validation. GATE passed: [ ]
- [ ] M8 Reports and rendering. GATE passed: [ ]
- [ ] M9 Streamlit interface and follow-ups. GATE passed: [ ]
- [ ] M10 Frozen experiments and documentation. GATE passed: [ ]

## Requirement status

| ID | Status | Evidence (test or file) |
| --- | --- | --- |
| FR01 | passed | `src/da_agent/data/loader.py`, `tests/unit/test_loader.py` |
| FR02 | passed | `src/da_agent/data/profiler.py`, `tests/unit/test_profiler.py` |
| FR03 | passed | `src/da_agent/data/profiler.py`, `src/da_agent/data/registry.py`, `tests/unit/test_profiler.py` |
| FR05 | passed | `src/da_agent/tools/`, `src/da_agent/validation/`, `tests/unit/tools/`, `tests/unit/validation/` |
| FR07 (recording side) | passed | `src/da_agent/tools/executor.py`, `tests/unit/tools/test_executor.py` |
| FR15 | in progress | `src/da_agent/core/trace.py`, `tests/unit/test_trace.py`, `tests/unit/tools/test_executor.py` |
| FR04, FR06, FR08 to FR14 | not started | |
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
