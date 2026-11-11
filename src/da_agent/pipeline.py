"""Unified execution pipeline for the fixed baseline and dynamic agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from da_agent.agent.baseline import BaselineRun
from da_agent.agent.baseline import run_baseline as _run_baseline
from da_agent.agent.executor import TaskExecutionRecord
from da_agent.agent.graph import run_agent as _run_agent
from da_agent.agent.planner import LLMClient, OllamaClient, Plan, generate_plan
from da_agent.contracts.models import (
    Budgets,
    DatasetProfile,
    ExecutionStatus,
    Failure,
    PlanRevision,
    ResolvedQuestion,
)
from da_agent.core.config import AppConfig, load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile


class AgentResult(BaseModel):
    """Typed output from a complete dynamic-agent pipeline run."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: ExecutionStatus
    resolved_question: ResolvedQuestion | None = None
    plan: Plan | None = None
    task_results: list[TaskExecutionRecord] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    failures: list[Failure] = Field(default_factory=list)
    revisions: list[PlanRevision] = Field(default_factory=list)
    final_answer: dict[str, Any] = Field(default_factory=dict)


def run_baseline(
    *,
    df: pd.DataFrame | None = None,
    dataset_path: Path | str | None = None,
    profile: DatasetProfile | None = None,
    budgets: Budgets | None = None,
) -> BaselineRun:
    """Run the deterministic fixed-workflow baseline."""
    if df is None:
        if dataset_path is None:
            dataset_path = Path("Sample-Superstore.csv")
        df = load_data(Path(dataset_path))
    if profile is None:
        profile = compute_profile(df, file_path=Path(dataset_path) if dataset_path else None)
    if budgets is None:
        budgets = load_config().budgets

    return _run_baseline(df=df, profile=profile, budgets=budgets)


def plan_question(
    question: str,
    *,
    df: pd.DataFrame | None = None,
    dataset_path: Path | str | None = None,
    profile: DatasetProfile | None = None,
    client: LLMClient | None = None,
    run_id: str | None = None,
    trace_writer: RunTraceWriter | None = None,
    max_steps: int = 5,
    max_repairs: int = 1,
) -> tuple[Plan | None, Failure | None]:
    """Generate and validate an analytical execution plan for a question.

    Returns (validated_plan, None) on success or (None, failure) on validation failure.
    Audit records including raw LLM output, validation failures, repair attempts,
    and final plan are persisted to the run trace.
    """
    if profile is None:
        if df is None:
            if dataset_path is None:
                dataset_path = Path("Sample-Superstore.csv")
            df = load_data(Path(dataset_path))
        profile = compute_profile(df, file_path=Path(dataset_path) if dataset_path else None)

    if trace_writer is None and run_id is not None:
        trace_writer = RunTraceWriter(run_id=run_id)

    return generate_plan(
        question=question,
        profile=profile,
        client=client,
        trace_writer=trace_writer,
        max_steps=max_steps,
        max_repairs=max_repairs,
    )


def run_agent(
    question: str,
    dataset: pd.DataFrame | Path | str | None = None,
    config: AppConfig | None = None,
    client: LLMClient | None = None,
    *,
    df: pd.DataFrame | None = None,
    dataset_path: Path | str | None = None,
    profile: DatasetProfile | None = None,
    run_id: str | None = None,
    budgets: Budgets | None = None,
    trace_writer: RunTraceWriter | None = None,
    max_replans: int | None = None,
) -> AgentResult:
    """Run a free-text question through the dynamic graph and return typed results."""
    config = config or load_config()
    if dataset is not None and (df is not None or dataset_path is not None):
        raise ValueError("Provide `dataset` or `df`/`dataset_path`, not both")
    if isinstance(dataset, pd.DataFrame):
        df = dataset
    elif dataset is not None:
        dataset_path = Path(dataset)

    if df is None:
        if dataset_path is None:
            dataset_path = Path("Sample-Superstore.csv")
        df = load_data(Path(dataset_path))
    if profile is None:
        profile = compute_profile(df, file_path=Path(dataset_path) if dataset_path else None)
    if budgets is None:
        budgets = config.budgets
    if run_id is None:
        run_id = uuid4().hex
    if trace_writer is None:
        trace_writer = RunTraceWriter(
            run_id=run_id,
            base_dir=config.run_trace.base_dir,
        )

    if client is None:
        client = OllamaClient(
            base_url=config.model.base_url,
            model=config.model.name,
            temperature=config.model.temperature,
            seed=config.model.seed,
            timeout_s=config.budgets.per_call_timeout_s,
        )

    state = _run_agent(
        question=question,
        df=df,
        profile=profile,
        run_id=run_id,
        llm_client=client,
        budgets=budgets,
        trace_writer=trace_writer,
        max_replans=max_replans,
    )
    return AgentResult(
        run_id=run_id,
        status=ExecutionStatus(state["status"]),
        resolved_question=state.get("resolved"),
        plan=state.get("plan"),
        task_results=state.get("executed_records", []),
        evidence_ids=state.get("evidence_ids", []),
        failures=state.get("failures", []),
        revisions=state.get("revisions", []),
        final_answer=state.get("final_answer") or {},
    )
