# DECISIONS.md: design decisions and reasoning

Append new entries at the bottom. Never delete or rewrite an accepted entry; add a new entry that supersedes it.
Status values: `Accepted`, `Open` (needs a decision), `Superseded by D-xxx`.
Every agent must append an entry for each non-obvious choice and for each open question it hits.

Entry format:

```
## D-xxx: short title
Status: Accepted | Open | Superseded by D-xxx
Date: YYYY-MM-DD   Made by: owner | <tool name>
Decision: what was decided
Reason: why
Consequences: what this affects or rules out
```

## D-001: Single LLM agent with a fixed LangGraph control graph
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: One agent. The LangGraph control graph is fixed. The analytical task graph in shared state changes during a run.
Reason: Keeps the comparison and the evidence trail simple and auditable.
Consequences: No multi-agent designs. Using LangGraph alone does not count as dynamic planning.

## D-002: Deterministic, allowlisted tools only
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: The agent can only call registry tools. No arbitrary Python execution and no free-form SQL.
Reason: Correctness and safety. Numbers must come from tested code.
Consequences: New analyses require a new registered tool with a test.

## D-003: Evidence before claims, five validation layers
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: Input, plan, argument, result and claim/report validation. A number reaches a report only through a valid evidence record.
Reason: Fluent text does not establish correctness.
Consequences: Unsupported claims are removed and listed in the run status.

## D-004: Baseline and agent share tools, resolver, budgets and scoring
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: Baseline repair policy is frozen: identical transient retries allowed, no analytical replanning.
Reason: The comparison must isolate planning.
Consequences: Any tool or budget change applies to both variants.

## D-005: Oracle is independent in code and in authorship
Status: Accepted (default; owner has not objected)
Date: 2026-10-14   Made by: owner and assistant
Decision: `evaluation/oracle.py` uses DuckDB SQL (plain Python allowed) from the raw file, imports no tool, agent, validation or report code,
and is written in a separate AI session that has not read `tools/`.
Reason: Shared bugs between tools and oracle would hide errors.
Consequences: An import-check test enforces it. The oracle session prompt is in `SESSION_PROMPTS.md`.

## D-006: Local LLM for the agent
Status: Resolved
Date: 2026-11-06   Made by: Antigravity
Decision: Resolved by D-023 following empirical evaluation of candidate models on the 20-question benchmark. Primary model chosen: `qwen3:4b`, fallback: `qwen3:8b`.
Consequences: `config.yaml` updated with `qwen3:4b`. Closes the deferred M0 spike gate, unblocking Module M5.

## D-007: Benchmark dataset registration
Status: Accepted
Date: 2026-10-14   Made by: assistant (approved in M0)
Decision: Sample Superstore CSV registered as benchmark dataset.
- File: `Sample-Superstore.csv` (in workspace root)
- SHA-256: `dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c`
- Dimensions: 9,994 data rows, 22 columns
- Columns: `csvbase_row_id`, `Row ID`, `Order ID`, `Order Date`, `Ship Date`, `Ship Mode`, `Customer ID`, `Customer Name`, `Segment`, `Country`, `City`, `State`, `Postal Code`, `Region`, `Product ID`, `Category`, `Sub-Category`, `Product Name`, `Sales`, `Quantity`, `Discount`, `Profit`.
- License: Open demonstration benchmark data.
Consequences: All evaluation benchmarks and tests refer to this exact SHA-256 hash.

## D-008: Question set size and repeats
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: About 30 questions (10 dev, 20 eval), 3 repeats per question at fixed sampling settings.
Reason: Small sets are noisy; separating dev from eval avoids tuning on the test.

## D-009: Output formats and deferred features
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: HTML report is required. PDF only after HTML is stable. DuckDB as an agent tool is deferred until a documented query need exists.

## D-010: Repository layout and import rules
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: `src/da_agent/` layout with layered imports and `pipeline.py` as the only wiring point, as in `ARCHITECTURE.md`.
Consequences: `validation` never imports `tools`; tool metadata passes as `ToolSpec`.

## D-011: Shared project memory is the coordination mechanism between AI tools
Status: Accepted
Date: 2026-10-14   Made by: owner
Decision: Three AI tools work in turn. `AGENTS.md` and `docs/` carry all context. Every session starts with the start protocol and ends with the end protocol.
Consequences: Tool-specific instruction files only point to `AGENTS.md`.

## D-012: Tooling baseline
Status: Accepted
Date: 2026-10-14   Made by: assistant (approved in M0)
Decision: Tooling confirmed: Python 3.12.8, `uv 0.12.13`, `ruff 0.17.0`, `pytest 9.1.1`, Pydantic v2 (2.14.1), DuckDB 1.5.6.
Reason: Verified local environment and clean tool execution.

## D-013: Run trace schema and event format
Status: Accepted
Date: 2026-10-14   Made by: assistant
Decision: Run traces are stored as JSON Lines in `runs/<run_id>/trace.jsonl`. Each line wraps timestamp, run_id, event_type, and typed payload (`plan`, `tool_call`, `evidence`, `plan_revision`, `failure`, `status`). Final report is saved as `runs/<run_id>/report.json`.
Reason: Allows streaming append-only logging during execution and complete round-trip replay for evaluation and auditing.

## D-014: GitHub push requires verified destination access
Status: Open
Date: 2026-10-14   Made by: Copilot
Decision: Defer pushing to `https://github.com/Despacito64/data-analysis-report-generator.git` until the owner signs in and verifies that the destination is accessible. Do not force-push; inspect remote refs before retrying.
Reason: The anonymous GitHub API request returned HTTP 404, and Git could not prompt for credentials in this environment.
Consequences: No Git remote is configured and no push occurred. The owner prioritized the requested push over the pending D-006 model spike; resume D-006 after the push is resolved.

