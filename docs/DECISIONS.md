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
Status: Open
Decision: To be chosen in M0 from the model spike (valid-JSON rate, tool-name accuracy, latency on 10 sample prompts).
Consequences: Record the choice, measured numbers and sampling settings here and in `config.yaml`.
Update (2026-10-14): Model spike deferred because Ollama could not be downloaded (network issues). Not needed for M1 to M4. MUST be resolved before M5 starts. Options to evaluate then: another local runtime (LM Studio, llama.cpp) or a hosted free-tier API. If a hosted API is used, add a new decision entry and re-check the scope rule about local models.

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

## D-020: Ollama model spike runner
Status: Accepted
Date: 2026-10-29   Made by: Copilot
Decision: Add `evaluation/model_spike.py` as the deferred M0 Ollama benchmark runner. It evaluates `qwen3:4b`, `qwen3:8b`, and `llama3.1:8b` with temperature 0 and seed 42, three runs per question, bounded validation retries, and the registered tool contract/argument validator. It writes per-run records to `evaluation/results/model_spike.csv` and prints model-level metrics. Real measurements remain pending because the frozen question JSON and independent oracle answers are not yet implemented.
Reason: Provides the reproducible harness required by D-006 without changing existing contracts, tool definitions, model prompts, or oracle independence boundaries.
Consequences: D-006 remains open until the benchmark artifacts exist and the runner has been executed against Ollama. A temporary smoke run completed 90 calls; its accuracy and answer-matching values are not valid D-006 evidence because they used the temporary prompt-derived question set, not the frozen independent oracle benchmark. The runner requires an explicit `--questions` file and normalizes Ollama JSON-string tool arguments to avoid silently running an unreproducible configuration or misclassifying native tool calls.
