# MODULES.md: implementation workflow, module by module

Build in this order: M0, M1, M2, M3, M5, M4, M6, M7, M8, M9, M10.
A module is finished only when its exit gate passes. Later modules may rely on a finished module without re-testing it.
Write tests from the gate first. Work on one module at a time.

## M0. Foundations and contracts
Depends on: nothing.

Build:
1. `uv` project with Pandas, openpyxl, Pydantic, LangGraph, Plotly, Streamlit, DuckDB, pytest, ruff.
2. Contracts from `CONTRACTS.md`, with `CONTRACT_VERSION`.
3. `config.yaml`: budgets, model name, sampling settings, seeds, input limits.
4. Run-trace writer: `runs/<run_id>/` as JSON lines (plans, tool calls, evidence, failures, status).
5. Dataset registry entry for the benchmark: file name, source, sheet, version, license, column schema, hash.
6. Model spike: run each candidate local model on 10 sample prompts; record valid-JSON rate, tool-name accuracy, latency. Choose one (DECISIONS D-006).
7. Import-rule test (see `ARCHITECTURE.md`).

Tests: each contract rejects a malformed example. The trace writer round-trips a run.
Gate: contracts validate. Dataset hash recorded. Chosen model has measured numbers.

## M1. Data layer (FR01, FR02, FR03)
Depends on: M0.

Build:
1. Loader: configurable CSV parsing (delimiter, encoding, date format), Excel sheet selection, `data_only` XLSX loading.
2. Input checks: extension allowlist, file size and row limits, empty data, corrupt file, invalid sheet, each with a clear message.
3. Profiler: physical type, semantic type, missing counts, exact duplicates, date coverage, descriptive statistics.
4. Dataset hash and transformation version.

Tests: fixtures with hand-computed missing and duplicate counts, dates in more than one format, numeric identifiers (postal codes),
empty file, corrupt XLSX. The same data as CSV and XLSX gives identical profiles.
Gate: both formats load. Every invalid input fails clearly. Counts match hand calculation. Profile serializes to JSON.

## M2. Deterministic analytical tools (FR05, tool side)
Depends on: M0, M1.

Build in this order: filter, group and aggregate, rank, period comparison, trend, segment contribution; then correlation and IQR anomaly flags
(with documented limitations); then Plotly chart builders that read tool output only. Each tool is a pure function from a data frame and typed
arguments to a typed result. DuckDB tools stay out until a query need is documented.

| Edge case | Required behavior |
| --- | --- |
| Ties in a ranking | Stable documented order, ties reported |
| All-missing sum | Reported as missing, not zero |
| Absent period | Explicit empty result, not a silent zero |
| Zero denominator in rate or growth | Undefined result with a reason |
| Contribution shares | Sum to the total within a stated tolerance |

Gate: all fixtures pass. Every successful call returns enough to reproduce it (arguments, input row count, result).

## M3. Tool registry and executor (FR05, FR07)
Depends on: M2.

Build:
1. Allowlisted registry: tool name to function, args model, result schema, invariants.
2. Argument validation against the profile: columns exist, types fit, periods within coverage.
3. Result validation: schema and per-tool numerical invariants.
4. Executor: runs one task, creates an `EvidenceRecord`, returns evidence or a classified `Failure`.
5. `ToolSpec` export generated from the registry, used by the planner prompt.

Tests: unknown tool, unknown column, wrong type, out-of-range period all rejected. Each invariant fires on a deliberately wrong result.
Gate: nothing outside the registry can run. Every executed task leaves evidence or a classified failure.

## M5. Question resolution and plan generation (FR04, FR13, FR14)
Depends on: M0, M1, M3. Build before M4: the baseline and the agent share the resolver.

Build:
1. Resolver: question and profile to `ResolvedQuestion`.
2. Ambiguity rule: if metric or period cannot be resolved, ask one clarifying question (interface) or record an explicit assumption (batch evaluation).
3. Answerability check: absent columns or excluded methods (forecasting, causal) are declined with a reason.
4. Planner prompt: resolved question, profile summary and `ToolSpec` list in; typed plan out.
5. Plan validator: tool names exist, columns exist, args type-check, no cycle, at least one task ready.

