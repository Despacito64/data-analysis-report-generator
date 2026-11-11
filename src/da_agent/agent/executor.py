"""DAG plan executor for deterministic analytical tasks.

Layer 6 module: executes a validated Plan in topological dependency order using
the Layer 5 tool executor (execute_task). Resolves upstream task references, subsets
DataFrames for filter dependencies, handles skipped tasks on failure, and enforces
step and timeout budgets.
Never imports evaluation/oracle or da_agent.agent.baseline.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from da_agent.agent.planner import Plan
from da_agent.contracts.models import (
    Budgets,
    DatasetProfile,
    Failure,
    FailureClass,
    Task,
)
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.profiler import compute_profile
from da_agent.tools.executor import execute_task
from da_agent.tools.registry import DEFAULT_REGISTRY, ToolRegistry


class TaskStatus(str, Enum):
    """Execution status for an individual task."""

    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskExecutionRecord(BaseModel):
    """Typed audit record of a single task's execution."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    tool: str
    args: dict[str, Any]
    depends_on: list[str] = Field(default_factory=list)
    status: TaskStatus
    output_summary: dict[str, Any] | None = None
    evidence_id: str | None = None
    error: str | None = None
    duration_s: float = 0.0


class PlanExecutionResult(BaseModel):
    """Result envelope summarizing complete or partial plan execution."""

    model_config = ConfigDict(extra="forbid")

    plan_version: int = 1
    records: list[TaskExecutionRecord] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    status: str = "complete"  # "complete" | "partial" | "failed"
    failure: Failure | None = None


def resolve_references(
    args: dict[str, Any],
    evidence_store: dict[str, Any],
    task_records: dict[str, TaskExecutionRecord],
) -> dict[str, Any]:
    """Resolve upstream references in task arguments.

    Supports:
      - "$<task_id>.<field>" or "$<task_id>" string patterns
      - {"$ref": "<task_id>.<field>"} objects
    """
    resolved: dict[str, Any] = {}

    for key, val in args.items():
        if isinstance(val, str) and val.startswith("$"):
            ref_path = val[1:].split(".")
            task_id = ref_path[0]
            if task_id in task_records:
                record = task_records[task_id]
                summary = record.output_summary or {}
                if len(ref_path) == 1:
                    resolved[key] = summary
                elif len(ref_path) == 2 and ref_path[1] in summary:
                    resolved[key] = summary[ref_path[1]]
                elif record.evidence_id and record.evidence_id in evidence_store:
                    full_res = evidence_store[record.evidence_id]
                    resolved[key] = full_res.get(ref_path[1], val)
                else:
                    resolved[key] = val
            else:
                resolved[key] = val
        elif isinstance(val, dict) and "$ref" in val and isinstance(val["$ref"], str):
            ref_path = val["$ref"].split(".")
            task_id = ref_path[0]
            if task_id in task_records:
                record = task_records[task_id]
                summary = record.output_summary or {}
                if len(ref_path) == 1:
                    resolved[key] = summary
                elif len(ref_path) == 2 and ref_path[1] in summary:
                    resolved[key] = summary[ref_path[1]]
                elif record.evidence_id and record.evidence_id in evidence_store:
                    full_res = evidence_store[record.evidence_id]
                    resolved[key] = full_res.get(ref_path[1], val)
                else:
                    resolved[key] = val
            else:
                resolved[key] = val
        else:
            resolved[key] = val

    return resolved


def topological_sort_tasks(tasks: list[Task]) -> list[Task]:
    """Sort tasks into deterministic dependency order, breaking ties by task id."""
    tasks_by_id = {t.id: t for t in tasks}
    in_degree: dict[str, int] = {t.id: 0 for t in tasks}
    dependents: dict[str, list[str]] = {t.id: [] for t in tasks}

    for t in tasks:
        for dep in t.depends_on:
            if dep in tasks_by_id:
                in_degree[t.id] += 1
                dependents[dep].append(t.id)

    # Deterministic priority queue / sorted list of ready tasks
    ready = sorted([tid for tid, deg in in_degree.items() if deg == 0])
    ordered: list[Task] = []

    while ready:
        curr_id = ready.pop(0)
        ordered.append(tasks_by_id[curr_id])
        for nxt in dependents[curr_id]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                ready.append(nxt)
                ready.sort()

    if len(ordered) != len(tasks):
        # Fallback to original order if circular (validator should have caught it)
        return tasks

    return ordered


