# M10 measured results (frozen benchmark)

**Superseded (2026-11-20).** The reference run recorded here (`m10-frozen-real-20261117`, previous model `qwen3:4b`, 3 repeats, 13/20) was removed together with the other earlier runs. Its diagnosis of the failures in this file (for example "answer extraction") was also found to be wrong. Current results, with the run ids, settings and the traced failure causes, are in `docs/EXPERIMENTS_SUMMARY.md` and decision D-052.

The earlier run and this file's original text remain in git history (local tag `pre-cleanup2-20261120`, and the pushed history of the `shivam` branch).

Artifacts that still exist:

- Freeze manifest: `evaluation/benchmark/freeze_manifest.json` (check with `uv run python evaluation/run_frozen_experiment.py --verify-only`)
- Summary of the latest frozen-experiment wrapper run: `evaluation/results/frozen_experiment/latest.json`
