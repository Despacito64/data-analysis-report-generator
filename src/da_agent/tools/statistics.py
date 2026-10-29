"""Statistical analytical tools: trend, segment contribution, correlation, and detect_anomalies_iqr.

All tools implement pure functions over DataFrames and typed Pydantic models.
Documented statistical limitations are included in docstrings and returned in result models.
"""

from typing import Literal

import numpy as np
import pandas as pd

from da_agent.contracts.models import FailureClass
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    AggregationType,
    AnomaliesIQRArgs,
    AnomaliesIQRResult,
    AnomalyPoint,
    AnomalyStatus,
    ContributionUndefinedReason,
    CorrelationArgs,
    CorrelationResult,
    CorrelationStatus,
    CorrelationUndefinedReason,
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

CORRELATION_LIMITATIONS: list[str] = [
    "Measures linear relationships only; does not capture nonlinear associations.",
    "Highly sensitive to bivariate outliers and extreme values.",
    "Correlation indicates statistical association and does not imply causation.",
]

IQR_LIMITATIONS: list[str] = [
    "Outliers flagged by the 1.5 x IQR rule are statistical extremes, not confirmed data errors.",
    "Assumes an approximately unimodal, symmetric distribution; sensitive to heavy-tailed distributions and skewness.",
    "Evaluates univariate values in isolation without considering multivariate, temporal, or grouping context.",
]


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
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        denominator = np.sum((x - x_mean) ** 2)

        if denominator > 0:
            numerator = np.sum((x - x_mean) * (y - y_mean))
            slope = float(numerator / denominator)

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

    clean_metric = df[args.metric_column].dropna()
    total_val = float(clean_metric.sum())

    work_df = df[[args.segment_column, args.metric_column]].copy()
    work_df[args.segment_column] = work_df[args.segment_column].fillna("<missing>")

    grouped = work_df.groupby(args.segment_column, dropna=False)

    segment_sums: list[tuple[str, float]] = []
    for seg_key, group in grouped:
        seg_sum = float(group[args.metric_column].dropna().sum())
        segment_sums.append((str(seg_key), seg_sum))

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


# ---------------------------------------------------------------------------
# 3. correlation
# ---------------------------------------------------------------------------


def correlation(df: pd.DataFrame, args: CorrelationArgs) -> ToolResultEnvelope[CorrelationResult]:
    """Calculate bivariate Pearson correlation with documented statistical limitations.

    Limitations:
    - Measures linear relationships only.
    - Sensitive to outliers and extreme observations.
    - Does not imply causal connection.
    """
    _check_non_empty(df)
    _check_columns_exist(df, [args.x_column, args.y_column])

    valid_pairs = df[[args.x_column, args.y_column]].dropna()
    valid_count = len(valid_pairs)

    # Minimum 3 valid pairs required for meaningful bivariate correlation
    if valid_count < 3:
        res = CorrelationResult(
            x_column=args.x_column,
            y_column=args.y_column,
            correlation=None,
            status=CorrelationStatus.INSUFFICIENT_DATA,
            valid_pairs_count=valid_count,
            undefined_reason=CorrelationUndefinedReason.TOO_FEW_PAIRS,
            limitations=CORRELATION_LIMITATIONS,
        )
        return ToolResultEnvelope(
            tool_name="correlation",
            args=args,
            input_row_count=len(df),
            result=res,
        )

    x = valid_pairs[args.x_column].to_numpy(dtype=float)
    y = valid_pairs[args.y_column].to_numpy(dtype=float)

    var_x = float(np.var(x, ddof=1))
    var_y = float(np.var(y, ddof=1))

    # Constant column check
    if var_x == 0.0 or var_y == 0.0:
        res = CorrelationResult(
            x_column=args.x_column,
            y_column=args.y_column,
            correlation=None,
            status=CorrelationStatus.UNDEFINED,
            valid_pairs_count=valid_count,
            undefined_reason=CorrelationUndefinedReason.CONSTANT_COLUMN,
            limitations=CORRELATION_LIMITATIONS,
        )
        return ToolResultEnvelope(
            tool_name="correlation",
            args=args,
            input_row_count=len(df),
            result=res,
        )

    r_matrix = np.corrcoef(x, y)
    r_val = float(r_matrix[0, 1])

    res = CorrelationResult(
        x_column=args.x_column,
        y_column=args.y_column,
        correlation=r_val,
        status=CorrelationStatus.OK,
        valid_pairs_count=valid_count,
        undefined_reason=None,
        limitations=CORRELATION_LIMITATIONS,
    )
    return ToolResultEnvelope(
        tool_name="correlation",
        args=args,
        input_row_count=len(df),
        result=res,
    )


