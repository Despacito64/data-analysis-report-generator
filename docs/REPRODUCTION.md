# Reproducing the frozen experiment (M10)

## Prerequisites

- Python 3.11+ with `uv sync`
- For **real** agent scores: Ollama running with the model in `config.yaml` (default `qwen3:4b`)

## One command

**CI / smoke (mock LLM, single pass per question):**

```bash
uv run python evaluation/run_frozen_experiment.py --mode mock --repeats 1 --questions q03
```

**Full frozen protocol (real model, 3 repeats per question — long-running):**

```bash
uv run python evaluation/run_frozen_experiment.py --mode real --repeats 3
```

**Verify benchmark assets only (no LLM):**

```bash
uv run python evaluation/run_frozen_experiment.py --verify-only
```

Outputs:

| Artifact | Path |
| --- | --- |
| Freeze manifest | `evaluation/benchmark/freeze_manifest.json` |
| Combined summary | `evaluation/results/frozen_experiment/latest.json` |
| Agent per-question traces | `evaluation/results/<run_id>/` |
| Recovery suite | `evaluation/results/recovery_suite/latest.json` |

## Reference run (2026-11-17)

Measured results with **`qwen3:4b`**, real Ollama, **3 repeats × 20 questions**: see `docs/M10_RESULTS.md`.

Pinned run id: `m10-frozen-real-20261117` → `evaluation/results/m10-frozen-real-20261117/agent_eval.json`.

## Refreshing the freeze (owner approval)

After an intentional change to questions, oracle, dataset, or `config.yaml`:

```bash
uv run python evaluation/run_frozen_experiment.py --write-freeze
```

Commit the updated `freeze_manifest.json` with a `DECISIONS.md` entry.

## Limitations

Scores are measured on **Sample Superstore** and **20 frozen questions** only. Do not generalize beyond this benchmark.