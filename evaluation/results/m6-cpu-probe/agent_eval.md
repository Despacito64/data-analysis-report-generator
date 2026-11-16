# Dynamic agent evaluation

Detailed results: `evaluation\results\m6-cpu-probe\agent_eval.json`
Score complete: **False**

| Accuracy measure | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| All questions (timeouts/not-run incorrect) | 2 | 20 | 0.100 |
| Completed only | 2 | 2 | 1.000 |

The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.

Total evaluation time: 326.692s
Warm-up time (excluded from question budgets): 23.455s
Total LLM calls including warm-up: 5
Aggregate stage timings (s): `{"answer_synthesis": 0.005833499992149882, "graph_finalization": 0.00671090000832919, "plan_generation": 205.56540519998816, "plan_validation": 0.11400919999869075, "question_resolution": 0.013496400002622977, "replanning": 120.73400020001282, "result_inspection": 0.004520200003753416, "tool_execution": 0.10644300001149531, "tool_executions": 0.07680000000000001}`
Agent-vs-baseline outcomes: `{"loss": 18, "tie": 2}`
Failure reasons: `{}`

## Per-question results

| Question | Status | Accuracy | Baseline outcome | Total time (s) | Stage timings (s) | Tool executions | Repair attempts | LLM calls | Failure stage/reason |
| --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- |
| q01 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q02 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q03 | passed | True | tie | 233.258 | `{"answer_synthesis": 0.0034376999974483624, "graph_finalization": 0.0034426000056555495, "plan_generation": 169.84433399999398, "plan_validation": 0.08546550000028219, "question_resolution": 0.010063800000352785, "replanning": 63.15037940000184, "result_inspection": 0.003683100003399886, "tool_execution": 0.08470310000120662, "tool_executions": 0.063}` | `[{"duration_s": 0.063, "status": "ok", "task_id": "t1", "tool": "group_aggregate"}]` | `[]` | 2 |  |
| q04 | passed | True | tie | 93.400 | `{"answer_synthesis": 0.0023957999947015196, "graph_finalization": 0.003268300002673641, "plan_generation": 35.721071199994185, "plan_validation": 0.028543699998408556, "question_resolution": 0.003432600002270192, "replanning": 57.583620800010976, "result_inspection": 0.00083710000035353, "tool_execution": 0.021739900010288693, "tool_executions": 0.0138}` | `[{"duration_s": 0.0138, "status": "ok", "task_id": "t1", "tool": "group_aggregate"}]` | `[]` | 2 |  |
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
