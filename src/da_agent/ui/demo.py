"""Streamlit demo presets: registered benchmark + starter question (real LLM only)."""

from __future__ import annotations

from pathlib import Path

from pandas import DataFrame

from da_agent.contracts.models import DatasetProfile
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHMARK_CSV = REPO_ROOT / "Sample-Superstore.csv"
DEMO_QUESTION = "What are total sales by category?"


def load_demo_dataset() -> tuple[DataFrame, DatasetProfile]:
    """Load the registered Sample Superstore benchmark for guided demos."""
    if not BENCHMARK_CSV.is_file():
        raise FileNotFoundError(
            f"Demo dataset missing at {BENCHMARK_CSV}. "
            "Add Sample-Superstore.csv per docs/DECISIONS.md D-007."
        )
    df = load_data(BENCHMARK_CSV)
    profile = compute_profile(df, file_path=BENCHMARK_CSV)
    return df, profile
