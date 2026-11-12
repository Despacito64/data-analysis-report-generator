# Dynamic agent evaluation

Detailed results: `evaluation\results\m6_qwen3-4b\agent_eval.json`

| Variant | Correct | Total | Accuracy |
| --- | ---: | ---: | ---: |
| agent | 0 | 20 | 0.000 |
| baseline | 20 | 20 | 1.000 |

The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.

## Agent run metrics

- runs: 20
- repeats_per_question: 1
- plan_validity_rate: 0.0
- repair_rate: 0.0
- repair_attempts_per_run: 0.0
- replan_rate: 0.0
- tool_calls_per_run: 0.0
- mean_latency_s: 62.14440641500259
- mean_latency_by_question_s: {'q01': 62.22890849999385, 'q02': 62.206308299995726, 'q03': 62.144797600019956, 'q04': 62.11557069999981, 'q05': 62.13041620000149, 'q06': 62.14670070001739, 'q07': 62.142349500005366, 'q08': 62.12721580002108, 'q09': 62.1150900000066, 'q10': 62.127629499998875, 'q11': 62.180793999985326, 'q12': 62.12621779998881, 'q13': 62.15336220001336, 'q14': 62.12858240000787, 'q15': 62.178845899994485, 'q16': 62.135642100009136, 'q17': 62.133455400005914, 'q18': 62.12576149997767, 'q19': 62.11955040000612, 'q20': 62.12092980000307}
- failure_categories: {'FailureClass.TRANSIENT': 20}

## Per-question outcome

| Question | Agent | Baseline | Outcome |
| --- | --- | --- | --- |
| q01 | 0.000 | True | unscored |
| q02 | 0.000 | True | unscored |
| q03 | 0.000 | True | unscored |
| q04 | 0.000 | True | unscored |
| q05 | 0.000 | True | unscored |
| q06 | 0.000 | True | unscored |
| q07 | 0.000 | True | unscored |
| q08 | 0.000 | True | unscored |
| q09 | 0.000 | True | unscored |
| q10 | 0.000 | True | unscored |
| q11 | 0.000 | True | unscored |
| q12 | 0.000 | True | unscored |
| q13 | 0.000 | True | unscored |
| q14 | 0.000 | True | unscored |
| q15 | 0.000 | True | unscored |
| q16 | 0.000 | True | unscored |
| q17 | 0.000 | True | unscored |
| q18 | 0.000 | True | unscored |
| q19 | 0.000 | True | unscored |
| q20 | 0.000 | True | unscored |

