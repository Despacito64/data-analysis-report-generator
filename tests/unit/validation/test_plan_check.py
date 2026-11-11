"""Unit tests for plan validation (src/da_agent/validation/plan_check.py)."""

from pathlib import Path

import pytest

from da_agent.contracts.models import DatasetProfile, FailureClass, Task
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.tools.registry import DEFAULT_REGISTRY
from da_agent.validation.plan_check import validate_plan

DATASET = Path("Sample-Superstore.csv")


@pytest.fixture(scope="module")
def profile() -> DatasetProfile:
    df = load_data(DATASET)
    return compute_profile(df, file_path=DATASET)


@pytest.fixture(scope="module")
def tool_args_models() -> dict:
    return {
        name: DEFAULT_REGISTRY.get(name).args_model
        for name in DEFAULT_REGISTRY.list_tools()
        if DEFAULT_REGISTRY.get(name) is not None
    }


def test_valid_single_task_plan(profile: DatasetProfile, tool_args_models: dict) -> None:
    task = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Ship Mode", "operator": "eq", "value": "First Class"}]},
        depends_on=[],
        rationale="Filter to First Class shipments",
    )
    failures = validate_plan([task], profile, tool_args_models=tool_args_models)
    assert len(failures) == 0


def test_valid_multistep_plan(profile: DatasetProfile, tool_args_models: dict) -> None:
    t1 = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
        depends_on=[],
        rationale="Filter to West region",
    )
    t2 = Task(
        id="t2",
        tool="group_aggregate",
        args={"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
        depends_on=["t1"],
        rationale="Aggregate sales by category in West",
    )
    failures = validate_plan([t1, t2], profile, tool_args_models=tool_args_models)
    assert len(failures) == 0


def test_empty_plan_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    failures = validate_plan([], profile, tool_args_models=tool_args_models)
    assert len(failures) == 1
    assert "no tasks" in failures[0].message.lower()


def test_plan_exceeding_max_steps_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    tasks = [
        Task(
            id=f"t{i}",
            tool="filter",
            args={"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
            depends_on=[],
            rationale=f"Task {i}",
        )
        for i in range(1, 7)
    ]
    failures = validate_plan(tasks, profile, tool_args_models=tool_args_models, max_steps=5)
    assert any("exceeds maximum" in f.message.lower() for f in failures)


def test_self_dependency_cycle_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    task = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Ship Mode", "operator": "eq", "value": "First Class"}]},
        depends_on=["t1"],
        rationale="Self depending task",
    )
    failures = validate_plan([task], profile, tool_args_models=tool_args_models)
    assert len(failures) > 0
    assert any("cycle" in f.message.lower() for f in failures)


def test_mutual_dependency_cycle_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    t1 = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
        depends_on=["t2"],
        rationale="Task 1",
    )
    t2 = Task(
        id="t2",
        tool="filter",
        args={"conditions": [{"column": "Category", "operator": "eq", "value": "Technology"}]},
        depends_on=["t1"],
        rationale="Task 2",
    )
    failures = validate_plan([t1, t2], profile, tool_args_models=tool_args_models)
    assert any("cycle" in f.message.lower() for f in failures)


def test_missing_dependency_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    task = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Ship Mode", "operator": "eq", "value": "First Class"}]},
        depends_on=["nonexistent_task"],
        rationale="Task with nonexistent parent",
    )
    failures = validate_plan([task], profile, tool_args_models=tool_args_models)
    assert any("nonexistent" in f.message.lower() for f in failures)


def test_no_ready_task_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    t1 = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]},
        depends_on=["t2"],
        rationale="Task 1",
    )
    t2 = Task(
        id="t2",
        tool="filter",
        args={"conditions": [{"column": "Category", "operator": "eq", "value": "Technology"}]},
        depends_on=["t3"],
        rationale="Task 2",
    )
    failures = validate_plan([t1, t2], profile, tool_args_models=tool_args_models)
    assert len(failures) > 0


def test_hallucinated_tool_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    task = Task(
        id="t1",
        tool="invented_magic_tool",
        args={"some_arg": 123},
        depends_on=[],
        rationale="Fake tool",
    )
    failures = validate_plan([task], profile, tool_args_models=tool_args_models)
    assert any(f.failure_class == FailureClass.UNKNOWN_TOOL for f in failures)


def test_hallucinated_column_fails(profile: DatasetProfile, tool_args_models: dict) -> None:
    task = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "InventedSalary", "operator": "eq", "value": 50000}]},
        depends_on=[],
        rationale="Fake column",
    )
    failures = validate_plan([task], profile, tool_args_models=tool_args_models)
    assert any("does not exist" in f.message.lower() for f in failures)
