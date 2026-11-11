"""Unified execution pipeline for the fixed baseline and dynamic agent."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from da_agent.agent.baseline import BaselineRun
from da_agent.agent.baseline import run_baseline as _run_baseline
from da_agent.agent.planner import LLMClient, Plan, generate_plan
from da_agent.contracts.models import Budgets, DatasetProfile, Failure
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile


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
