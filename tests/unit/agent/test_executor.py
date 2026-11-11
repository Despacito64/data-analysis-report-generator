"""Unit tests for the DAG plan executor (src/da_agent/agent/executor.py)."""

import tempfile
from pathlib import Path

from da_agent.agent.executor import (
    PlanExecutionResult,
    TaskExecutionRecord,
    TaskStatus,
    execute_plan,
    resolve_references,
    topological_sort_tasks,
)
from da_agent.agent.planner import Plan
from da_agent.contracts.models import Task
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET_PATH = Path("Sample-Superstore.csv")


def _get_dataset():
    df = load_data(DATASET_PATH)
    profile = compute_profile(df, file_path=DATASET_PATH)
    return df, profile


def test_topological_sort_tasks():
    """Verify tasks are sorted strictly in dependency order with tie-breaking."""
    tasks = [
        Task(id="t3", tool="rank", args={}, depends_on=["t2"], rationale="r3"),
        Task(id="t1", tool="filter", args={}, depends_on=[], rationale="r1"),
        Task(id="t2", tool="group_aggregate", args={}, depends_on=["t1"], rationale="r2"),
    ]
    sorted_tasks = topological_sort_tasks(tasks)
    assert [t.id for t in sorted_tasks] == ["t1", "t2", "t3"]


