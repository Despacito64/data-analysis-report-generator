"""Argument validation against tool schemas and DatasetProfile.

Layer 4 module: strictly imports contracts and core; NEVER imports da_agent.tools.
Validates planner arguments before execution as untrusted inputs.
"""

from typing import Any

from pydantic import BaseModel, ValidationError

from da_agent.contracts.models import (
    DatasetProfile,
    Failure,
    FailureClass,
    SemanticType,
)


def _extract_column_references(tool_name: str, args_obj: BaseModel) -> dict[str, list[str]]:
    """Extract columns partitioned by their analytical role from validated args."""
    data = args_obj.model_dump()
    roles: dict[str, list[str]] = {
        "metric": [],
        "date": [],
        "group": [],
        "filter": [],
        "entity": [],
        "other": [],
    }

    if tool_name == "filter":
        for cond in data.get("conditions", []):
            if "column" in cond:
                roles["filter"].append(cond["column"])
    elif tool_name == "group_aggregate":
        roles["group"].extend(data.get("by", []))
        if "metric_column" in data:
            roles["metric"].append(data["metric_column"])
    elif tool_name == "rank":
        if "entity_column" in data:
            roles["entity"].append(data["entity_column"])
        if "metric_column" in data:
            roles["metric"].append(data["metric_column"])
    elif tool_name == "period_compare" or tool_name == "trend":
        if "date_column" in data:
            roles["date"].append(data["date_column"])
        if "metric_column" in data:
            roles["metric"].append(data["metric_column"])
    elif tool_name == "segment_contribution":
        if "segment_column" in data:
            roles["group"].append(data["segment_column"])
        if "metric_column" in data:
            roles["metric"].append(data["metric_column"])
    elif tool_name == "correlation":
        if "x_column" in data:
            roles["metric"].append(data["x_column"])
        if "y_column" in data:
            roles["metric"].append(data["y_column"])
    elif tool_name == "detect_anomalies_iqr" and "metric_column" in data:
        roles["metric"].append(data["metric_column"])

    return roles


def validate_task_args(
    tool_name: str,
    args: dict[str, Any],
    profile: DatasetProfile,
    args_model: type[BaseModel] | None,
    available_tools: list[str] | None = None,
) -> tuple[BaseModel | None, Failure | None]:
    """Validate task arguments against the tool schema and dataset profile.

    Returns (parsed_args, None) on success or (None, Failure) on validation rejection.
    """
    # 1. Unknown tool check
    if args_model is None:
        return None, Failure(
            failure_class=FailureClass.UNKNOWN_TOOL,
            recoverable=True,
            message=f"Unknown tool '{tool_name}'",
            context={
                "requested_tool": tool_name,
                "available_tools": available_tools or [],
            },
        )

    # 2. Schema validation with args model (extra='forbid' enforced)
    try:
        parsed_args = args_model.model_validate(args)
    except ValidationError as exc:
        err_list = [
            {"loc": [str(loc) for loc in err["loc"]], "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return None, Failure(
            failure_class=FailureClass.INVALID_ARGS,
            recoverable=True,
            message=f"Argument schema validation failed for tool '{tool_name}'",
            context={
                "validation_errors": err_list,
                "tool_name": tool_name,
            },
        )

    # 3. Column existence and semantic type validation against profile
    profile_cols = {col.name: col for col in profile.columns}
    roles = _extract_column_references(tool_name, parsed_args)

    all_referenced_cols = (
        roles["metric"]
        + roles["date"]
        + roles["group"]
        + roles["filter"]
        + roles["entity"]
        + roles["other"]
    )

    for col in all_referenced_cols:
        if col not in profile_cols:
            return None, Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message=f"Column '{col}' does not exist in dataset profile",
                context={
                    "missing_column": col,
                    "available_columns": list(profile_cols.keys()),
                },
            )

    # Metric columns must be NUMERIC_MEASURE
    for col in roles["metric"]:
        col_prof = profile_cols[col]
        if col_prof.semantic_type != SemanticType.NUMERIC_MEASURE:
            return None, Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message=(
                    f"Column '{col}' has semantic type '{col_prof.semantic_type.value}', "
                    "expected 'numeric_measure'"
                ),
                context={
                    "column": col,
                    "actual_type": col_prof.semantic_type.value,
                    "required_types": [SemanticType.NUMERIC_MEASURE.value],
                },
            )

    # Date columns must be DATE
    for col in roles["date"]:
        col_prof = profile_cols[col]
        if col_prof.semantic_type != SemanticType.DATE:
            return None, Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message=(
                    f"Column '{col}' has semantic type '{col_prof.semantic_type.value}', "
                    "expected 'date'"
                ),
                context={
                    "column": col,
                    "actual_type": col_prof.semantic_type.value,
                    "required_types": [SemanticType.DATE.value],
                },
            )

    # Grouping columns must not be free TEXT
    for col in roles["group"]:
        col_prof = profile_cols[col]
        if col_prof.semantic_type == SemanticType.TEXT:
            return None, Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message=f"Cannot group by free-form text column '{col}'",
                context={
                    "column": col,
                    "actual_type": SemanticType.TEXT.value,
                    "allowed_types": [
                        SemanticType.CATEGORY.value,
                        SemanticType.IDENTIFIER.value,
                        SemanticType.DATE.value,
                    ],
                },
            )

    # 4. Period coverage check for period_compare
    if tool_name == "period_compare":
        data = parsed_args.model_dump()
        date_col = data.get("date_column")
        base_period = data.get("base_period")
        compare_period = data.get("compare_period")

        # Find date coverage for date_col
        coverage_map = {dc.column: dc for dc in profile.date_coverage}
        cov = coverage_map.get(date_col)

        if cov and cov.min and cov.max:
            for p_name, period_tuple in [
                ("base_period", base_period),
                ("compare_period", compare_period),
            ]:
                if isinstance(period_tuple, (list, tuple)) and len(period_tuple) == 2:
                    p_start, p_end = period_tuple[0], period_tuple[1]
                    # Out of bounds if period ends before dataset min or starts after dataset max
                    if p_end < cov.min or p_start > cov.max:
                        return None, Failure(
                            failure_class=FailureClass.INVALID_ARGS,
                            recoverable=True,
                            message=(
                                f"Requested {p_name} [{p_start}, {p_end}] lies strictly outside "
                                f"dataset coverage [{cov.min}, {cov.max}] for column '{date_col}'"
                            ),
                            context={
                                "column": date_col,
                                "period_name": p_name,
                                "requested_period": [p_start, p_end],
                                "coverage_min": cov.min,
                                "coverage_max": cov.max,
                            },
                        )

    return parsed_args, None
