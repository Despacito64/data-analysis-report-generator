# Dynamic agent evaluation

Detailed results: `evaluation/results/model-spike-qwen25-7b-instruct-20261119150629/agent_eval.json`
Score complete: **False**

| Accuracy measure | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| All questions (timeouts/not-run incorrect) | 2 | 20 | 0.100 |
| Completed only | 2 | 4 | 0.500 |

The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.

Total evaluation time: 449.449s
Warm-up time (excluded from question budgets): 14.899s
Total LLM calls including warm-up: 11
Aggregate stage timings (s): `{"answer_synthesis": 86.19377254194114, "graph_finalization": 0.013987337937578559, "plan_generation": 261.21057757607196, "plan_validation": 0.03816706989891827, "question_resolution": 0.0, "replanning": 79.50782273488585, "result_inspection": 0.00793818710371852, "tool_execution": 0.6990763768553734, "tool_executions": 0.6901999999999999}`
Agent-vs-baseline outcomes: `{"loss": 18, "tie": 2}`
Failure reasons: `{"no_score_shaped_answer": 2, "question_timeout": 1}`

## Per-question results

| Question | Status | Accuracy | Baseline outcome | Total time (s) | Stage timings (s) | Tool executions | Repair attempts | LLM calls | Failure stage/reason |
| --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- |
| q01 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q02 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q03 | passed | True | tie | 75.417 | `{"answer_synthesis": 0.004339750041253865, "graph_finalization": 0.0002565080067142844, "plan_generation": 55.79934166802559, "plan_validation": 0.01274918601848185, "question_resolution": 0.0, "replanning": 7.956568807945587, "result_inspection": 0.0020343890646472573, "tool_execution": 0.08794086193665862, "tool_executions": 0.085}` | `[{"duration_s": 0.085, "status": "ok", "task_id": "t1", "tool": "group_aggregate"}]` | `[]` | 3 |  |
| q04 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q05 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q06 | timeout | n/a | loss | 202.970 | `{"answer_synthesis": 86.18403672694694, "graph_finalization": 0.012049308978021145, "plan_generation": 56.057002151035704, "plan_validation": 0.012550196959637105, "question_resolution": 0.0, "replanning": 60.08036397700198, "result_inspection": 0.0028030710527673364, "tool_execution": 0.5991077159997076, "tool_executions": 0.596}` | `[{"duration_s": 0.596, "status": "ok", "task_id": "t1", "tool": "rank"}]` | `[]` | 2 | answer_synthesis / question_timeout |
| q07 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q08 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q09 | failed | False | loss | 60.077 | `{"answer_synthesis": 0.0012616469757631421, "graph_finalization": 0.0005929359467700124, "plan_generation": 60.065318978973664, "plan_validation": 0.0002505839802324772, "question_resolution": 0.0, "tool_executions": 0.0}` | `[]` | `[]` | 1 | graph_finalization / no_score_shaped_answer |
| q10 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q11 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q12 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q13 | passed | True | tie | 50.911 | `{"answer_synthesis": 0.0026067530270665884, "graph_finalization": 0.00029269594233483076, "plan_generation": 29.24432334303856, "plan_validation": 0.012357090949080884, "question_resolution": 0.0, "replanning": 11.470889949938282, "result_inspection": 0.0031007269863039255, "tool_execution": 0.012027798919007182, "tool_executions": 0.0092}` | `[{"duration_s": 0.0045, "status": "ok", "task_id": "t1", "tool": "group_aggregate"}, {"duration_s": 0.0047, "status": "ok", "task_id": "t2", "tool": "segment_contribution"}]` | `[]` | 3 |  |
| q14 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q15 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q16 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q17 | failed | False | loss | 60.060 | `{"answer_synthesis": 0.0015276649501174688, "graph_finalization": 0.0007958890637382865, "plan_generation": 60.04459143499844, "plan_validation": 0.00026001199148595333, "question_resolution": 0.0, "tool_executions": 0.0}` | `[]` | `[]` | 1 | graph_finalization / no_score_shaped_answer |
| q18 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q19 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
| q20 | not_run | n/a | loss | 0.000 | `{}` | `[]` | `[]` | 0 |  |
