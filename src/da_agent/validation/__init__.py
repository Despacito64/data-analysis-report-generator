"""Validation modules for arguments, results, plans, and claims.

Architectural Layer 4: strictly imports contracts and core; NEVER imports da_agent.tools.
"""

from da_agent.validation.args import validate_task_args
from da_agent.validation.claims import (
    ClaimStatus,
    ClaimValidationResult,
    EvidenceNumber,
    ExtractedNumericClaim,
    RejectedFinding,
    TextSpan,
    ValidatedClaimRecord,
    extract_evidence_numbers,
    extract_numeric_claims,
    match_claim_to_evidence,
    normalize_claim_number,
    validate_findings,
    validate_single_claim,
)
from da_agent.validation.plan_check import validate_plan
from da_agent.validation.results import validate_tool_result

__all__ = [
    "ClaimStatus",
    "ClaimValidationResult",
    "EvidenceNumber",
    "ExtractedNumericClaim",
    "RejectedFinding",
    "TextSpan",
    "ValidatedClaimRecord",
    "extract_evidence_numbers",
    "extract_numeric_claims",
    "match_claim_to_evidence",
    "normalize_claim_number",
    "validate_findings",
    "validate_plan",
    "validate_single_claim",
    "validate_task_args",
    "validate_tool_result",
]
