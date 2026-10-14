# CONTRACTS.md: data shapes shared by all modules

All models are Pydantic v2 classes in `src/da_agent/contracts/`. This file is the specification; the code must match it.
Contract version: `CONTRACT_VERSION = "0.1.0"` (a constant in the contracts package). Any change needs a `DECISIONS.md` entry,
a version bump and the owner's approval. Fields below are required unless marked optional.

## DatasetProfile

| Field | Type | Notes |
| --- | --- | --- |
| dataset_hash | str | Hash of the raw input bytes |
| transformation_version | str | Version of the loading and cleaning code |
| source_name | str | File name and sheet, if any |
| row_count | int | |
| columns | list[ColumnProfile] | name, physical_type, semantic_type, missing_count, distinct_count, examples |
| duplicate_row_count | int | Exact duplicate rows |
| date_coverage | list[DateCoverage] | column, min, max, parse_failures |
| descriptive_stats | dict[str, StatBlock] | Numeric columns only, as typed StatBlock objects |
| parsing_diagnostics | list[str] | Plain-language warnings |

`semantic_type` is one of: `identifier`, `numeric_measure`, `category`, `date`, `text`. Numeric identifiers (for example postal codes)
must be classified `identifier`, never `numeric_measure`.

## ResolvedQuestion

| Field | Type | Notes |
| --- | --- | --- |
| question_text | str | Original text |
| intent | str | Template name (for example `period_comparison`, `ranking`, `contribution`, `diagnostic`) |
| metric | str or None | Column and aggregation, for example `sum(Sales)` |
| period | PeriodSpec or None | |
| grouping | list[str] | |
| filters | list[FilterSpec] | |
| ambiguity_decisions | list[AmbiguityDecision] | What was ambiguous and how it was resolved |
| answerable | bool | |
| decline_reason | str or None | Required when answerable is false |

## ToolSpec

Metadata for one registered tool. Created by the registry (M3), consumed by the planner prompt and validators.

| Field | Type |
| --- | --- |
| name | str |
| description | str |
| args_model | name of the Pydantic argument model |
| args_schema | JSON schema of the arguments |
| result_schema | JSON schema of the result |
| invariants | list[str] (names of numerical checks) |

## Task

| Field | Type | Notes |
| --- | --- | --- |
| id | str | Unique within a run |
| tool | str | Must exist in the registry |
| args | dict (validated against the tool's args model) | |
| depends_on | list[str] | Task ids. The graph must be acyclic |
| status | enum | `pending`, `ready`, `running`, `done`, `failed`, `cancelled` |
| plan_version | int | Version in which the task was created or last changed |
| rationale | str | One sentence |

## EvidenceRecord

| Field | Type | Notes |
| --- | --- | --- |
| evidence_id | str | |
| task_id | str | |
| tool | str | |
| args_hash | str | Hash of the canonical args |
| dataset_hash | str | Must equal the run's dataset hash |
| input_row_count | int | |
| result_summary | dict (typed per tool) | Enough to reproduce and to cite |
| result_schema_version | str | |
| invariants_checked | list[str] | |
| valid | bool | |
| invalidated_by | str or None | Evidence id that invalidated it |
| created_at | datetime | |

## Failure

| Field | Type | Notes |
| --- | --- | --- |
| failure_class | enum | See the table below |
| recoverable | bool | |
| message | str | Factual description only |
| context | dict | Factual context such as valid column names or observed row counts. Never an expected answer |
| task_id | str or None | |

| Class | Example | Recoverable | Default response |
| --- | --- | --- | --- |
| invalid_args | Unknown column, bad period | Yes | Replan with the error and valid columns |
| unknown_tool | Tool not in registry | Yes | Replan, counts toward replan budget |
| empty_result | Filter removes all rows | Yes | Inspect, revise filter or question |
| schema_violation | Output does not match declared schema | No | Mark task failed |
| invariant_violation | Contributions do not sum to total | No | Mark failed, invalidate dependents |
| transient | Timeout | Yes | Identical retry within the retry budget |
| no_progress | Same task and args repeated, or revision adds no new evidence | No | Terminate as partial |
| budget_exhausted | A budget limit reached | No | Finalize as partial with valid evidence |

## PlanRevision

| Field | Type |
| --- | --- |
| from_version | int |
| to_version | int |
| trigger_evidence_id | str or None (a failure id when triggered by a failure) |
| change | enum: `added`, `replaced`, `cancelled` |
| observed_result | str (short factual summary of what was seen) |
| affected_tasks | list[str] |

A revision is valid only if at least one task or argument actually changed.

## Budgets (values live in `config.yaml`, never in code)

`max_llm_calls`, `max_tool_calls`, `max_replans`, `max_identical_retries`, `per_call_timeout_s`, `max_total_tokens`.
Both variants use identical values.

## RunStatus

`status`: `complete`, `partial` or `failed`. Plus `reason_code`, `reason_text`, `dropped_claims` (list), `unvalidated_claims` (list).

## Finding and Report

`Finding`: statement, numeric_claims (list of value, unit, label, evidence_id), evidence_ids, caveat (optional).
`Report`: run_id, dataset_hash, question, summary, findings, charts, methods, limitations, recommendations (qualified),
evidence_appendix, status (RunStatus).

A numeric claim without a valid `evidence_id` must be removed before rendering and listed in `dropped_claims`.
