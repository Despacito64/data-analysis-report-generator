"""Structured answer synthesis with evidence-grounded numeric claims."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from da_agent.agent.executor import TaskExecutionRecord, TaskStatus
from da_agent.agent.planner import Plan
from da_agent.contracts.models import (
    Failure,
    PlanRevision,
    ResolvedQuestion,
)
from da_agent.core.trace import RunTraceWriter
from da_agent.validation.claims import extract_evidence_numbers, normalize_claim_number


class AgentAnswerStatus(StrEnum):
    """User-facing outcome for an agent run."""

    ANSWERED = "answered"
    DECLINED = "declined"
    FAILED = "failed"


class AnswerEvidence(BaseModel):
    """Tool output attached to an answer with its task and evidence references."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    tool: str
    evidence_id: str
    tool_output: dict[str, Any]


class KeyNumber(BaseModel):
    """Numeric tool output cited in answer text."""

    model_config = ConfigDict(extra="forbid")

    label: str
    value: int | float
    task_id: str
    evidence_id: str


class AgentResult(BaseModel):
    """Structured final answer, its assumptions, and auditable evidence."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    question: str
    status: AgentAnswerStatus
    answer_text: str
    key_numbers: list[KeyNumber] = Field(default_factory=list)
    evidence: list[AnswerEvidence] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    failures: list[Failure] = Field(default_factory=list)
    revisions: list[PlanRevision] = Field(default_factory=list)
    plan: Plan | None = None
    task_results: list[TaskExecutionRecord] = Field(default_factory=list)
    final_answer: dict[str, Any] = Field(default_factory=dict)


_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?(?![\w]|\.\d)"
)
_NON_CLAIM_KEYS = {"matched_indices", "sample_matched_indices"}


def _numeric_values(value: Any, path: str = "") -> list[tuple[str, int | float]]:
    """Extract evidence numbers while excluding row indexes, booleans, and non-finite floats."""
    return [(num.path, num.value) for num in extract_evidence_numbers(value, path)]


def _normalize_number(text: str) -> float | None:
    return normalize_claim_number(text)


def validate_narrative_grounding(narrative: str, tool_outputs: list[dict[str, Any]]) -> bool:
    """Return whether every numeric token in narrative occurs in recorded tool outputs."""
    grounded = {
        number
        for output in tool_outputs
        for _, value in _numeric_values(output)
        if (number := _normalize_number(str(value))) is not None
    }
    for token in _NUMBER_PATTERN.findall(narrative):
        number = _normalize_number(token)
        if number is not None and number not in grounded:
            return False
    return True


def _format_number(value: float) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value)


def _template_answer(
    status: AgentAnswerStatus,
    resolved: ResolvedQuestion | None,
    key_numbers: list[KeyNumber],
    evidence: list[AnswerEvidence],
) -> str:
    if status == AgentAnswerStatus.DECLINED:
        reason = resolved.decline_reason if resolved else "The question could not be answered."
        return f"Declined: {reason}"
    if status == AgentAnswerStatus.FAILED:
        return "The analysis could not be completed. See the recorded failures and evidence."
    if key_numbers:
        details = "; ".join(
            f"{item.label}: {_format_number(item.value)} (evidence {item.evidence_id})"
            for item in key_numbers
        )
        return f"Tool results: {details}."
    references = ", ".join(item.evidence_id for item in evidence)
    return f"The analysis completed. Tool evidence: {references}."


def build_agent_result(
    *,
    run_id: str,
    question: str,
    resolved: ResolvedQuestion | None,
    task_results: list[TaskExecutionRecord],
    evidence_store: dict[str, Any],
    run_status: str,
    failures: list[Failure] | None = None,
    revisions: list[PlanRevision] | None = None,
    plan: Plan | None = None,
    trace_writer: RunTraceWriter | None = None,
    narrative: str | None = None,
) -> AgentResult:
    """Build a typed answer and reject narrative numeric claims lacking tool evidence."""
    failures = list(failures or [])
    revisions = list(revisions or [])
    evidence: list[AnswerEvidence] = []
    key_numbers: list[KeyNumber] = []
    for record in task_results:
        if record.status != TaskStatus.OK or not record.evidence_id:
            continue
        tool_output = evidence_store.get(record.evidence_id, record.output_summary or {})
        evidence.append(
            AnswerEvidence(
                task_id=record.task_id,
                tool=record.tool,
                evidence_id=record.evidence_id,
                tool_output=tool_output,
            )
        )
        key_numbers.extend(
            KeyNumber(
                label=f"{record.tool}.{label}",
                value=value,
                task_id=record.task_id,
                evidence_id=record.evidence_id,
            )
            for label, value in _numeric_values(record.output_summary or {})
        )

    assumptions = list(
        dict.fromkeys(
            decision.assumption or decision.decision
            for decision in (resolved.ambiguity_decisions if resolved else [])
            if decision.assumption or decision.decision
        )
    )
    if resolved is not None and not resolved.answerable:
        status = AgentAnswerStatus.DECLINED
    elif run_status == "complete" and evidence:
        status = AgentAnswerStatus.ANSWERED
    else:
        status = AgentAnswerStatus.FAILED

    fallback = _template_answer(status, resolved, key_numbers, evidence)
    selected_narrative = narrative if narrative is not None else fallback
    if not validate_narrative_grounding(
        selected_narrative, [item.tool_output for item in evidence]
    ):
        if trace_writer:
            trace_writer.log_event(
                "answer_narrative_fallback",
                {"reason": "unsupported_numeric_claim", "run_id": run_id},
            )
        selected_narrative = fallback

    result = AgentResult(
        run_id=run_id,
        question=question,
        status=status,
        answer_text=selected_narrative,
        key_numbers=key_numbers,
        evidence=evidence,
        assumptions=assumptions,
        failures=failures,
        revisions=revisions,
        plan=plan,
        task_results=task_results,
        final_answer={
            record.task_id: {
                "tool": record.tool,
                "summary": record.output_summary,
                "evidence_id": record.evidence_id,
            }
            for record in task_results
            if record.status == TaskStatus.OK and record.output_summary
        },
    )
    if trace_writer:
        trace_writer.log_event(
            "final_answer",
            {
                "run_id": result.run_id,
                "status": result.status.value,
                "answer_text": result.answer_text,
                "key_numbers": [item.model_dump(mode="json") for item in result.key_numbers],
                "evidence_ids": [item.evidence_id for item in result.evidence],
                "assumptions": result.assumptions,
                "failure_count": len(result.failures),
            },
        )
    return result
