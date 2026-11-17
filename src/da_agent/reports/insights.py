"""Turn valid evidence into findings. Unsupported numbers are dropped."""

from __future__ import annotations

from da_agent.contracts.models import EvidenceRecord, Finding, NumericClaim
from da_agent.core.config import ClaimValidationConfig
from da_agent.validation.claims import validate_findings


def findings_from_claims(
    claims: list[NumericClaim],
    evidence_records: dict[str, EvidenceRecord],
    *,
    caveat: str | None = None,
    config: ClaimValidationConfig | None = None,
) -> tuple[list[Finding], list[str]]:
    """Validate each claim against its evidence record and keep only supported findings."""
    drafts = [
        Finding(
            statement="Recorded tool value.",
            numeric_claims=[claim],
            evidence_ids=[claim.evidence_id],
            caveat=caveat,
        )
        for claim in claims
    ]
    result = validate_findings(drafts, evidence_records, config)
    dropped = [reason for rejected in result.rejected_findings for reason in rejected.reasons]
    return result.validated_findings, dropped
