# HANDOFF.md: current task and continuation

Updated: 2026-11-17 by Cursor

## Current task
**M9 Streamlit** in progress: `app.py` (upload, question, Ollama run, trace, HTML download) and `core/follow_up.py` (hash-gated evidence reuse). M8 committed (`b1afe13`). Gate still open: full follow-up wiring into the agent executor if required beyond trace `follow_up_reuse` events.

## State
- Branch: `shivam`. Recent work: M8 E2E finalize (uncommitted); prior commits through recovery suite and M8 renderer (`3cca72e`).
- `CONTRACT_VERSION` remains `0.1.0` (additive `AnalysisRun` / `KeyNumberCitation` only).
- M6 real-model gate: complete (`m6-shivam-full`, 13/20, D-034).
- M7 gate passed (D-035–D-037).
- M8 gate passed: unit renderer + **pipeline E2E** (`tests/integration/test_agent_report_e2e.py`, D-038).
- Dataset: registered SHA `dc81c957…` (D-007); commit `88451fc`.
- Tests: run `uv run pytest -q` after each M9 change.
- Run UI: `uv run streamlit run app.py` (demo mode ON: Sample Superstore + prefilled question, **real Ollama** — D-041)
- Recovery CLI: `uv run python evaluation/recovery_suite/run_recovery_suite.py`.

## Next steps (M9)
1. Streamlit upload + sheet selection with visible loader errors.
2. Question entry; show run trace progress; display `AgentResult` status and evidence.
3. HTML report download from the run directory produced by `run_agent()`.
4. Follow-up runs: new `run_id`, same dataset hash rules, no silent evidence reuse (M9 gate).
5. Optional UI polish: project skill **`design-taste-frontend`** (taste-skill) at `.agents/skills/design-taste-frontend/SKILL.md`; lockfile `skills-lock.json`. Reinstall: `npx --yes skills add Leonxlnx/taste-skill`. Untracked until the owner chooses to commit or gitignore (installer reported elevated third-party risk on [skills.sh](https://skills.sh/Leonxlnx/taste-skill)).

## References audit
- See `docs/REFERENCES.md` (D-040) for datasets, models, libraries, eval assets, taste-skill, and demo reproduction.
- Regenerate live demo: `uv run python demo/run_real_demo.py` → `demo/walkthrough.html` + `runs/demo-visual-real/`.

## Open questions
- Dataset redistribution approval remains as recorded in D-007.
- Semantic field binding for findings (D-033) still deferred inside insight builder.

## How to run
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run python evaluation/recovery_suite/run_recovery_suite.py`
- `uv run python evaluation/run_agent_eval.py --mode mock --questions q03`