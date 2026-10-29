"""Statistical analytical tools: trend and segment contribution.

(Correlation and IQR anomaly detection are implemented in Stage 3).
"""

import numpy as np
import pandas as pd

from da_agent.contracts.models import FailureClass
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    AggregationType,
    ContributionUndefinedReason,
    SegmentContributionArgs,
    SegmentContributionResult,
    SegmentShareRow,
    TimeGrain,
    ToolResultEnvelope,
    TrendArgs,
    TrendDirection,
    TrendPoint,
    TrendResult,
)


def _check_columns_exist(df: pd.DataFrame, required: list[str]) -> None:
    """Verify that all required columns exist in the DataFrame."""
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ToolError(
            failure_class=FailureClass.INVALID_ARGS,
            message=f"Column(s) not found in DataFrame: {missing}",
            context={
                "missing_columns": missing,
                "available_columns": list(df.columns),
            },
        )


def _check_non_empty(df: pd.DataFrame) -> None:
    """Ensure DataFrame is not empty."""
    if len(df) == 0:
        raise ToolError(
            failure_class=FailureClass.EMPTY_RESULT,
            message="Input DataFrame is empty (0 rows)",
            context={"input_row_count": 0},
        )


# ---------------------------------------------------------------------------
# 1. trend
# ---------------------------------------------------------------------------


def trend(df: pd.DataFrame, args: TrendArgs) -> ToolResultEnvelope[TrendResult]:
    """Aggregate metric values along chronological periods and evaluate direction."""
    _check_non_empty(df)
    _check_columns_exist(df, [args.date_column, args.metric_column])

    # Parse dates
    dt_series = pd.to_datetime(df[args.date_column], errors="coerce")
    valid_dates_mask = dt_series.notna()

    if valid_dates_mask.sum() == 0:
        raise ToolError(
            failure_class=FailureClass.EMPTY_RESULT,
            message=f"No valid dates could be parsed in column '{args.date_column}'",
            context={"input_row_count": len(df)},
        )

    work_df = df[valid_dates_mask].copy()
    work_dates = dt_series[valid_dates_mask]

    # Assign period string
    if args.grain == TimeGrain.DAILY:
        work_df["_period"] = work_dates.dt.strftime("%Y-%m-%d")
    elif args.grain == TimeGrain.MONTHLY:
        work_df["_period"] = work_dates.dt.strftime("%Y-%m")
    elif args.grain == TimeGrain.QUARTERLY:
        work_df["_period"] = work_dates.apply(lambda d: f"{d.year}-Q{d.quarter}")
    elif args.grain == TimeGrain.YEARLY:
        work_df["_period"] = work_dates.dt.strftime("%Y")
    else:
        raise ValueError(f"Unsupported time grain: {args.grain}")

    # Group chronologically
    grouped = work_df.groupby("_period", sort=True)

    points: list[TrendPoint] = []
    y_values: list[float] = []

    for period_str, group in grouped:
        metric_s = group[args.metric_column]
        clean_s = metric_s.dropna()
        cnt = len(metric_s)

        if len(clean_s) == 0:
            val = None
        elif args.aggregation == AggregationType.SUM:
            val = float(clean_s.sum())
        elif args.aggregation == AggregationType.MEAN:
            val = float(clean_s.mean())
        elif args.aggregation == AggregationType.COUNT:
            val = float(len(clean_s))
        elif args.aggregation == AggregationType.MIN:
            val = float(clean_s.min())
        elif args.aggregation == AggregationType.MAX:
            val = float(clean_s.max())
        else:
            val = float(clean_s.sum())

        points.append(
            TrendPoint(
                period=str(period_str),
                value=val,
                row_count=cnt,
                present=True,
            )
        )
        if val is not None:
            y_values.append(val)

    # Classify direction
    slope: float | None = None
    direction: TrendDirection = TrendDirection.INSUFFICIENT_DATA

    if len(y_values) >= 2:
        x = np.arange(len(y_values), dtype=float)
        y = np.array(y_values, dtype=float)
        # Least squares linear regression slope
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        denominator = np.sum((x - x_mean) ** 2)

        if denominator > 0:
            numerator = np.sum((x - x_mean) * (y - y_mean))
            slope = float(numerator / denominator)

            # Check for monotonicity or volatility
            diffs = np.diff(y)
            has_pos = np.any(diffs > 1e-9)
            has_neg = np.any(diffs < -1e-9)

            if abs(slope) < 1e-6:
                direction = TrendDirection.FLAT
            elif has_pos and has_neg:
                direction = TrendDirection.VOLATILE
            elif slope > 0:
                direction = TrendDirection.INCREASING
            else:
                direction = TrendDirection.DECREASING

    res = TrendResult(
        grain=args.grain,
        points=points,
        direction=direction,
        slope=slope,
        total_periods=len(points),
        missing_periods_count=0,
    )
    return ToolResultEnvelope(
        tool_name="trend",
        args=args,
        input_row_count=len(df),
        result=res,
    )


