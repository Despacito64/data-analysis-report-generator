"""Unit tests for Layer 4 numeric claim extraction, evidence matching, and finding validation."""

import tempfile
from datetime import UTC, datetime

from da_agent.contracts.models import (
    EvidenceRecord,
    Finding,
    NumericClaim,
)
from da_agent.core.config import ClaimValidationConfig, FindingDropPolicy
from da_agent.core.trace import RunTraceWriter
from da_agent.validation.claims import (
    ClaimStatus,
    extract_evidence_numbers,
    extract_numeric_claims,
    match_claim_to_evidence,
    validate_findings,
    validate_single_claim,
)


def _make_evidence_record(
    evidence_id: str,
    result_summary: dict,
    valid: bool = True,
    invalidated_by: str | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        task_id=f"task_{evidence_id}",
        tool="group_aggregate",
        args_hash="hash_123",
        dataset_hash="dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c",
        input_row_count=100,
        result_summary=result_summary,
        result_schema_version="0.1.0",
        valid=valid,
        invalidated_by=invalidated_by,
        created_at=datetime.now(UTC),
    )


def test_supported_exact_value_and_rounded_within_tolerance() -> None:
    config = ClaimValidationConfig(rtol=0.001, atol=0.01)
    ev_numbers = extract_evidence_numbers({"sales": 125.5, "profit_ratio": 0.12341234})

    # Exact value match
    claim_exact = extract_numeric_claims("Total sales was 125.5")[0]
    status, reason, path, val = match_claim_to_evidence(claim_exact, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "sales"
    assert val == 125.5
    assert "within tolerance" in reason

    # Rounded value within tolerance (125 matches 125.0001 or 125.12 when digits=0)
    claim_rounded = extract_numeric_claims("The count was 125")[0]
    ev_rounded = extract_evidence_numbers({"count": 125.002})
    status, reason, path, val = match_claim_to_evidence(claim_rounded, ev_rounded, config)
    assert status == ClaimStatus.SUPPORTED

    # Multi-digit rounding
    claim_ratio = extract_numeric_claims("Profit ratio was 0.1234")[0]
    status, reason, path, val = match_claim_to_evidence(claim_ratio, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "profit_ratio"


def test_percentage_fraction_thousands_currency_and_negative_changes() -> None:
    config = ClaimValidationConfig(rtol=0.001, atol=0.01)
    ev_data = {
        "share": 0.1234,  # fraction
        "margin_pct": 15.5,  # percentage
        "revenue": 1234567.89,  # large number
        "fee": 500.0,
        "growth": -0.034,  # negative fraction
    }
    ev_numbers = extract_evidence_numbers(ev_data)

    # 1. Percentage vs fraction: "12.3%" matches 0.1234 (rounds to 12.3%)
    claim_pct = extract_numeric_claims("Market share reached 12.3%")[0]
    status, _, path, _ = match_claim_to_evidence(claim_pct, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "share"

    # 2. Plain fraction claim "0.155" matches 15.5 (%)
    claim_frac = extract_numeric_claims("Margin was 0.155")[0]
    status, _, path, _ = match_claim_to_evidence(claim_frac, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "margin_pct"

    # 3. Thousands separators: "$1,234,567.89" matches 1234567.89
    claim_thousands = extract_numeric_claims("Revenue topped $1,234,567.89")[0]
    status, _, path, _ = match_claim_to_evidence(claim_thousands, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "revenue"

    # 4. Currency: "500 USD" matches 500.0
    claim_curr = extract_numeric_claims("Processing fee was 500 USD")[0]
    status, _, path, _ = match_claim_to_evidence(claim_curr, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "fee"

    # 5. Negative changes: "-3.4%" matches -0.034
    claim_neg = extract_numeric_claims("Sales dropped by -3.4%")[0]
    status, _, path, _ = match_claim_to_evidence(claim_neg, ev_numbers, config)
    assert status == ClaimStatus.SUPPORTED
    assert path == "growth"


def test_recomputed_claim_difference_and_share_matches_and_mismatches() -> None:
    config = ClaimValidationConfig(rtol=0.001, atol=0.01, allow_recomputation=True)
    ev_data = {
        "sales_2016": 500.0,
        "sales_2015": 200.0,
        "phones": 50.0,
        "total": 200.0,
    }
    ev_numbers = extract_evidence_numbers(ev_data)

    # Recomputed difference: 500 - 200 = 300
    claim_diff = extract_numeric_claims("Sales increased by $300.00")[0]
    status, reason, _, val = match_claim_to_evidence(claim_diff, ev_numbers, config)
    assert status == ClaimStatus.RECOMPUTED
    assert "difference" in reason
    assert val == 300.0

    # Recomputed share: 50 / 200 = 25.0%
    claim_share = extract_numeric_claims("Phones accounted for 25% of total")[0]
    status, reason, _, val = match_claim_to_evidence(claim_share, ev_numbers, config)
    assert status == ClaimStatus.RECOMPUTED
    assert "share" in reason
    assert val == 25.0

    # Mismatch recomputation: claim 888.0 cannot be formed by binary ops on this evidence
    claim_mismatch = extract_numeric_claims("Sales jumped by $888.00")[0]
    status, reason, _, _ = match_claim_to_evidence(claim_mismatch, ev_numbers, config)
    assert status == ClaimStatus.UNSUPPORTED
    assert "No matching value or recomputed derivation found" in reason


def test_manipulated_number_is_caught_as_unsupported() -> None:
    config = ClaimValidationConfig()
    ev_numbers = extract_evidence_numbers({"profit": 125.5})

    claim_tampered = extract_numeric_claims("Profit was 999.0")[0]
    status, reason, _, val = match_claim_to_evidence(claim_tampered, ev_numbers, config)
    assert status == ClaimStatus.UNSUPPORTED
    assert val is None
    assert "No matching value" in reason


def test_missing_evidence_id_and_invalid_evidence() -> None:
    config = ClaimValidationConfig()
    ev_valid = _make_evidence_record("ev_valid", {"sales": 100.0}, valid=True)
    ev_invalid = _make_evidence_record("ev_invalid", {"sales": 100.0}, valid=False)
    ev_invalidated = _make_evidence_record(
        "ev_invalidated", {"sales": 100.0}, valid=True, invalidated_by="ev_subsequent"
    )

    evidence_store = {
        "ev_valid": ev_valid,
        "ev_invalid": ev_invalid,
        "ev_invalidated": ev_invalidated,
    }

    claim = NumericClaim(value=100.0, label="sales", evidence_id="ev_missing")

    # Missing evidence record
    rec_missing = validate_single_claim(
        claim, evidence_store.get("ev_missing"), config, "ev_missing"
    )
    assert rec_missing.status == ClaimStatus.UNSUPPORTED
    assert "not found" in rec_missing.reason

    # Invalid evidence (valid=False)
    claim_inv = NumericClaim(value=100.0, label="sales", evidence_id="ev_invalid")
    rec_inv = validate_single_claim(
        claim_inv, evidence_store.get("ev_invalid"), config, "ev_invalid"
    )
    assert rec_inv.status == ClaimStatus.UNSUPPORTED
    assert "marked valid=False" in rec_inv.reason

    # Invalidated evidence (invalidated_by is set)
    claim_inved = NumericClaim(value=100.0, label="sales", evidence_id="ev_invalidated")
    rec_inved = validate_single_claim(
        claim_inved, evidence_store.get("ev_invalidated"), config, "ev_invalidated"
    )
    assert rec_inved.status == ClaimStatus.UNSUPPORTED
    assert "invalidated by ev_subsequent" in rec_inved.reason


def test_ambiguous_match() -> None:
    config = ClaimValidationConfig()
    # Evidence has two distinct paths with the identical matching metric value
    ev_numbers = extract_evidence_numbers({"east_sales": 100.0, "west_sales": 100.0})
    claim = extract_numeric_claims("Sales was $100.00")[0]

    status, reason, _, _ = match_claim_to_evidence(claim, ev_numbers, config)
    assert status == ClaimStatus.AMBIGUOUS
    assert "Ambiguous match" in reason
    assert "east_sales" in reason
    assert "west_sales" in reason


def test_non_claim_numbers_are_not_extracted() -> None:
    text = (
        "1. In 2016, customer 'CA-2016-152156' with postal code \"42420\" was ranked 1st "
        "between 2014 and 2017 with order FUR-BO-10001798 on 2016-11-08."
    )
    extracted = extract_numeric_claims(text)
    assert extracted == []


def test_finding_with_mixed_claims_under_both_drop_modes() -> None:
    ev_record = _make_evidence_record("ev_01", {"sales": 500.0})
    evidence_store = {"ev_01": ev_record}

    finding = Finding(
        statement="Sales reached $500 with $999 profit.",
        numeric_claims=[
            NumericClaim(value=500.0, label="sales", evidence_id="ev_01"),
            NumericClaim(value=999.0, label="profit", evidence_id="ev_01"),
        ],
        evidence_ids=["ev_01"],
    )

    # 1. Mode: drop_finding (default)
    cfg_drop = ClaimValidationConfig(drop_policy=FindingDropPolicy.DROP_FINDING)
    res_drop = validate_findings([finding], evidence_store, cfg_drop)

    assert len(res_drop.validated_findings) == 0
    assert len(res_drop.rejected_findings) == 1
    assert "999" in res_drop.rejected_findings[0].reasons[0]

    # 2. Mode: remove_claim
    cfg_remove = ClaimValidationConfig(drop_policy=FindingDropPolicy.REMOVE_CLAIM)
    res_remove = validate_findings([finding], evidence_store, cfg_remove)

    assert len(res_remove.validated_findings) == 1
    assert len(res_remove.rejected_findings) == 0
    # Unsupported claim (999.0) was pruned; only supported claim (500.0) remains
    assert len(res_remove.validated_findings[0].numeric_claims) == 1
    assert res_remove.validated_findings[0].numeric_claims[0].value == 500.0

    # 3. Mode: remove_claim where ALL claims are unsupported -> finding must be rejected
    all_bad_finding = Finding(
        statement="Sales reached $999.",
        numeric_claims=[NumericClaim(value=999.0, label="sales", evidence_id="ev_01")],
        evidence_ids=["ev_01"],
    )
    res_all_bad = validate_findings([all_bad_finding], evidence_store, cfg_remove)
    assert len(res_all_bad.validated_findings) == 0
    assert len(res_all_bad.rejected_findings) == 1


def test_claims_validator_emits_trace_event() -> None:
    ev_record = _make_evidence_record("ev_trace", {"sales": 100.0})
    evidence_store = {"ev_trace": ev_record}
    finding = Finding(
        statement="Sales reached $100.",
        numeric_claims=[NumericClaim(value=100.0, label="sales", evidence_id="ev_trace")],
        evidence_ids=["ev_trace"],
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        writer = RunTraceWriter(run_id="trace_claim_test", base_dir=temp_dir)
        res = validate_findings([finding], evidence_store, trace_writer=writer)
        events = writer.read_events()

    assert len(res.validated_findings) == 1
    claim_events = [e for e in events if e.event_type == "claim_validation"]
    assert len(claim_events) == 1
    payload = claim_events[0].payload
    assert payload["total_findings"] == 1
    assert payload["validated_findings_count"] == 1
    assert payload["rejected_findings_count"] == 0
    assert payload["supported_claims_count"] == 1


def test_extract_evidence_numbers_traversal_and_filtering() -> None:
    data = {
        "summary": {"total_sales": 1250.0, "matched_indices": [0, 1, 2]},
        "segments": [{"name": "Consumer", "value": 750.0}, {"name": "Corporate", "value": 500.0}],
        "is_active": True,
        "invalid_val": float("nan"),
    }
    extracted = extract_evidence_numbers(data)
    paths = {item.path: item.value for item in extracted}

    assert paths["summary.total_sales"] == 1250.0
    assert paths["segments[0].value"] == 750.0
    assert paths["segments[1].value"] == 500.0
    # Filtered out
    assert "summary.matched_indices" not in paths
    assert "is_active" not in paths
    assert "invalid_val" not in paths
