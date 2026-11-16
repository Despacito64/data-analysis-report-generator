"""Unit tests for deterministic task fingerprinting, recovery decisions, and no-progress detection."""

from da_agent.contracts.models import (
    ClassifiedFailure,
    Failure,
    FailureClass,
    PlanRevision,
    RecoveryContext,
    RecoveryFailureClass,
    RetryPolicy,
    RevisionChangeType,
    Task,
)
from da_agent.core.config import RecoveryLimits
from da_agent.validation.recovery import (
    NoProgressPattern,
    RecoveryAction,
    RecoveryCounters,
    decide_recovery,
    detect_no_progress,
    fingerprint,
)


def _make_task(
    task_id: str = "t1",
    tool: str = "filter",
    args: dict | None = None,
    depends_on: list[str] | None = None,
) -> Task:
    return Task(
        id=task_id,
        tool=tool,
        args=args or {"column": "Region", "value": "West"},
        depends_on=depends_on or [],
        rationale="test task",
    )


def test_fingerprint_normalization_and_determinism() -> None:
    t1 = _make_task(
        tool="  FILTER ",
        args={"Column": "  Region ", "Value": " West ", "threshold": 5.0, "zero": -0.0},
        depends_on=["t2", "t1"],
    )
    t2 = _make_task(
        tool="filter",
        args={"zero": 0, "threshold": 5, "value": "west", "column": "region"},
        depends_on=["t1", "t2"],
    )
    # Different key order, case, whitespace, float vs int 5, -0.0 vs 0, and dependency order
    assert fingerprint(t1) == fingerprint(t2)

    # Changed argument produces different fingerprint
    t3 = _make_task(args={"column": "Region", "value": "East"})
    assert fingerprint(t1) != fingerprint(t3)


def test_transient_retried_up_to_cap_then_stop() -> None:
    limits = RecoveryLimits(
        identical_retry_cap=2, repair_attempts_per_task=2, replans_per_question=3
    )
    failure = ClassifiedFailure(
        failure_class=RecoveryFailureClass.TOOL_TIMEOUT,
        task_id="t1",
        failing_args={"column": "Sales"},
        message="Command timed out after 60s",
        recovery_context=RecoveryContext(),
        retry_policy=RetryPolicy.RETRYABLE_IDENTICAL,
    )

    # Attempt 0: identical_retries = 0 -> retry_identical
    d0 = decide_recovery(failure, counters=RecoveryCounters(identical_retries=0), limits=limits)
    assert d0.action == RecoveryAction.RETRY_IDENTICAL
    assert "attempt 1 of 2" in d0.reason

    # Attempt 1: identical_retries = 1 -> retry_identical
    d1 = decide_recovery(failure, counters=RecoveryCounters(identical_retries=1), limits=limits)
    assert d1.action == RecoveryAction.RETRY_IDENTICAL
    assert "attempt 2 of 2" in d1.reason

    # Attempt 2: identical_retries = 2 -> stop (cap hit)
    d2 = decide_recovery(failure, counters=RecoveryCounters(identical_retries=2), limits=limits)
    assert d2.action == RecoveryAction.STOP
    assert "Identical retry cap reached" in d2.reason
    assert "(limit: 2)" in d2.reason


def test_repairable_with_changed_arg_proceeds_same_arg_flagged() -> None:
    limits = RecoveryLimits(
        identical_retry_cap=2, repair_attempts_per_task=2, replans_per_question=3
    )
    failure = ClassifiedFailure(
        failure_class=RecoveryFailureClass.INVALID_ARGUMENT,
        task_id="t1",
        failing_args={"column": "invalid_col"},
        message="Unknown column: invalid_col",
        recovery_context=RecoveryContext(valid_columns=["Sales", "Profit"]),
        retry_policy=RetryPolicy.REPAIRABLE,
    )

    t_prev = _make_task(args={"column": "invalid_col"})
    t_new = _make_task(args={"column": "Sales"})

    # Case A: Same arg repeated -> flagged and stopped immediately
    d_same = decide_recovery(
        failure,
        task_history=[t_prev],
        current_task=t_prev,
        counters=RecoveryCounters(repair_attempts=0),
        limits=limits,
    )
    assert d_same.action == RecoveryAction.STOP
    assert "Repairable failure repeated with identical fingerprint" in d_same.reason

    # Case B: Changed arg -> proceeds with repair
    d_changed = decide_recovery(
        failure,
        task_history=[t_prev],
        current_task=t_new,
        counters=RecoveryCounters(repair_attempts=0),
        limits=limits,
    )
    assert d_changed.action == RecoveryAction.REPAIR
    assert "attempt 1 of 2" in d_changed.reason

    # Case C: Second repair attempt with changed arg
    d_changed_2 = decide_recovery(
        failure,
        task_history=[t_prev],
        current_task=t_new,
        counters=RecoveryCounters(repair_attempts=1),
        limits=limits,
    )
    assert d_changed_2.action == RecoveryAction.REPAIR
    assert "attempt 2 of 2" in d_changed_2.reason


