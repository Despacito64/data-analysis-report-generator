"""Tests for evidence-grounded answer synthesis."""

import tempfile

from da_agent.agent.answer import (
    AgentAnswerStatus,
    build_agent_result,
    validate_narrative_grounding,
)
from da_agent.agent.executor import TaskExecutionRecord, TaskStatus
from da_agent.contracts.models import (
    AmbiguityDecision,
    EvidenceRecord,
    Failure,
    FailureClass,
    ResolvedQuestion,
    Task,
)
from da_agent.core.trace import RunTraceWriter


def _resolved(*, answerable: bool = True) -> ResolvedQuestion:
    return ResolvedQuestion(
        question_text="What is the total sales?",
        intent="diagnostic",
        answerable=answerable,
        decline_reason=None if answerable else "The requested method is out of scope.",
        ambiguity_decisions=[
            AmbiguityDecision(
                field="aggregation",
                issue="The aggregation was unspecified.",
                decision="Used the sum aggregation.",
                assumption="Total means sum.",
            )
        ],
    )


def _record() -> TaskExecutionRecord:
    return TaskExecutionRecord(
        task_id="task_sales",
        tool="group_aggregate",
        args={"by": ["Category"], "metric_column": "Sales", "aggregation": "sum"},
        status=TaskStatus.OK,
        output_summary={"total_groups": 1, "sample_groups": [{"value": 125.5}]},
        evidence_id="ev_task_sales_abc",
    )


def test_grounding_check_accepts_numbers_found_in_evidence() -> None:
    assert validate_narrative_grounding(
        "Sales value was 125.5 across 1 group.",
        [{"total_groups": 1, "sample_groups": [{"value": 125.5}]}],
    )


def test_grounding_check_rejects_unsupported_number() -> None:
    assert not validate_narrative_grounding(
        "Sales value was 125.5, which is 200% of the prior result.",
        [{"value": 125.5}],
    )


def test_templated_answer_preserves_tool_precision() -> None:
    value = 125.123456789
    record = _record().model_copy(update={"output_summary": {"value": value}})
    output = {"value": value}
    result = build_agent_result(
        run_id="answer_precision",
        question="What is the total sales?",
        resolved=_resolved(),
        task_results=[record],
        evidence_store={"ev_task_sales_abc": output},
        run_status="complete",
    )

    assert str(value) in result.answer_text
    assert validate_narrative_grounding(result.answer_text, [output])


def test_unsupported_narrative_falls_back_and_logs_trace() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        writer = RunTraceWriter(run_id="answer_fallback", base_dir=temp_dir)
        result = build_agent_result(
            run_id="answer_fallback",
            question="What is the total sales?",
            resolved=_resolved(),
            task_results=[_record()],
            evidence_store={"ev_task_sales_abc": {"rows": [{"value": 125.5}]}},
            run_status="complete",
            trace_writer=writer,
            narrative="The value is 999.",
        )
        event_types = [event.event_type for event in writer.read_events()]

    assert "999" not in result.answer_text
    assert [item.value for item in result.key_numbers] == [125.5]
    assert result.evidence[0].task_id == "task_sales"
    assert result.evidence[0].tool_output == {"rows": [{"value": 125.5}]}
    assert "answer_narrative_fallback" in event_types


def test_declined_result_is_well_formed_and_includes_assumptions() -> None:
    result = build_agent_result(
        run_id="declined",
        question="Forecast sales",
        resolved=_resolved(answerable=False),
        task_results=[],
        evidence_store={},
        run_status="failed",
    )

    assert result.status == AgentAnswerStatus.DECLINED
    assert "out of scope" in result.answer_text
    assert result.evidence == []
    assert result.key_numbers == []
    assert result.assumptions == ["Total means sum."]


def test_failed_result_is_well_formed_without_evidence() -> None:
    failure = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=False,
        message="No valid plan was produced.",
    )
    result = build_agent_result(
        run_id="failed",
        question="What is total sales?",
        resolved=_resolved(),
        task_results=[],
        evidence_store={},
        run_status="failed",
        failures=[failure],
    )

    assert result.status == AgentAnswerStatus.FAILED
    assert "could not be completed" in result.answer_text
    assert result.failures == [failure]


def _typed_evidence(evidence_id: str, task_id: str, value: float) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        task_id=task_id,
        tool="group_aggregate",
        args_hash="abc12345",
        dataset_hash="dataset",
        input_row_count=3,
        result_summary={"value": value},
        result_schema_version="0.1.0",
    )


def test_tampered_narrative_is_listed_as_a_dropped_claim() -> None:
    result = build_agent_result(
        run_id="tamper",
        question="What is the total sales?",
        resolved=_resolved(),
        task_results=[_record()],
        evidence_store={"ev_task_sales_abc": {"value": 125.5}},
        run_status="complete",
        narrative="The total is 999.",
    )

    assert "999" not in result.answer_text
    assert "999" in result.dropped_claims
    assert result.key_numbers
    assert all(item.value != 999 for item in result.key_numbers)


def test_invalidated_evidence_drops_dependents_and_keeps_an_independent_branch() -> None:
    parent = _typed_evidence("ev_parent", "t1", 10)
    child = _typed_evidence("ev_child", "t2", 3)
    independent = _typed_evidence("ev_independent", "t3", 7)
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
        run_id="invalidate",
        question="What are the totals?",
        resolved=_resolved(),
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
                message="Parent evidence failed its invariant.",
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

    cited = {item.evidence_id for item in result.key_numbers}
    assert cited == {"ev_independent"}
    assert "10" not in result.answer_text
    assert "3" not in result.answer_text
    assert result.dropped_claims
    assert parent.valid is False
    assert child.valid is False
    assert child.invalidated_by == "ev_parent"
    assert independent.valid is True


def test_supported_claim_stays_when_evidence_is_valid() -> None:
    record = _typed_evidence("ev_ok", "t1", 42)
    result = build_agent_result(
        run_id="supported",
        question="What is the total sales?",
        resolved=_resolved(),
        task_results=[
            TaskExecutionRecord(
                task_id="t1",
                tool="group_aggregate",
                args={},
                status=TaskStatus.OK,
                output_summary={"value": 42},
                evidence_id="ev_ok",
            )
        ],
        evidence_store={"ev_ok": {"value": 42}},
        run_status="complete",
        evidence_records={"ev_ok": record},
        narrative="The value is 42.",
    )

    assert result.dropped_claims == []
    assert result.key_numbers[0].value == 42
    assert "42" in result.answer_text
    assert record.valid is True
