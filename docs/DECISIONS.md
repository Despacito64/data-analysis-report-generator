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
