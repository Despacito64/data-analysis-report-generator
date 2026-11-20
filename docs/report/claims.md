# Claims ledger for docs/report/main.tex

Run labels in the paper: R1 = replanning on, R2 = replanning off. Run ids are internal and do not appear in the paper.

| Claim | Source |
|---|---|
| R1: 10/20 passed, 84 LLM calls, 29 min, 0 timeouts | evaluation/results/post-freeze-fixes-frozen-real-20261120/agent_eval.json |
| R2: 18/20 passed, 42 LLM calls, 12 min, 0 timeouts (`--max-replans 0`) | evaluation/results/post-freeze-fixes-no-replan-20261120/agent_eval.json |
| Stage seconds R1: plan 636, replan 971, repair 187, answer 35, tools 3; R2: plan 635, repair 9, answer 15, tools 1 | same files, `aggregate.stage_timings` |
| Eight questions pass only without replanning; ten pass in both; q11 and q20 fail in both | docs/report/generated/rerun_outcomes.csv |
| First plan has the same tool list in both runs for all 20 questions; R1 added tasks after a correct first plan (2 to 4 plan versions, 3 to 12 tool executions) | runs/agent_eval_<run id>_<q>_r1_*/trace.jsonl; docs/report/generated/rerun_failure_causes.md |
| q03 example (group_aggregate by Region, four replan calls, 8 executions, final answer profit shares by segment) | R1 attempt q03 and its trace |
| q11: plan has no 2017 restriction; q20: rank without aggregation after group_aggregate | R2 traces (plan events) |
| Four models, one run each, replanning on: 10, 8, 2, 1 of 20 | docs/report/generated/spike_fixed_summary.csv |
| Model-free ceiling check: passing plan for 20 of 20 | docs/report/generated/ceiling_check_fixed.json (scripts/ceiling_check.py) |
| Recovery suite 12/12 | evaluation/recovery_suite/run_recovery_suite.py, run 2026-11-20 |
| Planner: 4.0B parameters, Q4_K_M, Qwen3 architecture | `ollama show qwen3:4b-instruct` (upstream identity not verified) |
| Setup: Ollama 0.23.3, Python 3.14, pandas 3.0.6, Pydantic 2.14.1, LangGraph 1.2.15, temperature 0, seed 42 | docs/RERUN_STATE.md, agent_eval.json `evaluation` |
| Question, oracle and config hashes match the freeze manifest; manifest names the earlier model | `run_frozen_experiment.py --verify-only`, evaluation/benchmark/freeze_manifest.json |
| System changed after an earlier run on the same questions; model replaced after the freeze (disclosed in the paper) | commit 1703cf7, docs/DECISIONS.md D-052 |
| Not verified | upstream identity of the planner model; commit hash of the code at run time is `1703cf7` plus documentation commits |
