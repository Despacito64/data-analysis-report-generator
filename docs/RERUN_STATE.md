# Rerun state
Last updated: 2026-11-20T21:00:00Z
Current step: 15 (complete)
## Checklist
- [x] 0.1 git status and git log confirmed, branch post-freeze-fixes, source files unchanged since 1703cf7
- [x] 0.2 verify-only passed: "verified"; git checkout latest.json restored
- [x] 0.3 pytest: 328 passed, ruff: clean
- [x] 0.4 Dev servers stopped, ports 8000/5173 free
- [x] 0.5 Ollama models verified: qwen3:4b-instruct, qwen2.5:3b-instruct, qwen2.5:7b-instruct, llama3.2:3b all present with correct digests
- [x] 0.6 Smoke test: ran with --repeats 1, completed normally
- [x] 0.7 GPU free: nvidia-smi checked
- [ ] 0.8 Sleep prevention: not configured
- [x] 0.9 Versions recorded: Ollama 0.23.3, Python 3.14, pandas 3.0.6, pydantic 2.14.1, langgraph 1.2.15
- [x] 0.10 SHA-256 of evaluation/benchmark/questions.json, evaluation/benchmark/oracle.json, config.yaml match freeze_manifest.json
- [x] 2.1 Ceiling check: 20/20 questions have passing candidate
- [x] 2.2 Per-question outcome table: rerun_outcomes.csv generated (40 rows)
- [x] 2.3 Failure causes: rerun_failure_causes.md generated (MAIN's 10 failed questions)
- [x] 2.4 Spike summary: spike_fixed_summary.csv generated (4 models)
- [x] 2.5 Numbers for the paper: rerun_numbers.json generated
- [x] 2.6 Final checks: pytest passed, latest.json restored, commit on post-freeze-fixes

## Runs (all with --repeats 1 as user requested)
| name | run id | questions passed | attempts passed | timeouts | failure reasons |
|---|---|---|---|---|---|
| MAIN | post-freeze-fixes-frozen-real-20261120 | 10/20 | 10/10 | 0 | 10 incorrect_answer |
| NOREP | post-freeze-fixes-no-replan-20261120 | 18/20 | 18/20 | 0 | 2 incorrect_answer |
| Spike qwen2.5:3B | spike-fixed-qwen25-3b-20261120 | 1/20 | 1/20 | 0 | 8 incorrect_answer, 7 no_score_shaped_answer, 4 repair_cap |
| Spike qwen2.5:7B | spike-fixed-qwen25-7b-20261120 | 8/20 | 8/20 | 0 | 4 incorrect_answer, 8 no_score_shaped_answer |
| Spike llama3.2:3B | spike-fixed-llama32-3b-20261120 | 2/20 | 2/20 | 0 | 9 incorrect_answer, 5 no_score_shaped_answer, 4 repair_cap |

## 2.5b Comparison questions answered
(a) Questions passing in MAIN but not NOREP: none
    Questions passing in NOREP but not MAIN: q03, q04, q06, q09, q12, q17, q18, q19 (8 questions)
(b) Questions MAIN passes with fewer than all attempts: All 10 passed questions passed on attempt 1 (single repeat)

## Generated assets
- docs/report/generated/ceiling_check_fixed.json: 20/20 passing candidates (model-free)
- docs/report/generated/rerun_outcomes.csv: 40 rows (MAIN + NOREP per-question outcomes)
- docs/report/generated/rerun_failure_causes.md: failure causes for MAIN's 10 failed questions
- docs/report/generated/spike_fixed_summary.csv: 4 model spike summary rows
- docs/report/generated/rerun_numbers.json: per-run statistics for paper
- docs/RERUN_STATE.md: full session state

## Commit
Committed on post-freeze-fixes: Phase 1-2 complete with --repeats 1 per user request.

## Observations
- NOREP significantly outperforms MAIN: 18/20 vs 10/20 passed with replanning off
- qwen3:4b-instruct (MAIN) is substantially better than qwen2.5 family models on this task
- All 5 Phase 1 runs completed without infrastructure issues (0 timeouts)
- Ceiling check confirms 20/20 questions are reachable on the fixed code (model-free)
- The disclosure about post-freeze fixes and model replacement remains required per RERUN_AGENT_PROMPT section 9.0

## Open questions for the owner
Phase 3 (paper/deck/charts editing) must be approved by the owner per section 9.0 of RERUN_AGENT_PROMPT. The old result directories (post-freeze-fixes-failed8-*, m10-*, etc.) can be removed in Phase 4 with owner go-ahead. The recovery tag and D-052 entry for post-freeze fixes should be maintained.