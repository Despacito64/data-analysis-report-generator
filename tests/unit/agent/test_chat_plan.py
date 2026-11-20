"""Chat plan augmentation for filter-only drill-downs."""

from pathlib import Path

from da_agent.agent.chat_plan import (
    augment_chat_plan,
    infer_metric_from_thread,
    plan_needs_analysis_augment,
)
from da_agent.agent.planner import Plan
from da_agent.contracts.models import Task
from da_agent.core.chat_thread import ChatThread, append_user_message
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET = Path("Sample-Superstore.csv")


def _profile():
    return compute_profile(load_data(DATASET), file_path=DATASET)


def test_infer_metric_from_prior_user_question() -> None:
    thread = append_user_message(ChatThread(), "What are total sales by category?")
    assert infer_metric_from_thread(thread, "tell me more about furniture") == ("Sales", "sum")


def test_augment_appends_group_aggregate_after_filter() -> None:
    profile = _profile()
    thread = append_user_message(ChatThread(), "What are total sales by category?")
    plan = Plan(
        plan_version=1,
        tasks=[
            Task(
                id="t1",
                tool="filter",
                args={
                    "conditions": [{"column": "Category", "operator": "eq", "value": "Furniture"}]
                },
                depends_on=[],
                rationale="Filter to Furniture.",
            )
        ],
    )
    assert plan_needs_analysis_augment(plan)
    out = augment_chat_plan(
        plan,
        profile=profile,
        thread=thread,
        question="tell me more about furniture",
        filter_hints=[],
    )
    assert len(out.tasks) == 2
    assert out.tasks[1].tool == "group_aggregate"
    assert out.tasks[1].depends_on == ["t1"]
    assert out.tasks[1].args["metric_column"] == "Sales"


def _filter_only_plan(column: str, value: str) -> Plan:
    return Plan(
        plan_version=1,
        tasks=[
            Task(
                id="t1",
                tool="filter",
                args={"conditions": [{"column": column, "operator": "eq", "value": value}]},
                depends_on=[],
                rationale="filter",
            )
        ],
    )


def test_count_question_is_not_augmented() -> None:
    plan = _filter_only_plan("Region", "West")
    question = "How many rows are in the 'West' region?"
    out = augment_chat_plan(
        plan,
        profile=_profile(),
        thread=append_user_message(ChatThread(), question),
        question=question,
        filter_hints=[],
    )
    assert [t.tool for t in out.tasks] == ["filter"]


def test_plain_total_question_gets_overall_total_not_a_breakdown() -> None:
    plan = _filter_only_plan("Ship Mode", "First Class")
    question = "What is the total sales for orders shipped via 'First Class'?"
    out = augment_chat_plan(
        plan,
        profile=_profile(),
        thread=append_user_message(ChatThread(), question),
        question=question,
        filter_hints=[],
    )
    assert out.tasks[-1].tool == "group_aggregate"
    assert out.tasks[-1].args["by"] == []


def test_filter_then_trend_is_not_augmented() -> None:
    plan = _filter_only_plan("Region", "West")
    plan = plan.model_copy(
        update={
            "tasks": [
                *plan.tasks,
                Task(
                    id="t2",
                    tool="trend",
                    args={
                        "date_column": "Order Date",
                        "metric_column": "Sales",
                        "grain": "monthly",
                        "aggregation": "sum",
                    },
                    depends_on=["t1"],
                    rationale="trend",
                ),
            ]
        }
    )
    assert not plan_needs_analysis_augment(plan)