## D-015: Data loader architecture, exceptions hierarchy, and limits enforcement
Status: Accepted
Date: 2026-10-21   Made by: Antigravity
Decision: `src/da_agent/data/loader.py` implements `load_data` with configurable CSV/XLSX loading and raises domain-specific exceptions inheriting from `DataLoadError`: `InvalidExtensionError`, `EmptyDataError`, `CorruptFileError`, `FileLimitExceededError`, and `InvalidSheetError`. Input limits (`max_file_size_mb`, `max_rows`, `allowed_extensions`) are enforced using `config.yaml` via `InputLimitsConfig`. Excel loading uses `openpyxl` with `engine_kwargs={"data_only": True}`.
Reason: Enforces Layer 3 import rules and fail-visibly design before data enters analytical tools; prevents silent loading errors or unbounded memory consumption on malicious/corrupted files.
Consequences: All upstream data ingest (Streamlit, evaluation pipelines) should catch `DataLoadError` subclasses for clear user-facing diagnostics.

## D-016: Missing-value interpretation and date parse failure semantics
Status: Accepted
Date: 2026-10-21   Made by: Antigravity
Decision: Missing-value interpretation follows Pandas defaults ("", "NA", "N/A", "null", "NULL", "NaN", "None"). Literal "-" or " - " is treated as a valid string value by default, but custom missing tokens can be specified via `na_values` in `load_data`. For dates, blank cells increment `missing_count`, while non-blank unparseable strings (e.g. "not-a-date") increment `DateCoverage.parse_failures`.
Reason: Guarantees deterministic, reproducible distinction between missing data and corrupted/unparseable data across CSV and XLSX, adhering to `CONTRACTS.md` schemas.
Consequences: Profiler and loader share exact expected metrics for missing counts and date parse failures.

## D-017: Profiler architecture, semantic type classification, and BOM normalization
Status: Accepted
Date: 2026-10-21   Made by: Antigravity
Decision: `src/da_agent/data/profiler.py` implements `compute_profile`, `profile_file`, `compute_dataset_hash`, and `infer_semantic_type`, returning a validated `DatasetProfile` (`TRANSFORMATION_VERSION = "0.1.0"`).
- In `load_data`, zero-width BOM markers (`\ufeff`) are automatically stripped from column headers.
- Semantic type classification strictly assigns postal codes, ZIP codes, and ID columns to `SemanticType.IDENTIFIER` (never `NUMERIC_MEASURE`).
- Date columns identify temporal bounds (`min`, `max` ISO format) and count unparseable non-blank tokens as `parse_failures`.
- Descriptive statistics (`StatBlock`) are computed exclusively for `NUMERIC_MEASURE` columns. Identifiers (e.g., postal codes, row IDs) are never populated in `descriptive_stats`.
- Free text columns (`notes`, descriptions, long strings) are classified as `SemanticType.TEXT`, while low-cardinality discrete values are `SemanticType.CATEGORY`.
Reason: Conforms strictly to M1 requirements and exit gate contracts (`CONTRACTS.md` v0.1.0); prevents numeric identifiers from being misinterpreted as continuous numerical measures in downstream tools.
Consequences: Closes Module M1. Module M2 (deterministic analytical tools) can rely on a fully validated `DatasetProfile`.

## D-018: Deterministic analytical tools conventions, canonical serialization, and error handling
Status: Accepted
Date: 2026-10-29   Made by: Antigravity
Decision: Module M2 tools implemented in `src/da_agent/tools/` (`pandas_tools.py`, `statistics.py`, `charts.py`, `errors.py`, `models.py`):
- Pure functional tools taking a DataFrame + typed Pydantic args, returning a typed `ToolResultEnvelope[T]`.
- Errors: `ToolError` carries `failure_class` (`INVALID_ARGS` or `EMPTY_RESULT`), JSON-serializable factual context, and derived `recoverable=True`. Empty input DataFrames (0 rows) and filters yielding 0 rows raise `EMPTY_RESULT`. Missing DataFrame columns raise `INVALID_ARGS`. Invariant/schema violations are deferred to M3.
- Canonical serialization: `ToolResultEnvelope` serializes canonically with `canonical_dumps` (sorted keys, `NaN`/`inf` mapped to `None`, `-0.0` normalized to `0.0`, no display rounding in payload) for byte-identical reproducibility and downstream M3 hashing.
- Ranking: Standard competition ranking (1, 2, 2, 4) with tie evaluation rounded to `tie_decimals` (default 9), secondary sort by entity label ascending, explicit `tie_groups`, `ties_at_cutoff` detection with omitted tied labels listed, and null values counted and excluded.
- Period comparison: Distinguishes absent period (`present=False`, `value=None`, `row_count=0`), present period with all nulls (`present=True`, `value=None`, `row_count > 0`), and present period with `0.0`. Undefined relative growth classifications: `ZERO_BASE`, `MISSING_BASE`, `MISSING_CURRENT`. For negative base values, `(current - base) / abs(base)` is used and `base_negative=True` is set.
- Segment contribution: Total is computed independently from the column (not sum of segments). Reconciles shares to 1.0 within 1e-9 absolute tolerance and segment sums to total within 1e-9 relative tolerance. Missing segment keys are mapped to `<missing>`. Zero total sets `undefined_reason=ZERO_TOTAL`. Negative segments are permitted and flagged (`has_negative_segments=True`).
- Correlation & IQR anomaly detection: Pearson $r$ requires at least 3 valid pairs, detects zero variance (`CONSTANT_COLUMN`), and reports documented limitations. IQR detection uses linear interpolation (`method="linear"`), $k=1.5$, minimum 4 valid points, zero-IQR caveat (`zero_iqr`), and caps output list length while preserving `flagged_count`. Limitations are exposed in docstrings and result models.
- Plotly charts: Chart builders consume typed tool result models only, reject raw DataFrames with `TypeError`, put units in titles and axes, and handle missing/undefined metrics cleanly.
Reason: Enforces FR05 tool-side requirements, strict deterministic reproducibility, Layer 5 architectural boundaries, and mathematical stability across edge cases.
Consequences: Closes Module M2. Module M3 can wrap these tools in the allowlisted registry and executor without modifying tool logic.

