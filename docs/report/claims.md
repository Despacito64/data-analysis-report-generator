# Claims ledger for docs/report/main.tex

| Claim | Source |
|---|---|
| R1 12/20, 36/60 attempts, 258 calls, 93 min | evaluation/results/final-code-frozen-real-20261119/agent_eval.json |
| R2 12/20, 36/60, 118 calls, 61 min | evaluation/results/clean-ablation-max-replans-0-20261119/agent_eval.json |
| R0 13/20 (q02 passes) | evaluation/results/m10-frozen-real-20261117/agent_eval.json |
| 12 reachable questions | docs/report/generated/ceiling_check.json (scripts/ceiling_check.py) |
| q02 cause: augment_chat_plan | src/da_agent/agent/chat_plan.py:79; R1 q02 answer {"West": 251991.832} |
| q12 direction volatile vs increasing | R1 q12 answer vs evaluation/benchmark/oracle.json |
| Recovery suite 12/12 | R1 agent_eval.json recovery section |
| Spike 3B 0/4, 7B 2/4 (partial, 1 repeat) | model-spike-qwen25-*-20261119150629 |
| Not verified here | commit 5acc4f1 as R0's revision (from earlier notes); Menakshi's details; Shivam's email (from git history) |
