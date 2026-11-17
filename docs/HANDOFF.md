# HANDOFF.md: current task and continuation

Updated: 2026-11-17 by Cursor

## Current task
**M9** near complete; **M10** is next. Follow-up evidence now pre-seeds the graph (`seed_reused_evidence`, D-043). Presenters cover `group_aggregate`, `rank`, `period_compare`, `trend`.

## State
- Branch: `shivam` (commits through trace progress `1c9745c`; newer work may be uncommitted until pushed).
- Tests: `uv run pytest -q` → **293 passed**.
- UI: `uv run streamlit run app.py` — demo mode, live progress, follow-up checkboxes seed executor when hash matches.
- M8 gate passed; M9 gate: hash-gated reuse + executor seed + Streamlit path.

## Next steps
1. **M10:** freeze step, eval runner (baseline vs agent, 3×20 questions), reproduction command, manuscript.
2. Optional: gitignore or commit `demo/report.*`, `.agents/`, `skills-lock.json`.
3. Presenters: `segment_contribution`, charts for rank/period/trend in HTML.

## How to run
- `uv run pytest -q`
- `uv run streamlit run app.py`
- `uv run python demo/run_real_demo.py`