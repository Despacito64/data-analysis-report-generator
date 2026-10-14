# Data Analysis Agent

A single-agent system that answers natural-language questions about a tabular dataset (CSV or XLSX) by planning approved analytical operations,
executing them with deterministic tools, and producing an HTML report in which every number links to recorded evidence. A fixed-workflow baseline
is compared against the dynamic agent on frozen questions scored by an independent oracle.

Status: setup phase. See `docs/PROGRESS.md`.

## Setup and usage

To be filled in as modules are built (M0 adds installation, M9 adds running the app, M10 adds the evaluation reproduction command).

```
# install:      TBD (M0)
# run tests:    TBD (M0)
# run the app:  TBD (M9)
# reproduce evaluation: TBD (M10)
```

## Working on this repository with AI tools

Several AI tools take turns on this code and share no memory. `AGENTS.md` and `docs/` are the shared memory.

- Start every session with the start prompt in `docs/SESSION_PROMPTS.md`.
- End every session (or switch tools) with the end prompt, so `docs/HANDOFF.md` is current and the work is committed.
- Decisions go in `docs/DECISIONS.md`, progress in `docs/PROGRESS.md`.

## Layout

See `docs/ARCHITECTURE.md`.