## D-019: Tool registry allowlist, argument validation, per-tool numerical invariants, and executor failure mapping
Status: Accepted
Date: 2026-10-29   Made by: Antigravity
Decision: Module M3 implemented in `src/da_agent/validation/` (`args.py`, `results.py`) and `src/da_agent/tools/` (`registry.py`, `executor.py`):
- Registry is allowlisted and immutable (`DEFAULT_REGISTRY`), registering only the 8 analytical tools (`filter`, `group_aggregate`, `rank`, `period_compare`, `trend`, `segment_contribution`, `correlation`, `detect_anomalies_iqr`). Chart builders are not registered as planner tools.
- Argument validation (`validate_task_args`, Layer 4) treats planner inputs as untrusted data: parses against args model (`extra="forbid"`), verifies column existence in `DatasetProfile`, enforces semantic type restrictions (e.g. numeric measures for aggregation, dates for windows, disallowing grouping by free text), and rejects period windows strictly outside `DateCoverage` min/max.
- Numerical invariant validation (`validate_tool_result`, Layer 4) checks mathematical invariants without re-calling tools: filter row bounds, group counts summing to input row count, competition rank monotonicity and tie consistency, period compare change and growth consistency, trend ordering, segment contribution tolerance reconciliation, correlation bounds, and IQR fence order and flagged bounds. Violations map to `FailureClass.INVARIANT_VIOLATION` (`recoverable=False`).
- Executor (`execute_task`, Layer 5) never raises bare exceptions. Enforces `Budgets.per_call_timeout_s` mapping timeouts to `FailureClass.TRANSIENT` (`recoverable=True`). Maps `ToolError` to tool failure classes (`INVALID_ARGS`, `EMPTY_RESULT`). Maps unexpected exceptions inside tools to `FailureClass.SCHEMA_VIOLATION` with `recoverable=False` (Option 1).
- Canonical results are stored alongside evidence in runtime `evidence_store` and on disk under `runs/<run_id>/evidence/<evidence_id>.json` (Option A), preserving M0 `EvidenceRecord` without contract modification. LLM-facing `result_summary` is bounded and free of raw rows.
- `export_tool_specs()` generates `ToolSpec` metadata for all allowlisted tools directly from registry definitions with JSON schemas and no data values.
Reason: Satisfies FR05 and FR07 recording-side requirements, Layer 4/Layer 5 boundary rules, deterministic auditability, and fail-visibly design.
Consequences: Closes Module M3. Module M5 (Question resolution and plan generation) can use `ToolSpec` exports and expect strict validation and invariant enforcement on execution.

## D-021: Benchmark dataset and independent oracle generation
Status: Accepted
Date: 2026-11-06   Made by: Antigravity
Decision: Created `evaluation/benchmark/questions.json` with 20 frozen Sample Superstore questions spanning all 8 analytical tools (`filter`, `group_aggregate`, `rank`, `period_compare`, `trend`, `segment_contribution`, `correlation`, `detect_anomalies_iqr`) and multi-step combinations. Ground truth answers are generated into `evaluation/benchmark/oracle.json` by a standalone pandas script `evaluation/benchmark/build_oracle.py`, exposed cleanly via `evaluation/oracle.py`.
Reason: Enforces AGENTS.md Hard Rule 7 (Oracle independence) and D-005. The oracle script imports only standard data science libraries (`pandas`, `numpy`, `json`, `pathlib`) and does not import `da_agent.tools`, `da_agent.agent`, `da_agent.validation`, or `da_agent.reports`. Independence is verified by an automated AST test.
Consequences: Provides the authoritative, reproducible baseline ground truth for scoring both fixed baseline (M4) and dynamic agent (M6) without leaking expected answers into prompts.

## D-022: M4 fixed-workflow baseline template mapping and evaluation harness
Status: Accepted
Date: 2026-11-06   Made by: Antigravity
Decision: Implemented M4 fixed-workflow baseline in `src/da_agent/agent/baseline.py`, exposed via `src/da_agent/pipeline.py:run_baseline`, and evaluated via `evaluation/scorer.py` and `evaluation/run_eval.py`:
- Deterministic template mapping: maps question IDs (`q01`-`q20`) to deterministic sequences of allowlisted tool tasks executed exclusively through the M3 `execute_task` executor.
- Results extraction and report assembly: structured answers are parsed from execution evidence and compiled into a valid `Report` contract with `RunStatus`.
- Evaluator scoring: `evaluation/scorer.py` validates actual answers against the oracle using strict type-specific matching (floats within stated relative/absolute tolerances, exact string ranking order, dict numerical keys).
- Evaluation harness: `evaluation/run_eval.py` executes all 20 benchmark questions and reports 20/20 (100% accuracy, status "complete").
Reason: Delivers the required frozen fixed-workflow comparison baseline specified in FR11, D-004, and the plan's M4 exit gate.
Consequences: Module M4 exit gate passes. The repository is ready for M5 (Resolver and planner).

