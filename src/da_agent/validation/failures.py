"""Failure classification and factual recovery context.

Layer 4 module: strictly imports contracts and core; NEVER imports da_agent.tools,
da_agent.agent, da_agent.reports, da_agent.pipeline, or evaluation.
Maps tool errors and execution outcomes into typed ClassifiedFailure records
with factual context (never expected answers or oracle data).
"""

from __future__ import annotations

import re
from typing import Any

from da_agent.contracts.models import (
    ClassifiedFailure,
    DatasetProfile,
    Failure,
    FailureClass,
    RecoveryContext,
    RecoveryFailureClass,
    RetryPolicy,
)

RETRY_POLICY_MAP: dict[RecoveryFailureClass, RetryPolicy] = {
    RecoveryFailureClass.TOOL_TIMEOUT: RetryPolicy.RETRYABLE_IDENTICAL,
    RecoveryFailureClass.TRANSIENT_ERROR: RetryPolicy.RETRYABLE_IDENTICAL,
    RecoveryFailureClass.INVALID_ARGUMENT: RetryPolicy.REPAIRABLE,
    RecoveryFailureClass.UNKNOWN_COLUMN: RetryPolicy.REPAIRABLE,
    RecoveryFailureClass.TYPE_MISMATCH: RetryPolicy.REPAIRABLE,
    RecoveryFailureClass.EMPTY_RESULT: RetryPolicy.REPAIRABLE,
    RecoveryFailureClass.UNSUPPORTED_OPERATION: RetryPolicy.REPAIRABLE,
    RecoveryFailureClass.INVARIANT_VIOLATION: RetryPolicy.TERMINAL,
    RecoveryFailureClass.RUNTIME_ERROR: RetryPolicy.TERMINAL,
    RecoveryFailureClass.DEPENDENCY_FAILURE: RetryPolicy.TERMINAL,
    RecoveryFailureClass.UNKNOWN: RetryPolicy.TERMINAL,
}


def _clean_message(msg: str) -> str:
    """Normalize error message to factual one-line string."""
    cleaned = re.sub(r"\s+", " ", str(msg)).strip()
    return cleaned[:500] if len(cleaned) > 500 else cleaned


