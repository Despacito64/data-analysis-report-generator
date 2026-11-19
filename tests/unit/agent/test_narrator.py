"""Grounded LLM answer narrative (second call)."""

from da_agent.agent.answer import AgentAnswerStatus, AgentResult, build_agent_result
from da_agent.agent.executor import TaskExecutionRecord, TaskStatus
from da_agent.agent.narrator import apply_llm_answer_narrative
from da_agent.contracts.models import ResolvedQuestion


class _StubClient:
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> tuple[str, dict]:
        _ = messages
        return (
            "Furniture total sales are 125.50 for the filtered slice.",
            {"message": {"content": "ok"}},
        )


class _BadClient:
    def chat(self, messages: list[dict[str, str]], **kwargs: object) -> tuple[str, dict]:
        _ = messages
        return ("The total is 999.00.", {})


def _answered_result() -> AgentResult:
    record = TaskExecutionRecord(
        task_id="t1",
        tool="group_aggregate",
        args={},
        status=TaskStatus.OK,
        output_summary={
            "sample_groups": [{"group_keys": {"Category": "Furniture"}, "value": 125.5}]
        },
        evidence_id="ev1",
    )
    return build_agent_result(
        run_id="narr-test",
        question="tell me more about furniture",
        resolved=ResolvedQuestion(question_text="q", intent="chat", answerable=True),
        task_results=[record],
        evidence_store={"ev1": record.output_summary or {}},
        run_status="complete",
    )


def test_llm_narrative_replaces_template_when_grounded() -> None:
    base = _answered_result()
    assert base.answer_text.startswith("Tool results:")
    updated = apply_llm_answer_narrative(
        base,
        client=_StubClient(),
        headline="Furniture: 125.50.",
        allowed_claim_lines=["Furniture — Sales (sum): 125.50"],
    )
    assert "125.5" in updated.answer_text or "125.50" in updated.answer_text
    assert not updated.answer_text.startswith("Tool results:")


def test_ungrounded_llm_narrative_keeps_template() -> None:
    base = _answered_result()
    updated = apply_llm_answer_narrative(
        base,
        client=_BadClient(),
        headline="Furniture: 125.50.",
        allowed_claim_lines=["Furniture — Sales (sum): 125.50"],
    )
    assert updated.answer_text == base.answer_text
    assert updated.status == AgentAnswerStatus.ANSWERED
