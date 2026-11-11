"""Shared state for the dynamic planning agent.

Layer 6 module: defines the typed state passed between LangGraph nodes during execution.
Never imports evaluation/oracle or da_agent.agent.baseline.
"""

from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd

from da_agent.agent.executor import PlanExecutionResult, TaskExecutionRecord
from da_agent.agent.planner import Plan
from da_agent.contracts.models import (
    Budgets,
    DatasetProfile,
    Failure,
    PlanRevision,
    ResolvedQuestion,
)


class AgentState(TypedDict, total=False):
    """Shared state carrying all analysis context, plan, evidence, and execution records."""

    question: str
    df: pd.DataFrame
    profile: DatasetProfile
    resolved: ResolvedQuestion | None
    plan: Plan | None
    plan_version: int
    revisions: list[PlanRevision]
    executed_records: list[TaskExecutionRecord]
    evidence_store: dict[str, Any]
    evidence_ids: list[str]
    failures: list[Failure]
    budgets: Budgets
    replan_count: int
    max_replans: int
    status: str  # "complete" | "partial" | "failed"
    final_answer: Any | None
    run_id: str
    last_exec_result: PlanExecutionResult | None
    failed_task_id: str | None
