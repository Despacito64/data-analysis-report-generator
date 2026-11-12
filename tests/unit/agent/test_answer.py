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
    Failure,
    FailureClass,
    ResolvedQuestion,
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
    assert result.key_numbers[0].value == 1
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