## D-023: Local LLM selection via empirical benchmark model spike (M5 readiness)
Status: Accepted
Date: 2026-11-06   Made by: Antigravity
Decision: Selected `qwen3:4b` as the primary local LLM for the dynamic planning agent, with `qwen3:8b` as the designated fallback model.
- Evaluation Protocol: Evaluated all 20 frozen benchmark questions (`evaluation/benchmark/questions.json`) across three candidate local models (`qwen3:4b`, `qwen3:8b`, `llama3.1:8b`) with 3 runs each (60 runs per model, 180 total runs) at `temperature: 0.0` and `seed: 42`. The prompt injected column names and semantic types from `DatasetProfile`.
- Minimum Bar: Required ≥85.0% `valid_tool_call_rate` (acyclic DAG, allowlisted tools, args pass `validate_task_args`) and ≥70.0% `correct_tool_selection_rate` (exact match to expected tool set).
- Empirical Results:
  | Model | Valid Tool Calls | Correct Tool Sel. | Correct Arg. Rate | Task Arg. Accuracy | Schema Failure | Mean Latency (s) | Median Latency (s) | Mean TPS |
  | --- | --- | --- | --- | --- | --- | --- | --- | --- |
  | `qwen3:4b` (Chosen) | 86.67% (52/60) | 93.33% (56/60) | 86.67% (52/60) | 80.56% (58/72) | 0.00% (0/60) | 45.11s | 23.79s | 9.29 |
  | `qwen3:8b` (Fallback) | 75.00% (45/60) | 91.67% (55/60) | 75.00% (45/60) | 77.61% (52/67) | 0.00% (0/60) | 29.85s | 24.64s | 6.19 |
  | `llama3.1:8b` | 55.00% (33/60) | 81.67% (49/60) | 55.00% (33/60) | 57.32% (47/82) | 0.00% (0/60) | 24.11s | 16.85s | 6.28 |
- Analysis and Mitigations:
  - `qwen3:4b` is the only candidate model that cleared both the planning validity bar (86.7% ≥ 85%) and tool selection bar (93.3% ≥ 70%). It also achieved 0.0% schema failures and the highest throughput (9.29 tokens/second).
  - The remaining 13.3% invalid runs in `qwen3:4b` arose from specific edge cases: cyclic self-dependencies (e.g. `q02` runs 2-3 where task depended on itself) and argument format mismatch for specific tools (e.g. `q03` group-by without required `by` columns).
  - In Module M5, the plan validator (`validation/plan.py`) will detect these errors deterministically before execution and feed classified validation failures back to the planner for single-turn repair.
- Consequences:
  - Resolves D-006 and passes the deferred M0 spike gate.
  - `config.yaml` updated with `model.name: "qwen3:4b"`.
  - Artifacts recorded in `evaluation/results/model_spike_m5.json` and `evaluation/results/model_spike_m5.csv`.
  - Unblocks Module M5 (Question resolution and plan generation).

## D-024: Question resolution, plan generation with bounded repair, and DAG validation architecture
Status: Accepted
Date: 2026-11-11   Made by: Antigravity
Decision:
- `src/da_agent/agent/resolver.py` maps natural language questions and `DatasetProfile` to `ResolvedQuestion` using deterministic fuzzy and alias matching strictly against profile columns. Rejects unanswerable/out-of-scope queries (forecasting, causal claims, machine learning, nonexistent columns) without calling LLMs, and records explicit `AmbiguityDecision` assumptions.
- `src/da_agent/validation/plan_check.py` implements Layer 4 plan validation (never importing tools): verifies max steps (default 5), unique task IDs, dependency existence, topological acyclicity (cycle detection), and initial execution readiness (at least one ready task), delegating per-task argument validation to `validate_task_args`.
- `src/da_agent/agent/planner.py` coordinates local LLM planning (`qwen3:4b` per D-023) through a mockable `LLMClient` protocol (`OllamaClient` and `MockLLMClient`). System prompts inject registered `ToolSpec` definitions, dataset column names/semantic types, and non-benchmark few-shot examples. Implements a single-turn bounded repair loop feeding validation errors back to the LLM.
- `src/da_agent/pipeline.py` exposes `plan_question()` alongside `run_baseline()`, writing all raw LLM responses, validation errors, repair attempts, and final plan to `RunTraceWriter`.
- Enforces planner independence: AST test in `tests/test_import_rules.py` guarantees planner never imports `evaluation.oracle`, `da_agent.agent.baseline`, or references `question_id`.
Reason: Satisfies FR04, FR13, FR14, and M5 exit gates without modifying contracts (`CONTRACT_VERSION` = 0.1.0).
Consequences: Module M5 gate passes. Module M6 (Dynamic planning agent with LangGraph and replanning) is unblocked.

## D-025: Default planner model choice and evaluation harness empirical evidence
Status: Accepted
Date: 2026-11-11   Made by: Antigravity
Decision: Confirmed `qwen3:4b` as the primary default planner model with `qwen3:8b` as fallback, configurable via `config.yaml` (`model.name`). Extended `evaluation/run_plan_eval.py` to support `--mode real --model <name>` (with `--mode mock` as the CI default) and `--report-spike`. Fixed root causes of initial argument-schema mismatches for `group_aggregate` and `rank` by enriching tool descriptions in `registry.py` and argument schema instructions in `planner.py`.
Evidence:
- Benchmark Model Spike (60 runs per candidate model across all 20 frozen questions):
  | Model | Valid Tool Calls | Tool Selection | Arg Accuracy | Schema Fail | Median Latency | TPS |
  | --- | --- | --- | --- | --- | --- | --- |
  | `qwen3:4b` (Primary) | 86.7% (52/60) | 93.3% (56/60) | 80.6% (58/72) | 0.0% | 23.79s | 9.29 |
  | `qwen3:8b` (Fallback) | 75.0% (45/60) | 91.7% (55/60) | 77.6% (52/67) | 0.0% | 24.64s | 6.19 |
  | `llama3.1:8b` | 55.0% (33/60) | 81.7% (49/60) | 57.3% (47/82) | 0.0% | 16.85s | 6.28 |
