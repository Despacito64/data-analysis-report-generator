"""Deterministic pandas analytical tools: filter, group_aggregate, rank, period_compare.

Implements pure functions over DataFrames and typed Pydantic models.
All tools validate column existence cheaply and map known operational failures
to ToolError(FailureClass.INVALID_ARGS) or ToolError(FailureClass.EMPTY_RESULT).
"""

from typing import Any

import numpy as np
import pandas as pd

from da_agent.contracts.models import FailureClass
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    AggregationType,
    FilterArgs,
    FilterOperator,
    FilterResult,
    GroupAggregateArgs,
    GroupAggregateResult,
    GroupAggregateRow,
    GrowthUndefinedReason,
    PeriodCompareArgs,
    PeriodCompareResult,
    PeriodMetric,
    RankArgs,
    RankResult,
    RankRow,
    TieGroup,
    ToolResultEnvelope,
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


def _compute_agg(
    series: pd.Series, agg_type: AggregationType
) -> tuple[float | int | None, int, int]:
    """Compute aggregate value on a pandas series handling all-missing values."""
    row_count = len(series)
    missing_count = int(series.isna().sum())
    valid_count = row_count - missing_count

    if valid_count == 0:
        if agg_type == AggregationType.COUNT:
            return 0, 0, missing_count
        return None, 0, missing_count

    clean = series.dropna()
    if agg_type == AggregationType.SUM:
        val = float(clean.sum())
    elif agg_type == AggregationType.MEAN:
        val = float(clean.mean())
    elif agg_type == AggregationType.COUNT:
        val = int(valid_count)
    elif agg_type == AggregationType.MIN:
        val = float(clean.min())
    elif agg_type == AggregationType.MAX:
        val = float(clean.max())
    else:
        raise ValueError(f"Unsupported aggregation type: {agg_type}")

    return val, valid_count, missing_count


# ---------------------------------------------------------------------------
# 1. filter_data
# ---------------------------------------------------------------------------


def filter_data(df: pd.DataFrame, args: FilterArgs) -> ToolResultEnvelope[FilterResult]:
    """Filter DataFrame rows deterministically based on typed conditions."""
    _check_non_empty(df)
    req_cols = [c.column for c in args.conditions]
    _check_columns_exist(df, req_cols)

    mask = pd.Series(True, index=df.index)

    for cond in args.conditions:
        col = cond.column
        op = cond.operator
        val = cond.value
        series = df[col]

        if op == FilterOperator.EQ:
            cond_mask = series.isna() if val is None else (series == val)
        elif op == FilterOperator.NE:
            cond_mask = series.notna() if val is None else (series != val)
        elif op == FilterOperator.GT:
            cond_mask = series > val
        elif op == FilterOperator.GTE:
            cond_mask = series >= val
        elif op == FilterOperator.LT:
            cond_mask = series < val
        elif op == FilterOperator.LTE:
            cond_mask = series <= val
        elif op == FilterOperator.ISIN:
            cond_mask = series.isin(val)
        elif op == FilterOperator.NOTIN:
            cond_mask = ~series.isin(val)
        elif op == FilterOperator.BETWEEN:
            if not isinstance(val, (list, tuple)) or len(val) != 2:
                raise ToolError(
                    failure_class=FailureClass.INVALID_ARGS,
                    message="BETWEEN operator requires [min, max] list or tuple",
                    context={"column": col, "value": val},
                )
            cond_mask = series.between(val[0], val[1])
        elif op == FilterOperator.ISNULL:
            cond_mask = series.isna()
        elif op == FilterOperator.NOTNULL:
            cond_mask = series.notna()
        else:
            raise ToolError(
                failure_class=FailureClass.INVALID_ARGS,
                message=f"Unsupported operator: {op}",
                context={"operator": str(op)},
            )

        # For comparison operators (gt, gte, lt, lte, between), NaN values evaluate to False
        mask &= cond_mask.fillna(False)

    matched_indices = [int(i) for i in df.index[mask]]
    output_count = len(matched_indices)

    if output_count == 0:
        raise ToolError(
            failure_class=FailureClass.EMPTY_RESULT,
            message="Filter returned 0 matching rows",
            context={
                "matched_row_count": 0,
                "conditions": [c.model_dump(mode="json") for c in args.conditions],
            },
        )

    res = FilterResult(
        output_row_count=output_count,
        matched_indices=matched_indices,
    )
    return ToolResultEnvelope(
        tool_name="filter",
        args=args,
        input_row_count=len(df),
        result=res,
    )


