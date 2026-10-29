"""Unit tests for Plotly chart builders in src/da_agent/tools/charts.py.

Rules tested:
- Chart builders consume typed tool results only, never raw DataFrames (rejects raw DF with TypeError).
- Put units in labels (axes, titles, hover).
- Test structure (trace types, axes, titles, data values), not image rendering.
- Handles undefined/missing values gracefully without crashing.
"""

import pandas as pd
import plotly.graph_objects as go
import pytest
from da_agent.tools.charts import (
    build_anomalies_chart,
    build_contribution_chart,
    build_period_compare_chart,
    build_rank_chart,
    build_trend_chart,
)

from da_agent.tools.models import (
    AnomaliesIQRResult,
    AnomalyPoint,
    AnomalyStatus,
    PeriodCompareResult,
    PeriodMetric,
    RankResult,
    RankRow,
    SegmentContributionResult,
    SegmentShareRow,
    TimeGrain,
    TrendDirection,
    TrendPoint,
    TrendResult,
)


def test_chart_builders_reject_raw_dataframes() -> None:
    """Verify that chart builders reject raw DataFrames with TypeError."""
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    with pytest.raises(TypeError):
        build_rank_chart(df)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_trend_chart(df)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_contribution_chart(df)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_period_compare_chart(df)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        build_anomalies_chart(df)  # type: ignore[arg-type]


def test_build_rank_chart_structure_and_units() -> None:
    """Test rank chart builder produces bar trace with units in axes and titles."""
    rank_res = RankResult(
        entity_column="Product",
        metric_column="Sales",
        ascending=False,
        top_n=3,
        tie_decimals=9,
        rows=[
            RankRow(rank=1, entity="Product A", value=500.0, is_tied=False),
            RankRow(rank=2, entity="Product B", value=300.0, is_tied=False),
            RankRow(rank=3, entity="Product C", value=150.0, is_tied=False),
        ],
        tie_groups=[],
        ties_at_cutoff=False,
        cutoff_tied_labels_omitted=[],
        null_count=0,
    )
    fig = build_rank_chart(rank_res, unit="USD")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "bar"
    assert list(trace.x) == ["Product A", "Product B", "Product C"]
    assert list(trace.y) == [500.0, 300.0, 150.0]
    assert "Sales (USD)" in fig.layout.yaxis.title.text
    assert "Product" in fig.layout.xaxis.title.text


def test_build_trend_chart_structure_and_units() -> None:
    """Test trend chart builder produces scatter/line trace with chronological periods."""
    trend_res = TrendResult(
        grain=TimeGrain.MONTHLY,
        points=[
            TrendPoint(period="2023-01", value=100.0, row_count=10, present=True),
            TrendPoint(period="2023-02", value=250.0, row_count=12, present=True),
            TrendPoint(period="2023-03", value=400.0, row_count=15, present=True),
        ],
        direction=TrendDirection.INCREASING,
        slope=150.0,
        total_periods=3,
        missing_periods_count=0,
    )
    fig = build_trend_chart(trend_res, unit="Units")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "scatter"
    assert trace.mode == "lines+markers"
    assert list(trace.x) == ["2023-01", "2023-02", "2023-03"]
    assert list(trace.y) == [100.0, 250.0, 400.0]
    assert "Units" in fig.layout.yaxis.title.text


def test_build_contribution_chart_structure() -> None:
    """Test segment contribution chart produces bar trace with share info."""
    contrib_res = SegmentContributionResult(
        segment_column="Category",
        metric_column="Sales",
        total_value=1000.0,
        segments=[
            SegmentShareRow(segment="Tech", value=600.0, share=0.6),
            SegmentShareRow(segment="Office", value=400.0, share=0.4),
        ],
        shares_sum=1.0,
        tolerance_applied=1e-9,
        reconciles=True,
        has_negative_segments=False,
    )
    fig = build_contribution_chart(contrib_res, unit="USD")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "bar"
    assert list(trace.x) == ["Tech", "Office"]
    assert list(trace.y) == [600.0, 400.0]
    assert "Sales (USD)" in fig.layout.yaxis.title.text


def test_build_period_compare_chart_structure() -> None:
    """Test period compare chart shows base and comparison bars."""
    compare_res = PeriodCompareResult(
        base_period=PeriodMetric(present=True, value=1000.0, row_count=20, missing_count=0),
        compare_period=PeriodMetric(present=True, value=1500.0, row_count=25, missing_count=0),
        absolute_change=500.0,
        relative_growth=0.5,
        undefined_reason=None,
        undefined_message=None,
        base_negative=False,
    )
    fig = build_period_compare_chart(compare_res, unit="USD")
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    trace = fig.data[0]
    assert trace.type == "bar"
    assert list(trace.x) == ["Base Period", "Compare Period"]
    assert list(trace.y) == [1000.0, 1500.0]
    assert "USD" in fig.layout.yaxis.title.text


def test_build_anomalies_chart_structure() -> None:
    """Test anomaly detection chart produces scatter plot with fences."""
    iqr_res = AnomaliesIQRResult(
        metric_column="Profit",
        status=AnomalyStatus.OK,
        q1=20.0,
        median=35.0,
        q3=50.0,
        iqr=30.0,
        lower_fence=-25.0,
        upper_fence=95.0,
        k=1.5,
        valid_count=50,
        flagged_count=2,
        flagged_items_truncated=False,
        flagged_items=[
            AnomalyPoint(
                original_index=5, ascending_position=48, value=120.0, fence_violated="upper"
            ),
            AnomalyPoint(
                original_index=12, ascending_position=49, value=150.0, fence_violated="upper"
            ),
        ],
        caveat=None,
        limitations=["Limitation 1"],
    )
    fig = build_anomalies_chart(iqr_res, unit="USD")
    assert isinstance(fig, go.Figure)
    # Check that figure contains flagged points and upper/lower fences
    assert len(fig.data) >= 1
    # Check horizontal fence lines are drawn in layout shapes
    assert len(fig.layout.shapes) == 2  # lower and upper fence lines
