"""Task executor for deterministic analytical tools.

Layer 5 module: executes a single Task, enforces budgets/timeouts, records audit
traces, validates invariants, and produces an EvidenceRecord or Failure.
Never raises exceptions to callers.
"""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

import pandas as pd
from pydantic import BaseModel

from da_agent.contracts.models import (
    CONTRACT_VERSION,
    Budgets,
    DatasetProfile,
    EvidenceRecord,
    Failure,
    FailureClass,
    Task,
)
from da_agent.core.trace import RunTraceWriter
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    ToolResultEnvelope,
    canonical_dumps,
    normalize_canonical_value,
)
from da_agent.tools.registry import DEFAULT_REGISTRY, ToolRegistry
from da_agent.validation.args import validate_task_args
from da_agent.validation.results import validate_tool_result


def compute_args_hash(tool_name: str, args_dict: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 hash over canonical representation of tool name and args."""
    canonical_payload = {
        "args": normalize_canonical_value(args_dict),
        "tool": tool_name,
    }
    serialized = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_bounded_summary(tool_name: str, result_dict: dict[str, Any]) -> dict[str, Any]:
    """Build a concise, bounded summary of the result for LLM consumption without raw rows."""
    if tool_name == "filter":
        return {
            "output_row_count": result_dict.get("output_row_count", 0),
            "sample_matched_indices": result_dict.get("matched_indices", [])[:10],
        }
    if tool_name == "group_aggregate":
        rows = result_dict.get("rows", [])
        return {
            "total_groups": result_dict.get("total_groups", 0),
            "metric_column": result_dict.get("metric_column"),
            "aggregation": result_dict.get("aggregation"),
            "sample_groups": rows[:10],
        }
    if tool_name == "rank":
        rows = result_dict.get("rows", [])
        return {
            "total_ranked": len(rows),
            "top_rows": rows[:10],
            "tie_groups": result_dict.get("tie_groups", []),
            "ties_at_cutoff": result_dict.get("ties_at_cutoff", False),
            "null_count": result_dict.get("null_count", 0),
        }
    if tool_name == "period_compare":
        return {
            "base_period": result_dict.get("base_period"),
            "compare_period": result_dict.get("compare_period"),
            "absolute_change": result_dict.get("absolute_change"),
            "relative_growth": result_dict.get("relative_growth"),
            "undefined_reason": result_dict.get("undefined_reason"),
            "base_negative": result_dict.get("base_negative", False),
        }
    if tool_name == "trend":
        points = result_dict.get("points", [])
        return {
            "grain": result_dict.get("grain"),
            "direction": result_dict.get("direction"),
            "slope": result_dict.get("slope"),
            "total_periods": result_dict.get("total_periods", 0),
            "sample_points": points[:12],
        }
    if tool_name == "segment_contribution":
        segments = result_dict.get("segments", [])
        return {
            "total_value": result_dict.get("total_value"),
            "top_segments": segments[:10],
            "shares_sum": result_dict.get("shares_sum"),
            "reconciles": result_dict.get("reconciles"),
            "has_negative_segments": result_dict.get("has_negative_segments", False),
            "undefined_reason": result_dict.get("undefined_reason"),
        }
    if tool_name == "correlation":
        return {
            "x_column": result_dict.get("x_column"),
            "y_column": result_dict.get("y_column"),
            "correlation": result_dict.get("correlation"),
            "status": result_dict.get("status"),
            "valid_pairs_count": result_dict.get("valid_pairs_count"),
            "undefined_reason": result_dict.get("undefined_reason"),
        }
    if tool_name == "detect_anomalies_iqr":
        items = result_dict.get("flagged_items", [])
        return {
            "metric_column": result_dict.get("metric_column"),
            "status": result_dict.get("status"),
            "q1": result_dict.get("q1"),
            "median": result_dict.get("median"),
            "q3": result_dict.get("q3"),
            "iqr": result_dict.get("iqr"),
            "lower_fence": result_dict.get("lower_fence"),
            "upper_fence": result_dict.get("upper_fence"),
            "flagged_count": result_dict.get("flagged_count", 0),
            "sample_flagged_items": items[:10],
        }
    return result_dict


def execute_task(
    task: Task,
    df: pd.DataFrame,
    profile: DatasetProfile,
    budgets: Budgets,
    trace_writer: RunTraceWriter | None = None,
    registry: ToolRegistry = DEFAULT_REGISTRY,
    evidence_store: dict[str, Any] | None = None,
) -> tuple[EvidenceRecord | None, Failure | None]:
    """Execute a single analytical task deterministically with audit logging and invariant validation.

    Never raises bare exceptions to callers. Returns (EvidenceRecord, None) on success
    or (None, Failure) on classified rejection or error.
    """
    # 1. Log tool call initiation to trace
    if trace_writer is not None:
        trace_writer.log_tool_call(
            task_id=task.id,
            tool=task.tool,
            args=task.args,
        )

    # 2. Allowlisted Registry Lookup
    entry = registry.get(task.tool)
    if entry is None:
        failure = Failure(
            failure_class=FailureClass.UNKNOWN_TOOL,
            recoverable=True,
            message=f"Tool '{task.tool}' is not allowlisted in registry",
            context={
                "requested_tool": task.tool,
                "available_tools": registry.list_tools(),
            },
            task_id=task.id,
        )
        if trace_writer is not None:
            trace_writer.log_failure(failure)
        return None, failure

    # 3. Argument Validation (against schema and DatasetProfile)
    parsed_args, arg_failure = validate_task_args(
        tool_name=task.tool,
        args=task.args,
        profile=profile,
        args_model=entry.args_model,
        available_tools=registry.list_tools(),
    )
    if arg_failure is not None:
        arg_failure.task_id = task.id
        if trace_writer is not None:
            trace_writer.log_failure(arg_failure)
        return None, arg_failure

    assert parsed_args is not None

    # 4. Compute canonical args_hash
    args_hash = compute_args_hash(task.tool, parsed_args.model_dump(mode="json"))

    # 5. Execute tool with per-call timeout enforcement
    timeout_s = budgets.per_call_timeout_s
    envelope: ToolResultEnvelope | None = None

    try:
        with ThreadPoolExecutor(max_workers=1) as thread_pool:
            future = thread_pool.submit(entry.fn, df, parsed_args)
            envelope = future.result(timeout=timeout_s)
    except FuturesTimeoutError:
        timeout_failure = Failure(
            failure_class=FailureClass.TRANSIENT,
            recoverable=True,
            message=f"Tool '{task.tool}' exceeded per-call timeout of {timeout_s}s",
            context={"timeout_s": timeout_s, "task_id": task.id},
            task_id=task.id,
        )
        if trace_writer is not None:
            trace_writer.log_failure(timeout_failure)
        return None, timeout_failure
    except ToolError as tool_exc:
        tool_failure = Failure(
            failure_class=tool_exc.failure_class,
            recoverable=tool_exc.recoverable,
            message=tool_exc.message,
            context=tool_exc.context,
            task_id=task.id,
        )
        if trace_writer is not None:
            trace_writer.log_failure(tool_failure)
        return None, tool_failure
    except Exception as exc:  # noqa: BLE001
        # Option 1: Map unexpected tool exceptions to SCHEMA_VIOLATION with recoverable=False
        unexpected_failure = Failure(
            failure_class=FailureClass.SCHEMA_VIOLATION,
            recoverable=False,
            message=f"Unhandled tool execution exception: {type(exc).__name__}: {exc}",
            context={
                "exception_type": type(exc).__name__,
                "details": str(exc),
                "task_id": task.id,
            },
            task_id=task.id,
        )
        if trace_writer is not None:
            trace_writer.log_failure(unexpected_failure)
        return None, unexpected_failure

    assert envelope is not None

    # 6. Result Schema and Numerical Invariants Validation
    valid, invariants_checked, result_failure = validate_tool_result(
        tool_name=task.tool,
        result_data=envelope.result,
        input_row_count=envelope.input_row_count,
        result_model=entry.result_model,
    )
    if result_failure is not None:
        result_failure.task_id = task.id
        if trace_writer is not None:
            trace_writer.log_failure(result_failure)
        return None, result_failure

    # 7. Generate Bounded Summary for LLM and full result for storage
    raw_result_dict = (
        envelope.result.model_dump(mode="json")
        if isinstance(envelope.result, BaseModel)
        else dict(envelope.result)
    )
    bounded_summary = _build_bounded_summary(task.tool, raw_result_dict)

    # 8. Create EvidenceRecord
    revision_suffix = f"_v{task.plan_version}" if task.plan_version > 1 else ""
    evidence_id = f"ev_{task.id}{revision_suffix}_{args_hash[:8]}"
    evidence = EvidenceRecord(
        evidence_id=evidence_id,
        task_id=task.id,
        tool=task.tool,
        args_hash=args_hash,
        dataset_hash=profile.dataset_hash,
        input_row_count=envelope.input_row_count,
        result_summary=bounded_summary,
        result_schema_version=CONTRACT_VERSION,
        invariants_checked=invariants_checked,
        valid=valid,
        invalidated_by=None,
    )

    # 9. Store full canonical result alongside record (Option A)
    if evidence_store is not None:
        evidence_store[evidence_id] = raw_result_dict

    if trace_writer is not None:
        # Store full result file under runs/<run_id>/evidence/<evidence_id>.json
        evidence_dir = trace_writer.run_dir / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_file = evidence_dir / f"{evidence_id}.json"
        with evidence_file.open("w", encoding="utf-8") as f:
            f.write(canonical_dumps(envelope.result))

        # Log evidence record to trace
        trace_writer.log_evidence(evidence)

    return evidence, None
