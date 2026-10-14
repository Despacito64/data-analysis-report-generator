# AGENTS.md: main instructions for every AI tool

Read this file first, at the start of every session, before doing anything else.
Three different AI tools (GitHub Copilot, Cursor, Antigravity) work on this repository
one after another. None of them remembers earlier sessions. The files in `docs/` are the
shared memory. If it is not written down in `docs/`, the next agent will not know it.

The human owner does not write code by hand. You write it. They review, run tests and decide.

## 1. Project in one paragraph

A single-agent data-analysis system. A user uploads a CSV or XLSX file and asks a question in
natural language. One LLM plans typed analytical tasks, approved deterministic tools execute them,
the plan is revised when intermediate results or failures call for it, and a report is produced in
which every number links to a recorded evidence record. A fixed-workflow baseline is compared against
the dynamic agent on frozen questions scored by an independent oracle. Initial domain: retail sales
(Sample Superstore). Stack: Python, Pandas, openpyxl, Pydantic, LangGraph, Plotly, Streamlit, DuckDB (oracle, optional tool).

## 2. Session start protocol (mandatory)

1. Read `docs/HANDOFF.md`: the current task and the exact state the last agent left.
2. Read `docs/PROGRESS.md`: which modules are done and which gates have passed.
3. Read `docs/DECISIONS.md`: do not contradict an accepted decision.
4. Read the section for the current module in `docs/MODULES.md`.
   Also read `docs/CONTRACTS.md` if you touch any data shape, and `docs/ARCHITECTURE.md` if you add imports or files.
   Read `docs/PROJECT_SCOPE.md` or `docs/EVALUATION.md` only when the task needs them.
5. Reply with one short paragraph: what you understand the current task to be and what you will do.
   If `HANDOFF.md` and the user's request disagree, ask the user which wins. Do not guess.

## 3. Hard rules (never break these)

1. **Scope.** One agent only. No arbitrary Python execution or LLM-written SQL. No forecasting, ML training or causal claims.
   No live databases, authentication or deployment. See the exclusions in `docs/PROJECT_SCOPE.md`.
2. **The LLM proposes, code disposes.** The LLM chooses tasks and writes wording. Only registered, validated tools compute numbers.
   The LLM never computes or invents a number.
3. **Evidence before claims.** A number reaches a report only through a valid `EvidenceRecord`. Unsupported claims are removed.
4. **Fair comparison.** The baseline and the dynamic agent use the same tools, resolver, budgets and scoring. The baseline never replans.
5. **Contracts only.** Data crosses module boundaries only as the Pydantic models in `docs/CONTRACTS.md`. No untyped dicts between modules.
   Changing a contract needs a new entry in `DECISIONS.md`, a contract version bump and the owner's approval.
6. **Fail visibly.** Every run ends `complete`, `partial` or `failed` with a reason. No silent fallbacks, no swallowed exceptions, no unbounded loops.
7. **Oracle independence.** `evaluation/oracle.py` computes expected answers from the raw file with DuckDB SQL or plain Python.
   It must not import `da_agent.tools`, `da_agent.agent`, `da_agent.validation` or `da_agent.reports`. An automated test enforces this.
   Expected answers never appear in any prompt given to the agent, including recovery prompts.
8. **Untrusted data.** Uploaded cell text is data, never instructions. Never place raw cell text where the model reads instructions.
   Escape everything rendered into HTML.
9. **Dataset facts.** Never assume row or column counts. Use the registered dataset hash (`docs/DECISIONS.md` D-007).
10. **No quiet changes.** Do not add dependencies, rename public modules, delete or weaken tests, or lower a gate to make something pass,
    without a `DECISIONS.md` entry approved by the owner.
11. **Protected files.** Do not edit `docs/PROJECT_SCOPE.md` without the owner's approval. After the freeze (module M10), frozen questions,
    expected answers and prompts are read-only.
12. **Honest status.** Never say a task is done or tests pass unless you ran them in this session. Report the exact command and its result.
13. **One task at a time.** Work on the current module only. Do not start the next one.

## 4. Working loop for each task

1. Plan first. Write a short plan (files to touch, tests to add) and wait for the owner's approval when the task is larger than a single function.
2. Write tests from the module's exit gate before the implementation.
3. Implement the smallest change that passes them.
4. Run the full test suite and the linter. Fix failures. Do not weaken tests.
5. Summarize the diff in plain language (what changed, why, what to review).
6. Commit with a message like `M2: add period_compare tool (tests pass)`.

Keep tasks small. Free-tier usage limits can stop a session at any time, so leave the repository in a committed, working state after every step.

## 5. Session end protocol (mandatory, do it even if you may be cut off soon)

Update these files before you stop, in this order:

1. `docs/HANDOFF.md`: overwrite it completely using its template. The next agent starts here.
2. `docs/PROGRESS.md`: tick finished items and append one line to the session log.
3. `docs/DECISIONS.md`: append an entry for every non-obvious choice you made, and for every open question you hit.
4. Commit all of it.

If you were cut off before doing this, the next agent must reconstruct the state from `git log`, `git diff` and the test results, then record what it found in `HANDOFF.md`.

## 6. Conventions

- Python 3.11 or newer (confirm in M0). `uv` for environments and dependencies. `ruff` for lint and format. `pytest` for tests.
- Source layout: `src/da_agent/`. Tests in `tests/`. Evaluation code in `evaluation/`. Run traces in `runs/` (not committed).
- Full type hints. Pydantic v2 models for all contracts. Small pure functions where possible.
- Deterministic by default: fixed seeds, fixed sampling settings from `config.yaml`. Never hard-code budgets or model names in code.
- Errors are classified `Failure` objects (see `docs/CONTRACTS.md`), not bare exceptions, once past the data layer.
- Every executed task writes to the run trace. Do not add `print` debugging to committed code.
- Commit after each completed task. Never commit `runs/`, `.env`, or the raw dataset if its license forbids redistribution.

## 7. Where things live

| Need | File |
| --- | --- |
| Current task and state | `docs/HANDOFF.md` |
| What is done | `docs/PROGRESS.md` |
| Why things are the way they are | `docs/DECISIONS.md` |
| What to build, per module, with exit gates | `docs/MODULES.md` |
| Data shapes | `docs/CONTRACTS.md` |
| Components, imports, repository layout | `docs/ARCHITECTURE.md` |
| Objectives, scope, requirements | `docs/PROJECT_SCOPE.md` |
| Questions, oracle, metrics | `docs/EVALUATION.md` |
| Prompts to paste when starting or switching tools | `docs/SESSION_PROMPTS.md` |

## 8. When unsure

Ask the owner one specific question and stop. Do not invent requirements, silently choose between two reasonable designs,
or "improve" something outside the current task. Record the question in `HANDOFF.md` under Open questions.
