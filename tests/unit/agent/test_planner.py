"""Unit tests for plan generation and bounded repair (src/da_agent/agent/planner.py)."""

from pathlib import Path

import pytest

from da_agent.agent.planner import (
    MockLLMClient,
    Plan,
    build_system_prompt,
    generate_plan,
)
from da_agent.contracts.models import DatasetProfile, FailureClass
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.tools.registry import DEFAULT_REGISTRY

DATASET = Path("Sample-Superstore.csv")


@pytest.fixture(scope="module")
def profile() -> DatasetProfile:
    df = load_data(DATASET)
    return compute_profile(df, file_path=DATASET)


def test_build_system_prompt_does_not_contain_benchmark_questions(profile: DatasetProfile) -> None:
    prompt = build_system_prompt(profile, DEFAULT_REGISTRY.export_tool_specs())
    # Benchmark questions check
    assert "First Class" not in prompt
    assert "Technology" not in prompt or "Product Name" in prompt  # Technology in West is q02
    assert "Pearson correlation between Discount and Profit" not in prompt
    assert "1.5 x IQR rule" not in prompt


def test_planner_success_single_turn(profile: DatasetProfile, tmp_path: Path) -> None:
    valid_tasks = {
        "tasks": [
            {
                "id": "t1",
                "tool": "filter",
                "args": {
                    "conditions": [
                        {"column": "Ship Mode", "operator": "eq", "value": "First Class"}
                    ]
                },
                "depends_on": [],
                "rationale": "Filter to First Class shipments",
            }
        ]
    }
    client = MockLLMClient(responses=[valid_tasks])
    writer = RunTraceWriter(run_id="test_plan_001", base_dir=tmp_path)

    plan, failure = generate_plan(
        question="What is the total sales for First Class?",
        profile=profile,
        client=client,
        trace_writer=writer,
    )

    assert failure is None
    assert isinstance(plan, Plan)
    assert len(plan.tasks) == 1
    assert plan.tasks[0].tool == "filter"

    # Check trace contents
    events = writer.read_events()
    event_types = [e.event_type for e in events]
    assert "planner_llm_call" in event_types
    assert "plan" in event_types


def test_planner_repairs_hallucinated_column(profile: DatasetProfile, tmp_path: Path) -> None:
    # First turn: hallucinated column "InventedCol"
    bad_tasks = {
        "tasks": [
            {
                "id": "t1",
                "tool": "filter",
                "args": {
                    "conditions": [{"column": "InventedCol", "operator": "eq", "value": "Val"}]
                },
                "depends_on": [],
                "rationale": "Bad column",
            }
        ]
    }
    # Second turn: repaired to valid "Region"
    good_tasks = {
        "tasks": [
            {
                "id": "t1",
                "tool": "filter",
                "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
                "depends_on": [],
                "rationale": "Valid column",
            }
        ]
    }
    client = MockLLMClient(responses=[bad_tasks, good_tasks])
    writer = RunTraceWriter(run_id="test_repair_col", base_dir=tmp_path)

    plan, failure = generate_plan(
        question="Filter to West region",
        profile=profile,
        client=client,
        trace_writer=writer,
        max_repairs=1,
    )

    assert failure is None
    assert isinstance(plan, Plan)
    assert len(plan.tasks) == 1
    assert plan.tasks[0].args["conditions"][0]["column"] == "Region"

    # Verify repair event logged
    events = writer.read_events()
    event_types = [e.event_type for e in events]
    assert "planner_validation_failure" in event_types
    assert "planner_repair_attempt" in event_types
    assert "plan" in event_types


def test_planner_repairs_circular_dependency(profile: DatasetProfile) -> None:
    bad_cycle = {
        "tasks": [
            {
                "id": "t1",
                "tool": "filter",
                "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
                "depends_on": ["t1"],
                "rationale": "Self cycle",
            }
        ]
    }
    good_acyclic = {
        "tasks": [
            {
                "id": "t1",
                "tool": "filter",
                "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
                "depends_on": [],
                "rationale": "Acyclic",
            }
        ]
    }
    client = MockLLMClient(responses=[bad_cycle, good_acyclic])
    plan, failure = generate_plan(
        question="Filter West region",
        profile=profile,
        client=client,
        max_repairs=1,
    )

    assert failure is None
    assert isinstance(plan, Plan)
    assert plan.tasks[0].depends_on == []


def test_planner_exhausts_repairs_on_malformed_json(profile: DatasetProfile) -> None:
    client = MockLLMClient(responses=["Not valid json at all", "Still definitely not json"])
    plan, failure = generate_plan(
        question="Show sales",
        profile=profile,
        client=client,
        max_repairs=1,
    )

    assert plan is None
    assert failure is not None
    assert failure.failure_class == FailureClass.SCHEMA_VIOLATION
    assert len(client.call_history) == 2  # Initial call + 1 repair


def test_planner_exhausts_repairs_on_hallucinated_tool(profile: DatasetProfile) -> None:
    bad_tool = {
        "tasks": [
            {
                "id": "t1",
                "tool": "magical_crystal_ball",
                "args": {"prophesy": True},
                "depends_on": [],
                "rationale": "Predict with crystal ball",
            }
        ]
    }
    client = MockLLMClient(responses=[bad_tool, bad_tool])
    plan, failure = generate_plan(
        question="Analyze sales",
        profile=profile,
        client=client,
        max_repairs=1,
    )

    assert plan is None
    assert failure is not None
    assert failure.failure_class == FailureClass.UNKNOWN_TOOL


def test_planner_exceeds_max_steps_fails(profile: DatasetProfile) -> None:
    excess_tasks = {
        "tasks": [
            {
                "id": f"t{i}",
                "tool": "filter",
                "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
                "depends_on": [],
                "rationale": f"Step {i}",
            }
            for i in range(1, 8)
        ]
    }
    client = MockLLMClient(responses=[excess_tasks, excess_tasks])
    plan, failure = generate_plan(
        question="Filter sales in West region",
        profile=profile,
        client=client,
        max_steps=5,
        max_repairs=1,
    )

    assert plan is None
    assert failure is not None
    assert "exceeds maximum step limit" in failure.message.lower()


def test_unanswerable_question_fails_immediately_without_llm(profile: DatasetProfile) -> None:
    client = MockLLMClient()
    plan, failure = generate_plan(
        question="What is the employee salary and payroll?",
        profile=profile,
        client=client,
    )

    assert plan is None
    assert failure is not None
    assert len(client.call_history) == 0  # LLM never invoked for unanswerable question