# ---------------------------------------------------------------------------
# 2. segment_contribution
# ---------------------------------------------------------------------------


def segment_contribution(
    df: pd.DataFrame, args: SegmentContributionArgs
) -> ToolResultEnvelope[SegmentContributionResult]:
    """Calculate segment contribution shares and independently reconcile total."""
    _check_non_empty(df)
    _check_columns_exist(df, [args.segment_column, args.metric_column])

    # Compute total value independently from the entire column
    clean_metric = df[args.metric_column].dropna()
    total_val = float(clean_metric.sum())

    # Map missing segment keys to '<missing>'
    work_df = df[[args.segment_column, args.metric_column]].copy()
    work_df[args.segment_column] = work_df[args.segment_column].fillna("<missing>")

    # Sum metric per segment
    grouped = work_df.groupby(args.segment_column, dropna=False)

    segment_sums: list[tuple[str, float]] = []
    for seg_key, group in grouped:
        seg_sum = float(group[args.metric_column].dropna().sum())
        segment_sums.append((str(seg_key), seg_sum))

    # Sort deterministically: highest value first, tie-break by segment name ascending
    segment_sums.sort(key=lambda x: (-x[1], x[0]))

    sum_of_segments = sum(val for _, val in segment_sums)
    has_negative_segments = any(val < 0 for _, val in segment_sums)

    shares: list[SegmentShareRow] = []
    shares_sum: float | None = None
    undefined_reason: ContributionUndefinedReason | None = None
    undefined_msg: str | None = None

    if total_val == 0.0:
        undefined_reason = ContributionUndefinedReason.ZERO_TOTAL
        undefined_msg = (
            "Total metric value is zero: individual segment contribution shares are undefined"
        )
        for seg_name, val in segment_sums:
            shares.append(SegmentShareRow(segment=seg_name, value=val, share=None))
        reconciles = abs(sum_of_segments - total_val) <= args.tolerance_applied
    else:
        for seg_name, val in segment_sums:
            share_val = float(val / total_val)
            shares.append(SegmentShareRow(segment=seg_name, value=val, share=share_val))
        shares_sum = float(sum(s.share for s in shares if s.share is not None))

        # Check reconciliation:
        # 1. sum of shares equals 1.0 within absolute tolerance
        # 2. sum of segments equals total within relative tolerance
        shares_reconcile = abs(shares_sum - 1.0) <= args.tolerance_applied
        total_scale = max(abs(total_val), 1.0)
        totals_reconcile = abs(sum_of_segments - total_val) / total_scale <= args.tolerance_applied
        reconciles = bool(shares_reconcile and totals_reconcile)

    res = SegmentContributionResult(
        segment_column=args.segment_column,
        metric_column=args.metric_column,
        total_value=total_val,
        segments=shares,
        shares_sum=shares_sum,
        tolerance_applied=args.tolerance_applied,
        reconciles=reconciles,
        has_negative_segments=has_negative_segments,
        undefined_reason=undefined_reason,
        undefined_message=undefined_msg,
    )
    return ToolResultEnvelope(
        tool_name="segment_contribution",
        args=args,
        input_row_count=len(df),
        result=res,
    )