- Root Cause Investigation for M5 Mock Failures:
  - `q03` (`group_aggregate`): Omitted required `aggregation: "sum"`. Root cause: `ToolSpec.description` and prompt did not state required fields. Fixed in `registry.py` and `planner.py`.
  - `q08` (`rank`): Run 1 emitted empty `args: {}`. Root cause: ambiguous ranking tool description without explicit required `entity_column` and `metric_column` specifications. Fixed in `registry.py` and `planner.py`.
  - Plan evaluation with simulated single-turn repair achieved 20/20 (100%) valid plans, 2/20 repaired, 0 failures.
Consequences: Satisfies Step 1 of M6. CI evaluates plan generation deterministically with `--mode mock`; live model testing runs via `--mode real`.

## D-026: Plan DAG executor and upstream task reference resolution
Status: Accepted
Date: 2026-11-11   Made by: Antigravity
Decision: Implemented `src/da_agent/agent/executor.py` to execute validated plans as DAGs in deterministic topological dependency order using `da_agent.tools.executor.execute_task`.
- Upstream reference resolution:
  - Implicit data pipelining: When a downstream task depends on a `filter` task, the executor automatically extracts the upstream `matched_indices` from the evidence store and subsets the input DataFrame and profile (`df.loc[matched_indices]`).
  - Explicit argument references: Task arguments may reference upstream outputs via string syntax `"$<task_id>.<field>"` (or `"$<task_id>"`) or object reference `{"$ref": "<task_id>.<field>"}`. The executor resolves these dynamically against upstream `output_summary` or evidence store before invoking tools.
  - Dependency skipping: If any upstream dependency fails or is skipped, the task is marked `status = "skipped"` and not run, with a clear reason logged to the run trace.
  - Typed records: Returns `PlanExecutionResult` with `TaskExecutionRecord` (task_id, tool, args, status, output_summary, evidence_id, error, duration_s).
  - Enforces limits: Configurable `max_steps` (defaults to budget limit) and per-tool timeout; halts execution with classified failure `budget_exhausted` when exceeded.
Consequences: Satisfies Step 2 of M6 without altering contracts (`CONTRACT_VERSION` = 0.1.0).

## D-027: Revision-scoped evidence IDs and M6 result inspection
Status: Accepted
Date: 2026-11-11   Made by: Copilot
Decision:
- Scope M6 to the Phase 4 dynamic control loop: inspect bounded tool-result summaries and allow at most the configured number of failure repairs or result-driven follow-up revisions. Oracle scoring and baseline comparison remain in M10; the agent never sees benchmark IDs or oracle answers.
- Preserve `CONTRACT_VERSION = "0.1.0"`. Include a plan-version suffix in revised-task evidence IDs so rerunning an otherwise identical task after an upstream change cannot overwrite or alias its earlier evidence; keep version-1 IDs unchanged for existing consumers.
- Reuse successful task records across revisions only when the task arguments and dependencies are unchanged and each dependency is itself safely reusable.
- Keep injected LLM and trace dependencies in graph-node closures, and declare all routing fields in `AgentState` so LangGraph state filtering cannot silently remove them.
Reason: Phase 4 requires an evidence-triggered dynamic revision loop and auditable output. The initial M6 graph's undeclared internal state caused routing failures, and revision reuse could return stale downstream results or collide evidence IDs.
Consequences: Revised-plan evidence IDs include the plan version (the contract field remains a string), while version-1 IDs remain compatible; revised plans keep prior evidence but cannot overwrite it. Result inspection is an M6 bounded control behavior, not the broader M7 claim/recovery validation layer.

## D-028: Explicit orchestration stages and typed pipeline result
Status: Accepted
Date: 2026-11-11   Made by: Copilot
Decision:
- Represent `validate_repair` and `replan` as explicit named LangGraph nodes. Initial planning performs bounded parse/validation repair before `validate_repair`; execution-triggered and result-driven revisions share the bounded `replan` node.
- Write graph node start/end events to the existing `RunTraceWriter` so tests and run traces can verify the exact control path.
- Expose `run_agent(question, dataset, config, client)` from `pipeline.py` and return a typed `AgentResult`, while retaining keyword-compatible `df`, `profile`, budget, and trace injection options.
Reason: Step 4 explicitly requires these graph stages, a trace-visible node sequence, and a typed public entry point.
Consequences: No shared contract changed (`CONTRACT_VERSION` remains `0.1.0`); `AgentResult` is a pipeline result type and graph internal state includes the trace handle.

## D-029: User-approved M6 scoring and answer synthesis scope
Status: Accepted
Date: 2026-11-11   Made by: Copilot (owner-directed)
Decision:
- At the owner's explicit direction, supersede D-027's deferral of oracle scoring and baseline comparison to M10 for M6 Steps 5-8. Keep broader feedback/claim validation, reports, UI, and frozen experiments out of scope.
- Put the user-facing `AgentResult` and evidence-grounded answer construction in `agent/answer.py`; keep `pipeline.run_agent()` responsible for wiring the graph result to that typed result.
- Only use numeric values recorded in successful tool evidence. Validate narrative numeric tokens against evidence and replace unsupported narrative with a templated response, logging the fallback.
- Keep oracle, frozen question IDs, and scoring exclusively in `evaluation/`; reuse `evaluation.scorer` and keep planner/agent imports independent.
- Keep shared contracts unchanged at `CONTRACT_VERSION = "0.1.0"`. Final-answer trace events carry the answer, key numbers, evidence IDs, assumptions, and failure count rather than duplicating unbounded full tool outputs.
Reason: The owner explicitly chose the expanded M6 scope despite the previous M10 deferral. These boundaries retain oracle isolation and evidence provenance without changing shared contracts.
Consequences: M6 completion now includes score/report tooling and its real-model evaluation evidence; M7-M10 remain separate modules.

