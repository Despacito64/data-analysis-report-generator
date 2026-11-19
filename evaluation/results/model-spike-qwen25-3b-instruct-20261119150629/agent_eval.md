# Dynamic agent evaluation

Detailed results: `evaluation/results/model-spike-qwen25-3b-instruct-20261119150629/agent_eval.json`
Score complete: **False**

| Accuracy measure | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| All questions (timeouts/not-run incorrect) | 0 | 20 | 0.000 |
| Completed only | 0 | 4 | 0.000 |

The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.

Total evaluation time: 424.920s
Warm-up time (excluded from question budgets): 38.745s
Total LLM calls including warm-up: 23
Aggregate stage timings (s): `{"answer_synthesis": 82.97845912212506, "graph_finalization": 0.005067242891527712, "plan_generation": 107.85230554908048, "plan_validation": 0.050045729032717645, "question_resolution": 0.0, "repair_attempt_1": 54.669766919105314, "repair_attempt_2": 39.14819633087609, "replanning": 188.88478586799465, "result_inspection": 0.030213000951334834, "tool_execution": 1.880844859057106, "tool_executions": 1.6512}`
Agent-vs-baseline outcomes: `{"loss": 20}`
Failure reasons: `{"no_score_shaped_answer": 2, "question_timeout": 1, "repair_cap": 2}`

## Per-question results

| Question | Status | Accuracy | Baseline outcome | Total time (s) | Stage timings (s) | Tool executions | Repair attempts | LLM calls | Failure stage/reason |
| --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- |
| q01 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q02 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q03 | failed | False | loss | 33.713 | `{"answer_synthesis": 0.000526588992215693, "graph_finalization": 0.000251909950748086, "plan_generation": 24.587037204997614, "plan_validation": 0.014398353989236057, "question_resolution": 0.0, "replanning": 9.086746267043054, "result_inspection": 0.006363968946970999, "tool_execution": 0.006418862962163985, "tool_executions": 0.0029}` | `[{"duration_s": 0.0029, "status": "failed", "task_id": "t1", "tool": "filter"}, {"duration_s": 0.0, "status": "skipped", "task_id": "t2", "tool": "group_aggregate"}]` | `[]` | 2 | graph_finalization / no_score_shaped_answer |
| q04 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q05 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q06 | timeout | n/a | loss | 204.167 | `{"answer_synthesis": 82.9774661930278, "graph_finalization": 0.004574476042762399, "plan_generation": 7.911624187021516, "plan_validation": 0.012751542963087559, "question_resolution": 0.0, "repair_attempt_1": 21.443842506967485, "repair_attempt_2": 22.429315690067597, "replanning": 111.94623470597435, "result_inspection": 0.010210230015218258, "tool_execution": 1.2811832940205932, "tool_executions": 1.0678}` | `[{"duration_s": 0.0058, "status": "ok", "task_id": "t1", "tool": "filter"}, {"duration_s": 0.0072, "status": "ok", "task_id": "t2", "tool": "group_aggregate"}, {"duration_s": 0.5143, "status": "ok", "task_id": "t3", "tool": "rank"}, {"duration_s": 0.0045, "status": "ok", "task_id": "task_1", "tool": "segment_contribution"}, {"duration_s": 0.004, "status": "ok", "task_id": "t1", "tool": "segment_contribution"}, {"duration_s": 0.0069, "status": "ok", "task_id": "t2", "tool": "group_aggregate"}, {"duration_s": 0.5251, "status": "ok", "task_id": "t3", "tool": "rank"}]` | `[{"attempt": 1, "duration_s": 21.443842506967485}, {"attempt": 2, "duration_s": 22.429315690067597}]` | 6 | answer_synthesis / question_timeout |
| q07 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q08 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q09 | failed | False | loss | 100.906 | `{"plan_generation": 9.440724237007089, "plan_validation": 0.011101868934929371, "question_resolution": 0.0, "repair_attempt_1": 22.052678631036542, "repair_attempt_2": 4.841059383936226, "replanning": 61.07564958394505, "result_inspection": 0.00841598806437105, "tool_execution": 0.579422245034948, "tool_executions": 0.5716}` | `[{"duration_s": 0.0114, "status": "ok", "task_id": "t1", "tool": "period_compare"}, {"duration_s": 0.5546, "status": "ok", "task_id": "t2", "tool": "rank"}, {"duration_s": 0.0056, "status": "ok", "task_id": "task_1", "tool": "filter"}]` | `[{"attempt": 1, "duration_s": 22.052678631036542}, {"attempt": 2, "duration_s": 4.841059383936226}, {"attempt": 3, "duration_s": null}]` | 6 | replanning / repair_cap |
| q10 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q11 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q12 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q13 | failed | False | loss | 48.010 | `{"plan_generation": 27.805549007025547, "plan_validation": 0.01168300211429596, "question_resolution": 0.0, "repair_attempt_1": 4.286569498013705, "repair_attempt_2": 4.969261338934302, "replanning": 6.776155311032198, "result_inspection": 0.0052228139247745275, "tool_execution": 0.013820457039400935, "tool_executions": 0.0089}` | `[{"duration_s": 0.0046, "status": "ok", "task_id": "t1", "tool": "group_aggregate"}, {"duration_s": 0.0043, "status": "ok", "task_id": "t2", "tool": "segment_contribution"}]` | `[{"attempt": 1, "duration_s": 4.286569498013705}, {"attempt": 2, "duration_s": 4.969261338934302}, {"attempt": 3, "duration_s": null}]` | 5 | replanning / repair_cap |
| q14 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q15 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q16 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q17 | failed | False | loss | 38.118 | `{"answer_synthesis": 0.0004663401050493121, "graph_finalization": 0.00024085689801722765, "plan_generation": 38.10737091302872, "plan_validation": 0.00011096103116869926, "question_resolution": 0.0, "repair_attempt_1": 6.886676283087581, "repair_attempt_2": 6.908559917937964, "tool_executions": 0.0}` | `[]` | `[{"attempt": 1, "duration_s": 6.886676283087581}, {"attempt": 2, "duration_s": 6.908559917937964}]` | 3 | graph_finalization / no_score_shaped_answer |
| q18 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q19 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q20 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
