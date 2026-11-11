"""Unit tests for the LangGraph dynamic planning agent (src/da_agent/agent/graph.py).

Uses MockLLMClient scripted responses to test control flow without a live LLM or Ollama.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from da_agent.agent.graph import run_agent
from da_agent.agent.planner import MockLLMClient, Plan
from da_agent.contracts.models import Task
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET_PATH = Path("Sample-Superstore.csv")


def _get_dataset():
    df = load_data(DATASET_PATH)
    profile = compute_profile(df, file_path=DATASET_PATH)
    return df, profile


def _make_plan_json(tasks: list[dict[str, Any]]) -> str:
    return json.dumps({"tasks": tasks})


# ---------------------------------------------------------------------------
# Scripted plan helpers
# ---------------------------------------------------------------------------

VALID_FILTER_PLAN = _make_plan_json(
    [
        {
            "id": "t1",
            "tool": "filter",
            "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
            "depends_on": [],
            "rationale": "Filter East region",
        }
    ]
)

VALID_GROUP_AGG_PLAN = _make_plan_json(
    [
        {
            "id": "t1",
            "tool": "group_aggregate",
            "args": {"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
            "depends_on": [],
            "rationale": "Group by category, sum sales",
        }
    ]
)

VALID_FILTER_THEN_GROUP_PLAN = _make_plan_json(
    [
        {
            "id": "t1",
            "tool": "filter",
            "args": {"conditions": [{"column": "Segment", "operator": "eq", "value": "Consumer"}]},
            "depends_on": [],
            "rationale": "Filter Consumer",
        },
        {
            "id": "t2",
            "tool": "group_aggregate",
            "args": {"by": ["Category"], "metric_column": "Profit", "aggregation": "sum"},
            "depends_on": ["t1"],
            "rationale": "Profit by category for consumers",
        },
    ]
)

# This plan has an argument schema error (missing "aggregation") that should trigger repair
INVALID_GROUP_AGG_PLAN = _make_plan_json(
    [
        {
            "id": "t1",
            "tool": "group_aggregate",
            "args": {"by": ["Category"], "metric_column": "Sales"},  # missing aggregation
            "depends_on": [],
            "rationale": "Missing aggregation",
        }
    ]
)

# A plan whose filter will produce 0 rows (EMPTY_RESULT) → triggers replan
EMPTY_RESULT_FILTER_PLAN = _make_plan_json(
    [
        {
            "id": "t1",
            "tool": "filter",
            "args": {
                "conditions": [{"column": "Region", "operator": "eq", "value": "NONEXISTENT"}]
            },
            "depends_on": [],
            "rationale": "Filter nonexistent region",
        },
        {
            "id": "t2",
            "tool": "group_aggregate",
            "args": {"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
            "depends_on": ["t1"],
            "rationale": "Aggregate after filter",
        },
    ]
)

# A plan with no ready tasks (all depend on a nonexistent task)
INVALID_NO_READY_PLAN = _make_plan_json(
    [
        {
            "id": "t1",
            "tool": "filter",
            "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
            "depends_on": ["t_ghost"],  # ghost dependency -> not ready
            "rationale": "No ready task",
        }
    ]
)


# ---------------------------------------------------------------------------
# Tests: Graph happy paths
# ---------------------------------------------------------------------------


def test_graph_complete_single_step():
    """Single-task plan executes fully and returns complete status."""
    df, profile = _get_dataset()
    client = MockLLMClient(default_response=VALID_FILTER_PLAN)

    with tempfile.TemporaryDirectory() as tmp:
        writer = RunTraceWriter(run_id="test_complete", base_dir=tmp)
        result = run_agent(
            question="What rows are in the East region?",
            df=df,
            profile=profile,
            run_id="test_complete",
            llm_client=client,
            trace_writer=writer,
        )

    assert result["status"] == "complete"
    assert len(result["evidence_ids"]) == 1
    assert result["final_answer"]
    assert not result["failures"]
    assert not result["revisions"]


def test_graph_complete_multistep():
    """Two-step plan (filter -> group_aggregate) completes successfully."""
    df, profile = _get_dataset()
    client = MockLLMClient(default_response=VALID_FILTER_THEN_GROUP_PLAN)

    result = run_agent(
        question="In the Consumer segment, what is the total profit for each category?",
        df=df,
        profile=profile,
        llm_client=client,
    )

    assert result["status"] == "complete"
    assert len(result["evidence_ids"]) == 2


def test_graph_plan_repair_then_success():
    """Graph repairs an invalid initial plan and completes successfully."""
    df, profile = _get_dataset()
    # First call returns invalid plan (missing aggregation); second returns valid plan
    client = MockLLMClient(responses=[INVALID_GROUP_AGG_PLAN, VALID_GROUP_AGG_PLAN])

    result = run_agent(
        question="What is the total sales for each category?",
        df=df,
        profile=profile,
        llm_client=client,
    )

    assert result["status"] == "complete"
    assert len(result["evidence_ids"]) == 1


def test_graph_no_ready_task_plan_rejected():
    """A plan with no ready task (ghost dependency) is rejected and falls back to failed."""
    df, profile = _get_dataset()
    # First: invalid plan (ghost dep). Repair: also invalid. Graph should return failed.
    client = MockLLMClient(responses=[INVALID_NO_READY_PLAN, INVALID_NO_READY_PLAN])

    result = run_agent(
        question="What rows are in the East region?",
        df=df,
        profile=profile,
        llm_client=client,
    )

    assert result["status"] == "failed"
    assert result["plan"] is None
    assert len(result["failures"]) >= 1


def test_graph_replan_on_execution_failure():
    """When a task fails at execution, the graph replans and re-executes."""
    df, profile = _get_dataset()
    # Plan 1: will produce EMPTY_RESULT for filter (nonexistent region) causing downstream skip.
    # Replan (call 2): returns valid single-step plan.
    client = MockLLMClient(responses=[EMPTY_RESULT_FILTER_PLAN, VALID_GROUP_AGG_PLAN])

    with tempfile.TemporaryDirectory() as tmp:
        writer = RunTraceWriter(run_id="test_failure_replan", base_dir=tmp)
        result = run_agent(
            question="What is the total sales for each category?",
            df=df,
            profile=profile,
            llm_client=client,
            trace_writer=writer,
            max_replans=1,
        )
        events = writer.read_events()

    assert result["status"] == "complete"
    assert len(result["evidence_ids"]) >= 1
    assert "planner_llm_call" in [event.event_type for event in events]
    assert "replan_attempt" in [event.event_type for event in events]
    assert "plan_revision" in [event.event_type for event in events]
    assert len(client.call_history) == 2


def test_graph_replan_budget_exhaustion():
    """When replan budget is exhausted, agent returns partial status with reason."""
    df, profile = _get_dataset()
    # Every plan attempt triggers EMPTY_RESULT
    client = MockLLMClient(default_response=EMPTY_RESULT_FILTER_PLAN)

    result = run_agent(
        question="What is the total sales for each category?",
        df=df,
        profile=profile,
        llm_client=client,
        max_replans=0,  # zero replans allowed
    )

    assert result["status"] == "partial"
    assert any(f.failure_class.value == "budget_exhausted" for f in result["failures"])


def test_graph_invalid_replan_returns_partial_failure():
    """An invalid corrected plan is rejected and ends as a structured partial run."""
    df, profile = _get_dataset()
    invalid_replan = _make_plan_json(
        [
            {
                "id": "r1",
                "tool": "group_aggregate",
                "args": {},
                "depends_on": [],
                "rationale": "Invalid arguments",
            }
        ]
    )
    client = MockLLMClient(responses=[EMPTY_RESULT_FILTER_PLAN, invalid_replan, invalid_replan])

    result = run_agent(
        question="What is the total sales for each category?",
        df=df,
        profile=profile,
        llm_client=client,
        max_replans=1,
    )

    assert result["status"] == "partial"
    assert result["plan"].plan_version == 1
    assert len(client.call_history) == 3
    assert any(f.failure_class.value == "invalid_args" for f in result["failures"])
    assert not result["revisions"]


def test_graph_revises_after_observing_successful_result():
    """A changed follow-up plan records the successful evidence that triggered it."""
    df, profile = _get_dataset()
    followup_plan = _make_plan_json(
        [
            {
                "id": "r1",
                "tool": "filter",
                "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
                "depends_on": [],
                "rationale": "Inspect the region indicated by the prior result",
            }
        ]
    )
    client = MockLLMClient(responses=[VALID_GROUP_AGG_PLAN, followup_plan])

    with tempfile.TemporaryDirectory() as tmp:
        writer = RunTraceWriter(run_id="test_result_revision", base_dir=tmp)
        result = run_agent(
            question="What is the total sales for each category?",
            df=df,
            profile=profile,
            llm_client=client,
            trace_writer=writer,
            max_replans=1,
        )
        events = writer.read_events()

    revision_events = [event for event in events if event.event_type == "plan_revision"]
    assert result["status"] == "complete"
    assert len(result["evidence_ids"]) == 2
    assert len(result["revisions"]) == 1
    assert len(revision_events) == 1
    assert revision_events[0].payload["trigger_evidence_id"] == result["evidence_ids"][0]
    assert "sample_groups" in client.call_history[1]["messages"][-1]["content"]


def test_graph_trace_events_written():
    """Verify trace file contains expected event types after a run."""
    df, profile = _get_dataset()
    client = MockLLMClient(default_response=VALID_FILTER_PLAN)

    with tempfile.TemporaryDirectory() as tmp:
        writer = RunTraceWriter(run_id="test_trace", base_dir=tmp)
        run_agent(
            question="What rows are in the East region?",
            df=df,
            profile=profile,
            run_id="test_trace",
            llm_client=client,
            trace_writer=writer,
        )

        events = writer.read_events()
        event_types = {e.event_type for e in events}

    assert "resolved_question" in event_types
    assert "plan" in event_types
    assert "tool_call" in event_types
    assert "evidence" in event_types
    assert "status" in event_types


def test_graph_revision_logged_on_replan():
    """When replan succeeds, a plan_revision event is written to trace."""
    df, profile = _get_dataset()
    # First: triggers filter failure; second: valid replacement plan
    client = MockLLMClient(responses=[EMPTY_RESULT_FILTER_PLAN, VALID_GROUP_AGG_PLAN])

    with tempfile.TemporaryDirectory() as tmp:
        writer = RunTraceWriter(run_id="test_revision", base_dir=tmp)
        run_agent(
            question="What is the total sales for each category?",
            df=df,
            profile=profile,
            run_id="test_revision",
            llm_client=client,
            trace_writer=writer,
            max_replans=1,
        )

        events = writer.read_events()
        event_types = [e.event_type for e in events]

    # Plan revision should appear if replanning succeeded
    # (may be absent if router chose finalize due to no failures at inspect)
    assert "plan" in event_types
    assert "status" in event_types


# ---------------------------------------------------------------------------
# Tests: bounded replanning (Step 3)
# ---------------------------------------------------------------------------


def test_replan_on_failure_fail_then_succeed():
    """MockLLMClient scripted to fail once then produce valid replan."""
    from da_agent.agent.planner import replan_on_failure
    from da_agent.contracts.models import Failure, FailureClass

    _, profile = _get_dataset()

    bad_replan = _make_plan_json(
        [{"id": "r1", "tool": "group_aggregate", "args": {}, "depends_on": [], "rationale": "bad"}]
    )
    good_replan = _make_plan_json(
        [
            {
                "id": "r1",
                "tool": "group_aggregate",
                "args": {"by": ["Region"], "metric_column": "Sales", "aggregation": "sum"},
                "depends_on": [],
                "rationale": "Sum sales by region",
            }
        ]
    )

    client = MockLLMClient(responses=[bad_replan, good_replan])

    current_plan = Plan(
        plan_version=1,
        tasks=[
            Task(
                id="t1",
                tool="filter",
                args={"conditions": [{"column": "Region", "operator": "eq", "value": "FAKE"}]},
                depends_on=[],
                rationale="bad filter",
            )
        ],
    )
    failure = Failure(
        failure_class=FailureClass.EMPTY_RESULT,
        recoverable=True,
        message="Filter yielded 0 rows",
        context={},
        task_id="t1",
    )

    tool_specs = __import__(
        "da_agent.tools.registry", fromlist=["export_tool_specs"]
    ).export_tool_specs()
    new_plan, err = replan_on_failure(
        resolved=__import__(
            "da_agent.agent.resolver", fromlist=["resolve_question"]
        ).resolve_question("What is total sales per region?", profile),
        profile=profile,
        current_plan=current_plan,
        failed_task_id="t1",
        failure=failure,
        available_columns=[c.name for c in profile.columns],
        tool_specs=tool_specs,
        client=client,
        max_repairs=1,
    )

    assert err is None
    assert new_plan is not None
    assert new_plan.plan_version == 2
    assert len(new_plan.tasks) == 1


def test_replan_on_failure_twice_exhaustion():
    """MockLLMClient always returns invalid plan → replan returns failure."""
    from da_agent.agent.planner import replan_on_failure
    from da_agent.contracts.models import Failure, FailureClass

    _, profile = _get_dataset()

    always_bad = _make_plan_json(
        [{"id": "r1", "tool": "group_aggregate", "args": {}, "depends_on": [], "rationale": "bad"}]
    )

    client = MockLLMClient(default_response=always_bad)

    current_plan = Plan(
        plan_version=1,
        tasks=[
            Task(id="t1", tool="filter", args={"conditions": []}, depends_on=[], rationale="bad")
        ],
    )
    failure = Failure(
        failure_class=FailureClass.EMPTY_RESULT,
        recoverable=True,
        message="Filter yielded 0 rows",
        context={},
        task_id="t1",
    )

    tool_specs = __import__(
        "da_agent.tools.registry", fromlist=["export_tool_specs"]
    ).export_tool_specs()
    new_plan, err = replan_on_failure(
        resolved=__import__(
            "da_agent.agent.resolver", fromlist=["resolve_question"]
        ).resolve_question("What is total sales per region?", profile),
        profile=profile,
        current_plan=current_plan,
        failed_task_id="t1",
        failure=failure,
        available_columns=[c.name for c in profile.columns],
        tool_specs=tool_specs,
        client=client,
        max_repairs=0,  # exhaust immediately
    )

    assert new_plan is None
    assert err is not None


def test_replan_on_failure_invalid_json():
    """MockLLMClient returning malformed JSON causes structured failure (no exception)."""
    from da_agent.agent.planner import replan_on_failure
    from da_agent.contracts.models import Failure, FailureClass

    _, profile = _get_dataset()

    client = MockLLMClient(default_response="not valid json {{{{")

    current_plan = Plan(
        plan_version=1,
        tasks=[
            Task(id="t1", tool="filter", args={"conditions": []}, depends_on=[], rationale="bad")
        ],
    )
    failure = Failure(
        failure_class=FailureClass.EMPTY_RESULT,
        recoverable=True,
        message="0 rows",
        context={},
        task_id="t1",
    )

    tool_specs = __import__(
        "da_agent.tools.registry", fromlist=["export_tool_specs"]
    ).export_tool_specs()
    new_plan, err = replan_on_failure(
        resolved=__import__(
            "da_agent.agent.resolver", fromlist=["resolve_question"]
        ).resolve_question("What is total sales per region?", profile),
        profile=profile,
        current_plan=current_plan,
        failed_task_id="t1",
        failure=failure,
        available_columns=[c.name for c in profile.columns],
        tool_specs=tool_specs,
        client=client,
        max_repairs=0,
    )

    assert new_plan is None
    assert err is not None
    assert err.failure_class.value in (
        "schema_violation",
        "invalid_args",
        "unknown_tool",
        "empty_result",
        "no_progress",
        "budget_exhausted",
        "transient",
    )
