# Copilot instructions

The full instructions are in `AGENTS.md` at the repository root. Read it first, then follow its session start protocol
(`docs/HANDOFF.md`, `docs/PROGRESS.md`, `docs/DECISIONS.md`, then the current module in `docs/MODULES.md`).

Key rules in brief (details in `AGENTS.md`):

- One LLM agent only. No arbitrary Python or LLM-written SQL. No forecasting, ML training, or causal claims.
- The LLM never computes numbers. Only registered, validated tools do. A number reaches a report only through a valid evidence record.
- Data crosses module boundaries only as the Pydantic contracts in `docs/CONTRACTS.md`. Do not change contracts without a `DECISIONS.md` entry and the owner's approval.
- Respect the import rules in `docs/ARCHITECTURE.md`. `evaluation/oracle.py` must not import tool, agent, validation or report code.
- Write tests first from the module's exit gate. Never weaken a test or gate to make it pass. Never claim tests pass unless you ran them.
- Work on one task only. Commit after each task.
- Before the session ends, overwrite `docs/HANDOFF.md`, update `docs/PROGRESS.md`, and append to `docs/DECISIONS.md`.