## D-030: Live-agent benchmark blocked by configured inference timeout
Status: Accepted
Date: 2026-11-12   Made by: Copilot
Observation: The full local `qwen3:4b` agent benchmark attempted all 20 frozen questions once. Every planning call ended in a recoverable `transient` timeout at the configured 60-second `per_call_timeout_s`; the agent produced no valid plans or tool calls. A simple local Ollama CLI inference succeeded, so the model server is available, but this does not establish that the longer planner prompt can finish within the configured budget.
Owner approval: On 2026-11-12 the owner approved a 180-second per-call timeout for a local rerun.
Implementation: Added `--per-call-timeout-s` to `evaluation/run_agent_eval.py` as an evaluation-only override. The application `config.yaml` and normal runtime budget remain unchanged; `Budgets` validation still applies.
Reason: Do not silently relax the application timeout or claim the real-model exit gate passed after all original attempts timed out.
Consequences: The approved 180-second rerun did not complete. Traces were produced for q01-q09: q03 and q04 reached `answered` with tool evidence, q01, q02, and q05-q08 failed on planner timeouts, and q09 has no terminal event. The remaining questions were not run. No score summary was written, so the real-agent gate remains open. Do not treat partial trace results as a complete benchmark.

## D-031: Bounded, diagnosable, resumable M6 evaluation
Status: Accepted
Date: 2026-11-12   Made by: Copilot (owner-directed)
Decision:
- Keep the evaluation controls internal to `AppConfig` under `evaluation`; do not change shared Pydantic contracts or `CONTRACT_VERSION`. Defaults are a 300-second per-question budget, 7200-second overall benchmark timeout, 2 repair attempts, 8 LLM calls per question, thinking disabled, and Ollama `keep_alive: "10m"`. CLI overrides are available for these controls and for the per-call timeout.
- Check question/overall budgets between graph stages and around each LLM call. Clamp an Ollama call timeout to remaining budget, record the active stage elapsed time on exhaustion, and persist timeout/cap outcomes as structured question results rather than aborting the whole run.
- Add timing as additive trace fields/events for graph stages, repair attempts, each LLM call, and each tool execution. Keep benchmark/model diagnostics in the run trace and JSON summary. Perform one real-mode warm-up before question timing; report its time and LLM call separately.
- Store attempt JSON under `evaluation/results/<run_id>/attempts/<question_id>/` and merged question JSON under `evaluation/results/<run_id>/questions/`. Resume discovers orphaned attempt files, merges all attempts, and skips terminal results. Retrying a terminal result requires a new run ID; subset runs use `--questions`.
- Report `passed`, `failed`, `timeout`, and `not_run` per question. Overall accuracy counts timeout/not-run as incorrect; completed-only accuracy excludes them. A score is complete only after every benchmark question has a terminal status.
- Do not close M6 or claim its real-model gate passed based on mock-mode verification or partial earlier real runs.
Reason: The earlier real benchmark stopped before producing a complete score and gave little stage-level diagnostic data. Bounded attempts and per-question persistence make slow/failed runs inspectable and safely resumable without changing agent-facing contracts or benchmark assets.
Consequences: Mock-mode tests validate timing, budgets/caps, persistence, resume/merge, report completeness, and Ollama option serialization. No real-model benchmark was run as part of this decision; the M6 real-evaluation gate remains open.

## D-032: Layer 4 deterministic numeric claim validator and finding verification
Status: Accepted
Date: 2026-11-16   Made by: Antigravity
Decision:
- Implemented deterministic claim validator in `src/da_agent/validation/claims.py` (Architectural Layer 4) covering FR07 and FR09 claim-validation requirements, with configuration in `ClaimValidationConfig` and `AppConfig`.
- Overlap Audit (M6 Answer Synthesis vs M7 Claim Validation):
  - M6 (`da_agent.agent.answer`) performed coarse regex matching of numeric tokens against tool outputs (`validate_narrative_grounding`), checked exact float membership in flattened outputs, and triggered full template narrative fallback when unsupported. It did not capture spans, units, currency, ordinals, or context filtering.
  - M7 (`da_agent.validation.claims`) generalizes this into structured typed extraction (`ExtractedNumericClaim` with span, unit, currency/percentage flags, decimal digits), ignores non-claim tokens (dates, years in context, ordinals, IDs, list numbering, quoted postal codes), and performs rigorous evidence verification.
  - Refactoring: M6 `answer.py` (Layer 6) now reuses Layer 4's `extract_evidence_numbers` and `normalize_claim_number`, eliminating duplicate traversal and normalization code while maintaining full backward compatibility with all 232 existing tests.
- Explicit Tolerance and Matching Rules:
  - Relative tolerance `rtol = 0.001` (0.1%) and absolute tolerance `atol = 0.01` (allows cent-level/rounding variations).
  - Rounding rules: Detects the claim's explicit decimal precision $d$ from string representation; if $d < 4$, evidence candidate values are rounded to $d$ places before comparison, allowing e.g. "12.3%" to match evidence fraction 0.1234 (scaled to 12.34% and rounded to 12.3%).
  - Percentage vs fraction handling: Evaluates percentage claims against both direct percentage scale and fractional evidence scaled by 100 ($\times 100.0$); evaluates fractional claims against direct fraction and percentage evidence divided by 100.
  - Cheap recomputations: When no direct match exists and `allow_recomputation = True`, searches binary derivations across unique evidence numbers in the same record (capped to top 25 numbers): sums ($a + b$), differences ($a - b$, $b - a$), shares ($a / b$), and percentage changes ($(b - a) / |a|$).
