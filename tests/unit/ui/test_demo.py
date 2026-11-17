"""Demo presets use the registered benchmark and a non-empty starter question."""

from da_agent.ui.demo import BENCHMARK_CSV, DEMO_QUESTION, load_demo_dataset
from da_agent.data.registry import BENCHMARK_SUPERSTORE


def test_demo_loads_registered_superstore() -> None:
    assert BENCHMARK_CSV.is_file()
    df, profile = load_demo_dataset()
    assert len(df) == BENCHMARK_SUPERSTORE.row_count
    assert profile.dataset_hash == BENCHMARK_SUPERSTORE.sha256_hash
    assert DEMO_QUESTION.strip()