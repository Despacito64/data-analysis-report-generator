"""Unit tests verifying RunTraceWriter recording and replay capability."""

from datetime import UTC, datetime
from pathlib import Path

from da_agent.contracts import (
    EvidenceRecord,
    ExecutionStatus,
    Failure,
    FailureClass,
    Finding,
    NumericClaim,
    PlanRevision,
    Report,
    RevisionChangeType,
    RunStatus,
    Task,
)
from da_agent.core import AppConfig, RunTraceWriter, load_config


def test_load_config() -> None:
    config = load_config("config.yaml")
    assert isinstance(config, AppConfig)
    assert config.budgets.max_llm_calls > 0
    assert config.sampling.seed == 42


def test_trace_writer_roundtrip(tmp_path: Path) -> None:
    run_id = "test-run-001"
    writer = RunTraceWriter(run_id=run_id, base_dir=tmp_path)

    # 1. Log initial plan
    t1 = Task(id="t-1", tool="group_aggregate", args={"group_by": "Region"}, rationale="First step")
    writer.log_plan(plan_version=1, tasks=[t1])

    # 2. Log tool call
    writer.log_tool_call(task_id="t-1", tool="group_aggregate", args={"group_by": "Region"})

    # 3. Log evidence
    ev = EvidenceRecord(
        evidence_id="ev-1",
        task_id="t-1",
        tool="group_aggregate",
        args_hash="hash_args",
        dataset_hash="hash_data",
        input_row_count=1000,
        result_summary={"Region": ["East", "West"], "Sales": [100.0, 200.0]},
        result_schema_version="1.0.0",
        invariants_checked=["rows_positive"],
        created_at=datetime.now(UTC),
    )
    writer.log_evidence(ev)

    # 4. Log plan revision
    rev = PlanRevision(
        from_version=1,
        to_version=2,
        trigger_evidence_id="ev-1",
        change=RevisionChangeType.ADDED,
        observed_result="West has high sales",
        affected_tasks=["t-2"],
    )
    writer.log_plan_revision(rev)

    # 5. Log failure
    fail = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=True,
        message="Bad arg",
        context={"allowed": ["Sales"]},
    )
    writer.log_failure(fail)

    # 6. Log status
    status = RunStatus(status=ExecutionStatus.COMPLETE)
    writer.log_status(status)

    # 7. Read back and verify all events
    events = writer.read_events()
    assert len(events) == 6
    event_types = [e.event_type for e in events]
    assert event_types == ["plan", "tool_call", "evidence", "plan_revision", "failure", "status"]

    for e in events:
        assert e.run_id == run_id
        assert e.timestamp is not None

    # Check evidence payload matches
    ev_event = events[2]
    assert ev_event.payload["evidence_id"] == "ev-1"
    assert ev_event.payload["input_row_count"] == 1000

    # Save and verify report
    report = Report(
        run_id=run_id,
        dataset_hash="hash_data",
        question="What is total sales?",
        summary="Completed successfully",
        findings=[
            Finding(
                statement="Total sales is 300",
                numeric_claims=[NumericClaim(value=300, label="Sales", evidence_id="ev-1")],
                evidence_ids=["ev-1"],
            )
        ],
        evidence_appendix=[ev],
        status=status,
    )
    saved_path = writer.save_report(report)
    assert saved_path.is_file()