def classify_failure(
    outcome: Any,
    *,
    task_id: str | None = None,
    failing_args: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    profile: DatasetProfile | None = None,
    available_columns: list[str] | None = None,
    available_tools: list[str] | None = None,
    input_row_count: int | None = None,
    observed_row_count: int | None = None,
) -> ClassifiedFailure:
    """Map any tool error, executor outcome, or exception into a typed ClassifiedFailure.

    Never raises an exception; unknown or unhandled errors map to RecoveryFailureClass.UNKNOWN.
    Guarantees factual-only recovery context without benchmark or oracle data.
    """
    try:
        # 1. Already a ClassifiedFailure
        if isinstance(outcome, ClassifiedFailure):
            ctx = outcome.recovery_context
            # Enrich context if caller provided additional metadata
            cols = available_columns or (
                [c.name for c in profile.columns] if profile is not None else ctx.valid_columns
            )
            enriched_ctx = RecoveryContext(
                valid_columns=list(cols or ctx.valid_columns),
                observed_row_count=observed_row_count
                if observed_row_count is not None
                else ctx.observed_row_count,
                input_row_count=input_row_count
                if input_row_count is not None
                else ctx.input_row_count,
                failing_parameter=ctx.failing_parameter,
                expected_type=ctx.expected_type,
                actual_type=ctx.actual_type,
                available_tools=list(available_tools or ctx.available_tools),
                failed_upstream_task_id=ctx.failed_upstream_task_id,
            )
            return ClassifiedFailure(
                failure_class=outcome.failure_class,
                task_id=task_id or outcome.task_id,
                failing_args=failing_args if failing_args is not None else outcome.failing_args,
                message=outcome.message,
                recovery_context=enriched_ctx,
                retry_policy=outcome.retry_policy,
            )

        # 2. Extract raw attributes from outcome
        raw_msg = ""
        raw_class_str = ""
        context_dict: dict[str, Any] = dict(context or {})
        assigned_task_id = task_id

        if isinstance(outcome, Failure):
            raw_msg = outcome.message
            raw_class_str = (
                outcome.failure_class.value
                if hasattr(outcome.failure_class, "value")
                else str(outcome.failure_class)
            )
            context_dict.update(outcome.context or {})
            if outcome.task_id:
                assigned_task_id = outcome.task_id
            if outcome.failing_args and failing_args is None:
                failing_args = outcome.failing_args
            if outcome.detailed_class is not None:
                classified_class = outcome.detailed_class
                policy = RETRY_POLICY_MAP.get(classified_class, RetryPolicy.TERMINAL)
                return _build_classified_record(
                    failure_class=classified_class,
                    task_id=assigned_task_id,
                    failing_args=failing_args or {},
                    message=_clean_message(raw_msg),
                    context_dict=context_dict,
                    profile=profile,
                    available_columns=available_columns,
                    available_tools=available_tools,
                    input_row_count=input_row_count,
                    observed_row_count=observed_row_count,
                    policy=policy,
                )
        elif hasattr(outcome, "failure_class"):
            # ToolError or similar domain object
            fc = outcome.failure_class
            raw_class_str = fc.value if hasattr(fc, "value") else str(fc)
            raw_msg = getattr(outcome, "message", str(outcome))
            context_dict = dict(getattr(outcome, "context", {}) or {})
        elif isinstance(outcome, Exception):
            raw_msg = str(outcome)
            exc_name = type(outcome).__name__
            if "Timeout" in exc_name:
                raw_class_str = "timeout"
            else:
                raw_class_str = exc_name.lower()
        elif isinstance(outcome, str):
            raw_msg = outcome
            raw_class_str = "string"
        elif isinstance(outcome, dict):
            raw_msg = str(outcome.get("message", outcome.get("error", "")))
            raw_class_str = str(outcome.get("failure_class", outcome.get("class", "")))
            context_dict = dict(outcome.get("context", {}))
        else:
            raw_msg = str(outcome)
            raw_class_str = "unknown"

        # 3. Classify into RecoveryFailureClass
        msg_lower = raw_msg.lower()
        classified_class = _determine_failure_class(raw_class_str, msg_lower, context_dict)
        policy = RETRY_POLICY_MAP.get(classified_class, RetryPolicy.TERMINAL)

        return _build_classified_record(
            failure_class=classified_class,
            task_id=assigned_task_id,
            failing_args=failing_args or {},
            message=_clean_message(raw_msg or f"Failure of class '{classified_class.value}'"),
            context_dict=context_dict,
            profile=profile,
            available_columns=available_columns,
            available_tools=available_tools,
            input_row_count=input_row_count,
            observed_row_count=observed_row_count,
            policy=policy,
        )

    except Exception as exc:  # noqa: BLE001
        # Safe default that NEVER raises
        return ClassifiedFailure(
            failure_class=RecoveryFailureClass.UNKNOWN,
            task_id=task_id,
            failing_args=failing_args or {},
            message=f"Safe fallback: error during failure classification ({type(exc).__name__}: {exc})",
            recovery_context=RecoveryContext(),
            retry_policy=RetryPolicy.TERMINAL,
        )


