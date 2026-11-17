# HANDOFF.md: current task and continuation

Updated: 2026-11-17 by Cursor

## Current task
**M9 Streamlit** — polish and remaining gate items. Commits on `shivam`: M8 presenters (`7abf512`), M9 demo UI (`5b27965`), docs (`d294892`). Live trace progress and XLSX sheet hints landed in working tree (uncommitted).

## State
- Branch: `shivam`.
- M8 gate: passed (D-038, D-042 reader layer for `group_aggregate`).
- M7 gate passed (D-035–D-037).
- M6 real-model gate complete (D-034).
- `CONTRACT_VERSION` remains `0.1.0`.
- Dataset SHA `dc81c957…` (D-007).
- Tests: `uv run pytest -q` → **290 passed** (last run this session).
- UI: `uv run streamlit run app.py` — demo mode ON uses real Ollama (D-041); run shows **st.status** progress from `trace.jsonl`.
- Recovery CLI: `uv run python evaluation/recovery_suite/run_recovery_suite.py`.

## Next steps (M9)
1. Optional: wire **follow-up reuse** into LangGraph executor (D-039 says metadata-only today).
2. M8 presenters for `rank`, `period_compare`, `trend` (D-042 consequences).
3. M10 freeze / eval runner — not started.
4. Owner decision: commit `.agents/` taste-skill and `skills-lock.json` or gitignore.

## References audit
- `docs/REFERENCES.md` (D-040).
- Real demo: `uv run python demo/run_real_demo.py`.

## Open questions
- Dataset redistribution (D-007).
- Semantic field binding for findings (D-033) deferred.

## How to run
- `uv run pytest -q`
- `uv run ruff check .`
- `uv run streamlit run app.py`
- `uv run python evaluation/recovery_suite/run_recovery_suite.py`