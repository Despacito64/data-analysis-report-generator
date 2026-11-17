"""Assemble a Report from validated findings."""

from __future__ import annotations

from da_agent.contracts.models import (
    EvidenceRecord,
    ExecutionStatus,
    NumericClaim,
    Report,
    RunStatus,
)
from da_agent.core.config import ClaimValidationConfig
from da_agent.reports.insights import findings_from_claims


def build_report(
    *,
    run_id: str,
    dataset_hash: str,
    question: str,
    claims: list[NumericClaim],
    evidence_records: dict[str, EvidenceRecord],
    status: RunStatus,
    caveat: str | None = None,
    methods: list[str] | None = None,
    limitations: list[str] | None = None,
    claim_config: ClaimValidationConfig | None = None,
) -> Report:
    """Build a report and re-check claims immediately before the object is returned."""
    findings, dropped = findings_from_claims(
        claims,
        evidence_records,
        caveat=caveat,
        config=claim_config,
    )
    findings, dropped_again = findings_from_claims(
        [claim for finding in findings for claim in finding.numeric_claims],
        evidence_records,
        caveat=caveat,
        config=claim_config,
    )
    dropped_claims = list(status.dropped_claims) + dropped + dropped_again
    appendix = [
        record
        for record in evidence_records.values()
        if record.valid and record.invalidated_by is None
    ]
    summary = (
        f"{len(findings)} supported finding(s)." if findings else "No supported numeric findings."
    )
    return Report(
        run_id=run_id,
        dataset_hash=dataset_hash,
        question=question,
        summary=summary,
        findings=findings,
        methods=methods or ["Numbers come from registered analytical tools."],
        limitations=limitations
        or ["A number is shown only when it matches a valid evidence record."],
        recommendations=[],
        evidence_appendix=appendix,
        status=RunStatus(
            status=status.status
            if findings or status.status != ExecutionStatus.COMPLETE
            else ExecutionStatus.PARTIAL,
            reason_code=status.reason_code,
            reason_text=status.reason_text,
            dropped_claims=dropped_claims,
            unvalidated_claims=list(status.unvalidated_claims),
        ),
    )