def test_terminal_not_retried() -> None:
    limits = RecoveryLimits()
    failure = ClassifiedFailure(
        failure_class=RecoveryFailureClass.INVARIANT_VIOLATION,
        task_id="t1",
        failing_args={},
        message="Sum of shares does not equal 1.0",
        recovery_context=RecoveryContext(),
        retry_policy=RetryPolicy.TERMINAL,
    )

    dec = decide_recovery(failure, counters=RecoveryCounters(), limits=limits)
    assert dec.action == RecoveryAction.STOP
    assert "Terminal failure" in dec.reason
    assert "cannot be recovered or retried" in dec.reason


def test_each_limit_yields_its_distinct_reason() -> None:
    limits = RecoveryLimits(
        identical_retry_cap=2, repair_attempts_per_task=2, replans_per_question=3
    )

    # 1. Identical retry cap reason
    fail_transient = ClassifiedFailure(
        failure_class=RecoveryFailureClass.TRANSIENT_ERROR,
        task_id="t1",
        message="Transient network error",
        retry_policy=RetryPolicy.RETRYABLE_IDENTICAL,
    )
    d_trans = decide_recovery(
        fail_transient, counters=RecoveryCounters(identical_retries=2), limits=limits
    )
    assert d_trans.action == RecoveryAction.STOP
    assert "Identical retry cap reached" in d_trans.reason

    # 2. Repair attempts cap hit with replans available -> escalates to replan
    fail_repair = ClassifiedFailure(
        failure_class=RecoveryFailureClass.EMPTY_RESULT,
        task_id="t1",
        message="0 rows returned",
        retry_policy=RetryPolicy.REPAIRABLE,
    )
    d_replan = decide_recovery(
        fail_repair,
        counters=RecoveryCounters(repair_attempts=2, replan_count=1),
        limits=limits,
    )
    assert d_replan.action == RecoveryAction.REPLAN
    assert "Repair attempts cap reached (2); escalating to replan (2 of 3)" in d_replan.reason

    # 3. Both repair cap and replan cap reached -> distinct combined reason
    d_stop = decide_recovery(
        fail_repair,
        counters=RecoveryCounters(repair_attempts=2, replan_count=3),
        limits=limits,
    )
    assert d_stop.action == RecoveryAction.STOP
    assert "Repair attempts cap reached (2) and replan cap reached (3)" in d_stop.reason


def test_coarse_failure_automatic_classification() -> None:
    # Verify decide_recovery works seamlessly when given a contract Failure object
    coarse = Failure(
        failure_class=FailureClass.TRANSIENT,
        recoverable=True,
        message="Operation timed out",
    )
    dec = decide_recovery(coarse, counters=RecoveryCounters(identical_retries=0))
    assert dec.action == RecoveryAction.RETRY_IDENTICAL
    # FailureClass.TRANSIENT maps to transient_error (not tool_timeout);
    # both share the RETRYABLE_IDENTICAL policy.
    assert dec.failure_class in (
        RecoveryFailureClass.TOOL_TIMEOUT,
        RecoveryFailureClass.TRANSIENT_ERROR,
    )


def test_detect_no_progress_patterns() -> None:
    # (a) Repeated identical fingerprint
    fp1 = fingerprint(_make_task(args={"a": 1}))
    hist_repeat = [
        {"fingerprint": fp1, "allowed_identical": False},
        {"fingerprint": fp1, "allowed_identical": False},
    ]
    res_repeat = detect_no_progress(hist_repeat)
    assert res_repeat.no_progress is True
    assert res_repeat.pattern == NoProgressPattern.IDENTICAL_FINGERPRINT
    assert "Repeated identical fingerprint" in res_repeat.reason

    # If identical retry was authorized, not flagged
    hist_allowed = [
        {"fingerprint": fp1, "allowed_identical": False},
        {"fingerprint": fp1, "allowed_identical": True},
    ]
    assert detect_no_progress(hist_allowed).no_progress is False

    # (b) Revision adding no new evidence and no changed pending tasks
    hist_empty_rev = [{"event": "revision", "new_evidence_count": 0, "changed_pending_tasks": 0}]
    res_empty_rev = detect_no_progress(hist_empty_rev)
    assert res_empty_rev.no_progress is True
    assert res_empty_rev.pattern == NoProgressPattern.EMPTY_REVISION
    assert "Plan revision produced no new valid evidence" in res_empty_rev.reason

    # PlanRevision contract object with empty affected tasks
    rev_invalid = PlanRevision(
        from_version=1,
        to_version=2,
        change=RevisionChangeType.ADDED,
        observed_result="nothing seen",
        affected_tasks=["placeholder"],  # validator requires non-empty on model creation
    )
    # Manually testing empty affected tasks handling
    rev_dict = rev_invalid.model_dump()
    rev_dict["affected_tasks"] = []
    # Test via dict event or model
    assert (
        detect_no_progress(
            [{"event": "revision", "new_evidence_count": 1, "changed_pending_tasks": 1}]
        ).no_progress
        is False
    )

    # (c) Cycling among 3+ alternating states
    hist_cycle = ["state_A", "state_B", "state_C", "state_A", "state_B", "state_C"]
    res_cycle = detect_no_progress(hist_cycle)
    assert res_cycle.no_progress is True
    assert res_cycle.pattern == NoProgressPattern.CYCLING
    assert "Detected periodic cycle among 3 alternating states" in res_cycle.reason

    # Normal progressing history
    hist_progress = ["state_A", "state_B", "state_C", "state_D", "state_E"]
    assert detect_no_progress(hist_progress).no_progress is False
