"""Deterministic chat-plan repairs when the model stops at filter-only steps."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from da_agent.contracts.models import DatasetProfile, FilterSpec, SemanticType, Task

if TYPE_CHECKING:
    from da_agent.agent.planner import Plan
from da_agent.core.chat_thread import ChatThread

_ANALYTIC_TOOLS = frozenset(
    {
        "group_aggregate",
        "rank",
        "period_compare",
        "segment_contribution",
        "share_of_total",
        "concentration",
        "pareto",
        "compare_groups",
    }
)

_METRIC_HINTS: tuple[tuple[str, str, str], ...] = (
    (r"\bsales\b", "Sales", "sum"),
    (r"\bprofit\b", "Profit", "sum"),
    (r"\bquantity\b", "Quantity", "sum"),
    (r"\bdiscount\b", "Discount", "sum"),
)


def infer_metric_from_thread(thread: ChatThread, question: str) -> tuple[str, str]:
    """Pick metric column and aggregation from the thread or current question."""
    blob = question.lower()
    for msg in reversed(thread.messages):
        if msg.metric_column:
            return msg.metric_column, msg.aggregation or "sum"
        if msg.role == "user":
            blob = f"{msg.text.lower()} {blob}"
        if msg.role == "assistant" and msg.summary:
            blob = f"{msg.summary.lower()} {blob}"
            match = re.search(
                r"([\w ][\w ]*?)\s*\((sum|mean|count|min|max)\)", msg.summary, re.IGNORECASE
            )
            if match:
                return match.group(1).strip(), match.group(2).lower()
    for pattern, column, agg in _METRIC_HINTS:
        if re.search(pattern, blob):
            return column, agg
    return "Sales", "sum"


def _profile_metric_column(profile: DatasetProfile, preferred: str) -> str:
    names = {c.name for c in profile.columns}
    if preferred in names:
        return preferred
    for col in profile.columns:
        if col.semantic_type == SemanticType.MEASURE and col.name in names:
            return col.name
    return preferred


def plan_needs_analysis_augment(plan: Plan) -> bool:
    if len(plan.tasks) == 1 and plan.tasks[0].tool == "filter":
        return True
    filters = [t for t in plan.tasks if t.tool == "filter"]
    for ftask in filters:
        has_analytic_child = any(
            ftask.id in t.depends_on and t.tool in _ANALYTIC_TOOLS for t in plan.tasks
        )
        if not has_analytic_child:
            return True
    return False


def augment_chat_plan(
    plan: Plan,
    *,
    profile: DatasetProfile,
    thread: ChatThread,
    question: str,
    filter_hints: list[FilterSpec],
) -> Plan:
    """Append group_aggregate after filter-only plans for drill-down questions."""
    if not plan_needs_analysis_augment(plan):
        return plan
    filter_task = next((t for t in reversed(plan.tasks) if t.tool == "filter"), None)
    conditions = (filter_task.args.get("conditions") if filter_task else None) or []
    if not conditions and filter_hints:
        conditions = [
            {"column": h.column, "operator": h.operator, "value": h.value} for h in filter_hints
        ]
    if not conditions or filter_task is None:
        return plan
    group_col = str(conditions[0].get("column", ""))
    if not group_col:
        return plan
    metric, agg = infer_metric_from_thread(thread, question)
    metric = _profile_metric_column(profile, metric)
    existing_ids = {t.id for t in plan.tasks}
    suffix = 2
    while f"t{suffix}" in existing_ids:
        suffix += 1
    new_task = Task(
        id=f"t{suffix}",
        tool="group_aggregate",
        args={
            "by": [group_col],
            "metric_column": metric,
            "aggregation": agg,
        },
        depends_on=[filter_task.id],
        rationale=f"Aggregate {metric} ({agg}) for the filtered {group_col} slice.",
    )
    return plan.model_copy(update={"tasks": [*plan.tasks, new_task]})
