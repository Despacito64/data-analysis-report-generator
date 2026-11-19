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
