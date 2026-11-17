# Dynamic agent evaluation

Detailed results: `evaluation/results/m6-shivam-smoke/agent_eval.json`
Score complete: **False**

| Accuracy measure | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| All questions (timeouts/not-run incorrect) | 1 | 20 | 0.050 |
| Completed only | 1 | 1 | 1.000 |

The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.

Total evaluation time: 40.002s
Warm-up time (excluded from question budgets): 1.811s
Total LLM calls including warm-up: 5
Aggregate stage timings (s): `{"answer_synthesis": 0.0010845930082723498, "graph_finalization": 0.00038502004463225603, "plan_generation": 27.978191526024602, "plan_validation": 0.014169479021802545, "question_resolution": 0.0025750179775059223, "repair_attempt_1": 2.6895180080318823, "repair_attempt_2": 2.6909039550228044, "replanning": 11.968775079003535, "result_inspection": 0.00011383602395653725, "tool_execution": 0.009326174040324986, "tool_executions": 0.0062}`
Agent-vs-baseline outcomes: `{"loss": 19, "tie": 1}`
Failure reasons: `{}`

## Per-question results

| Question | Status | Accuracy | Baseline outcome | Total time (s) | Stage timings (s) | Tool executions | Repair attempts | LLM calls | Failure stage/reason |
| --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- |
| q01 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q02 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q03 | passed | True | tie | 39.992 | `{"answer_synthesis": 0.0010845930082723498, "graph_finalization": 0.00038502004463225603, "plan_generation": 27.978191526024602, "plan_validation": 0.014169479021802545, "question_resolution": 0.0025750179775059223, "repair_attempt_1": 2.6895180080318823, "repair_attempt_2": 2.6909039550228044, "replanning": 11.968775079003535, "result_inspection": 0.00011383602395653725, "tool_execution": 0.009326174040324986, "tool_executions": 0.0062}` | `[{"duration_s": 0.0062, "status": "ok", "task_id": "t1", "tool": "group_aggregate"}]` | `[{"attempt": 1, "duration_s": 2.6895180080318823}, {"attempt": 2, "duration_s": 2.6909039550228044}]` | 4 |  |
| q04 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q05 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q06 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q07 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q08 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q09 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q10 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q11 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q12 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q13 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q14 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q15 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q16 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q17 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q18 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q19 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q20 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
