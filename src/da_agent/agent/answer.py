"""Structured answer synthesis with evidence-grounded numeric claims."""

from __future__ import annotations

import math
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from da_agent.agent.executor import TaskExecutionRecord, TaskStatus
from da_agent.agent.planner import Plan
from da_agent.contracts.models import (
    EvidenceRecord,
    Failure,
    FailureClass,
    Finding,
    NumericClaim,
    PlanRevision,
    ResolvedQuestion,
    Task,
)
from da_agent.core.config import ClaimValidationConfig
from da_agent.core.trace import RunTraceWriter
from da_agent.validation.claims import (
    extract_evidence_numbers,
    normalize_claim_number,
    validate_findings,
)
from da_agent.validation.invalidation import invalidate_evidence


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
    dropped_claims: list[str] = Field(default_factory=list)


_NUMBER_PATTERN = re.compile(
    r"(?<![\w.])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?(?![\w]|\.\d)"
)
_NON_CLAIM_KEYS = {
    "matched_indices",
    "sample_matched_indices",
    "output_row_count",
    "input_row_count",
    "valid_count",
    "missing_count",
    "total_groups",
}


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


def _claim_store(
    evidence_store: dict[str, Any],
    evidence_records: dict[str, EvidenceRecord] | None,
) -> dict[str, Any]:
    """Prefer typed evidence records so validity flags are visible to the claim check."""
    store = dict(evidence_store)
    for evidence_id, record in (evidence_records or {}).items():
        summary = dict(record.result_summary)
        summary["valid"] = record.valid
        summary["invalidated_by"] = record.invalidated_by
        store[evidence_id] = summary
    return store


def _invalidate_named_evidence(
    failures: list[Failure],
    evidence_records: dict[str, EvidenceRecord] | None,
    tasks: list[Task] | None,
) -> None:
    """Cascade invalidation when a failure names an evidence record."""
    if not evidence_records:
        return
    roots: list[str] = []
    for failure in failures:
        named = failure.context.get("evidence_id")
        if isinstance(named, str) and named in evidence_records:
            roots.append(named)
        elif failure.failure_class == FailureClass.INVARIANT_VIOLATION and failure.task_id:
            roots.extend(
                record.evidence_id
                for record in evidence_records.values()
                if record.task_id == failure.task_id and record.evidence_id not in roots
            )
    for root in dict.fromkeys(roots):
        invalidate_evidence(
            root,
            tasks=tasks or [],
            evidence_store=evidence_records,
            findings=[],
            reason=f"Invalidated after {root}",
        )


def _findings_for_numbers(key_numbers: list[KeyNumber]) -> list[Finding]:
    return [
        Finding(
            statement="Recorded tool value.",
            numeric_claims=[
                NumericClaim(
                    value=item.value,
                    label=item.label,
                    evidence_id=item.evidence_id,
                )
            ],
            evidence_ids=[item.evidence_id],
        )
        for item in key_numbers
    ]


def _same_claim(left: KeyNumber, evidence_id: str, value: float) -> bool:
    return left.evidence_id == evidence_id and math.isclose(
        float(left.value),
        float(value),
        rel_tol=0.001,
        abs_tol=0.01,
    )


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
    evidence_records: dict[str, EvidenceRecord] | None = None,
    tasks: list[Task] | None = None,
    claim_config: ClaimValidationConfig | None = None,
) -> AgentResult:
    """Build a typed answer and reject narrative numeric claims lacking tool evidence."""
    failures = list(failures or [])
    revisions = list(revisions or [])
    _invalidate_named_evidence(failures, evidence_records, tasks)
    validation_store = _claim_store(evidence_store, evidence_records)
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

    proposed_numbers = list(key_numbers)
    claim_result = validate_findings(
        _findings_for_numbers(proposed_numbers),
        validation_store,
        claim_config,
        trace_writer,
    )
    dropped_claims = [
        reason for rejected in claim_result.rejected_findings for reason in rejected.reasons
    ]
    key_numbers = [
        item
        for item in proposed_numbers
        if any(
            _same_claim(item, claim.evidence_id or "", float(claim.value))
            for finding in claim_result.validated_findings
            for claim in finding.numeric_claims
            if isinstance(claim.value, (int, float))
        )
    ]
    invalid_ids = {
        evidence_id
        for evidence_id, record in (evidence_records or {}).items()
        if not record.valid or record.invalidated_by
    }
    kept_ids = {item.evidence_id for item in key_numbers}
    proposed_ids = {item.evidence_id for item in proposed_numbers}
    evidence = [
        item
        for item in evidence
        if item.evidence_id not in invalid_ids
        and (item.evidence_id in kept_ids or item.evidence_id not in proposed_ids)
    ]

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
    grounded_outputs = [item.tool_output for item in evidence]
    if not validate_narrative_grounding(selected_narrative, grounded_outputs):
        grounded = {
            number
            for output in grounded_outputs
            for _, value in _numeric_values(output)
            if (number := _normalize_number(str(value))) is not None
        }
        for token in _NUMBER_PATTERN.findall(selected_narrative):
            number = _normalize_number(token)
            if number is not None and number not in grounded and token not in dropped_claims:
                dropped_claims.append(token)
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
            if record.status == TaskStatus.OK
            and record.output_summary
            and record.evidence_id not in invalid_ids
            and (record.evidence_id in kept_ids or record.evidence_id not in proposed_ids)
        },
        dropped_claims=dropped_claims,
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
