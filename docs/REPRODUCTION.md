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

## Refreshing the freeze (owner approval)

After an intentional change to questions, oracle, dataset, or `config.yaml`:

```bash
uv run python evaluation/run_frozen_experiment.py --write-freeze
```

Commit the updated `freeze_manifest.json` with a `DECISIONS.md` entry.

## Limitations

Scores are measured on **Sample Superstore** and **20 frozen questions** only. Do not generalize beyond this benchmark.