# ---------------------------------------------------------------------------
# 2. group_aggregate
# ---------------------------------------------------------------------------


def group_aggregate(
    df: pd.DataFrame, args: GroupAggregateArgs
) -> ToolResultEnvelope[GroupAggregateResult]:
    """Group rows by given keys and compute deterministic aggregate values."""
    _check_non_empty(df)
    _check_columns_exist(df, args.by + [args.metric_column])

    # Copy grouping columns and fill nulls with '<missing>'
    work_df = df[args.by + [args.metric_column]].copy()
    for col in args.by:
        work_df[col] = work_df[col].fillna("<missing>")

    # Deterministic group sorting
    grouped = work_df.groupby(args.by, dropna=False, sort=True)

    result_rows: list[GroupAggregateRow] = []
    for group_key, group_subset in grouped:
        if not isinstance(group_key, tuple):
            group_key_tuple = (group_key,)
        else:
            group_key_tuple = group_key

        keys_dict: dict[str, Any] = {
            col_name: val for col_name, val in zip(args.by, group_key_tuple)
        }

        series = group_subset[args.metric_column]
        val, valid_cnt, missing_cnt = _compute_agg(series, args.aggregation)

        result_rows.append(
            GroupAggregateRow(
                group_keys=keys_dict,
                value=val,
                valid_count=valid_cnt,
                missing_count=missing_cnt,
            )
        )

    res = GroupAggregateResult(
        metric_column=args.metric_column,
        aggregation=args.aggregation,
        total_groups=len(result_rows),
        rows=result_rows,
    )
    return ToolResultEnvelope(
        tool_name="group_aggregate",
        args=args,
        input_row_count=len(df),
        result=res,
    )


# ---------------------------------------------------------------------------
# 3. rank
# ---------------------------------------------------------------------------


def rank(df: pd.DataFrame, args: RankArgs) -> ToolResultEnvelope[RankResult]:
    """Perform deterministic competition ranking (1, 2, 2, 4) with explicit tie groups."""
    _check_non_empty(df)
    _check_columns_exist(df, [args.entity_column, args.metric_column])

    metric_series = df[args.metric_column]
    null_mask = metric_series.isna()
    null_count = int(null_mask.sum())

    valid_df = df[~null_mask].copy()
    if len(valid_df) == 0:
        raise ToolError(
            failure_class=FailureClass.EMPTY_RESULT,
            message="No valid non-null rows to rank",
            context={"input_row_count": len(df), "null_count": null_count},
        )

    # Round metric values to tie_decimals for tie detection
    valid_df["_rounded_metric"] = valid_df[args.metric_column].round(args.tie_decimals)

    # Sort deterministically: primary by rounded metric, secondary by entity label ascending
    if args.ascending:
        valid_df = valid_df.sort_values(
            by=["_rounded_metric", args.entity_column], ascending=[True, True]
        )
    else:
        valid_df = valid_df.sort_values(
            by=["_rounded_metric", args.entity_column], ascending=[False, True]
        )

    # Standard competition ranking: rank 1, 2, 2, 4
    # Compute competition rank using pandas rank(method="min")
    valid_df["_comp_rank"] = (
        valid_df["_rounded_metric"].rank(method="min", ascending=args.ascending).astype(int)
    )

    # Group counts to identify ties
    rank_counts = valid_df["_comp_rank"].value_counts().to_dict()

    tie_groups_dict: dict[int, list[Any]] = {}
    tie_values_dict: dict[int, float] = {}

    all_rows: list[RankRow] = []
    for _, row in valid_df.iterrows():
        r = int(row["_comp_rank"])
        entity = row[args.entity_column]
        val = row[args.metric_column]
        rounded_val = float(row["_rounded_metric"])
        is_tied = rank_counts[r] > 1

        if is_tied:
            if r not in tie_groups_dict:
                tie_groups_dict[r] = []
                tie_values_dict[r] = rounded_val
            tie_groups_dict[r].append(entity)

        all_rows.append(
            RankRow(
                rank=r,
                entity=entity,
                value=float(val) if isinstance(val, (int, float, np.number)) else val,
                is_tied=is_tied,
            )
        )

    # Build tie groups list
    tie_groups: list[TieGroup] = [
        TieGroup(
            rank=r,
            rounded_value=tie_values_dict[r],
            tied_entities=entities,
        )
        for r, entities in sorted(tie_groups_dict.items(), key=lambda x: x[0])
    ]

    # Handle top_n cutoff
    ties_at_cutoff = False
    cutoff_tied_labels_omitted: list[str | int | float] = []
    final_rows = all_rows

    if args.top_n is not None and args.top_n < len(all_rows):
        last_included = all_rows[args.top_n - 1]
        first_excluded = all_rows[args.top_n]

        if last_included.rank == first_excluded.rank:
            ties_at_cutoff = True
            cutoff_rank = last_included.rank
            # Entities sharing this cutoff rank beyond top_n
            cutoff_tied_labels_omitted = [
                row.entity for row in all_rows[args.top_n :] if row.rank == cutoff_rank
            ]

        final_rows = all_rows[: args.top_n]

    res = RankResult(
        entity_column=args.entity_column,
        metric_column=args.metric_column,
        ascending=args.ascending,
        top_n=args.top_n,
        tie_decimals=args.tie_decimals,
        rows=final_rows,
        tie_groups=tie_groups,
        ties_at_cutoff=ties_at_cutoff,
        cutoff_tied_labels_omitted=cutoff_tied_labels_omitted,
        null_count=null_count,
    )
    return ToolResultEnvelope(
        tool_name="rank",
        args=args,
        input_row_count=len(df),
        result=res,
    )


