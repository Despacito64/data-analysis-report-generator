# ARCHITECTURE.md: components, data flow, imports, layout

## Components

```
                         Interface (M9, Streamlit)
                       /                          \
         Data layer (M1)  ---profile--->  Question resolver (M5)
                                            |            |
                                   Fixed baseline (M4)  Dynamic agent (M6, M7)   <- only difference
                                            \            /
                              Tool registry and executor (M3)
                                  /                        \
                    Analytical tools (M2)          Evidence store + run trace (M0)
                                                           |
                                         Claim validation (M7) -> Report (M8)

  Evaluation (M4, M10): independent oracle + scorer, offline, compares both variants.
```

Both variants share the data layer, resolver, registry, evidence store and report path. Only the planner differs.

## End-to-end run

1. Receive file and question. Create run id. Check input limits. (M1, M9)
2. Load and profile. Assign immutable dataset hash and transformation version. (M1)
3. Resolve the question: metric, period, grouping, ambiguity decisions, or decline if unanswerable. (M5)
4. Generate an initial plan of typed tasks with dependencies. Validate it. (M5)
5. Select a ready task (all dependencies have valid results). Validate its arguments. (M6, M3)
6. Execute the deterministic tool. Validate result schema and numerical invariants. (M3)
7. Store an `EvidenceRecord`. Send a concise summary or a classified `Failure` to the inspector. (M3, M6, M7)
8. Continue a ready task, revise pending tasks, or finalize, based on the objective and budgets. (M6)
9. Build findings from valid evidence. Validate every numerical claim. (M7, M8)
10. Render the report and charts with final status and limitations. (M8)

The fixed baseline follows the same steps but replaces steps 4 and 8 with a template chosen from the intent and a frozen repair policy
(identical transient retries allowed, no analytical replanning).

## Repository layout

```
data-analysis-agent/
├── AGENTS.md  README.md  config.yaml  pyproject.toml
├── docs/                         # shared memory for all AI tools
├── app.py                        # M9 Streamlit entry
├── src/da_agent/
│   ├── contracts/                # M0 Pydantic models (see CONTRACTS.md)
│   ├── core/                     # M0 config, budgets, run-trace writer
│   ├── data/                     # M1 loader.py, profiler.py, registry.py (dataset registration + hash)
│   ├── validation/               # args.py, results.py, plan.py (M3, M5), claims.py (M7)
│   ├── tools/                    # M2 pandas_tools.py, statistics.py, charts.py, sql_tools.py (optional)
│   │                             # M3 registry.py (allowlist + executor)
│   ├── agent/                    # M5 resolver.py, planner.py; M4 baseline.py;
│   │                             # M6 state.py, graph.py, prompts.py; M7 recovery.py
│   ├── reports/                  # M8 insights.py, generator.py, renderer.py, templates/
│   └── pipeline.py               # run_baseline(), run_agent(): the only entry points for app and evaluation
├── evaluation/                   # questions_dev.json, questions_eval.json, oracle.py, scorer.py,
│                                 # run_eval.py, recovery_suite/
├── tests/                        # fixtures/, unit/, integration/, security/
└── runs/                         # per-run traces and reports (gitignored)
```

## Import rules (lower layers never import higher ones)

| Layer | Package | May import |
| --- | --- | --- |
| 1 | `contracts` | nothing from `da_agent` |
| 2 | `core` | contracts |
| 3 | `data` | contracts, core |
| 4 | `validation` | contracts, core |
| 5 | `tools` | contracts, core, data, validation |
| 6 | `agent`, `reports` | layers 1 to 5. `agent` and `reports` never import each other |
| 7 | `pipeline` | everything above |
| 8 | `app.py`, `evaluation/run_eval.py` | `pipeline`, contracts, core |

Additional rules:

- `validation` never imports `tools`. Tool metadata arrives as `ToolSpec` objects (a contract). Recomputation in the claim validator
  uses an injected callable.
- `evaluation/oracle.py` imports no `da_agent` tool, agent, validation or report code. It reads the raw file and uses DuckDB SQL or plain Python.
- Only `pipeline.py` wires modules together. No module reaches into another module's internals.
- An import-check test enforces these rules (added in M0, extended as packages appear).

## Build order

M0, M1, M2, M3, M5, M4, M6, M7, M8, M9, M10. M5 precedes M4 because the baseline reuses the resolver.
Report templates (M8) and the Streamlit shell (M9) may start earlier with stub evidence, but a module is finished only when its gate passes.

## Validation layers

| Layer | When | Checks | Module |
| --- | --- | --- | --- |
| Input | Upload | Extension, size and row limits, readability, sheet, non-empty | M1 |
| Plan | Before execution | Known tools, existing columns, typed args, acyclic dependencies, one ready task | M5 |
| Arguments | Before each task | Types fit the profile, periods within coverage | M3 |
| Result | After each task | Declared schema, numerical invariants | M3 |
| Claim and report | Before rendering | Every numeric claim matches a valid evidence record | M7, M8 |
