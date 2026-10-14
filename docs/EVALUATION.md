# EVALUATION.md: questions, oracle, metrics, procedure

The oracle-writing session reads this file, `AGENTS.md` and the raw dataset only. It must not read `src/da_agent/tools/`.

## Question set

About 30 questions: 10 development (for tuning prompts and templates) and 20 evaluation (frozen before any final run). Tune only on the development set.

| Category | Tests | Evaluation questions |
| --- | --- | --- |
| Single-step lookup | Filter, aggregate, period | 3 |
| Period comparison | Change between periods, absent periods | 3 |
| Ranking | Top or bottom items, tie handling | 3 |
| Contribution | Share of a total by segment, reconciliation | 3 |
| Multistep diagnostic | Follow-up breakdown that depends on the first result | 5 |
| Ambiguous | Correct clarification or recorded assumption | 2 |
| Unanswerable | Correct decline (missing column, forecasting, causal) | 1 |

Each question record: id, text, category, difficulty, split (dev or eval), expected answer fields, answer type (number, label, ranked list, multistep).
Do not store the expected tool path where the agent could read it. Write the multistep questions so the best second step depends on the first result.

## Oracle

`evaluation/oracle.py` reads the raw file and computes expected answers with DuckDB SQL or plain Python. It imports nothing from the tools, agent,
validation or report code, so a bug in a shared Pandas function cannot hide itself. Hand-check at least 5 oracle answers before relying on it.
Expected answers are never shown to the agent, including in recovery prompts.

## Metrics

| Metric | Definition |
| --- | --- |
| Answer correctness | Numbers within a stated tolerance, labels exact, tied rankings accepted in any tied order |
| Unsupported-claim rate | Claims in the final validated report without a valid evidence record |
| Invalid tool-call rate | Calls rejected by argument validation, per run |
| Recovery success | Controlled failures resolved within limits, plus correct partial or failed status when unrecoverable |
| Cost | Tool calls, LLM calls, tokens, latency per question |
| Plan revisions | Count of revisions that changed a task or argument, with triggering evidence |

## Procedure

1. Freeze dataset hash, questions, expected answers, prompts, model settings, budgets, code revision.
2. Run both variants with the same tools and budgets, 3 repeats per question at fixed sampling settings.
3. Run the recovery suite separately.
4. Report counts per category (for example 14 of 20), per-question results and every failure. Not percentages alone.
5. Optional ablation: dynamic agent with validation feedback off.

State the limitation: results come from one dataset and 20 evaluation questions and do not support general claims.
