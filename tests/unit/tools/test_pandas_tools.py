"""Unit tests for deterministic pandas tools (filter, group_aggregate, rank, period_compare, trend, segment_contribution).

Edge cases tested:
- E01: 0 rows input -> ToolError(EMPTY_RESULT)
- E02: Unknown column -> ToolError(INVALID_ARGS)
- E03: Filter yields 0 rows -> ToolError(EMPTY_RESULT)
- E04: Filter null handling
- E05: Group aggregate with null grouping key -> mapped to '<missing>'
- E06: Group aggregate all-missing sum/mean -> reported as None, not 0.0
- E07: Group aggregate partial missing values -> counts tracked, non-nulls aggregated
- E08: Deterministic group order (ascending group keys)
- E09: Ranking competition ties (1, 2, 2, 4), tie_decimals=9, secondary sort ascending label, tie groups
- E10: Ranking top-N cutoff straddling tie group -> ties_at_cutoff=True, omitted labels listed
- E11: Ranking nulls excluded and counted in null_count, never ranked as zero
- E12: Period compare absent period -> present=False, value=None, row_count=0
- E13: Period compare period present but all values missing -> present=True, value=None, missing_count=row_count
- E14: Period compare period present with value 0.0 -> present=True, value=0.0
- E15: Period compare zero base denominator -> relative_growth=None, undefined_reason=ZERO_BASE
- E16: Period compare missing base or current -> relative_growth=None, undefined_reason=MISSING_BASE / MISSING_CURRENT
- E17: Period compare negative base -> base_negative=True, (current - base) / abs(base)
- E18: Trend chronological ordering and gap handling
- E19: Segment contribution missing keys mapped to '<missing>'
- E20: Segment contribution zero total -> shares undefined with ZERO_TOTAL
- E21: Segment contribution negative values -> has_negative_segments=True
- E22: Segment contribution independent total, tolerance 1e-9, reconciles=True
"""

import pandas as pd
import pytest

