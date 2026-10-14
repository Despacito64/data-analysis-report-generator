# PROJECT_SCOPE.md: objectives and boundaries

Protected file. Agents must not edit it without the owner's approval.

## Problem

Users can ask analytical questions in natural language, but answering them reliably needs several connected operations:
inspecting the dataset, resolving the intended metric and period, selecting calculations, examining intermediate results
and presenting supported conclusions. A fixed sequence answers routine questions but fails when a result calls for a different
breakdown or when a recoverable operation fails. An LLM can choose an investigation path, but fluent text does not establish
correctness. This project combines LLM planning with deterministic calculations and explicit evidence records.

## Main objective

Develop a single-agent data-analysis system that dynamically plans and executes approved analytical operations on a tabular
dataset, uses intermediate results and validation feedback to revise the plan, and generates reports with traceable numerical evidence.

## Specific objectives

1. Load CSV and XLSX data with explicit parsing and data-quality checks.
2. Produce a structured profile: columns, physical and semantic types, missing values, duplicates, date coverage, descriptive statistics.
3. Translate a natural-language objective into structured tasks with dependencies and validated tool arguments.
4. Execute predefined Pandas tools, selected statistical functions and, optionally, constrained DuckDB operations.
5. Support filtering, aggregation, ranking, period comparison, trend, segment contribution, correlation and selected anomaly checks.
6. Replan after informative results or recoverable failures within finite budgets.
7. Link each verifiable finding to recorded computations and validate reported values before rendering.
8. Generate a structured report with charts, methodology, caveats and cautiously framed recommendations.
9. Compare a fixed workflow and the dynamic agent using independent expected answers and reproducible logs.

## Included

| Component | Capability | Implementation |
| --- | --- | --- |
| Ingestion | CSV and XLSX validation and loading | Python, Pandas, openpyxl |
| Profiling | Schema, missingness, duplicates, statistics, date coverage | Deterministic Python |
| Analysis agent | Interpret objective, plan, choose tools, inspect, replan | One LLM, LangGraph |
| Analytical tools | Filters, groupings, aggregates, rankings, comparisons | Predefined Pandas functions |
| Statistical tools | Trends, contributions, correlation, selected anomaly flags | Documented deterministic methods |
| SQL option | Approved local tabular queries | DuckDB templates (optional, deferred) |
| Validation | Arguments, result schemas, invariants, numerical claims | Python rules and recomputation |
| Reports | Summary, findings, charts, methods, limitations | Structured output, HTML renderer |
| Interface | Upload, question, progress, report, follow-up | Streamlit |
| Evaluation | Fixed vs dynamic, recovery tests | Independent oracle and runner |

HTML is the required export. PDF is optional and only after the HTML path is stable. Follow-ups reuse the same dataset and explicitly
selected prior context, but start a new run with separate budgets. Recommendations are qualified suggestions; their business usefulness
is not an automated evaluation target.

## Explicit exclusions

- Multiple autonomous agents or a multi-agent swarm.
- Arbitrary Python execution or unrestricted LLM-generated SQL.
- Live database integrations, enterprise authentication, production deployment.
- General forecasting, machine-learning training, causal inference.
- Scheduled reporting, production monitoring, automated operational decisions.
- Reproducing every method or benchmark in the reference papers.
- Claims of general analytical intelligence or production readiness from one dataset and a small question set.

## Dataset

Initial focus is retail sales. Sample Superstore is the proposed benchmark. Before any development claim or experiment refers to its contents,
register the exact file, source, sheet, version, license conditions, column schema and hash (DECISIONS D-007).
Row and column counts such as 9,994 and 21 are not requirements and must not be assumed for an uninspected variant.

## Definition of dynamic planning

The LLM can add, revise, replace or cancel pending tasks based on the question, intermediate results and structured failure feedback.
Completed valid evidence stays available. Example: after seeing regional changes, the agent investigates categories in the largest
declining region instead of following a predetermined category analysis.

The LangGraph control graph stays fixed. The analytical task graph in shared state changes. Using LangGraph, routing through conditional
nodes, or retrying identical arguments is not dynamic planning. A logged revision must show a changed task or argument and the observable
result that prompted it.

## Requirements

| ID | Requirement | Acceptance evidence | Module |
| --- | --- | --- | --- |
| FR01 | Load valid CSV and XLSX files | Both formats yield expected rows and columns on fixtures | M1 |
| FR02 | Reject invalid or unusable input clearly | Unsupported extension, corrupt file, empty data, invalid sheet handled | M1 |
| FR03 | Profile quality and semantic types | Exact missing and duplicate counts with parsing diagnostics | M1 |
| FR04 | Generate a valid structured plan | Tool names, columns and dependency graph pass validation | M5, M6 |
| FR05 | Execute approved tools only | Unknown tools and unapproved operations rejected | M2, M3 |
| FR06 | Adapt pending analysis to feedback | Trace shows a result-dependent plan revision | M6 |
| FR07 | Record reproducible evidence | Each required numeric finding links to a valid evidence record | M3, M7 |
| FR08 | Bound retries and execution | Repeated failure ends with explicit partial or failed status | M6, M7 |
| FR09 | Validate reports before display | Deliberately altered numerical claim is rejected or removed | M7, M8 |
| FR10 | Produce HTML and charts | Export matches validated report values and labels | M8 |
| FR11 | Compare both system variants | Same frozen questions, data, tools, scoring policy | M4, M10 |
| FR12 | Support dataset-based follow-ups | New run keeps dataset identity, avoids stale evidence | M9 |
| FR13 | Handle ambiguous questions | Unresolved metric or period triggers clarification or a recorded assumption | M5, M9 |
| FR14 | Decline unanswerable or out-of-scope questions | Missing-column or excluded-method question gets a clear decline | M5 |
| FR15 | Store a full run trace | Plans, tool calls, evidence, failures, status saved and replayable | M0, M6 |

| ID | Non-functional requirement | Acceptance evidence |
| --- | --- | --- |
| NFR1 | Reproducibility | Documented command reproduces evaluation scores |
| NFR2 | Safety: input limits, escaped output, no execution outside the registry | Injection and oversized-file tests pass |
| NFR3 | Latency measured per question on the chosen local model | Reported, not guaranteed |

## Definition of done

A module is done when its exit gate in `MODULES.md` passes, its acceptance evidence exists as an automated test or saved artifact,
its public functions use the contracts with no untyped dicts across boundaries, failures return classified errors, and its behavior
appears in the run trace where applicable. The project is done when an end-to-end run produces a validated HTML report, the documented
command reproduces the evaluation scores, and every failure is reported.

## Cut list (if time runs short, remove in this order)

1. Optional ablation (validation feedback off).
2. PDF export.
3. DuckDB as an agent tool (the oracle still uses DuckDB).
4. Correlation and anomaly tools.
5. Streamlit follow-up polish (keep upload, question, report).

The core that must remain: M0 to M8, a command-line run, and the frozen comparison in M10.
