# SESSION_PROMPTS.md: prompts to paste when starting, ending or switching tools

Paste these into Copilot Chat, Cursor or Antigravity. They make every tool follow the same protocol. Replace the angle-bracket parts.

## 1. Start of any session (any tool)

```
Read AGENTS.md first and follow it. Then follow the session start protocol: read docs/HANDOFF.md, docs/PROGRESS.md, docs/DECISIONS.md and the
current module section in docs/MODULES.md. Do not write code yet. Reply with one short paragraph: what the current task is, what you plan to do,
and which files you will touch. Wait for my approval before editing.
```

## 2. Give a task

```
Task: <for example, "M1: implement the CSV loader and its tests">.
Write tests from the module's exit gate first, then the implementation. Keep to this task only. Run the tests and linter and show me the exact
commands and results. Summarize the diff in plain language. Commit when tests pass.
```

## 3. End of a session (before you run out of free quota)

```
Stop coding. Follow the session end protocol in AGENTS.md: overwrite docs/HANDOFF.md using its template, update docs/PROGRESS.md (tick only what
you verified by running tests, and append one line to the session log), append any new decisions or open questions to docs/DECISIONS.md, then commit.
Tell me what the next agent should do first.
```

## 4. Switching tools checklist

1. Ask the current tool to run prompt 3. Check that `HANDOFF.md` looks correct and the work is committed (`git status` is clean).
2. Open the repository in the next tool.
3. Paste prompt 1. Make sure the reply matches `HANDOFF.md`. If it does not, tell it to re-read the file.
4. Give the next task with prompt 2.

If a tool was cut off mid-task without running prompt 3: in the next tool, say "The previous session was cut off. Rebuild the state from `git log`,
`git status`, `git diff` and by running the tests. Write what you found into `docs/HANDOFF.md`, then wait for me."

## 5. Oracle session (M4 only, use a different tool from the one that wrote the tools)

```
Read AGENTS.md and docs/EVALUATION.md only. Do NOT open or read anything under src/da_agent/tools/, src/da_agent/agent/, src/da_agent/validation/ or
src/da_agent/reports/. Write evaluation/oracle.py that computes the expected answer for each question in evaluation/questions_dev.json directly from the
raw dataset file using DuckDB SQL (or plain Python). It must not import any da_agent tool, agent, validation or report code. Add tests, including a test that
fails if oracle.py imports forbidden modules. I will hand-check five of its answers.
```

## 6. Review session (read-only audit, useful when switching tools)

```
Read AGENTS.md, docs/CONTRACTS.md and docs/ARCHITECTURE.md. Review module <Mx> against its exit gate in docs/MODULES.md. Do not change any code.
List: contract violations, import-rule violations, missing or weak tests, silent fallbacks, places where the LLM could produce or alter a number,
and anything that contradicts docs/DECISIONS.md. Rank findings by severity.
```

## 7. Habits that save free-tier quota

- One module per session, small tasks, plan before edits.
- Do not paste large files into chat. Name the file and let the tool read it.
- Commit after every task so a cut-off costs you little.
- Use the review prompt (6) in a different tool than the one that wrote the code.