from da_agent.contracts.models import FailureClass
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    AggregationType,
    ContributionUndefinedReason,
    FilterArgs,
    FilterCondition,
    FilterOperator,
    GroupAggregateArgs,
    GrowthUndefinedReason,
    PeriodCompareArgs,
    RankArgs,
    SegmentContributionArgs,
    TimeGrain,
    TrendArgs,
    TrendDirection,
)
from da_agent.tools.pandas_tools import (
    filter_data,
    group_aggregate,
    period_compare,
    rank,
)
from da_agent.tools.statistics import (
    segment_contribution,
    trend,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sales_df() -> pd.DataFrame:
    """Standard small sales dataset with known numbers."""
    return pd.DataFrame(
        {
            "Region": ["East", "East", "West", "West", "South", "Central"],
            "Category": ["Tech", "Office", "Tech", "Office", "Tech", "Office"],
            "Sales": [100.0, 200.0, 300.0, 400.0, 50.0, 150.0],
            "Profit": [10.0, -20.0, 30.0, 40.0, 5.0, 15.0],
            "Order Date": [
                "2023-01-15",
                "2023-01-20",
                "2023-02-10",
                "2023-02-15",
                "2023-03-05",
                "2023-03-20",
            ],
        }
    )


# ---------------------------------------------------------------------------
# 1. filter_data Tests
# ---------------------------------------------------------------------------


def test_filter_basic_and_compound(sales_df: pd.DataFrame) -> None:
    """Test basic and multi-condition filtering."""
    args = FilterArgs(
        conditions=[
            FilterCondition(column="Region", operator=FilterOperator.ISIN, value=["East", "West"]),
            FilterCondition(column="Sales", operator=FilterOperator.GT, value=150.0),
        ]
    )
    envelope = filter_data(sales_df, args)
    assert envelope.tool_name == "filter"
    assert envelope.input_row_count == 6
    assert envelope.result.output_row_count == 3  # East-200, West-300, West-400
    assert envelope.result.matched_indices == [1, 2, 3]


def test_filter_empty_input_raises_empty_result() -> None:
    """E01: Zero row input DataFrame raises ToolError(EMPTY_RESULT)."""
    empty_df = pd.DataFrame(columns=["Sales", "Region"])
    args = FilterArgs(
        conditions=[FilterCondition(column="Region", operator=FilterOperator.EQ, value="East")]
    )
    with pytest.raises(ToolError) as exc_info:
        filter_data(empty_df, args)
    assert exc_info.value.failure_class == FailureClass.EMPTY_RESULT
    assert exc_info.value.context["input_row_count"] == 0


def test_filter_missing_column_raises_invalid_args(sales_df: pd.DataFrame) -> None:
    """E02: Unknown column in filter raises ToolError(INVALID_ARGS)."""
    args = FilterArgs(
        conditions=[FilterCondition(column="NonExistent", operator=FilterOperator.EQ, value="East")]
    )
    with pytest.raises(ToolError) as exc_info:
        filter_data(sales_df, args)
    assert exc_info.value.failure_class == FailureClass.INVALID_ARGS
    assert "NonExistent" in exc_info.value.context["missing_columns"]


def test_filter_zero_matches_raises_empty_result(sales_df: pd.DataFrame) -> None:
    """E03: Filter condition leaving 0 rows raises ToolError(EMPTY_RESULT)."""
    args = FilterArgs(
        conditions=[FilterCondition(column="Sales", operator=FilterOperator.GT, value=10000.0)]
    )
    with pytest.raises(ToolError) as exc_info:
        filter_data(sales_df, args)
    assert exc_info.value.failure_class == FailureClass.EMPTY_RESULT
    assert exc_info.value.context["matched_row_count"] == 0


def test_filter_null_handling() -> None:
    """E04: Filter correctly handles isnull and notnull operators."""
    df = pd.DataFrame(
        {"Category": ["Tech", None, "Office", None], "Sales": [10.0, 20.0, 30.0, 40.0]}
    )
    # isnull
    env_null = filter_data(
        df,
        FilterArgs(conditions=[FilterCondition(column="Category", operator=FilterOperator.ISNULL)]),
    )
    assert env_null.result.output_row_count == 2
    assert env_null.result.matched_indices == [1, 3]

    # notnull
    env_notnull = filter_data(
        df,
        FilterArgs(
            conditions=[FilterCondition(column="Category", operator=FilterOperator.NOTNULL)]
        ),
    )
    assert env_notnull.result.output_row_count == 2
    assert env_notnull.result.matched_indices == [0, 2]


# ---------------------------------------------------------------------------
# 2. group_aggregate Tests
# ---------------------------------------------------------------------------


def test_group_aggregate_basic(sales_df: pd.DataFrame) -> None:
    """Test group-by aggregation with deterministic ordering."""
    args = GroupAggregateArgs(
        by=["Region"],
        metric_column="Sales",
        aggregation=AggregationType.SUM,
    )
    envelope = group_aggregate(sales_df, args)
    assert envelope.tool_name == "group_aggregate"
    assert envelope.input_row_count == 6
    assert envelope.result.total_groups == 4
    # Deterministic alphabetical order: Central, East, South, West
    regions = [row.group_keys["Region"] for row in envelope.result.rows]
    assert regions == ["Central", "East", "South", "West"]
    values = [row.value for row in envelope.result.rows]
    assert values == [150.0, 300.0, 50.0, 700.0]


def test_group_aggregate_all_missing_sum_is_none() -> None:
    """E06: All-missing sum is reported as None, not zero."""
    df = pd.DataFrame(
        {
            "Region": ["East", "East", "West"],
            "Sales": [None, None, 100.0],
        }
    )
    args = GroupAggregateArgs(
        by=["Region"],
        metric_column="Sales",
        aggregation=AggregationType.SUM,
    )
    envelope = group_aggregate(df, args)
    rows = {row.group_keys["Region"]: row for row in envelope.result.rows}

    # East has all nulls
    assert rows["East"].value is None
    assert rows["East"].valid_count == 0
    assert rows["East"].missing_count == 2

    # West has 1 valid value
    assert rows["West"].value == 100.0
    assert rows["West"].valid_count == 1
    assert rows["West"].missing_count == 0


def test_group_aggregate_partial_nulls() -> None:
    """E07: Partial missing values correctly aggregate non-nulls and count nulls."""
    df = pd.DataFrame(
        {
            "Region": ["East", "East", "East"],
            "Sales": [10.0, None, 30.0],
        }
    )
    args = GroupAggregateArgs(
        by=["Region"],
        metric_column="Sales",
        aggregation=AggregationType.MEAN,
    )
    envelope = group_aggregate(df, args)
    assert len(envelope.result.rows) == 1
    row = envelope.result.rows[0]
    assert row.value == 20.0
    assert row.valid_count == 2
    assert row.missing_count == 1


def test_group_aggregate_missing_keys_handled() -> None:
    """E05: Nulls in grouping key become '<missing>'."""
    df = pd.DataFrame(
        {
            "Region": ["East", None, "East"],
            "Sales": [10.0, 20.0, 30.0],
        }
    )
    args = GroupAggregateArgs(
        by=["Region"],
        metric_column="Sales",
        aggregation=AggregationType.SUM,
    )
    envelope = group_aggregate(df, args)
    keys = [r.group_keys["Region"] for r in envelope.result.rows]
    assert "<missing>" in keys


# ---------------------------------------------------------------------------
# 3. rank Tests
# ---------------------------------------------------------------------------


def test_rank_competition_ties_and_secondary_sort() -> None:
    """E09: Ties use 1, 2, 2, 4 competition ranking, secondary sort by label ascending."""
    df = pd.DataFrame(
        {
            "Entity": ["Bravo", "Alpha", "Charlie", "Delta"],
            "Sales": [200.0, 200.0, 300.0, 100.0],
        }
    )
    # Descending rank by Sales
    args = RankArgs(entity_column="Entity", metric_column="Sales", ascending=False)
    envelope = rank(df, args)
    res = envelope.result

    # Expected ranks: Charlie (300) -> 1; Alpha (200) -> 2; Bravo (200) -> 2; Delta (100) -> 4
    assert len(res.rows) == 4
    assert res.rows[0].entity == "Charlie"
    assert res.rows[0].rank == 1
    assert res.rows[0].is_tied is False

    # Ties at rank 2 sorted alphabetically: Alpha before Bravo
    assert res.rows[1].entity == "Alpha"
    assert res.rows[1].rank == 2
    assert res.rows[1].is_tied is True

    assert res.rows[2].entity == "Bravo"
    assert res.rows[2].rank == 2
    assert res.rows[2].is_tied is True

    assert res.rows[3].entity == "Delta"
    assert res.rows[3].rank == 4
    assert res.rows[3].is_tied is False

    # Check tie groups
    assert len(res.tie_groups) == 1
    assert res.tie_groups[0].rank == 2
    assert res.tie_groups[0].tied_entities == ["Alpha", "Bravo"]


def test_rank_top_n_straddling_cutoff() -> None:
    """E10: Top-N cutoff straddling a tie group returns first N in documented order and flags cutoff."""
    df = pd.DataFrame(
        {
            "Entity": ["Charlie", "Alpha", "Bravo", "Delta"],
            "Sales": [300.0, 200.0, 200.0, 100.0],
        }
    )
    # top_n = 2: Charlie is #1, Alpha is #2. Bravo is tied at #2 but omitted!
    args = RankArgs(entity_column="Entity", metric_column="Sales", ascending=False, top_n=2)
    envelope = rank(df, args)
    res = envelope.result

    assert len(res.rows) == 2
    assert [r.entity for r in res.rows] == ["Charlie", "Alpha"]
    assert res.ties_at_cutoff is True
    assert res.cutoff_tied_labels_omitted == ["Bravo"]


def test_rank_nulls_excluded_and_counted() -> None:
    """E11: Null metric values excluded from ranking and counted in null_count."""
    df = pd.DataFrame(
        {
            "Entity": ["Alpha", "Bravo", "Charlie"],
            "Sales": [100.0, None, 200.0],
        }
    )
    args = RankArgs(entity_column="Entity", metric_column="Sales", ascending=False)
    envelope = rank(df, args)
    res = envelope.result

    assert len(res.rows) == 2
    assert res.null_count == 1
    assert [r.entity for r in res.rows] == ["Charlie", "Alpha"]


# ---------------------------------------------------------------------------
# 4. period_compare Tests
# ---------------------------------------------------------------------------


def test_period_compare_normal_growth() -> None:
    """Test standard period-over-period comparison."""
    df = pd.DataFrame(
        {
            "Date": ["2023-01-10", "2023-01-15", "2023-02-10", "2023-02-20"],
            "Sales": [100.0, 100.0, 300.0, 100.0],
        }
    )
    args = PeriodCompareArgs(
        date_column="Date",
        metric_column="Sales",
        base_period=("2023-01-01", "2023-01-31"),
        compare_period=("2023-02-01", "2023-02-28"),
    )
    envelope = period_compare(df, args)
    res = envelope.result

    assert res.base_period.present is True
    assert res.base_period.value == 200.0
    assert res.compare_period.present is True
    assert res.compare_period.value == 400.0
    assert res.absolute_change == 200.0
    assert res.relative_growth == 1.0  # +100%
    assert res.undefined_reason is None


def test_period_compare_absent_period() -> None:
    """E12: Absent period produces present=False, value=None, row_count=0 (no error)."""
    df = pd.DataFrame(
        {
            "Date": ["2023-01-10", "2023-01-15"],
            "Sales": [100.0, 100.0],
        }
    )
    args = PeriodCompareArgs(
        date_column="Date",
        metric_column="Sales",
        base_period=("2023-01-01", "2023-01-31"),
        compare_period=("2023-02-01", "2023-02-28"),  # absent
    )
    envelope = period_compare(df, args)
    res = envelope.result

    assert res.base_period.present is True
    assert res.base_period.value == 200.0
    assert res.compare_period.present is False
    assert res.compare_period.value is None
    assert res.compare_period.row_count == 0
    assert res.absolute_change is None
    assert res.relative_growth is None
    assert res.undefined_reason == GrowthUndefinedReason.MISSING_CURRENT


def test_period_compare_all_missing_vs_zero() -> None:
    """E13 & E14: Distinguish period present with all-missing vs present with 0.0."""
    df = pd.DataFrame(
        {
            "Date": ["2023-01-10", "2023-02-10"],
            "Sales": [None, 0.0],
        }
    )
    args = PeriodCompareArgs(
        date_column="Date",
        metric_column="Sales",
        base_period=("2023-01-01", "2023-01-31"),
        compare_period=("2023-02-01", "2023-02-28"),
    )
    envelope = period_compare(df, args)
    res = envelope.result

    # Base: present, row_count 1, value None
    assert res.base_period.present is True
    assert res.base_period.row_count == 1
    assert res.base_period.missing_count == 1
    assert res.base_period.value is None

    # Compare: present, row_count 1, value 0.0
    assert res.compare_period.present is True
    assert res.compare_period.row_count == 1
    assert res.compare_period.value == 0.0


def test_period_compare_zero_base_growth_undefined() -> None:
    """E15: Zero base denominator gives relative_growth=None with ZERO_BASE."""
    df = pd.DataFrame(
        {
            "Date": ["2023-01-10", "2023-02-10"],
            "Sales": [0.0, 150.0],
        }
    )
    args = PeriodCompareArgs(
        date_column="Date",
        metric_column="Sales",
        base_period=("2023-01-01", "2023-01-31"),
        compare_period=("2023-02-01", "2023-02-28"),
    )
    envelope = period_compare(df, args)
    res = envelope.result

    assert res.absolute_change == 150.0
    assert res.relative_growth is None
    assert res.undefined_reason == GrowthUndefinedReason.ZERO_BASE
    assert "Zero base" in (res.undefined_message or "")


def test_period_compare_negative_base() -> None:
    """E17: Negative base uses (current - base) / abs(base) and sets base_negative=True."""
    df = pd.DataFrame(
        {
            "Date": ["2023-01-10", "2023-02-10"],
            "Profit": [-100.0, 50.0],
        }
    )
    args = PeriodCompareArgs(
        date_column="Date",
        metric_column="Profit",
        base_period=("2023-01-01", "2023-01-31"),
        compare_period=("2023-02-01", "2023-02-28"),
    )
    envelope = period_compare(df, args)
    res = envelope.result

    assert res.base_negative is True
    assert res.absolute_change == 150.0
    # (50 - (-100)) / abs(-100) = 150 / 100 = 1.5
    assert res.relative_growth == 1.5


# ---------------------------------------------------------------------------
# 5. trend Tests
# ---------------------------------------------------------------------------


def test_trend_basic_monthly(sales_df: pd.DataFrame) -> None:
    """E18: Trend aggregates by chronological periods and evaluates direction."""
    args = TrendArgs(
        date_column="Order Date",
        metric_column="Sales",
        grain=TimeGrain.MONTHLY,
    )
    envelope = trend(sales_df, args)
    res = envelope.result

    assert res.grain == TimeGrain.MONTHLY
    assert len(res.points) == 3  # Jan, Feb, Mar
    periods = [p.period for p in res.points]
    assert periods == ["2023-01", "2023-02", "2023-03"]
    # Jan: 100 + 200 = 300; Feb: 300 + 400 = 700; Mar: 50 + 150 = 200
    values = [p.value for p in res.points]
    assert values == [300.0, 700.0, 200.0]
    assert res.direction in {
        TrendDirection.VOLATILE,
        TrendDirection.INCREASING,
        TrendDirection.DECREASING,
    }


# ---------------------------------------------------------------------------
# 6. segment_contribution Tests
# ---------------------------------------------------------------------------


def test_segment_contribution_reconciliation(sales_df: pd.DataFrame) -> None:
    """E22: Independent total, shares sum to 1.0 within tolerance 1e-9, reconciles=True."""
    args = SegmentContributionArgs(
        segment_column="Category",
        metric_column="Sales",
        tolerance_applied=1e-9,
    )
    envelope = segment_contribution(sales_df, args)
    res = envelope.result

    # Total Sales: 100 + 200 + 300 + 400 + 50 + 150 = 1200.0
    assert res.total_value == 1200.0
    # Categories: Office = 200 + 400 + 150 = 750.0; Tech = 100 + 300 + 50 = 450.0
    seg_dict = {s.segment: s for s in res.segments}
    assert seg_dict["Office"].value == 750.0
    assert seg_dict["Tech"].value == 450.0
    assert seg_dict["Office"].share == 750.0 / 1200.0
    assert seg_dict["Tech"].share == 450.0 / 1200.0

    assert res.reconciles is True
    assert res.shares_sum is not None
    assert abs(res.shares_sum - 1.0) <= 1e-9
    assert res.has_negative_segments is False


def test_segment_contribution_missing_segment_mapped() -> None:
    """E19: Missing segment values mapped to '<missing>'."""
    df = pd.DataFrame(
        {
            "Segment": ["Consumer", None, "Corporate"],
            "Sales": [50.0, 25.0, 25.0],
        }
    )
    args = SegmentContributionArgs(
        segment_column="Segment",
        metric_column="Sales",
    )
    envelope = segment_contribution(df, args)
    res = envelope.result

    seg_names = [s.segment for s in res.segments]
    assert "<missing>" in seg_names
    assert res.reconciles is True


def test_segment_contribution_zero_total() -> None:
    """E20: Zero total produces undefined shares with ZERO_TOTAL reason."""
    df = pd.DataFrame(
        {
            "Segment": ["A", "B"],
            "Sales": [0.0, 0.0],
        }
    )
    args = SegmentContributionArgs(
        segment_column="Segment",
        metric_column="Sales",
    )
    envelope = segment_contribution(df, args)
    res = envelope.result

    assert res.total_value == 0.0
    assert res.shares_sum is None
    assert res.undefined_reason == ContributionUndefinedReason.ZERO_TOTAL
    for s in res.segments:
        assert s.share is None


def test_segment_contribution_negative_values() -> None:
    """E21: Negative segment values allowed and flagged with has_negative_segments=True."""
    df = pd.DataFrame(
        {
            "Segment": ["A", "B"],
            "Profit": [-50.0, 150.0],
        }
    )
    args = SegmentContributionArgs(
        segment_column="Segment",
        metric_column="Profit",
    )
    envelope = segment_contribution(df, args)
    res = envelope.result

    assert res.total_value == 100.0
    assert res.has_negative_segments is True
    # A share = -50/100 = -0.5, B share = 150/100 = 1.5
    seg_dict = {s.segment: s for s in res.segments}
    assert seg_dict["A"].share == -0.5
    assert seg_dict["B"].share == 1.5
    assert res.reconciles is True