def execute_plan(
    plan: Plan,
    df: pd.DataFrame,
    profile: DatasetProfile,
    budgets: Budgets | None = None,
    trace_writer: RunTraceWriter | None = None,
    registry: ToolRegistry = DEFAULT_REGISTRY,
    evidence_store: dict[str, Any] | None = None,
    max_steps: int | None = None,
    prior_records: list[TaskExecutionRecord] | None = None,
) -> PlanExecutionResult:
    """Execute a validated plan as a DAG in dependency order."""
    if budgets is None:
        budgets = load_config().budgets
    if evidence_store is None:
        evidence_store = {}

    effective_max_steps = max_steps if max_steps is not None else budgets.max_tool_calls

    ordered_tasks = topological_sort_tasks(plan.tasks)
    records: list[TaskExecutionRecord] = []
    prior_by_id = {record.task_id: record for record in prior_records or []}
    reusable_task_ids: set[str] = set()
    for task in ordered_tasks:
        previous = prior_by_id.get(task.id)
        if (
            previous
            and previous.status == TaskStatus.OK
            and previous.tool == task.tool
            and previous.args == task.args
            and previous.depends_on == task.depends_on
            and all(dependency in reusable_task_ids for dependency in task.depends_on)
        ):
            reusable_task_ids.add(task.id)
    records_by_id: dict[str, TaskExecutionRecord] = dict(prior_by_id)
    evidence_ids: list[str] = []
    first_failure: Failure | None = None

    # Track dataframe state per task to propagate filter outputs
    dfs_by_task: dict[str, pd.DataFrame] = {}
    profiles_by_task: dict[str, DatasetProfile] = {}

    executed_count = 0

    for task in ordered_tasks:
        previous = records_by_id.get(task.id)
        if previous and task.id in reusable_task_ids:
            records.append(previous)
            if previous.evidence_id:
                evidence_ids.append(previous.evidence_id)
            if task.tool == "filter" and previous.evidence_id:
                filtered_rows = evidence_store.get(previous.evidence_id, {}).get(
                    "matched_indices", []
                )
                dfs_by_task[task.id] = df.loc[filtered_rows].copy()
                profiles_by_task[task.id] = compute_profile(
                    dfs_by_task[task.id],
                    dataset_hash=profile.dataset_hash,
                    source_name=profile.source_name,
                )
            continue

        # Check max steps limit
        if executed_count >= effective_max_steps:
            failure = Failure(
                failure_class=FailureClass.BUDGET_EXHAUSTED,
                recoverable=False,
                message=f"Plan execution exceeded max steps budget ({effective_max_steps})",
                context={"max_steps": effective_max_steps, "executed_steps": executed_count},
                task_id=task.id,
            )
            rec = TaskExecutionRecord(
                task_id=task.id,
                tool=task.tool,
                args=task.args,
                depends_on=task.depends_on,
                status=TaskStatus.SKIPPED,
                error="Step budget exhausted",
            )
            records.append(rec)
            records_by_id[task.id] = rec
            if first_failure is None:
                first_failure = failure
            if trace_writer:
                trace_writer.log_failure(failure)
            continue

        # Check dependency statuses
        failed_deps = [
            dep
            for dep in task.depends_on
            if dep in records_by_id and records_by_id[dep].status != TaskStatus.OK
        ]
        if failed_deps:
            rec = TaskExecutionRecord(
                task_id=task.id,
                tool=task.tool,
                args=task.args,
                depends_on=task.depends_on,
                status=TaskStatus.SKIPPED,
                error=f"Upstream dependency failed or skipped: {', '.join(failed_deps)}",
            )
            records.append(rec)
            records_by_id[task.id] = rec
            if trace_writer:
                trace_writer.log_event(
                    "task_skipped",
                    {
                        "task_id": task.id,
                        "tool": task.tool,
                        "reason": rec.error,
                    },
                )
            continue

        # Determine input DataFrame and DatasetProfile for this task
        task_df = df
        task_profile = profile

        # If dependent on upstream task(s), check if any was a filter
        for dep in task.depends_on:
            if dep in records_by_id and records_by_id[dep].tool == "filter":
                ev_id = records_by_id[dep].evidence_id
                if ev_id and ev_id in evidence_store:
                    matched_indices = evidence_store[ev_id].get("matched_indices", [])
                    task_df = df.loc[matched_indices].copy()
                    task_profile = compute_profile(
                        task_df,
                        dataset_hash=profile.dataset_hash,
                        source_name=profile.source_name,
                    )
            elif dep in dfs_by_task:
                task_df = dfs_by_task[dep]
                task_profile = profiles_by_task.get(dep, profile)

        # Resolve any explicit upstream references in arguments
        resolved_args = resolve_references(task.args, evidence_store, records_by_id)
        current_task = Task(
            id=task.id,
            tool=task.tool,
            args=resolved_args,
            depends_on=task.depends_on,
            status="running",
            plan_version=task.plan_version,
            rationale=task.rationale,
        )

        start_t = time.perf_counter()
        evidence, failure = execute_task(
            task=current_task,
            df=task_df,
            profile=task_profile,
            budgets=budgets,
            trace_writer=trace_writer,
            registry=registry,
            evidence_store=evidence_store,
        )
        duration = round(time.perf_counter() - start_t, 4)
        executed_count += 1

        if failure is not None:
            rec = TaskExecutionRecord(
                task_id=task.id,
                tool=task.tool,
                args=resolved_args,
                depends_on=task.depends_on,
                status=TaskStatus.FAILED,
                error=failure.message,
                duration_s=duration,
            )
            records.append(rec)
            records_by_id[task.id] = rec
            if first_failure is None:
                first_failure = failure
        else:
            assert evidence is not None
            rec = TaskExecutionRecord(
                task_id=task.id,
                tool=task.tool,
                args=resolved_args,
                depends_on=task.depends_on,
                status=TaskStatus.OK,
                output_summary=evidence.result_summary,
                evidence_id=evidence.evidence_id,
                duration_s=duration,
            )
            records.append(rec)
            records_by_id[task.id] = rec
            evidence_ids.append(evidence.evidence_id)
            dfs_by_task[task.id] = task_df
            profiles_by_task[task.id] = task_profile

    # Determine overall status
    ok_count = sum(1 for r in records if r.status == TaskStatus.OK)

    if ok_count == len(plan.tasks) and ok_count > 0:
        overall_status = "complete"
    elif ok_count > 0:
        overall_status = "partial"
    else:
        overall_status = "failed"

    return PlanExecutionResult(
        plan_version=plan.plan_version,
        records=records,
        evidence_ids=evidence_ids,
        status=overall_status,
        failure=first_failure,
    )
