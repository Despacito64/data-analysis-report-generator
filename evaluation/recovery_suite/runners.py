"""Execute controlled failure scenarios without benchmark questions or oracle data."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from da_agent.agent.answer import build_agent_result
from da_agent.agent.executor import (
    PlanExecutionResult,
    TaskExecutionRecord,
    TaskStatus,
    execute_plan,
)
from da_agent.agent.graph import run_agent
from da_agent.agent.planner import MockLLMClient
from da_agent.contracts.models import (
    EvidenceRecord,
    Failure,
    FailureClass,
    RecoveryFailureClass,
    RetryPolicy,
    Task,
)
from da_agent.core.config import RecoveryLimits
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.validation.failures import classify_failure
from da_agent.validation.recovery import (
    RecoveryAction,
    decide_recovery,
    detect_no_progress,
)

DATASET_PATH = Path("Sample-Superstore.csv")
_FILTER_PLAN = json.dumps(
    {
        "tasks": [
            {
                "id": "t1",
                "tool": "filter",
                "args": {
                    "conditions": [{"column": "Region", "operator": "eq", "value": "East"}]
                },
                "depends_on": [],
                "rationale": "Filter East region for recovery scenario",
            }
        ]
    }
)


def _transient_failure_result() -> PlanExecutionResult:
    return PlanExecutionResult(
        status="failed",
        records=[
            TaskExecutionRecord(
                task_id="t1",
                tool="filter",
                args={
                    "conditions": [{"column": "Region", "operator": "eq", "value": "East"}]
                },
                status=TaskStatus.FAILED,
                error="temporary connection reset",
            )
        ],
        failure=Failure(
            failure_class=FailureClass.TRANSIENT,
            recoverable=True,
            message="temporary connection reset",
            context={},
            task_id="t1",
        ),
    )


def run_classify_transient(_scenario: dict[str, Any]) -> dict[str, Any]:
    classified = classify_failure(
        Failure(
            failure_class=FailureClass.TRANSIENT,
            recoverable=True,
            message="connection reset by peer",
            context={},
        )
    )
    passed = (
        classified.failure_class == RecoveryFailureClass.TRANSIENT_ERROR
        and classified.retry_policy == RetryPolicy.RETRYABLE_IDENTICAL
    )
    return {"passed": passed, "retry_policy": classified.retry_policy.value}


def run_classify_empty_result(_scenario: dict[str, Any]) -> dict[str, Any]:
    classified = classify_failure(
        Failure(
            failure_class=FailureClass.EMPTY_RESULT,
            recoverable=True,
            message="filter matched 0 rows",
            context={},
        )
    )
    passed = (
        classified.failure_class == RecoveryFailureClass.EMPTY_RESULT
        and classified.retry_policy == RetryPolicy.REPAIRABLE
    )
    return {"passed": passed, "retry_policy": classified.retry_policy.value}


def run_classify_invariant_terminal(_scenario: dict[str, Any]) -> dict[str, Any]:
    classified = classify_failure(
        Failure(
            failure_class=FailureClass.INVARIANT_VIOLATION,
            recoverable=False,
            message="segment shares do not reconcile",
            context={"invariant": "share_sum"},
        )
    )
    passed = (
        classified.failure_class == RecoveryFailureClass.INVARIANT_VIOLATION
        and classified.retry_policy == RetryPolicy.TERMINAL
    )
    return {"passed": passed, "retry_policy": classified.retry_policy.value}


def run_decide_transient_retry(_scenario: dict[str, Any]) -> dict[str, Any]:
    failure = Failure(
        failure_class=FailureClass.TRANSIENT,
        recoverable=True,
        message="tool_timeout after 60s",
        context={"timeout_s": 60},
    )
    decision = decide_recovery(
        failure,
        [],
        {"identical_retries": 0, "repair_attempts": 0, "replan_count": 0},
        RecoveryLimits(identical_retry_cap=2),
    )
    passed = decision.action == RecoveryAction.RETRY_IDENTICAL
    return {"passed": passed, "action": decision.action.value}


def run_decide_transient_cap_stop(_scenario: dict[str, Any]) -> dict[str, Any]:
    failure = Failure(
        failure_class=FailureClass.TRANSIENT,
        recoverable=True,
        message="transient_error: temporary",
        context={},
    )
    decision = decide_recovery(
        failure,
        [],
        {"identical_retries": 2, "repair_attempts": 0, "replan_count": 0},
        RecoveryLimits(identical_retry_cap=2),
    )
    passed = decision.action == RecoveryAction.STOP
    return {"passed": passed, "action": decision.action.value}


def run_detect_identical_fingerprint(_scenario: dict[str, Any]) -> dict[str, Any]:
    same = {
        "tool": "filter",
        "args": {"conditions": [{"column": "Region", "operator": "eq", "value": "X"}]},
        "depends_on": [],
        "fingerprint": "fp-repeat",
    }
    result = detect_no_progress([same, dict(same)])
    passed = (
        result.no_progress
        and result.pattern is not None
        and result.pattern.value == "identical_fingerprint"
    )
    return {"passed": passed, "pattern": result.pattern.value if result.pattern else None}


def run_detect_cycle(_scenario: dict[str, Any]) -> dict[str, Any]:
    cycle = ["state-a", "state-b", "state-c"]
    history = [{"state": s} for s in cycle + cycle]
    result = detect_no_progress(history)
    passed = result.no_progress and result.pattern is not None and result.pattern.value == "cycling"
    return {"passed": passed, "pattern": result.pattern.value if result.pattern else None}


def run_agent_transient_retry_cap(_scenario: dict[str, Any]) -> dict[str, Any]:
    df = load_data(DATASET_PATH)
    profile = compute_profile(df, file_path=DATASET_PATH)
    client = MockLLMClient(default_response=_FILTER_PLAN)
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 2:
            return _transient_failure_result()
        return execute_plan(*args, **kwargs)

    import da_agent.agent.graph as graph_mod

    original = graph_mod.execute_plan
    graph_mod.execute_plan = flaky
    try:
        result = run_agent(
            question="List rows in the East region for recovery scenario rs08.",
            df=df,
            profile=profile,
            llm_client=client,
            max_replans=1,
        )
    finally:
        graph_mod.execute_plan = original

    passed = (
        result["status"] == _scenario.get("expected_status", "complete")
        and result.get("identical_retry_count")
        == _scenario.get("expected_identical_retry_count", 2)
        and calls["n"] == 3
    )
    return {
        "passed": passed,
        "status": result.get("status"),
        "identical_retry_count": result.get("identical_retry_count"),
    }


def run_agent_transient_cap_stop(_scenario: dict[str, Any]) -> dict[str, Any]:
    df = load_data(DATASET_PATH)
    profile = compute_profile(df, file_path=DATASET_PATH)
    client = MockLLMClient(default_response=_FILTER_PLAN)

    def always_transient(*_args, **_kwargs):
        return _transient_failure_result()

    import da_agent.agent.graph as graph_mod

    original = graph_mod.execute_plan
    graph_mod.execute_plan = always_transient
    try:
        result = run_agent(
            question="East region filter with only transient failures in rs08b.",
            df=df,
            profile=profile,
            llm_client=client,
            max_replans=1,
        )
    finally:
        graph_mod.execute_plan = original

    passed = (
        result["status"] == _scenario.get("expected_status", "partial")
        and result.get("recovery_action") == _scenario.get("expected_recovery_action", "stop")
        and result.get("identical_retry_count") == 2
    )
    return {
        "passed": passed,
        "status": result.get("status"),
        "recovery_action": result.get("recovery_action"),
    }


def run_agent_no_progress_fingerprint(_scenario: dict[str, Any]) -> dict[str, Any]:
    df = load_data(DATASET_PATH)
    profile = compute_profile(df, file_path=DATASET_PATH)
    same_args = {
        "conditions": [{"column": "Region", "operator": "eq", "value": "RECOVERY_SUITE_ONLY"}]
    }
    plan_a = json.dumps(
        {
            "tasks": [
                {
                    "id": "t1",
                    "tool": "filter",
                    "args": same_args,
                    "depends_on": [],
                    "rationale": "First filter attempt",
                }
            ]
        }
    )
    plan_b = json.dumps(
        {
            "tasks": [
                {
                    "id": "t9",
                    "tool": "filter",
                    "args": same_args,
                    "depends_on": [],
                    "rationale": "Renamed filter with identical arguments",
                }
            ]
        }
    )
    client = MockLLMClient(responses=[plan_a, plan_b, plan_b])
    result = run_agent(
        question="Filter a region that does not exist in the recovery scenario rs09.",
        df=df,
        profile=profile,
        llm_client=client,
        max_replans=2,
    )
    passed = result["status"] == "partial" and any(
        f.failure_class == FailureClass.NO_PROGRESS for f in result.get("failures", [])
    )
    return {"passed": passed, "status": result.get("status")}


def run_claim_tamper_dropped(_scenario: dict[str, Any]) -> dict[str, Any]:
    record = TaskExecutionRecord(
        task_id="task_sales",
        tool="group_aggregate",
        args={"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
        status=TaskStatus.OK,
        output_summary={"sample_groups": [{"value": 125.5}]},
        evidence_id="ev_recovery_claim",
    )
    result = build_agent_result(
        run_id="rs10",
        question="Recovery scenario numeric tamper check.",
        resolved=None,
        task_results=[record],
        evidence_store={"ev_recovery_claim": {"sample_groups": [{"value": 125.5}]}},
        run_status="complete",
        narrative="The total is 999.",
    )
    needle = _scenario.get("expected_dropped_contains", "999")
    passed = needle in result.dropped_claims and needle not in result.answer_text
    return {"passed": passed, "dropped_claims": result.dropped_claims}


def run_invalidation_cascade(_scenario: dict[str, Any]) -> dict[str, Any]:
    parent = EvidenceRecord(
        evidence_id="ev_parent",
        task_id="t1",
        tool="group_aggregate",
        args_hash="abc12345",
        dataset_hash="dataset",
        input_row_count=3,
        result_summary={"value": 10},
        result_schema_version="0.1.0",
    )
    child = EvidenceRecord(
        evidence_id="ev_child",
        task_id="t2",
        tool="group_aggregate",
        args_hash="def67890",
        dataset_hash="dataset",
        input_row_count=3,
        result_summary={"value": 3},
        result_schema_version="0.1.0",
    )
    independent = EvidenceRecord(
        evidence_id="ev_independent",
        task_id="t3",
        tool="group_aggregate",
        args_hash="ghi11111",
        dataset_hash="dataset",
        input_row_count=3,
        result_summary={"value": 7},
        result_schema_version="0.1.0",
    )
    tasks = [
        Task(id="t1", tool="group_aggregate", args={}, depends_on=[], rationale="parent"),
        Task(id="t2", tool="group_aggregate", args={}, depends_on=["t1"], rationale="child"),
        Task(id="t3", tool="group_aggregate", args={}, depends_on=[], rationale="independent"),
    ]
    records = [
        TaskExecutionRecord(
            task_id=task_id,
            tool="group_aggregate",
            args={},
            status=TaskStatus.OK,
            output_summary={"value": value},
            evidence_id=evidence_id,
        )
        for evidence_id, task_id, value in (
            ("ev_parent", "t1", 10),
            ("ev_child", "t2", 3),
            ("ev_independent", "t3", 7),
        )
    ]
    result = build_agent_result(
        run_id="rs11",
        question="Recovery scenario invalidation cascade.",
        resolved=None,
        task_results=records,
        evidence_store={
            "ev_parent": {"value": 10},
            "ev_child": {"value": 3},
            "ev_independent": {"value": 7},
        },
        run_status="partial",
        failures=[
            Failure(
                failure_class=FailureClass.INVARIANT_VIOLATION,
                recoverable=False,
                message="Parent evidence failed an invariant.",
                context={"evidence_id": "ev_parent"},
                task_id="t1",
            )
        ],
        evidence_records={
            "ev_parent": parent,
            "ev_child": child,
            "ev_independent": independent,
        },
        tasks=tasks,
    )
    kept = {item.evidence_id for item in result.key_numbers}
    expected = set(_scenario.get("expected_kept_evidence", ["ev_independent"]))
    passed = kept == expected and parent.valid is False and child.invalidated_by == "ev_parent"
    return {"passed": passed, "kept_evidence": sorted(kept)}


HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "classify_transient": run_classify_transient,
    "classify_empty_result": run_classify_empty_result,
    "classify_invariant_terminal": run_classify_invariant_terminal,
    "decide_transient_retry": run_decide_transient_retry,
    "decide_transient_cap_stop": run_decide_transient_cap_stop,
    "detect_identical_fingerprint": run_detect_identical_fingerprint,
    "detect_cycle": run_detect_cycle,
    "agent_transient_retry_cap": run_agent_transient_retry_cap,
    "agent_transient_cap_stop": run_agent_transient_cap_stop,
    "agent_no_progress_fingerprint": run_agent_no_progress_fingerprint,
    "claim_tamper_dropped": run_claim_tamper_dropped,
    "invalidation_cascade": run_invalidation_cascade,
}


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return list(payload["scenarios"])


def run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    handler_name = scenario["handler"]
    handler = HANDLERS.get(handler_name)
    if handler is None:
        return {
            "id": scenario["id"],
            "handler": handler_name,
            "passed": False,
            "error": f"Unknown handler: {handler_name}",
        }
    outcome = handler(scenario)
    return {
        "id": scenario["id"],
        "handler": handler_name,
        "failure_family": scenario.get("failure_family"),
        **outcome,
    }


def run_all_scenarios(scenarios_path: Path) -> dict[str, Any]:
    scenarios = load_scenarios(scenarios_path)
    results = [run_scenario(item) for item in scenarios]
    passed_count = sum(1 for item in results if item.get("passed"))
    return {
        "version": "0.1.0",
        "scenario_count": len(results),
        "passed_count": passed_count,
        "all_passed": passed_count == len(results),
        "results": results,
    }