def _determine_failure_class(
    raw_class: str,
    msg_lower: str,
    context: dict[str, Any],
) -> RecoveryFailureClass:
    """Determine fine-grained failure class from coarse indicators."""
    # 1. Dependency failure
    if (
        "dependency" in msg_lower
        or "skipped" in msg_lower
        or raw_class == "dependency_failure"
        or "failed_upstream" in context
    ):
        return RecoveryFailureClass.DEPENDENCY_FAILURE

    # 2. Timeout
    if (
        raw_class in ("timeout", "tool_timeout", "transient_timeout")
        or "timeout" in msg_lower
        or "timeout_s" in context
    ):
        return RecoveryFailureClass.TOOL_TIMEOUT

    # 3. Transient error
    if (
        raw_class in ("transient", "transient_error")
        or "connection" in msg_lower
        or "temporar" in msg_lower
    ):
        return RecoveryFailureClass.TRANSIENT_ERROR

    # 4. Unknown tool or unsupported operation
    if (
        raw_class in ("unknown_tool", "unsupported_operation")
        or "not allowlisted" in msg_lower
        or "unknown tool" in msg_lower
        or "unsupported" in msg_lower
    ):
        return RecoveryFailureClass.UNSUPPORTED_OPERATION

    # 5. Empty result
    if (
        raw_class in ("empty_result", FailureClass.EMPTY_RESULT.value)
        or "empty result" in msg_lower
        or "zero input rows" in msg_lower
        or "0 matched rows" in msg_lower
        or "matched 0 rows" in msg_lower
    ):
        return RecoveryFailureClass.EMPTY_RESULT

    # 6. Invariant violation
    if (
        raw_class in ("invariant_violation", FailureClass.INVARIANT_VIOLATION.value)
        or "invariant violation" in msg_lower
        or "invariant" in context
    ):
        return RecoveryFailureClass.INVARIANT_VIOLATION

    # 7. Unknown column
    if (
        "missing_column" in context
        or "column" in msg_lower
        and (
            "does not exist" in msg_lower
            or "unknown column" in msg_lower
            or "not found" in msg_lower
        )
    ):
        return RecoveryFailureClass.UNKNOWN_COLUMN

    # 8. Type mismatch
    if (
        "actual_type" in context
        or "required_types" in context
        or "semantic type" in msg_lower
        or ("type" in msg_lower and ("expected" in msg_lower or "mismatch" in msg_lower))
        or "free-form text" in msg_lower
    ):
        return RecoveryFailureClass.TYPE_MISMATCH

    # 9. Invalid args
    if (
        raw_class in ("invalid_args", "invalid_argument", FailureClass.INVALID_ARGS.value)
        or "validation" in msg_lower
        or "outside dataset coverage" in msg_lower
        or "argument" in msg_lower
    ):
        return RecoveryFailureClass.INVALID_ARGUMENT

    # 10. Runtime error / schema violation
    if (
        raw_class in ("schema_violation", "runtime_error", FailureClass.SCHEMA_VIOLATION.value)
        or "exception" in msg_lower
        or "error" in msg_lower
    ):
        return RecoveryFailureClass.RUNTIME_ERROR

    # 11. Fallback
    return RecoveryFailureClass.UNKNOWN


def _build_classified_record(
    failure_class: RecoveryFailureClass,
    task_id: str | None,
    failing_args: dict[str, Any],
    message: str,
    context_dict: dict[str, Any],
    profile: DatasetProfile | None,
    available_columns: list[str] | None,
    available_tools: list[str] | None,
    input_row_count: int | None,
    observed_row_count: int | None,
    policy: RetryPolicy,
) -> ClassifiedFailure:
    """Build factual recovery context and typed ClassifiedFailure."""
    # Extract valid columns
    cols: list[str] = []
    if available_columns is not None:
        cols = list(available_columns)
    elif profile is not None:
        cols = [c.name for c in profile.columns]
    elif "available_columns" in context_dict and isinstance(
        context_dict["available_columns"], list
    ):
        cols = [str(c) for c in context_dict["available_columns"]]

    # Extract tools
    tools: list[str] = []
    if available_tools is not None:
        tools = list(available_tools)
    elif "available_tools" in context_dict and isinstance(context_dict["available_tools"], list):
        tools = [str(t) for t in context_dict["available_tools"]]

    # Failing parameter
    param = context_dict.get("missing_column") or context_dict.get("column")
    if not param and "validation_errors" in context_dict:
        verrs = context_dict["validation_errors"]
        if isinstance(verrs, list) and verrs and isinstance(verrs[0], dict):
            loc = verrs[0].get("loc", [])
            if loc:
                param = str(loc[-1])

    # Expected / actual types
    exp_type: str | None = None
    if "required_types" in context_dict:
        req = context_dict["required_types"]
        exp_type = ", ".join(req) if isinstance(req, list) else str(req)
    act_type = str(context_dict["actual_type"]) if "actual_type" in context_dict else None

    # Upstream failed task
    failed_upstream = context_dict.get("failed_upstream_task_id")
    if not failed_upstream and "dependency" in message.lower():
        match = re.search(r"dependency\s*['\"]?([A-Za-z0-9_-]+)['\"]?", message, re.IGNORECASE)
        if match:
            failed_upstream = match.group(1)

    rec_ctx = RecoveryContext(
        valid_columns=cols,
        observed_row_count=observed_row_count
        if observed_row_count is not None
        else context_dict.get("output_row_count", context_dict.get("observed_row_count")),
        input_row_count=input_row_count
        if input_row_count is not None
        else context_dict.get("input_row_count"),
        failing_parameter=str(param) if param is not None else None,
        expected_type=exp_type,
        actual_type=act_type,
        available_tools=tools,
        failed_upstream_task_id=str(failed_upstream) if failed_upstream else None,
    )

    return ClassifiedFailure(
        failure_class=failure_class,
        task_id=task_id,
        failing_args=failing_args,
        message=message,
        recovery_context=rec_ctx,
        retry_policy=policy,
    )


