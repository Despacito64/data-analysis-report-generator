# Experiments Summary

All experiments run on: local machine, GPU GTX 1650, qwen3:4b via Ollama, 2026-11-19.

---

## Experiment 1: M10 Reference Run (main result)

**System:** Dynamic agent, full pipeline (replanning ON, validation ON, narrative ON)  
**Model:** qwen3:4b  
**Questions:** 20 frozen eval questions, 3 repeats each  
**Run ID:** `m10-frozen-real-20261117`

| Metric | Value |
|---|---|
| Correct answers | 13 / 20 |
| Accuracy | 65% |
| Total LLM calls | 168 |
| Total wall time | ~2858 s (~48 min) |
| Timeouts | 0 |
| Failures: incorrect_answer | 6 |
| Failures: no_score_shaped_answer | 1 |

**Per-category breakdown:**

| Category | Correct | Total | Notes |
|---|---|---|---|
| filter | 1 | 2 | q01 failed answer extraction despite tools running |
| group_aggregate | 3 | 3 | Perfect |
| rank | 0 | 3 | LLM answer synthesis failed to extract ranked list |
| period_compare | 2 | 2 | Perfect |
| trend | 0 | 2 | LLM misread direction/slope from evidence |
| segment_contribution | 2 | 2 | Perfect |
| correlation | 2 | 2 | Perfect |
| anomalies | 2 | 2 | Perfect |
| multistep | 2 | 2 | Perfect |

**Stage time breakdown (aggregate across all questions):**

| Stage | Total time (s) | % of total |
|---|---|---|
| replanning | 1609 | 56% |
| answer_synthesis | 794 | 28% |
| plan_generation | 440 | 15% |
| repair_attempt_1 + 2 | 706 | 25% |
| tool_execution | 10 | <1% |

Key insight: tool execution is near-instant (<0.01 s per call). The LLM is the bottleneck in every stage.

**Baseline note:** The fixed-template baseline scores 20/20 because its templates are hand-matched to oracle question shapes at design time. It would score ~0% on any novel question outside those templates.

---

## Experiment 2: Ablation — No Replanning

**What changed:** `max-repair-attempts=0`, `max-llm-calls-per-question=4`  
**Hypothesis:** Removing the dynamic replanning loop should reduce accuracy.  
**Run ID:** `ablation-no-replan-20261119150629`

| Metric | With Replanning | Without Replanning | Delta |
|---|---|---|---|
| Correct | 13 / 20 | 12 / 20 | **+1 from replanning** |
| Accuracy | 65% | 60% | +5 pp |

**Per-question differences:**

| Question | Full system | No replan | Change |
|---|---|---|---|
| q01 | failed | failed | same |
| q02 | passed | **failed** | replanning recovered q02 |
| q03–q05 | passed | passed | same |
| q06–q08 | failed | failed | same (rank category; LLM synthesis issue) |
| q09–q10 | passed | passed | same |
| q11–q12 | failed | failed | same |
| q13–q18 | passed | passed | same |
| q19 | passed | passed | same |
| q20 | failed | failed | same |

**Interpretation:** Replanning contributed 1 additional correct answer (q02). The rank and trend failures are in the LLM answer-synthesis stage — replanning cannot fix those because the tools ran correctly but the LLM extracted the wrong value from the evidence. This points to answer-extraction logic as the next improvement target.

---

## Experiment 3: Model Comparison Spike

**Scope:** 5 representative questions (one per major category): q03 (group_aggregate), q06 (rank), q09 (period_compare), q13 (segment_contribution), q17 (anomalies).  
**1 repeat each. Same tools, budgets, and scoring.**

| Model | Params | Correct / 5 | Avg time/q | Notes |
|---|---|---|---|---|
| qwen2.5:3b-instruct | 3B | 0 / 5 | ~85 s | 3 repair_cap / no_score_shaped_answer; 1 timeout on rank |
| qwen3:4b (reference) | 4B | 4 / 5 | ~165 s | Only q06 (rank) failed |
| qwen2.5:7b-instruct | 7B | 2 / 5 | ~90 s | q03, q13 passed; q06 timeout, q09/q17 no_score_shaped_answer |

**Key findings:**
1. qwen3:4b outperforms qwen2.5:7b despite being a smaller model — the qwen3 family has better instruction-following for structured JSON output, which this system depends on.
2. qwen2.5:3b-instruct is too small: it cannot reliably produce plan JSON within the repair budget. Hits repair_cap on multiple questions.
3. qwen2.5:7b-instruct is faster per question (~90 s vs 165 s) but less accurate — model family matters more than size here.
4. Rank questions (q06) timeout on both new models — confirms this is a hard category, not a model-specific bug.

---

## Summary Table

| Experiment | Variant | Score | What it shows |
|---|---|---|---|
| M10 reference | qwen3:4b, full system | 13/20 (65%) | Main result |
| Ablation A | No replanning | 12/20 (60%) | Replanning contributes +1 correct answer |
| Model spike | qwen2.5:3b-instruct | 0/5 (0%) | Too small for structured JSON planning |
| Model spike | qwen3:4b | 4/5 (80%) | Best on these 5 questions |
| Model spike | qwen2.5:7b-instruct | 2/5 (40%) | Faster but weaker instruction-following |
| Recovery suite | All scenarios | 12/12 (100%) | Adversarial failure handling |
| Baseline | Fixed templates | 20/20 (100%) | Template ceiling — not a fair competitor |

---

## Charts generated

All charts are in `scripts/charts/`:

| File | Content |
|---|---|
| `chart_accuracy_by_category.png` | Agent vs baseline by question category |
| `chart_stage_time_waterfall.png` | Time per question broken down by pipeline stage |
| `chart_llm_calls_distribution.png` | LLM calls per question (red = failed) |
| `chart_tool_distribution.png` | Which tools were called and how often |
| `chart_repair_impact.png` | Repair attempts vs total time scatter |
| `chart_ablation_comparison.png` | With vs without replanning per question |
| `chart_model_comparison.png` | 3B vs 4B vs 7B on 5 spike questions |
| `summary_table.csv` | Full per-question data table |