def test_execute_linear_plan():
    """Execute a valid linear 2-step plan (filter -> group_aggregate)."""
    df, profile = _get_dataset()
    tasks = [
        Task(
            id="t1",
            tool="filter",
            args={"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
            depends_on=[],
            rationale="Filter East region",
        ),
        Task(
            id="t2",
            tool="group_aggregate",
            args={"by": ["Category"], "metric_column": "Profit", "aggregation": "sum"},
            depends_on=["t1"],
            rationale="Sum profit by category in East region",
        ),
    ]
    plan = Plan(plan_version=1, tasks=tasks)
    evidence_store = {}

    with tempfile.TemporaryDirectory() as tmp_dir:
        writer = RunTraceWriter(run_id="test_linear", base_dir=tmp_dir)
        result: PlanExecutionResult = execute_plan(
            plan=plan,
            df=df,
            profile=profile,
            trace_writer=writer,
            evidence_store=evidence_store,
        )

        assert result.status == "complete"
        assert len(result.records) == 2
        assert result.records[0].status == TaskStatus.OK
        assert result.records[1].status == TaskStatus.OK
        assert result.records[0].task_id == "t1"
        assert result.records[1].task_id == "t2"
        assert len(result.evidence_ids) == 2

        # Verify trace events
        events = writer.read_events()
        event_types = [e.event_type for e in events]
        assert "tool_call" in event_types
        assert "evidence" in event_types


def test_execute_branching_plan():
    """Execute a branching plan: t1 (filter) -> t2 (group_aggregate) and t1 -> t3 (rank)."""
    df, profile = _get_dataset()
    tasks = [
        Task(
            id="t1",
            tool="filter",
            args={"conditions": [{"column": "Segment", "operator": "eq", "value": "Consumer"}]},
            depends_on=[],
            rationale="Filter Consumer segment",
        ),
        Task(
            id="t2",
            tool="group_aggregate",
            args={"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
            depends_on=["t1"],
            rationale="Category sales in Consumer",
        ),
        Task(
            id="t3",
            tool="rank",
            args={
                "entity_column": "City",
                "metric_column": "Sales",
                "ascending": False,
                "top_n": 3,
            },
            depends_on=["t1"],
            rationale="Top 3 cities in Consumer",
        ),
    ]
    plan = Plan(plan_version=1, tasks=tasks)
    result = execute_plan(plan=plan, df=df, profile=profile)

    assert result.status == "complete"
    assert len(result.records) == 3
    assert all(r.status == TaskStatus.OK for r in result.records)


def test_execute_failed_dependency_skips_downstream():
    """When an upstream task fails, downstream dependent tasks are marked skipped."""
    df, profile = _get_dataset()
    tasks = [
        Task(
            id="t1",
            tool="filter",
            # Intentionally cause EMPTY_RESULT failure
            args={
                "conditions": [{"column": "Region", "operator": "eq", "value": "NonExistentRegion"}]
            },
            depends_on=[],
            rationale="Filter impossible region",
        ),
        Task(
            id="t2",
            tool="group_aggregate",
            args={"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
            depends_on=["t1"],
            rationale="Aggregate filtered rows",
        ),
        Task(
            id="t3",
            tool="rank",
            args={"entity_column": "Category", "metric_column": "Sales"},
            depends_on=["t2"],
            rationale="Rank aggregate rows",
        ),
    ]
    plan = Plan(plan_version=1, tasks=tasks)
    with tempfile.TemporaryDirectory() as tmp_dir:
        writer = RunTraceWriter(run_id="test_skip", base_dir=tmp_dir)
        result = execute_plan(plan=plan, df=df, profile=profile, trace_writer=writer)

        assert result.status == "failed"
        assert len(result.records) == 3
        assert result.records[0].status == TaskStatus.FAILED
        assert result.records[1].status == TaskStatus.SKIPPED
        assert result.records[2].status == TaskStatus.SKIPPED
        assert "Upstream dependency failed" in (result.records[1].error or "")
        assert "Upstream dependency failed" in (result.records[2].error or "")

        events = writer.read_events()
        skipped_events = [e for e in events if e.event_type == "task_skipped"]
        assert len(skipped_events) == 2


def test_execute_max_steps_limit():
    """Verify execution halts and skips tasks beyond max_steps budget."""
    df, profile = _get_dataset()
    tasks = [
        Task(
            id="t1",
            tool="filter",
            args={"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
            depends_on=[],
            rationale="Step 1",
        ),
        Task(
            id="t2",
            tool="group_aggregate",
            args={"by": ["Category"], "metric_column": "Profit", "aggregation": "sum"},
            depends_on=[],
            rationale="Step 2",
        ),
    ]
    plan = Plan(plan_version=1, tasks=tasks)
    result = execute_plan(plan=plan, df=df, profile=profile, max_steps=1)

    assert result.status == "partial"
    assert result.records[0].status == TaskStatus.OK
    assert result.records[1].status == TaskStatus.SKIPPED
    assert "Step budget exhausted" in (result.records[1].error or "")


def test_resolve_explicit_references():
    """Verify resolve_references extracts upstream outputs."""
    records = {
        "t1": TaskExecutionRecord(
            task_id="t1",
            tool="group_aggregate",
            args={},
            status=TaskStatus.OK,
            output_summary={"total_groups": 4, "metric_column": "Sales"},
            evidence_id="ev_t1",
        )
    }
    evidence_store = {"ev_t1": {"total_groups": 4, "deep_field": 42}}

    args = {
        "count": "$t1.total_groups",
        "deep": {"$ref": "t1.deep_field"},
        "literal": "hello",
    }
    resolved = resolve_references(args, evidence_store, records)
    assert resolved["count"] == 4
    assert resolved["deep"] == 42
    assert resolved["literal"] == "hello"


def test_revised_upstream_invalidates_dependent_task_evidence():
    """A changed upstream filter reruns downstream tasks and gets fresh evidence IDs."""
    df, profile = _get_dataset()
    common_downstream = Task(
        id="t2",
        tool="group_aggregate",
        args={"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
        depends_on=["t1"],
        rationale="Sum sales by category after filtering",
    )
    first_plan = Plan(
        plan_version=1,
        tasks=[
            Task(
                id="t1",
                tool="filter",
                args={"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
                depends_on=[],
                rationale="Filter East",
            ),
            common_downstream,
        ],
    )
    evidence_store = {}
    first = execute_plan(
        plan=first_plan,
        df=df,
        profile=profile,
        evidence_store=evidence_store,
    )

    revised_plan = Plan(
        plan_version=2,
        tasks=[
            Task(
                id="t1",
                tool="filter",
                args={"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
                depends_on=[],
                plan_version=2,
                rationale="Revise to West",
            ),
            common_downstream.model_copy(update={"plan_version": 2}),
        ],
    )
    revised = execute_plan(
        plan=revised_plan,
        df=df,
        profile=profile,
        evidence_store=evidence_store,
        prior_records=first.records,
    )

    assert first.status == revised.status == "complete"
    assert [record.status for record in revised.records] == [TaskStatus.OK, TaskStatus.OK]
    assert revised.records[0].evidence_id != first.records[0].evidence_id
    assert revised.records[1].evidence_id != first.records[1].evidence_id
    assert revised.records[1].output_summary != first.records[1].output_summary