def render_recovery_context(failure: ClassifiedFailure | Failure) -> dict[str, Any]:
    """Render structured factual recovery context for the planner without changing planner prompts.

    Guarantees that context contains only factual observations: valid column names,
    observed row counts, failing parameter, expected type, and safe guidance.
    Never includes expected answers or benchmark question data.
    """
    if isinstance(failure, Failure):
        classified = classify_failure(failure)
    else:
        classified = failure

    ctx = classified.recovery_context

    # Derive factual guidance based on failure class
    guidance: str
    if classified.failure_class == RecoveryFailureClass.UNKNOWN_COLUMN:
        cols_preview = ", ".join(ctx.valid_columns[:15]) if ctx.valid_columns else "none declared"
        guidance = f"Select from available columns: [{cols_preview}]"
    elif classified.failure_class == RecoveryFailureClass.TYPE_MISMATCH:
        guidance = (
            f"Parameter '{ctx.failing_parameter or 'unknown'}' expects type '{ctx.expected_type or 'numeric_measure'}', "
            f"got '{ctx.actual_type or 'unknown'}'"
        )
    elif classified.failure_class == RecoveryFailureClass.EMPTY_RESULT:
        guidance = "Filter or condition resulted in 0 rows. Adjust filter threshold or remove restrictive condition"
    elif classified.failure_class == RecoveryFailureClass.UNSUPPORTED_OPERATION:
        tools_preview = (
            ", ".join(ctx.available_tools[:10]) if ctx.available_tools else "allowlisted tools"
        )
        guidance = f"Use an allowlisted tool from: [{tools_preview}]"
    elif classified.failure_class in (
        RecoveryFailureClass.TOOL_TIMEOUT,
        RecoveryFailureClass.TRANSIENT_ERROR,
    ):
        guidance = "Transient execution error; retry with identical arguments"
    elif classified.failure_class == RecoveryFailureClass.DEPENDENCY_FAILURE:
        guidance = (
            f"Upstream task '{ctx.failed_upstream_task_id or 'unknown'}' failed; "
            "replan to replace or omit this dependency"
        )
    elif classified.failure_class == RecoveryFailureClass.INVARIANT_VIOLATION:
        guidance = "Mathematical invariant check failed; task cannot be recovered with same inputs"
    else:
        guidance = "Execution error; review failing arguments and dataset schema"

    return {
        "failure_class": classified.failure_class.value,
        "retry_policy": classified.retry_policy.value,
        "task_id": classified.task_id,
        "message": classified.message,
        "failing_args": classified.failing_args,
        "valid_columns": ctx.valid_columns,
        "observed_row_count": ctx.observed_row_count,
        "input_row_count": ctx.input_row_count,
        "failing_parameter": ctx.failing_parameter,
        "expected_type": ctx.expected_type,
        "actual_type": ctx.actual_type,
        "available_tools": ctx.available_tools,
        "failed_upstream_task_id": ctx.failed_upstream_task_id,
        "guidance": guidance,
    }
