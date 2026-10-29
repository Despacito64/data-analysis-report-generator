"""Unit tests for tool result schema and numerical invariant validation (src/da_agent/validation/results.py).

Tests schema checks and deliberate corruptions for every per-tool invariant in Table 2:
- filter: filter_row_bounds
- group_aggregate: group_aggregate_reconciliation, group_aggregate_group_count
- rank: rank_monotonicity, rank_tie_consistency, rank_cutoff_integrity, rank_null_exclusion
- period_compare: period_compare_abs_change, period_compare_growth, period_compare_undefined_reason
- trend: trend_chronological_order, trend_points_integrity
- segment_contribution: contribution_shares_sum, contribution_total_reconciliation, contribution_reconciles_flag
- correlation: correlation_bounds, correlation_status_consistency
- detect_anomalies_iqr: anomalies_fence_order, anomalies_flagged_bounds, anomalies_truncation_consistency
"""

from da_agent.contracts.models import FailureClass
from da_agent.tools.models import (
    AggregationType,
    AnomaliesIQRResult,
    AnomalyPoint,
    AnomalyStatus,
    CorrelationResult,
    CorrelationStatus,
    FilterResult,
    GroupAggregateResult,
    GroupAggregateRow,
    GrowthUndefinedReason,
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
from da_agent.validation.results import validate_tool_result


def test_schema_violation_caught() -> None:
    """Invalid result schema produces FailureClass.SCHEMA_VIOLATION with recoverable=False."""
    bad_result = {"output_row_count": "not-an-integer", "matched_indices": [1, 2]}
    valid, _, failure = validate_tool_result(
        tool_name="filter",
        result_data=bad_result,
        input_row_count=10,
        result_model=FilterResult,
    )
    assert valid is False
    assert failure is not None
    assert failure.failure_class == FailureClass.SCHEMA_VIOLATION
    assert failure.recoverable is False


def test_filter_row_bounds_invariant_corruption() -> None:
    """Corrupted filter output row count (> input_row_count) fires invariant violation."""
    corrupted_result = FilterResult(output_row_count=15, matched_indices=list(range(15)))
    valid, checked, failure = validate_tool_result(
        tool_name="filter",
        result_data=corrupted_result,
        input_row_count=10,  # input is only 10, output is 15!
        result_model=FilterResult,
    )
    assert valid is False
    assert "filter_row_bounds" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION
    assert failure.recoverable is False


def test_group_aggregate_reconciliation_corruption() -> None:
    """Corrupted group row counts failing to sum to input_row_count fires invariant."""
    corrupted_result = GroupAggregateResult(
        metric_column="Sales",
        aggregation=AggregationType.SUM,
        total_groups=2,
        rows=[
            GroupAggregateRow(
                group_keys={"Region": "East"}, value=100.0, valid_count=5, missing_count=0
            ),
            GroupAggregateRow(
                group_keys={"Region": "West"}, value=200.0, valid_count=3, missing_count=0
            ),
        ],  # sum is 8, but input_row_count is 10!
    )
    valid, checked, failure = validate_tool_result(
        tool_name="group_aggregate",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=GroupAggregateResult,
    )
    assert valid is False
    assert "group_aggregate_reconciliation" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION
    assert failure.recoverable is False


def test_rank_monotonicity_corruption() -> None:
    """Corrupted non-monotonic rank sequence fires invariant."""
    corrupted_result = RankResult(
        entity_column="Product",
        metric_column="Sales",
        ascending=False,
        top_n=None,
        tie_decimals=9,
        rows=[
            RankRow(rank=2, entity="Prod B", value=100.0, is_tied=False),  # Rank 2 before Rank 1!
            RankRow(rank=1, entity="Prod A", value=200.0, is_tied=False),
        ],
        tie_groups=[],
        ties_at_cutoff=False,
        cutoff_tied_labels_omitted=[],
        null_count=0,
    )
    valid, checked, failure = validate_tool_result(
        tool_name="rank",
        result_data=corrupted_result,
        input_row_count=2,
        result_model=RankResult,
    )
    assert valid is False
    assert "rank_monotonicity" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_rank_tie_consistency_corruption() -> None:
    """Entities sharing same rank with different values fires invariant."""
    corrupted_result = RankResult(
        entity_column="Product",
        metric_column="Sales",
        ascending=False,
        top_n=None,
        tie_decimals=9,
        rows=[
            RankRow(rank=1, entity="Prod A", value=200.0, is_tied=True),
            RankRow(rank=1, entity="Prod B", value=150.0, is_tied=True),  # Rank 1 but value 150!
        ],
        tie_groups=[],
        ties_at_cutoff=False,
        cutoff_tied_labels_omitted=[],
        null_count=0,
    )
    valid, checked, failure = validate_tool_result(
        tool_name="rank",
        result_data=corrupted_result,
        input_row_count=2,
        result_model=RankResult,
    )
    assert valid is False
    assert "rank_tie_consistency" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_period_compare_growth_corruption() -> None:
    """Manipulated relative growth fires period_compare_growth invariant."""
    corrupted_result = PeriodCompareResult(
        base_period=PeriodMetric(present=True, value=100.0, row_count=5, missing_count=0),
        compare_period=PeriodMetric(present=True, value=200.0, row_count=5, missing_count=0),
        absolute_change=100.0,
        relative_growth=5.0,  # True growth is 1.0 (100%), but manipulated to 5.0!
        undefined_reason=None,
        undefined_message=None,
        base_negative=False,
    )
    valid, checked, failure = validate_tool_result(
        tool_name="period_compare",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=PeriodCompareResult,
    )
    assert valid is False
    assert "period_compare_growth" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_period_compare_undefined_reason_corruption() -> None:
    """relative_growth present with undefined_reason set fires invariant."""
    corrupted_result = PeriodCompareResult(
        base_period=PeriodMetric(present=True, value=100.0, row_count=5, missing_count=0),
        compare_period=PeriodMetric(present=True, value=200.0, row_count=5, missing_count=0),
        absolute_change=100.0,
        relative_growth=1.0,
        undefined_reason=GrowthUndefinedReason.ZERO_BASE,  # Inconsistent!
        undefined_message="Zero base",
        base_negative=False,
    )
    valid, checked, failure = validate_tool_result(
        tool_name="period_compare",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=PeriodCompareResult,
    )
    assert valid is False
    assert "period_compare_undefined_reason" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_trend_chronological_order_corruption() -> None:
    """Non-chronological trend points fire trend_chronological_order invariant."""
    corrupted_result = TrendResult(
        grain=TimeGrain.MONTHLY,
        points=[
            TrendPoint(period="2023-02", value=200.0, row_count=5, present=True),
            TrendPoint(period="2023-01", value=100.0, row_count=5, present=True),  # Out of order!
        ],
        direction=TrendDirection.INCREASING,
        slope=10.0,
        total_periods=2,
        missing_periods_count=0,
    )
    valid, checked, failure = validate_tool_result(
        tool_name="trend",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=TrendResult,
    )
    assert valid is False
    assert "trend_chronological_order" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_segment_contribution_shares_sum_corruption() -> None:
    """Shares summing to 0.8 instead of 1.0 fires contribution_shares_sum invariant."""
    corrupted_result = SegmentContributionResult(
        segment_column="Category",
        metric_column="Sales",
        total_value=100.0,
        segments=[
            SegmentShareRow(segment="Tech", value=50.0, share=0.5),
            SegmentShareRow(segment="Office", value=30.0, share=0.3),  # Sum is 0.8!
        ],
        shares_sum=0.8,
        tolerance_applied=1e-9,
        reconciles=False,
        has_negative_segments=False,
    )
    valid, checked, failure = validate_tool_result(
        tool_name="segment_contribution",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=SegmentContributionResult,
    )
    assert valid is False
    assert "contribution_shares_sum" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_correlation_bounds_corruption() -> None:
    """Pearson r exceeding 1.0 fires correlation_bounds invariant."""
    corrupted_result = CorrelationResult(
        x_column="X",
        y_column="Y",
        correlation=1.5,  # Invalid r!
        status=CorrelationStatus.OK,
        valid_pairs_count=10,
        undefined_reason=None,
        limitations=[],
    )
    valid, checked, failure = validate_tool_result(
        tool_name="correlation",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=CorrelationResult,
    )
    assert valid is False
    assert "correlation_bounds" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_anomalies_fence_order_corruption() -> None:
    """Inverted fences (lower_fence > upper_fence) fires anomalies_fence_order invariant."""
    corrupted_result = AnomaliesIQRResult(
        metric_column="Sales",
        status=AnomalyStatus.OK,
        q1=20.0,
        median=30.0,
        q3=40.0,
        iqr=20.0,
        lower_fence=100.0,  # lower fence > upper fence!
        upper_fence=0.0,
        k=1.5,
        valid_count=10,
        flagged_count=0,
        flagged_items_truncated=False,
        flagged_items=[],
        caveat=None,
        limitations=[],
    )
    valid, checked, failure = validate_tool_result(
        tool_name="detect_anomalies_iqr",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=AnomaliesIQRResult,
    )
    assert valid is False
    assert "anomalies_fence_order" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION


def test_anomalies_flagged_value_inside_fences_corruption() -> None:
    """Flagged item whose value lies inside fences fires anomalies_flagged_bounds invariant."""
    corrupted_result = AnomaliesIQRResult(
        metric_column="Sales",
        status=AnomalyStatus.OK,
        q1=20.0,
        median=30.0,
        q3=40.0,
        iqr=20.0,
        lower_fence=-10.0,
        upper_fence=70.0,
        k=1.5,
        valid_count=10,
        flagged_count=1,
        flagged_items_truncated=False,
        flagged_items=[
            AnomalyPoint(
                original_index=0, ascending_position=5, value=30.0, fence_violated="upper"
            ),  # 30 is inside fences!
        ],
        caveat=None,
        limitations=[],
    )
    valid, checked, failure = validate_tool_result(
        tool_name="detect_anomalies_iqr",
        result_data=corrupted_result,
        input_row_count=10,
        result_model=AnomaliesIQRResult,
    )
    assert valid is False
    assert "anomalies_flagged_bounds" in checked
    assert failure is not None
    assert failure.failure_class == FailureClass.INVARIANT_VIOLATION
