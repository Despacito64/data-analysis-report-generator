"""Unified execution pipeline for the fixed baseline and dynamic agent."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from da_agent.agent.baseline import BaselineRun
from da_agent.agent.baseline import run_baseline as _run_baseline
from da_agent.contracts.models import Budgets, DatasetProfile
from da_agent.core.config import load_config
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