# ---------------------------------------------------------------------------
# 4. period_compare
# ---------------------------------------------------------------------------


def period_compare(
    df: pd.DataFrame, args: PeriodCompareArgs
) -> ToolResultEnvelope[PeriodCompareResult]:
    """Perform deterministic period-over-period comparison."""
    _check_non_empty(df)
    _check_columns_exist(df, [args.date_column, args.metric_column])

    # Convert date column to datetime for strict window comparison
    dates = pd.to_datetime(df[args.date_column], errors="coerce")

    def _get_period_metric(period_bounds: tuple[str, str]) -> PeriodMetric:
        start_dt = pd.to_datetime(period_bounds[0])
        end_dt = pd.to_datetime(period_bounds[1])

        # Window inclusion: [start_dt, end_dt]
        mask = (dates >= start_dt) & (dates <= end_dt)
        subset = df[mask]
        row_cnt = len(subset)

        if row_cnt == 0:
            return PeriodMetric(
                present=False,
                value=None,
                row_count=0,
                missing_count=0,
            )

        series = subset[args.metric_column]
        val, _, missing_cnt = _compute_agg(series, args.aggregation)

        return PeriodMetric(
            present=True,
            value=val,
            row_count=row_cnt,
            missing_count=missing_cnt,
        )

    base_metric = _get_period_metric(args.base_period)
    comp_metric = _get_period_metric(args.compare_period)

    # Compute absolute change
    if base_metric.value is not None and comp_metric.value is not None:
        abs_change = float(comp_metric.value - base_metric.value)
    else:
        abs_change = None

    # Compute relative growth
    rel_growth: float | None = None
    undefined_reason: GrowthUndefinedReason | None = None
    undefined_msg: str | None = None
    base_neg = False

    if base_metric.value is None:
        undefined_reason = GrowthUndefinedReason.MISSING_BASE
        undefined_msg = "Base period value is missing or period absent"
    elif comp_metric.value is None:
        undefined_reason = GrowthUndefinedReason.MISSING_CURRENT
        undefined_msg = "Comparison period value is missing or period absent"
    elif base_metric.value == 0.0:
        undefined_reason = GrowthUndefinedReason.ZERO_BASE
        undefined_msg = "Zero base denominator: cannot compute relative percentage change"
    else:
        base_val = base_metric.value
        curr_val = comp_metric.value
        if base_val < 0:
            base_neg = True
            rel_growth = float((curr_val - base_val) / abs(base_val))
        else:
            rel_growth = float((curr_val - base_val) / base_val)

    res = PeriodCompareResult(
        base_period=base_metric,
        compare_period=comp_metric,
        absolute_change=abs_change,
        relative_growth=rel_growth,
        undefined_reason=undefined_reason,
        undefined_message=undefined_msg,
        base_negative=base_neg,
    )
    return ToolResultEnvelope(
        tool_name="period_compare",
        args=args,
        input_row_count=len(df),
        result=res,
    )
