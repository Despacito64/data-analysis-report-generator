"""Assemble a Report from validated findings."""

from __future__ import annotations

from da_agent.contracts.models import (
    EvidenceRecord,
    ExecutionStatus,
    Finding,
    NumericClaim,
    Report,
    RunStatus,
)
from da_agent.core.config import ClaimValidationConfig
from da_agent.reports.insights import findings_from_claims
from da_agent.reports.presenters import (
    executive_summary_from_findings,
    present_findings_from_evidence,
)
from da_agent.validation.claims import validate_findings


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
    answer_text: str = "",
) -> Report:
    """Build a report and re-check claims immediately before the object is returned."""
    presented, highlights, used_evidence = present_findings_from_evidence(evidence_records)
    dropped_claims = list(status.dropped_claims)

    if presented:
        validation = validate_findings(presented, evidence_records, claim_config)
        findings = validation.validated_findings
        dropped_claims.extend(
            reason for rejected in validation.rejected_findings for reason in rejected.reasons
        )
        fallback_claims = [claim for claim in claims if claim.evidence_id not in used_evidence]
    else:
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
        dropped_claims.extend(dropped + dropped_again)
        fallback_claims = []

    if fallback_claims:
        extra_findings, extra_dropped = findings_from_claims(
            fallback_claims,
            evidence_records,
            caveat=caveat,
            config=claim_config,
        )
        findings = _merge_findings(findings, extra_findings)
        dropped_claims.extend(extra_dropped)

    appendix = [
        record
        for record in evidence_records.values()
        if record.valid and record.invalidated_by is None
    ]
    summary = (
        executive_summary_from_findings(findings) if findings else _technical_summary(findings)
    )
    if not highlights and findings:
        highlights = [
            f"{claim.label.split(' — ')[0]}: {float(claim.value):,.2f}"
            for finding in findings
            for claim in finding.numeric_claims
            if isinstance(claim.value, (int, float))
        ]
    _ = answer_text  # reserved for a future grounded-narrative slot (pipeline validates first)

    return Report(
        run_id=run_id,
        dataset_hash=dataset_hash,
        question=question,
        summary=summary,
        highlights=highlights if presented else [],
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


def _technical_summary(findings: list[Finding]) -> str:
    if findings:
        return f"{len(findings)} supported finding(s)."
    return "No supported numeric findings."


def _merge_findings(primary: list[Finding], extra: list[Finding]) -> list[Finding]:
    seen = {tuple(c.evidence_id for c in f.numeric_claims) for f in primary}
    merged = list(primary)
    for finding in extra:
        key = tuple(c.evidence_id for c in finding.numeric_claims)
        if key not in seen:
            merged.append(finding)
            seen.add(key)
    return merged
