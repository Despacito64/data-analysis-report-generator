"""Unit tests for the M5 question resolver (src/da_agent/agent/resolver.py)."""

from pathlib import Path

import pytest

from da_agent.agent.resolver import map_columns, resolve_question
from da_agent.contracts.models import DatasetProfile
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET = Path("Sample-Superstore.csv")


@pytest.fixture(scope="module")
def superstore_profile() -> DatasetProfile:
    df = load_data(DATASET)
    return compute_profile(df, file_path=DATASET)


def test_map_columns_exact_and_alias(superstore_profile: DatasetProfile) -> None:
    # Exact match
    cols = map_columns("total Sales and Profit", superstore_profile)
    assert "Sales" in cols
    assert "Profit" in cols

    # Case-insensitive
    cols = map_columns("total sales by category", superstore_profile)
    assert "Sales" in cols
    assert "Category" in cols

    # Alias matching: "date" -> "Order Date"
    cols = map_columns("sales by date", superstore_profile)
    assert "Sales" in cols
    assert "Order Date" in cols


def test_map_columns_rejects_hallucinated_columns(superstore_profile: DatasetProfile) -> None:
    cols = map_columns("warehouse inventory and employee salary", superstore_profile)
    # None of these exist in Superstore
    assert "warehouse" not in cols
    assert "inventory" not in cols
    assert "salary" not in cols
    assert len(cols) == 0


def test_unanswerable_nonexistent_data(superstore_profile: DatasetProfile) -> None:
    res = resolve_question("What is the average employee salary by department?", superstore_profile)
    assert not res.answerable
    assert res.decline_reason is not None
    assert (
        "does not contain" in res.decline_reason.lower()
        or "unanswerable" in res.decline_reason.lower()
    )


def test_out_of_scope_forecasting(superstore_profile: DatasetProfile) -> None:
    res = resolve_question("Forecast sales for the next 12 months", superstore_profile)
    assert not res.answerable
    assert res.decline_reason is not None
    assert "forecasting" in res.decline_reason.lower() or "predict" in res.decline_reason.lower()


def test_out_of_scope_causal_inference(superstore_profile: DatasetProfile) -> None:
    res = resolve_question(
        "What caused the decline in profit in the Central region?", superstore_profile
    )
    assert not res.answerable
    assert res.decline_reason is not None
    assert "causal" in res.decline_reason.lower() or "cause" in res.decline_reason.lower()


def test_out_of_scope_ml_training(superstore_profile: DatasetProfile) -> None:
    res = resolve_question(
        "Train a machine learning classifier to predict customer churn", superstore_profile
    )
    assert not res.answerable
    assert res.decline_reason is not None
    assert "machine learning" in res.decline_reason.lower() or "train" in res.decline_reason.lower()


def test_ambiguity_records_assumption(superstore_profile: DatasetProfile) -> None:
    res = resolve_question("What are the sales?", superstore_profile)
    assert res.answerable
    assert len(res.ambiguity_decisions) > 0
    decision = res.ambiguity_decisions[0]
    assert decision.field == "metric" or decision.field == "aggregation"
    assert decision.assumption is not None


def test_completely_vague_question_declined(superstore_profile: DatasetProfile) -> None:
    res = resolve_question("Tell me something interesting about the business", superstore_profile)
    assert not res.answerable
    assert res.decline_reason is not None


@pytest.mark.parametrize(
    ("question", "expected_intent", "expected_metric_col", "expected_answerable"),
    [
        ("What is the total sales for orders shipped via 'First Class'?", "filter", "Sales", True),
        (
            "How many rows in the dataset are in the 'Technology' category in the 'West' region?",
            "filter",
            None,
            True,
        ),
        ("What is the total sales for each Region?", "group_aggregate", "Sales", True),
        ("What is the total profit for each Segment?", "group_aggregate", "Profit", True),
        ("What is the average discount across each Category?", "group_aggregate", "Discount", True),
        ("What are the top 5 Sub-Categories ranked by total Sales?", "rank", "Sales", True),
        ("What are the top 3 States ranked by total Profit?", "rank", "Profit", True),
        ("What are the bottom 5 Sub-Categories ranked by total Profit?", "rank", "Profit", True),
        (
            "Compare total sales between 2016-01-01 to 2016-12-31 and 2017-01-01 to 2017-12-31.",
            "period_compare",
            "Sales",
            True,
        ),
        (
            "Compare total profit between 2015-01-01 to 2015-12-31 and 2016-01-01 to 2016-12-31.",
            "period_compare",
            "Profit",
            True,
        ),
        ("What is the monthly trend and direction of sales in 2017?", "trend", "Sales", True),
        ("What is the quarterly trend of profit over the entire dataset?", "trend", "Profit", True),
        (
            "What is the share of total sales contributed by each Category?",
            "segment_contribution",
            "Sales",
            True,
        ),
        (
            "What is the share of total sales contributed by each Region?",
            "segment_contribution",
            "Sales",
            True,
        ),
        (
            "What is the Pearson correlation between Discount and Profit across all orders?",
            "correlation",
            "Discount",
            True,
        ),
        (
            "What is the Pearson correlation between Sales and Profit across all orders?",
            "correlation",
            "Sales",
            True,
        ),
        (
            "Detect anomalies in Sales using the 1.5 x IQR rule.",
            "detect_anomalies_iqr",
            "Sales",
            True,
        ),
        (
            "Detect anomalies in Profit using the 1.5 x IQR rule.",
            "detect_anomalies_iqr",
            "Profit",
            True,
        ),
        (
            "In the 'East' region, what is the total profit for each Category?",
            "multistep",
            "Profit",
            True,
        ),
        (
            "In the 'Consumer' segment, what are the top 3 Cities by total sales?",
            "multistep",
            "Sales",
            True,
        ),
    ],
)
def test_phrasings_table_resolution(
    superstore_profile: DatasetProfile,
    question: str,
    expected_intent: str,
    expected_metric_col: str | None,
    expected_answerable: bool,
) -> None:
    res = resolve_question(question, superstore_profile)
    assert res.answerable == expected_answerable
    assert res.intent == expected_intent
    if expected_metric_col:
        assert expected_metric_col in (res.metric or "")
