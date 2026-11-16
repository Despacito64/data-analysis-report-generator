"""Deterministic task fingerprinting, recovery decisions, and no-progress detection.

Architectural Layer 4 (Validation):
- Pure functions only.
- Deterministic only (zero LLM calls).
- Strictly imports from da_agent.contracts, da_agent.core, and da_agent.validation.
- NEVER imports da_agent.tools, da_agent.agent, da_agent.reports, da_agent.pipeline, or evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts.models import (
    ClassifiedFailure,
    Failure,
    PlanRevision,
    RecoveryFailureClass,
    RetryPolicy,
    Task,
)
from da_agent.core.config import RecoveryLimits
from da_agent.validation.failures import classify_failure


class RecoveryAction(str, Enum):
    """Action to be taken by the agent control loop in response to an execution failure."""

    RETRY_IDENTICAL = "retry_identical"
    REPAIR = "repair"
    REPLAN = "replan"
    STOP = "stop"


class NoProgressPattern(str, Enum):
    """Classified pattern of execution stagnation."""

    IDENTICAL_FINGERPRINT = "identical_fingerprint"
    EMPTY_REVISION = "empty_revision"
    CYCLING = "cycling"


class RecoveryCounters(BaseModel):
    """Counters tracking retry, repair, and replan occurrences."""

    model_config = ConfigDict(extra="forbid")

    identical_retries: int = Field(default=0, ge=0)
    repair_attempts: int = Field(default=0, ge=0)
    replan_count: int = Field(default=0, ge=0)


class RecoveryDecision(BaseModel):
    """Deterministic recovery decision with explicit rationale."""

    model_config = ConfigDict(extra="forbid")

    action: RecoveryAction
    reason: str
    failure_class: RecoveryFailureClass
    retry_policy: RetryPolicy


class NoProgressResult(BaseModel):
    """Outcome of execution progress inspection."""

    model_config = ConfigDict(extra="forbid")

    no_progress: bool
    reason: str | None = None
    pattern: NoProgressPattern | None = None


def _normalize_value(val: Any) -> Any:
    """Recursively normalize data values for deterministic hashing."""
    if isinstance(val, bool):
        return val
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        if not math.isfinite(val):
            return None
        if val == 0.0 or val == -0.0:
            return 0
        if val.is_integer():
            return int(val)
        return round(val, 9)
    if isinstance(val, str):
        return val.strip().casefold()
    if isinstance(val, dict):
        return {
            str(k).strip().casefold(): _normalize_value(v)
            for k, v in sorted(val.items(), key=lambda item: str(item[0]).strip().casefold())
        }
    if isinstance(val, (list, tuple, set)):
        return [_normalize_value(v) for v in val]
    return str(val)


def fingerprint(task: Task | dict[str, Any] | Any) -> str:
    """Compute deterministic SHA-256 hash of tool + normalized arguments + dependency IDs.

    Normalization rules:
    - Tool name: stripped and lowercased.
    - Dict keys: recursively sorted and lowercased.
    - Strings: stripped and lowercased.
    - Numbers: canonicalized (finite, -0.0 -> 0, float integers converted to int).
    - Dependencies: sorted list of stripped and lowercased task IDs.
    """
    if hasattr(task, "tool"):
        tool = getattr(task, "tool", "")
        args = getattr(task, "args", {})
        depends_on = getattr(task, "depends_on", [])
    elif isinstance(task, dict):
        tool = task.get("tool", "")
        args = task.get("args", {})
        depends_on = task.get("depends_on", [])
    else:
        raise TypeError(f"Unsupported task type for fingerprint: {type(task)}")

    norm_tool = str(tool).strip().casefold()
    norm_args = _normalize_value(args)
    norm_deps = sorted(str(d).strip().casefold() for d in (depends_on or []))

    payload = {
        "tool": norm_tool,
        "args": norm_args,
        "depends_on": norm_deps,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def decide_recovery(
    failure: ClassifiedFailure | Failure | Exception | dict[str, Any] | Any,
    task_history: list[Any] | None = None,
    counters: RecoveryCounters | dict[str, int] | None = None,
    limits: RecoveryLimits | None = None,
    current_task: Task | dict[str, Any] | None = None,
) -> RecoveryDecision:
    """Recommend recovery action using D-033 retry policies and configured limits."""
    # Normalize failure to ClassifiedFailure
    if isinstance(failure, ClassifiedFailure):
        classified = failure
    else:
        classified = classify_failure(failure)

    active_limits = limits or RecoveryLimits()

    if isinstance(counters, RecoveryCounters):
        c_identical = counters.identical_retries
        c_repair = counters.repair_attempts
        c_replan = counters.replan_count
    elif isinstance(counters, dict):
        c_identical = counters.get("identical_retries", 0)
        c_repair = counters.get("repair_attempts", 0)
        c_replan = counters.get("replan_count", 0)
    else:
        c_identical = 0
        c_repair = 0
        c_replan = 0

    f_class = classified.failure_class
    policy = classified.retry_policy

    # 1. Terminal failures are never retried
    if policy == RetryPolicy.TERMINAL:
        return RecoveryDecision(
            action=RecoveryAction.STOP,
            reason=f"Terminal failure ({f_class.value}): cannot be recovered or retried",
            failure_class=f_class,
            retry_policy=policy,
        )

    # 2. Identical retries strictly for retryable_identical (transient_error, tool_timeout)
    if policy == RetryPolicy.RETRYABLE_IDENTICAL:
        if c_identical >= active_limits.identical_retry_cap:
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                reason=(
                    f"Identical retry cap reached (limit: {active_limits.identical_retry_cap}) "
                    f"for {f_class.value}"
                ),
                failure_class=f_class,
                retry_policy=policy,
            )
        return RecoveryDecision(
            action=RecoveryAction.RETRY_IDENTICAL,
            reason=(
                f"Transient failure ({f_class.value}) eligible for identical retry "
                f"(attempt {c_identical + 1} of {active_limits.identical_retry_cap})"
            ),
            failure_class=f_class,
            retry_policy=policy,
        )

    # 3. Repairable failures (invalid_argument, unknown_column, type_mismatch, empty_result)
    # Check if a repair attempt repeats an identical fingerprint
    if current_task is not None and task_history:
        current_fp = fingerprint(current_task)
        prev_fps = []
        for item in task_history:
            if isinstance(item, str):
                prev_fps.append(item)
            elif hasattr(item, "tool") or (isinstance(item, dict) and "tool" in item):
                prev_fps.append(fingerprint(item))
            elif isinstance(item, dict) and "fingerprint" in item:
                prev_fps.append(item["fingerprint"])

        if prev_fps and current_fp == prev_fps[-1]:
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                reason="Repairable failure repeated with identical fingerprint (no argument change)",
                failure_class=f_class,
                retry_policy=policy,
            )

    # Check repair attempts cap
    if c_repair >= active_limits.repair_attempts_per_task:
        # Check if replans are exhausted
        if c_replan >= active_limits.replans_per_question:
            return RecoveryDecision(
                action=RecoveryAction.STOP,
                reason=(
                    f"Repair attempts cap reached ({active_limits.repair_attempts_per_task}) "
                    f"and replan cap reached ({active_limits.replans_per_question})"
                ),
                failure_class=f_class,
                retry_policy=policy,
            )
        return RecoveryDecision(
            action=RecoveryAction.REPLAN,
            reason=(
                f"Repair attempts cap reached ({active_limits.repair_attempts_per_task}); "
                f"escalating to replan ({c_replan + 1} of {active_limits.replans_per_question})"
            ),
            failure_class=f_class,
            retry_policy=policy,
        )

    return RecoveryDecision(
        action=RecoveryAction.REPAIR,
        reason=(
            f"Repairable failure ({f_class.value}) eligible for repair "
            f"(attempt {c_repair + 1} of {active_limits.repair_attempts_per_task})"
        ),
        failure_class=f_class,
        retry_policy=policy,
    )


def detect_no_progress(history: list[Any]) -> NoProgressResult:
    """Inspect execution history for stagnation patterns.

    Detects:
    (a) Repeated identical task fingerprint when not allowed.
    (b) Plan revision adding no new valid evidence and leaving pending tasks unchanged.
    (c) Periodic cycling among 3+ alternating states.
    """
    if not history:
        return NoProgressResult(no_progress=False)

    # (a) Check for repeated identical task fingerprints
    for i in range(1, len(history)):
        curr = history[i]
        prev = history[i - 1]

        # Extract fingerprints and retry authorizations
        curr_fp = None
        prev_fp = None
        is_allowed_identical = False

        if isinstance(curr, dict) and isinstance(prev, dict):
            curr_fp = curr.get("fingerprint") or (
                fingerprint(curr) if "tool" in curr else None
            )
            prev_fp = prev.get("fingerprint") or (
                fingerprint(prev) if "tool" in prev else None
            )
            is_allowed_identical = bool(curr.get("allowed_identical", False))
        elif hasattr(curr, "tool") and hasattr(prev, "tool"):
            curr_fp = fingerprint(curr)
            prev_fp = fingerprint(prev)

        if curr_fp and prev_fp and curr_fp == prev_fp and not is_allowed_identical:
            # Check if this repetition was an unapproved identical repair or failure repeat
            return NoProgressResult(
                no_progress=True,
                pattern=NoProgressPattern.IDENTICAL_FINGERPRINT,
                reason=f"Repeated identical fingerprint '{curr_fp}' detected without valid retry authorization",
            )

    # (b) Check for plan revision adding no new valid evidence and leaving pending tasks unchanged
    for item in history:
        if isinstance(item, PlanRevision):
            # If revision has no affected tasks
            if not item.affected_tasks:
                return NoProgressResult(
                    no_progress=True,
                    pattern=NoProgressPattern.EMPTY_REVISION,
                    reason="Plan revision specifies no affected tasks",
                )
        elif isinstance(item, dict):
            if item.get("event") == "revision" or "new_evidence_count" in item:
                new_ev = item.get("new_evidence_count", 0)
                changed_tasks = item.get("changed_pending_tasks", 0)
                if new_ev == 0 and changed_tasks == 0:
                    return NoProgressResult(
                        no_progress=True,
                        pattern=NoProgressPattern.EMPTY_REVISION,
                        reason="Plan revision produced no new valid evidence and left pending tasks unchanged",
                    )

    # (c) Check for cycling among 3+ alternating states
    state_tokens: list[str] = []
    for item in history:
        if isinstance(item, str):
            state_tokens.append(item)
        elif isinstance(item, dict):
            token = (
                item.get("state")
                or item.get("fingerprint")
                or (fingerprint(item) if "tool" in item else None)
            )
            if token:
                state_tokens.append(str(token))
        elif hasattr(item, "tool"):
            state_tokens.append(fingerprint(item))

    n = len(state_tokens)
    for k in range(3, n // 2 + 1):
        suffix1 = state_tokens[-k:]
        suffix2 = state_tokens[-2 * k : -k]
        if suffix1 == suffix2 and len(set(suffix1)) >= 3:
            return NoProgressResult(
                no_progress=True,
                pattern=NoProgressPattern.CYCLING,
                reason=f"Detected periodic cycle among {len(set(suffix1))} alternating states: {suffix1}",
            )

    return NoProgressResult(no_progress=False)