# ---------------------------------------------------------------------------
# 4. detect_anomalies_iqr
# ---------------------------------------------------------------------------


def detect_anomalies_iqr(
    df: pd.DataFrame, args: AnomaliesIQRArgs
) -> ToolResultEnvelope[AnomaliesIQRResult]:
    """Detect univariate anomalies using the deterministic 1.5 x IQR fence rule.

    Quartile Method:
    - Linear interpolation (method="linear", numpy default).
    - Fences: [Q1 - k*IQR, Q3 + k*IQR] where default k=1.5.

    Limitations:
    - Statistical extremes flagged are not guaranteed ground-truth errors.
    - Sensitive to skewness and heavy tails.
    - Operates univariately without grouping or time-series context.
    """
    _check_non_empty(df)
    _check_columns_exist(df, [args.metric_column])

    clean_series = df[args.metric_column].dropna()
    valid_count = len(clean_series)

    # Minimum 4 values required for meaningful quartile calculation
    if valid_count < 4:
        res = AnomaliesIQRResult(
            metric_column=args.metric_column,
            status=AnomalyStatus.INSUFFICIENT_DATA,
            q1=None,
            median=None,
            q3=None,
            iqr=None,
            lower_fence=None,
            upper_fence=None,
            k=args.k,
            valid_count=valid_count,
            flagged_count=0,
            flagged_items_truncated=False,
            flagged_items=[],
            caveat=None,
            limitations=IQR_LIMITATIONS,
        )
        return ToolResultEnvelope(
            tool_name="detect_anomalies_iqr",
            args=args,
            input_row_count=len(df),
            result=res,
        )

    values = clean_series.to_numpy(dtype=float)
    q1 = float(np.percentile(values, 25, method="linear"))
    med = float(np.percentile(values, 50, method="linear"))
    q3 = float(np.percentile(values, 75, method="linear"))
    iqr = float(q3 - q1)

    lower_fence = float(q1 - args.k * iqr)
    upper_fence = float(q3 + args.k * iqr)
    caveat = "zero_iqr" if iqr == 0.0 else None

    # Sort values to establish deterministic ascending position rank
    sorted_df = clean_series.sort_values(ascending=True)
    ascending_positions = {idx: pos for pos, idx in enumerate(sorted_df.index)}

    flagged_list: list[AnomalyPoint] = []
    for idx, val in clean_series.items():
        val_float = float(val)
        if val_float < lower_fence:
            fence_type: Literal["lower", "upper"] = "lower"
        elif val_float > upper_fence:
            fence_type = "upper"
        else:
            continue

        flagged_list.append(
            AnomalyPoint(
                original_index=int(idx),
                ascending_position=ascending_positions[idx],
                value=val_float,
                fence_violated=fence_type,
            )
        )

    # Sort flagged items by original index for deterministic output
    flagged_list.sort(key=lambda p: p.original_index)
    total_flagged = len(flagged_list)
    truncated = total_flagged > args.max_flagged_items
    capped_items = flagged_list[: args.max_flagged_items]

    res = AnomaliesIQRResult(
        metric_column=args.metric_column,
        status=AnomalyStatus.OK,
        q1=q1,
        median=med,
        q3=q3,
        iqr=iqr,
        lower_fence=lower_fence,
        upper_fence=upper_fence,
        k=args.k,
        valid_count=valid_count,
        flagged_count=total_flagged,
        flagged_items_truncated=truncated,
        flagged_items=capped_items,
        caveat=caveat,
        limitations=IQR_LIMITATIONS,
    )
    return ToolResultEnvelope(
        tool_name="detect_anomalies_iqr",
        args=args,
        input_row_count=len(df),
        result=res,
    )