Tests: table of 15 to 20 phrasings with expected resolution (including ambiguous and unanswerable). Hand-built invalid plans (cycle, unknown tool, missing column) rejected.
Gate: a fully specified multistep question yields a valid plan. Ambiguous questions never silently pick a metric.

## M4. Fixed baseline and evaluation foundation (FR11 setup)
Depends on: M1, M3, M5 (resolver).

Build:
1. Analysis templates chosen from the resolved intent. Task order fixed per template.
2. Frozen repair policy: identical transient retries allowed, no analytical replanning.
3. Oracle (`evaluation/oracle.py`): DuckDB SQL or plain Python from the raw file. Imports nothing from tool, agent, validation or report code.
   Written in a separate AI session (see `SESSION_PROMPTS.md`).
4. Scorer: numeric tolerance, labels, tied rankings, multistep answer fields.
5. Question files: development questions (tuning) and separate evaluation questions (frozen later), each with category and difficulty.
6. Minimal end-to-end slice: one question through load, template, tools, bare-bones answer.

Tests: oracle values for 5 questions checked by hand. Scorer tested on correct, wrong, tied and partial answers.
Gate: baseline returns structured answers for all development questions. Expected answers come from the oracle alone.

## M6. Dynamic planning agent (FR04, FR06, FR08, FR15)
Depends on: M3, M5.

Build:
1. Shared state: resolved question, task graph, plan version, evidence store, failures, budgets, status.
2. LangGraph nodes: resolve, plan, select ready task, validate and execute (through M3), inspect, revise or finalize. Control graph is fixed.
3. Plan versioning: every change creates a new version and a `PlanRevision` naming the triggering evidence.
4. Reject plans with no ready task and revisions that change nothing.
5. Same tool interfaces, budgets and resolver as the baseline.
6. Concise result summaries to the inspector, not raw data frames.

Tests: a scripted stub model drives plan, execute, revise, finalize with no real LLM. One controlled case shows a result-dependent revision.
Gate: valid plan for a multistep question. At least one logged revision with a changed task and the result that caused it. No-ready-task graph rejected.

## M7. Feedback and evidence validation (FR07, FR08, FR09)
Depends on: M3, M6.

Build:
1. Failure classification (see `CONTRACTS.md`) with factual recovery context, never an expected answer.
2. Bounded recovery: retry and replan counters. Identical retries only for transient failures.
3. No-progress detection.
4. Dependent-evidence invalidation: invalid evidence invalidates dependent tasks and findings.
5. Claim validator: extract numeric claims, check against evidence, recompute where cheap.
6. Controlled-failure suite (`evaluation/recovery_suite/`), separate from benchmark questions.

Tests: each failure class triggers its documented response. A manipulated claim value is caught. An unrecoverable error stops the run.
Gate: recoverable errors resolve within limits or yield explicit partial status. Unrecoverable errors stop. Unsupported claims never appear in validated findings.

## M8. Report generation and rendering (FR09, FR10)
Depends on: M2 (charts), M7.

Build: insight builder (valid evidence to `Finding`), structured report, HTML renderer with Plotly charts, units and evidence links (all content escaped),
final re-validation before render, PDF only after HTML is stable (optional).

Tests: rendered numbers, units and chart labels match validated values. An altered number is removed or rejected. HTML in a cell value is escaped.
Gate: an end-to-end run produces a downloadable HTML report whose numbers, charts, units and evidence links agree.

## M9. Streamlit interface and follow-ups (FR12, FR13)
Depends on: M1, M6, M8.

Build: upload with file and sheet selection and visible errors; question entry with a clarifying question when needed; progress from the run trace;
report view with status, evidence inspection and HTML download; follow-ups as a new run on the same dataset hash with explicitly selected prior context
and fresh budgets. Reuse earlier evidence only if dataset hash and arguments match, and mark it as reused.

Tests: a follow-up on a changed file does not reuse earlier evidence.
Gate: a follow-up run cannot silently reuse stale evidence.

## M10. Frozen experiments and documentation
Depends on: all earlier modules.

Build: freeze step (dataset hash, questions, expected answers, prompts, model settings, budgets, code revision); evaluation runner (both variants,
3 repeats per question, scores and failures exported); recovery suite run separately; one documented reproduction command; manuscript with measured results
and limitations; per-question traces kept.
Gate: the command reproduces the scores. All failures are included. Conclusions follow the recorded results; any improvement is reported only if observed.