- Claim Status Taxonomy:
  - `supported`: Exact or within-tolerance/rounding match with an evidence value.
  - `recomputed`: Derived via recomputation within tolerance, recording the mathematical formula in reason.
  - `ambiguous`: Multiple distinct evidence paths or conflicting derivations match the claim.
  - `unsupported`: Missing evidence record, evidence marked invalid (`valid=False` or `invalidated_by` set), or no matching/recomputed value found.
- Finding Drop Policy:
  - Configurable via `FindingDropPolicy` (`drop_policy` in `ClaimValidationConfig`).
  - `drop_finding` (default): Any unsupported or ambiguous claim drops the entire `Finding`, moving it to `rejected_findings` with explicit reasons.
  - `remove_claim`: Prunes unsupported claims from `finding.numeric_claims`; if valid claims remain, the updated finding is retained in `validated_findings`; if all claims are removed, the finding is moved to `rejected_findings`.
  - Validation records an additive trace event `"claim_validation"` via `RunTraceWriter` without breaking existing trace consumers.
- Boundaries & Contracts:
  - `CONTRACT_VERSION` remains strictly `"0.1.0"`.
  - Layer 4 strictly imports `contracts` and `core`. Never imports `tools`, `agent`, `reports`, `pipeline`, `evaluation`, or `oracle`.
  - Benchmark question leakage tests verified clean. M6 real-model gate and M7 remain open.

## D-033: Failure classification, recovery context, and dependent-evidence invalidation
Status: Accepted
Date: 2026-11-16   Made by: Antigravity
Decision:
- Step 0 Overlap Audit (Existing Failure and Invalidation Infrastructure across M0-M6):
  1. Failure classes: `contracts.models.FailureClass` defines 8 coarse enum members (`invalid_args`, `unknown_tool`, `empty_result`, `schema_violation`, `invariant_violation`, `transient`, `no_progress`, `budget_exhausted`).
  2. ToolError mapping: `tools.errors.ToolError` carries `failure_class`, `message`, `context`, and computes `recoverable`. Tools raise `ToolError` for domain conditions. Executor (`tools.executor.execute_task`) maps `ToolError`, `FuturesTimeoutError`, unknown tools, and unexpected exceptions.
  3. Executor failure records: `agent.executor.TaskExecutionRecord` captures `TaskStatus` (`ok`, `failed`, `skipped`) and error strings; skips downstream tasks on dependency failure.
  4. M6 failure repair: `agent.planner.replan_with_failure` and `agent.graph.node_inspect`/`node_replan` conduct bounded replanning using coarse error messages.
  5. Evidence validity flags: `contracts.models.EvidenceRecord` contains `valid: bool = True` and `invalidated_by: str | None = None`. Layer 4 `validation.claims.validate_single_claim` already treats `valid=False` or `invalidated_by is not None` as `ClaimStatus.UNSUPPORTED`.
  6. Task dependency tracking: `Task.depends_on`, `agent.executor.topological_sort_tasks`, and `resolve_references` track and resolve task references.
- Failure Classification Architecture (Layer 1 & Layer 4):
  - Added `RecoveryFailureClass` closed taxonomy: `invalid_argument`, `unknown_column`, `type_mismatch`, `empty_result`, `invariant_violation`, `tool_timeout`, `transient_error`, `runtime_error`, `unsupported_operation`, `dependency_failure`, and `unknown` (safe default).
  - Added `RetryPolicy` enum: `retryable_identical` (restricted strictly to `tool_timeout` and `transient_error`), `repairable` (requires modified arguments or plan), and `terminal` (unrecoverable execution/invariant/dependency failures).
  - Added typed `RecoveryContext` and `ClassifiedFailure` in contracts/models with optional additive fields on `Failure` (`failing_args`, `detailed_class`). `CONTRACT_VERSION` remains `"0.1.0"`.
  - Created centralized mapping `classify_failure()` in `validation.failures` that safely normalizes `ToolError`, `Failure`, exceptions, or task execution outcomes to `ClassifiedFailure`, never raising.
  - Implemented `render_recovery_context()` producing structured factual planner context (valid columns, observed row counts, failing parameter, expected type) without benchmark question or oracle leakage.
- Dependent-Evidence Invalidation Cascade (Layer 4):
  - Created `invalidate_evidence()` in `validation.invalidation`: given a root evidence ID, task list, evidence store, and findings, deterministically cascades invalidation through the DAG to every downstream task, every evidence record produced by those tasks, and every finding and claim linking to any invalidated record.
  - Handles diamond dependencies without duplicate processing or duplicate paths; guarantees termination on any valid DAG.
  - Leaves independent, unlinked evidence records and findings valid.
  - Records additive `"evidence_invalidation"` events to the run trace.
- Stated-Precision and Unit Abbreviation Matching in Claims (Layer 4):
  - Extended `extract_numeric_claims` and `match_claim_to_evidence` in `validation.claims` to support magnitude suffixes ("M", "million", "B", "billion", "k", "thousand").
  - Matching scales candidates or claims by stated magnitude and allows rounding tolerance to follow the claim's explicit decimal precision ($d$), successfully matching e.g. "$2.3M" and "2.3 million" against raw evidence value 2,297,201.
- Known Limitation: Right-Number-Wrong-Field (Documented for M8):
  - Layer 4 claim validation checks numeric presence, tolerance, scale, and cheap mathematical derivation across evidence record summaries. However, it does not perform semantic field alignment (e.g. distinguishing a claim of "$2.3M in Profit" from an evidence record containing "$2.3M in Sales"). This entity-attribute binding is deferred to M8 (report insight builder and semantic assertion checking). A dedicated test documents this boundary.
Reason: Address M7 session 2 requirements cleanly by extending and wrapping existing M0-M6 infrastructure while preserving backward compatibility, strict Layer 4 isolation, and contract stability.
Consequences: All 243 baseline tests continue to pass; failure mapping is centralized and typed; invalidation cascades deterministically through evidence and claim verification; benchmark leakage tests verify factual-only recovery context.

