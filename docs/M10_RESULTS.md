# M10 measured results (frozen benchmark)

Reference run: **`m10-frozen-real-20261117`** (2026-11-17).

## Reproduction

```bash
uv run python evaluation/run_frozen_experiment.py --verify-only
uv run python evaluation/run_frozen_experiment.py --mode real --repeats 3 --run-id m10-frozen-real-20261117
```

Requires Ollama with **`qwen3:4b`** per `config.yaml` (60s per-call timeout). Elapsed time for the reference run: **~48 minutes** wall clock.

Artifacts:

- Summary: `evaluation/results/frozen_experiment/latest.json`
- Per-question detail: `evaluation/results/m10-frozen-real-20261117/agent_eval.json`
- Markdown table: `evaluation/results/m10-frozen-real-20261117/agent_eval.md`
- Freeze manifest: `evaluation/benchmark/freeze_manifest.json`

## Headline scores (20 evaluation questions, 3 repeats each)

| Variant | Correct | Total | Notes |
| --- | ---: | ---: | --- |
| Fixed baseline | 20 | 20 | Template-keyed ceiling, not a fair competitor |
| Dynamic agent (`qwen3:4b`) | 13 | 20 | `score_complete: true`, **0 timeouts** |
| Recovery suite | 12 / 12 scenarios | — | Separate harness, no benchmark leakage |

Agent vs baseline (per-question, scored after repeats): **13 ties, 7 losses**, 0 wins.

Failure reasons (agent): **6 incorrect_answer**, **1 no_score_shaped_answer** (q01).

## Questions marked incorrect (agent)

| ID | Failure reason |
| --- | --- |
| q01 | no_score_shaped_answer |
| q06 | incorrect_answer |
| q07 | incorrect_answer |
| q08 | incorrect_answer |
| q11 | incorrect_answer |
| q12 | incorrect_answer |
| q20 | incorrect_answer |

Rank-style questions (q06–q08) and some trend / multistep items dominate failures. Filter (q01) failed answer extraction despite tool runs.

## Cost (aggregate, reference run)

- Total agent-eval time: **~2858 s** (~47.6 min)
- LLM calls (incl. warmup): **168**
- Dominant stage time: **replanning**, then **answer_synthesis**, then **plan_generation** (see `agent_eval.md`)

## Limitations

- Single dataset: **Sample Superstore** (SHA in freeze manifest).
- **20** frozen questions only; no claim of generalization.
- Model: local **qwen3:4b** on one GPU/CPU configuration.
- Baseline 20/20 reflects fixed templates on the same oracle, not open-ended planning quality.