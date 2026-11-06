"""Tests for the M4 fixed-workflow baseline."""

from pathlib import Path

from da_agent.agent.baseline import BASELINE_TASKS, run_baseline
from da_agent.core.config import load_config
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET = Path("Sample-Superstore.csv")


def test_fixed_task_mapping_covers_benchmark() -> None:
    assert set(BASELINE_TASKS) == {f"q{i:02d}" for i in range(1, 21)}


def test_baseline_runs_all_benchmark_questions() -> None:
    df = load_data(DATASET)
    profile = compute_profile(df, file_path=DATASET)
    budgets = load_config().budgets

    run = run_baseline(df=df, profile=profile, budgets=budgets)

    assert len(run.answers) == 20
    assert len(run.evidence) == 20
    assert run.failures == {}
    assert run.report.status.status == "complete"
