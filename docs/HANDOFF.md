# HANDOFF.md: current task and continuation

Updated: 2026-11-20 by Claude Code

## Current task
**D-052**: post-freeze fixes were measured (R1, R2, model comparison) and the paper, deck, charts and documents were updated to those results. Remaining: owner review, and the optional cleanup of old results (Phase 4 in `docs/RERUN_AGENT_PROMPT.md`).

## State
- Branch: `post-freeze-fixes` (cut from `shivam`; contains the paper work). Nothing from this session is pushed except earlier commits on `shivam`.
- `CONTRACT_VERSION` is `0.2.0`. Tool names unchanged. Tests: `uv run pytest -q` 328 passed. Recovery suite 12/12.
- Planner model: `qwen3:4b-instruct` (passed with `--model`; `config.yaml` and the freeze manifest still say `qwen3:4b` and were not edited).
- Results (one run per question): R1 replanning on 10/20 (84 calls, 29 min); R2 replanning off 18/20 (42 calls, 12 min); model comparison with replanning on: qwen2.5:7b 8, llama3.2:3b 2, qwen2.5:3b 1. Model-free ceiling check: 20/20 reachable.
- Cause of the R1 shortfall (traces): after a correct first plan the inspection step added tasks and the scorer reads the last executed task. See `docs/report/generated/rerun_failure_causes.md`.
- The results are not held-out: the system was fixed after an earlier run on the same questions and the model was replaced after the freeze. The paper and deck say so.

## Next steps
1. Owner review of the paper (`docs/report/`, 6 pages) and the deck (`docs/Technical-Review-Deck.pptx`, 22 slides). Both are local only: they are not tracked in git (an earlier version of the paper and a deck were pushed to GitHub before this was decided; they remain in history).
2. Decide about the demo video, which was recorded with the previous model.
3. Old result directories, the M10 reference run, the M6 and M5 outputs and the earlier deck were removed on 2026-11-20; recovery tags `pre-cleanup-20261120` and `pre-cleanup2-20261120` are local.
4. Decide whether to merge `post-freeze-fixes` into `shivam` and push. Nothing from this branch is pushed.

## Open questions
- Upstream identity of `qwen3:4b-instruct` was not verified beyond `ollama show` (architecture qwen3, 4.0B, Q4_K_M); the paper says "instruction-tuned model of the Qwen3 family".
- The `qwen3:4b` Ollama tag no longer exists locally; README setup lines still say `ollama pull qwen3:4b`.

## How to run
- Evaluation: `uv run python evaluation/run_agent_eval.py --mode real --repeats 1 --model qwen3:4b-instruct --run-id <id>` (add `--max-replans 0` for no replanning)
- Paper assets: `uv run python scripts/make_report_assets.py --main <R1 dir> --noreplan <R2 dir> --ceiling docs/report/generated/ceiling_check_fixed.json --spike docs/report/generated/spike_fixed_summary.csv`, then `tectonic -X compile main.tex` in `docs/report`
- Charts: `uv run python scripts/generate_metrics_charts.py`
- Deck: `uv run --with python-pptx python scripts/build_technical_ppt.py --template "<path>/askMNIT_SmritiStyle.pptx" --out docs/Technical-Review-Deck.pptx`
- Tests: `uv run pytest -q`
