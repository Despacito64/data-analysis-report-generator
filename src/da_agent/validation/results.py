"""Result schema and numerical invariant validation.

Layer 4 module: strictly imports contracts and core; NEVER imports da_agent.tools.
Verifies tool output results against declared Pydantic schemas and numerical invariants
without re-executing tools.
"""

from typing import Any

from pydantic import BaseModel, ValidationError

from da_agent.contracts.models import Failure, FailureClass

TOLERANCE = 1e-9


def validate_tool_result(
    tool_name: str,
    result_data: Any,
    input_row_count: int,
    result_model: type[BaseModel] | None,
) -> tuple[bool, list[str], Failure | None]:
    """Validate a tool result against its declared schema and mathematical invariants.

    Returns:
        (valid: bool, invariants_checked: list[str], failure: Failure | None)
    """
    invariants_checked: list[str] = []

    # 1. Schema Validation
    if result_model is not None:
        try:
            if isinstance(result_data, result_model):
                validated_model = result_data
            elif isinstance(result_data, BaseModel):
                validated_model = result_model.model_validate(result_data.model_dump())
            elif isinstance(result_data, dict):
                validated_model = result_model.model_validate(result_data)
            else:
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.SCHEMA_VIOLATION,
                        recoverable=False,
                        message=f"Result for '{tool_name}' is not a valid model or dict (got {type(result_data).__name__})",
                        context={"tool_name": tool_name},
                    ),
                )
        except ValidationError as exc:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.SCHEMA_VIOLATION,
                    recoverable=False,
                    message=f"Result schema validation failed for '{tool_name}'",
                    context={
                        "tool_name": tool_name,
                        "validation_errors": [
                            {"loc": [str(loc) for loc in err["loc"]], "msg": err["msg"]}
                            for err in exc.errors()
                        ],
                    },
                ),
            )
    else:
        validated_model = result_data

    # Convert to dict for consistent attribute inspection
    res_dict = (
        validated_model.model_dump()
        if isinstance(validated_model, BaseModel)
        else dict(validated_model)
    )

    # 2. Numerical Invariants per Tool
    if tool_name == "filter":
        invariants_checked.append("filter_row_bounds")
        out_cnt = res_dict.get("output_row_count", 0)
        matched_indices = res_dict.get("matched_indices", [])

        if not (0 < out_cnt <= input_row_count):
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=(
                        f"Invariant violation: output_row_count ({out_cnt}) must be > 0 and <= "
                        f"input_row_count ({input_row_count})"
                    ),
                    context={
                        "invariant": "filter_row_bounds",
                        "output_row_count": out_cnt,
                        "input_row_count": input_row_count,
                    },
                ),
            )
        if len(matched_indices) != out_cnt:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=(
                        f"Invariant violation: matched_indices count ({len(matched_indices)}) does not "
                        f"match output_row_count ({out_cnt})"
                    ),
                    context={
                        "invariant": "filter_row_bounds",
                        "matched_indices_count": len(matched_indices),
                        "output_row_count": out_cnt,
                    },
                ),
            )

    elif tool_name == "group_aggregate":
        invariants_checked.extend(["group_aggregate_group_count", "group_aggregate_reconciliation"])
        rows = res_dict.get("rows", [])
        total_groups = res_dict.get("total_groups", 0)

        if total_groups != len(rows) or total_groups < 1:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=(
                        f"Invariant violation: total_groups ({total_groups}) does not match "
                        f"len(rows) ({len(rows)}) or is < 1"
                    ),
                    context={"invariant": "group_aggregate_group_count"},
                ),
            )

        total_reconciled_rows = 0
        for r in rows:
            valid_cnt = r.get("valid_count", 0)
            missing_cnt = r.get("missing_count", 0)
            group_row_cnt = valid_cnt + missing_cnt

            if not (0 <= group_row_cnt <= input_row_count):
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message=(
                            f"Invariant violation: group row count ({group_row_cnt}) exceeds "
                            f"input_row_count ({input_row_count})"
                        ),
                        context={"invariant": "group_aggregate_reconciliation"},
                    ),
                )
            total_reconciled_rows += group_row_cnt

        if total_reconciled_rows != input_row_count:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=(
                        f"Invariant violation: sum of group row counts ({total_reconciled_rows}) does "
                        f"not match input_row_count ({input_row_count})"
                    ),
                    context={
                        "invariant": "group_aggregate_reconciliation",
                        "sum_group_rows": total_reconciled_rows,
                        "input_row_count": input_row_count,
                    },
                ),
            )

    elif tool_name == "rank":
        invariants_checked.extend(
            [
                "rank_monotonicity",
                "rank_tie_consistency",
                "rank_cutoff_integrity",
                "rank_null_exclusion",
            ]
        )
        rows = res_dict.get("rows", [])
        top_n = res_dict.get("top_n")
        ties_at_cutoff = res_dict.get("ties_at_cutoff", False)
        cutoff_omitted = res_dict.get("cutoff_tied_labels_omitted", [])
        null_cnt = res_dict.get("null_count", 0)
        tie_decimals = res_dict.get("tie_decimals", 9)
        tie_tol = 10**-tie_decimals

        if len(rows) + null_cnt > input_row_count:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message="Invariant violation: ranked rows count + null_count exceeds input_row_count",
                    context={"invariant": "rank_null_exclusion"},
                ),
            )

        if top_n is not None and len(rows) > top_n:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=f"Invariant violation: rows returned ({len(rows)}) exceeds top_n ({top_n})",
                    context={"invariant": "rank_cutoff_integrity"},
                ),
            )

        if ties_at_cutoff and not cutoff_omitted:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message="Invariant violation: ties_at_cutoff is True but cutoff_tied_labels_omitted is empty",
                    context={"invariant": "rank_cutoff_integrity"},
                ),
            )

        # Check monotonicity and tie consistency
        for i in range(len(rows) - 1):
            curr_r = rows[i]["rank"]
            next_r = rows[i + 1]["rank"]
            curr_val = rows[i]["value"]
            next_val = rows[i + 1]["value"]

            if curr_r > next_r:
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message="Invariant violation: ranks are not monotonically increasing",
                        context={"invariant": "rank_monotonicity"},
                    ),
                )
            if curr_r == next_r:
                if abs(curr_val - next_val) > tie_tol:
                    return (
                        False,
                        invariants_checked,
                        Failure(
                            failure_class=FailureClass.INVARIANT_VIOLATION,
                            recoverable=False,
                            message=f"Invariant violation: entities sharing rank {curr_r} have different values",
                            context={"invariant": "rank_tie_consistency"},
                        ),
                    )
                if not (rows[i]["is_tied"] and rows[i + 1]["is_tied"]):
                    return (
                        False,
                        invariants_checked,
                        Failure(
                            failure_class=FailureClass.INVARIANT_VIOLATION,
                            recoverable=False,
                            message="Invariant violation: tied entities must have is_tied == True",
                            context={"invariant": "rank_tie_consistency"},
                        ),
                    )

    elif tool_name == "period_compare":
        invariants_checked.extend(
            [
                "period_compare_abs_change",
                "period_compare_growth",
                "period_compare_undefined_reason",
            ]
        )
        base = res_dict.get("base_period", {})
        comp = res_dict.get("compare_period", {})
        abs_change = res_dict.get("absolute_change")
        growth = res_dict.get("relative_growth")
        undef_reason = res_dict.get("undefined_reason")
        base_neg = res_dict.get("base_negative", False)

        base_val = base.get("value")
        comp_val = comp.get("value")

        # Absolute change check
        if base_val is not None and comp_val is not None:
            expected_abs = comp_val - base_val
            if abs_change is None or abs(abs_change - expected_abs) > TOLERANCE:
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message=f"Invariant violation: absolute_change ({abs_change}) != compare - base ({expected_abs})",
                        context={"invariant": "period_compare_abs_change"},
                    ),
                )

        # Growth check
        if growth is not None:
            if undef_reason is not None:
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message="Invariant violation: relative_growth is present but undefined_reason is set",
                        context={"invariant": "period_compare_undefined_reason"},
                    ),
                )
            if base_val is not None and comp_val is not None and base_val != 0.0:
                denom = abs(base_val) if base_neg else base_val
                expected_growth = (comp_val - base_val) / denom
                if abs(growth - expected_growth) > TOLERANCE:
                    return (
                        False,
                        invariants_checked,
                        Failure(
                            failure_class=FailureClass.INVARIANT_VIOLATION,
                            recoverable=False,
                            message=f"Invariant violation: relative_growth ({growth}) != expected ({expected_growth})",
                            context={"invariant": "period_compare_growth"},
                        ),
                    )
        else:
            if undef_reason is None:
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message="Invariant violation: relative_growth is None but undefined_reason is not set",
                        context={"invariant": "period_compare_undefined_reason"},
                    ),
                )

    elif tool_name == "trend":
        invariants_checked.extend(["trend_chronological_order", "trend_points_integrity"])
        points = res_dict.get("points", [])
        total_p = res_dict.get("total_periods", 0)

        if len(points) != total_p:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=f"Invariant violation: len(points) ({len(points)}) != total_periods ({total_p})",
                    context={"invariant": "trend_points_integrity"},
                ),
            )

        for i in range(len(points) - 1):
            if points[i]["period"] >= points[i + 1]["period"]:
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message="Invariant violation: trend points are not in strict chronological order",
                        context={"invariant": "trend_chronological_order"},
                    ),
                )

    elif tool_name == "segment_contribution":
        invariants_checked.extend(
            [
                "contribution_shares_sum",
                "contribution_total_reconciliation",
                "contribution_reconciles_flag",
            ]
        )
        total_v = res_dict.get("total_value", 0.0)
        segments = res_dict.get("segments", [])
        shares_sum = res_dict.get("shares_sum")
        tol = res_dict.get("tolerance_applied", TOLERANCE)
        reconciles = res_dict.get("reconciles", False)

        seg_values_sum = sum(s.get("value", 0.0) for s in segments)
        total_scale = max(abs(total_v), 1.0)
        totals_reconcile = abs(seg_values_sum - total_v) / total_scale <= tol

        if total_v != 0.0 and shares_sum is not None and abs(shares_sum - 1.0) > tol:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=f"Invariant violation: shares_sum ({shares_sum}) does not equal 1.0 within tolerance",
                    context={"invariant": "contribution_shares_sum"},
                ),
            )
        if total_v != 0.0:
            shares_reconcile = shares_sum is not None and (abs(shares_sum - 1.0) <= tol)
            expected_reconciles = shares_reconcile and totals_reconcile
        else:
            expected_reconciles = totals_reconcile

        if reconciles != expected_reconciles:
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message=f"Invariant violation: reconciles flag ({reconciles}) != recomputed ({expected_reconciles})",
                    context={"invariant": "contribution_reconciles_flag"},
                ),
            )

    elif tool_name == "correlation":
        invariants_checked.extend(["correlation_bounds", "correlation_status_consistency"])
        r = res_dict.get("correlation")
        status = res_dict.get("status")
        pairs_cnt = res_dict.get("valid_pairs_count", 0)

        if status == "ok":
            if r is None or not (-1.0 - TOLERANCE <= r <= 1.0 + TOLERANCE):
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message=f"Invariant violation: Pearson r ({r}) must lie in [-1.0, 1.0]",
                        context={"invariant": "correlation_bounds"},
                    ),
                )
        elif status == "insufficient_data" and (pairs_cnt >= 3 or r is not None):
            return (
                False,
                invariants_checked,
                Failure(
                    failure_class=FailureClass.INVARIANT_VIOLATION,
                    recoverable=False,
                    message="Invariant violation: status is insufficient_data but correlation is not None",
                    context={"invariant": "correlation_status_consistency"},
                ),
            )

    elif tool_name == "detect_anomalies_iqr":
        invariants_checked.extend(
            [
                "anomalies_fence_order",
                "anomalies_flagged_bounds",
                "anomalies_truncation_consistency",
            ]
        )
        status = res_dict.get("status")
        q1 = res_dict.get("q1")
        med = res_dict.get("median")
        q3 = res_dict.get("q3")
        lf = res_dict.get("lower_fence")
        uf = res_dict.get("upper_fence")
        flagged_items = res_dict.get("flagged_items", [])
        flagged_cnt = res_dict.get("flagged_count", 0)

        if status == "ok" and q1 is not None and med is not None and q3 is not None:
            if not (lf <= q1 <= med <= q3 <= uf):
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message="Invariant violation: IQR fences order violated (lower_fence <= q1 <= median <= q3 <= upper_fence)",
                        context={"invariant": "anomalies_fence_order"},
                    ),
                )

            for item in flagged_items:
                val = item.get("value")
                viol = item.get("fence_violated")
                if viol == "lower" and val >= lf:
                    return (
                        False,
                        invariants_checked,
                        Failure(
                            failure_class=FailureClass.INVARIANT_VIOLATION,
                            recoverable=False,
                            message=f"Invariant violation: flagged lower item ({val}) is >= lower_fence ({lf})",
                            context={"invariant": "anomalies_flagged_bounds"},
                        ),
                    )
                if viol == "upper" and val <= uf:
                    return (
                        False,
                        invariants_checked,
                        Failure(
                            failure_class=FailureClass.INVARIANT_VIOLATION,
                            recoverable=False,
                            message=f"Invariant violation: flagged upper item ({val}) is <= upper_fence ({uf})",
                            context={"invariant": "anomalies_flagged_bounds"},
                        ),
                    )

            if flagged_cnt < len(flagged_items):
                return (
                    False,
                    invariants_checked,
                    Failure(
                        failure_class=FailureClass.INVARIANT_VIOLATION,
                        recoverable=False,
                        message="Invariant violation: flagged_count cannot be less than len(flagged_items)",
                        context={"invariant": "anomalies_truncation_consistency"},
                    ),
                )

    return True, invariants_checked, None