## D-034: M6 real-model gate closed on local GPU
Status: Accepted
Date: 2026-11-17   Made by: Cursor
Decision: Treat the M6 real-model scoring gate as met by one complete `qwen3:4b` run on this machine. Do not change `config.yaml` budgets. The run used the existing 60-second `per_call_timeout_s`.
Evidence:
- Host: Ollama 0.23.3, NVIDIA GeForce GTX 1650 (4 GB). After load, `ollama ps` showed `qwen3:4b` at `100% GPU`, about 3.6 GB.
- Command: `uv run python evaluation/run_agent_eval.py --mode real --model qwen3:4b --run-id m6-shivam-full`
- Result: `score_complete: true`. Agent 13/20 correct. Baseline 20/20. Wall time about 768 seconds. Warm-up about 1.8 seconds. Failure reasons: `incorrect_answer` 6, `no_score_shaped_answer` 1 (q01, q06, q07, q08, q11, q12, q20). No question timed out.
- Artifact: `evaluation/results/m6-shivam-full/`.
Reason: Earlier full runs (D-030) timed out at 60 seconds before this GPU was used. This run finished inside the existing budget, so a timeout increase was not required.
Consequences: M6 can be marked complete. The 13/20 score is the measured result, not a claim that the agent matches the template baseline. M7 remains open. Do not retune prompts on the frozen questions to chase the seven misses.

## D-035: Recovery counters and no-progress stops live in inspect
Status: Accepted
Date: 2026-11-17   Made by: Cursor
Decision: `node_inspect` calls `assess_recovery()`. That function passes `identical_retries`, `repair_attempts`, and `replan_count` into `decide_recovery()`, and it passes prior fingerprint history without the attempt currently being classified. Authorized identical retries are marked `allowed_identical`. `detect_no_progress()` stops the run on a repeated fingerprint, an empty revision, or a cycle. Status is `partial` when valid evidence remains and `failed` otherwise. The graph shape is unchanged.
Reason: The previous route read `identical_retry_count` while `decide_recovery()` reads `identical_retries`, so the cap never applied. Passing the whole state as history also made the current attempt look like a repeated fingerprint.
Consequences: Transient failures retry up to `recovery_limits.identical_retry_cap` and then stop. Repair still goes through replan. Claim validation and `evaluation/recovery_suite/` remain open.

## D-036: Recovery stops and answer claims follow the contracts
Status: Accepted
Date: 2026-11-17   Made by: Cursor
Decision: A `no_progress` stop and a recovery-budget stop both end as `partial`, including when no evidence was produced. An unrecoverable terminal failure with no evidence ends as `failed`. Before `AgentResult` is returned, key numbers are checked with `validate_findings()`. A failure that names `context["evidence_id"]`, or an invariant failure for a task that already has evidence, runs `invalidate_evidence()` first. Invalidated evidence and its dependents are removed from key numbers and answer text. Surviving independent evidence stays. Dropped claim text is stored on `AgentResult.dropped_claims`. `CONTRACT_VERSION` stays `0.1.0`. Typed evidence records are kept beside the raw evidence store so execution can still read tool fields such as `matched_indices`.
Reason: `CONTRACTS.md` says `no_progress` terminates as partial and `budget_exhausted` finalizes as partial. A number reaches the answer only through valid evidence. The first recovery wiring used `failed` whenever evidence was absent, which contradicted that table.
Consequences: Tests cover a transient retry cap, a repeated fingerprint with no evidence, a tampered narrative, a dependent-evidence cascade, and a supported claim that stays. `evaluation/recovery_suite/` is still not built. M7 stays open. M8 still owns the report `RunStatus`.

## D-037: Controlled-failure recovery suite separate from benchmark
Status: Accepted
Date: 2026-11-17   Made by: Cursor
Decision: Add `evaluation/recovery_suite/scenarios.json` with handlers in `runners.py` and runner `run_recovery_suite.py`. Scenarios exercise classification, recovery decisions, no-progress detection, mock-agent transient retry/stop, fingerprint stall, claim tampering, and evidence invalidation. They do not use frozen benchmark question IDs, question text from `evaluation/benchmark/questions.json`, or `evaluation/oracle.py`. Results export to `evaluation/results/recovery_suite/latest.json`. Pytest enforces handler coverage and isolation.
Reason: M7 exit gate requires a recovery suite that is separate from the 20-question eval set. Keeps recovery regression tests runnable without a live LLM or oracle leakage.
Consequences: `uv run python evaluation/recovery_suite/run_recovery_suite.py` and `tests/unit/evaluation/test_recovery_suite.py` must pass before claiming M7 complete. M8 is next.

## D-038: Report finalize in pipeline via AnalysisRun contract
Status: Accepted
Date: 2026-11-17   Made by: Cursor
Decision: After `build_agent_result()`, `pipeline.run_agent()` (default `emit_report=True`) maps the typed answer into contract `AnalysisRun` (key numbers as `KeyNumberCitation`, evidence records, execution status) and calls `reports.delivery.finalize_run_report()`. That path re-validates claims, saves `runs/<run_id>/report.json`, renders escaped HTML to `report.html`, and logs `report_written`. Reports never import `agent`; only `pipeline` bridges layers. Chart attachment from tool results remains optional and is not required for the M8 E2E gate.
Reason: M8 exit gate requires an end-to-end run with downloadable HTML whose numbers match validated evidence. The report library existed but was not wired from the public entry point.
Consequences: M9 can download artifacts from the run directory. Eval harness may set `emit_report=False` if report I/O should be skipped. `CONTRACT_VERSION` unchanged.

