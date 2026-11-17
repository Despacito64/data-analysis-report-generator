"""Map pipeline AnalysisRun contracts into a validated Report."""

from __future__ import annotations

from da_agent.contracts.models import AnalysisRun, NumericClaim, Report, RunStatus
from da_agent.core.config import ClaimValidationConfig
from da_agent.reports.generator import build_report


def assemble_report(
    run: AnalysisRun,
    *,
    claim_config: ClaimValidationConfig | None = None,
) -> Report:
    """Build a report from typed run artifacts without importing agent code."""
    claims = [
        NumericClaim(value=item.value, label=item.label, evidence_id=item.evidence_id)
        for item in run.key_numbers
    ]
    status = RunStatus(
        status=run.execution_status,
        dropped_claims=list(run.dropped_claims),
    )
    limitations = (
        [f"Assumption: {item}" for item in run.assumptions] if run.assumptions else None
    )
    return build_report(
        run_id=run.run_id,
        dataset_hash=run.dataset_hash,
        question=run.question,
        claims=claims,
        evidence_records=run.evidence_records,
        status=status,
        limitations=limitations,
        claim_config=claim_config,
        answer_text=run.answer_text,
    )