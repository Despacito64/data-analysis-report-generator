"""Deterministic numerical claim extraction, evidence matching, and finding validation.

Architectural Layer 4 (Validation):
- Imports strictly from da_agent.contracts and da_agent.core.
- NEVER imports da_agent.tools, da_agent.agent, da_agent.reports, da_agent.pipeline, or evaluation.
"""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts.models import (
    EvidenceRecord,
    Finding,
    NumericClaim,
)
from da_agent.core.config import ClaimValidationConfig, FindingDropPolicy
from da_agent.core.trace import RunTraceWriter


class ClaimStatus(str, Enum):
    """Validation status for an individual numerical claim."""

    SUPPORTED = "supported"
    RECOMPUTED = "recomputed"
    UNSUPPORTED = "unsupported"
    AMBIGUOUS = "ambiguous"


class TextSpan(BaseModel):
    """Character offset span in source text."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ExtractedNumericClaim(BaseModel):
    """Typed numerical claim extracted from unstructured text."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str
    value: float
    unit: str | None = None
    span: TextSpan
    is_percentage: bool = False
    is_currency: bool = False
    decimal_digits: int = 0
    magnitude_multiplier: float = 1.0


class EvidenceNumber(BaseModel):
    """Flattened scalar numeric value extracted from an evidence record envelope."""

    model_config = ConfigDict(extra="forbid")

    path: str
    value: float


class ValidatedClaimRecord(BaseModel):
    """Audit record capturing the validation outcome and provenance of a claim."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str
    value: float
    unit: str | None = None
    evidence_id: str | None = None
    status: ClaimStatus
    matched_path: str | None = None
    matched_value: float | None = None
    reason: str
    is_recomputed: bool = False
    recomputation_formula: str | None = None


class RejectedFinding(BaseModel):
    """Finding rejected during validation with explicit failure reasons."""

    model_config = ConfigDict(extra="forbid")

    finding: Finding
    reasons: list[str]
    unsupported_claims: list[ValidatedClaimRecord] = Field(default_factory=list)


class ClaimValidationResult(BaseModel):
    """Outcome of validating a collection of report findings."""

    model_config = ConfigDict(extra="forbid")

    validated_findings: list[Finding]
    rejected_findings: list[RejectedFinding]
    claim_records: list[ValidatedClaimRecord] = Field(default_factory=list)


_NON_CLAIM_KEYS = {
    "matched_indices",
    "sample_matched_indices",
    "invariants_checked",
    "dataset_hash",
    "args_hash",
    "result_schema_version",
    "task_id",
    "evidence_id",
    "valid",
    "invalidated_by",
    "created_at",
}

_STOP_WORDS_AS_UNITS = {
    "and",
    "or",
    "in",
    "of",
    "to",
    "at",
    "for",
    "with",
    "by",
    "from",
    "on",
    "as",
    "is",
    "was",
    "were",
    "are",
    "be",
    "been",
    "that",
    "this",
    "which",
    "than",
    "then",
    "but",
    "into",
    "over",
    "after",
    "before",
    "between",
    "under",
    "above",
    "through",
    "during",
    "out",
    "up",
    "down",
    "off",
    "about",
    "against",
    "among",
    "per",
}

_CURRENCY_CODES = {"usd", "eur", "gbp", "jpy", "cad", "aud", "inr", "cny"}

_MAGNITUDE_MULTIPLIERS = {
    "k": 1e3,
    "thousand": 1e3,
    "thousands": 1e3,
    "m": 1e6,
    "million": 1e6,
    "millions": 1e6,
    "b": 1e9,
    "billion": 1e9,
    "billions": 1e9,
    "t": 1e12,
    "trillion": 1e12,
}


def normalize_claim_number(text: str) -> float | None:
    """Normalize numeric string representation to a finite float, handling currency, commas, and magnitude suffixes."""
    stripped = text.strip().rstrip("%").replace(",", "")
    for symbol in ("$", "€", "£", "¥", "₹"):
        stripped = stripped.replace(symbol, "")
    stripped = stripped.strip()

    # Check for magnitude suffix (e.g. 2.3M or 2.3 million)
    for suffix, m_val in _MAGNITUDE_MULTIPLIERS.items():
        if stripped.lower().endswith(suffix):
            num_part = stripped[: -len(suffix)].strip()
            try:
                val = float(num_part) * m_val
                return val if math.isfinite(val) else None
            except ValueError:
                break

    try:
        val = float(stripped)
    except ValueError:
        return None
    return val if math.isfinite(val) else None


def extract_evidence_numbers(data: Any, path: str = "") -> list[EvidenceNumber]:
    """Recursively extract finite scalar numbers and their JSON-path provenance from tool evidence."""
    numbers: list[EvidenceNumber] = []
    if isinstance(data, bool):
        return numbers
    if isinstance(data, (int, float)):
        if math.isfinite(data):
            numbers.append(EvidenceNumber(path=path or "value", value=float(data)))
    elif isinstance(data, dict):
        for key, child in data.items():
            if key not in _NON_CLAIM_KEYS:
                child_path = f"{path}.{key}" if path else str(key)
                numbers.extend(extract_evidence_numbers(child, child_path))
    elif isinstance(data, list):
        for idx, child in enumerate(data):
            child_path = f"{path}[{idx}]" if path else f"[{idx}]"
            numbers.extend(extract_evidence_numbers(child, child_path))
    elif isinstance(data, EvidenceRecord):
        # Extract from result_summary
        summary_path = f"{path}.result_summary" if path else "result_summary"
        numbers.extend(extract_evidence_numbers(data.result_summary, summary_path))
    return numbers


def extract_numeric_claims(text: str) -> list[ExtractedNumericClaim]:
    """Extract typed numeric claims from text while ignoring dates, years, ordinals, IDs, and list numbers."""
    ignored_spans: set[int] = set()

    # 1. Quoted identifiers and strings (e.g. '42420', "90036", 'CA-123')
    for m in re.finditer(r"['\"][^'\"]*['\"]", text):
        for i in range(m.start(), m.end()):
            ignored_spans.add(i)

    # 2. List numbering at start of line or after punctuation (e.g. "1. ", "2) ", "(3) ")
    for m in re.finditer(r"(?:^|[\n\r]|(?<=[.!?]\s))\s*(?:\d+[\.\)]|\(\d+\)|\[\d+\])\s*", text):
        for i in range(m.start(), m.end()):
            ignored_spans.add(i)

    # 3. Alphanumeric IDs with mixed letters/digits/hyphens/underscores (e.g. CA-2016-152156, FUR-BO-10001798, P101)
    for m in re.finditer(
        r"\b(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]+\b",
        text,
    ):
        matched_str = m.group(0)
        # Preserve scientific notation (1.5e6) and magnitude suffix abbreviations (3M, 10k, 5B)
        if re.match(r"^\d+(?:\.\d+)?[eE][+-]?\d+$", matched_str):
            continue
        if re.match(r"^\d+(?:\.\d+)?[kKmMgGbBtT]$", matched_str):
            continue
        for i in range(m.start(), m.end()):
            ignored_spans.add(i)

    # 4. Ordinals (1st, 2nd, 3rd, 4th, 21st, etc.)
    for m in re.finditer(r"\b\d+(?:st|nd|rd|th)\b", text, re.IGNORECASE):
        for i in range(m.start(), m.end()):
            ignored_spans.add(i)

    # 5. Full dates and quarters (e.g. 2016-11-08, 11/08/2016, Q1 2016)
    for m in re.finditer(
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\bQ[1-4]\s+\d{4}\b",
        text,
        re.IGNORECASE,
    ):
        for i in range(m.start(), m.end()):
            ignored_spans.add(i)

    # 6. Years in temporal context (e.g. "in 2016", "between 2014 and 2017", "2014-2017", "year 2018")
    year_ctx = re.finditer(
        r"\b(?:in|during|since|from|to|between|and|until|before|after|through|year|years|fy|fiscal|dated|as\s+of|q[1-4])\s+((?:19|20)\d{2})\b"
        r"|\b((?:19|20)\d{2})\s*(?:-|to|and|through)\s*((?:19|20)\d{2})\b"
        r"|\b((?:19|20)\d{2})\s+(?:sales|revenue|profit|growth|orders|results|performance|period|data|annual)\b",
        text,
        re.IGNORECASE,
    )
    for m in year_ctx:
        for g_idx in range(1, len(m.groups()) + 1):
            if m.group(g_idx):
                start, end = m.span(g_idx)
                for i in range(start, end):
                    ignored_spans.add(i)

    claims: list[ExtractedNumericClaim] = []

    # 7. Ratios (e.g. 1:4, 3.5:1)
    ratio_spans: set[int] = set()
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)\b", text):
        if any(i in ignored_spans for i in range(m.start(), m.end())):
            continue
        v1 = float(m.group(1))
        v2 = float(m.group(2))
        val = v1 / v2 if v2 != 0 else float("inf")
        claims.append(
            ExtractedNumericClaim(
                raw_text=m.group(0),
                value=val,
                unit="ratio",
                span=TextSpan(start=m.start(), end=m.end()),
                is_percentage=False,
                is_currency=False,
                decimal_digits=max(
                    len(m.group(1).split(".")[1]) if "." in m.group(1) else 0,
                    len(m.group(2).split(".")[1]) if "." in m.group(2) else 0,
                ),
            )
        )
        for i in range(m.start(), m.end()):
            ratio_spans.add(i)

    # 8. Numeric claims (currency prefix, signed changes, numbers, percentages, units)
    num_pattern = re.compile(
        r"(?P<prefix>[$€£¥₹])?"
        r"(?P<sign>[+-])?"
        r"(?P<num>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?)"
        r"(?P<pct>%)?"
        r"(?:\s*(?P<unit>[A-Za-z]+))?",
        re.IGNORECASE,
    )

    for m in num_pattern.finditer(text):
        raw_num_part = m.group("num")
        if not raw_num_part:
            continue

        num_start = (
            m.start("prefix")
            if m.group("prefix")
            else (m.start("sign") if m.group("sign") else m.start("num"))
        )
        num_end = m.end("pct") if m.group("pct") else m.end("num")

        if any(i in ignored_spans or i in ratio_spans for i in range(num_start, num_end)):
            continue

        raw_num = raw_num_part.replace(",", "")

        # Ignore standalone 4-digit year without prefix, sign, pct, or unit
        if (
            not m.group("prefix")
            and not m.group("pct")
            and not m.group("sign")
            and not m.group("unit")
            and len(raw_num) == 4
            and raw_num.isdigit()
            and 1900 <= int(raw_num) <= 2099
        ):
            continue

        sign_mult = -1.0 if m.group("sign") == "-" else 1.0
        try:
            val = float(raw_num) * sign_mult
        except ValueError:
            continue

        if not math.isfinite(val):
            continue

        is_pct = bool(m.group("pct"))
        is_curr = bool(m.group("prefix"))

        decimal_digits = 0
        if "." in raw_num:
            decimal_digits = len(raw_num.split(".")[1].split("e")[0].split("E")[0])

        unit: str | None = None
        end = num_end

        magnitude_mult = 1.0
        if is_curr:
            unit = m.group("prefix")
            if m.group("unit"):
                unit_candidate = m.group("unit")
                unit_lower = unit_candidate.lower()
                if unit_lower in _MAGNITUDE_MULTIPLIERS:
                    magnitude_mult = _MAGNITUDE_MULTIPLIERS[unit_lower]
                    end = m.end("unit")
        elif is_pct:
            unit = "%"
        elif m.group("unit"):
            unit_candidate = m.group("unit")
            unit_lower = unit_candidate.lower()
            if unit_lower in _MAGNITUDE_MULTIPLIERS:
                magnitude_mult = _MAGNITUDE_MULTIPLIERS[unit_lower]
                unit = unit_candidate
                end = m.end("unit")
            elif unit_lower in _CURRENCY_CODES:
                unit = unit_candidate.upper()
                is_curr = True
                end = m.end("unit")
            elif unit_lower not in _STOP_WORDS_AS_UNITS:
                unit = unit_candidate
                end = m.end("unit")

        claims.append(
            ExtractedNumericClaim(
                raw_text=text[num_start:end],
                value=val,
                unit=unit,
                span=TextSpan(start=num_start, end=end),
                is_percentage=is_pct,
                is_currency=is_curr,
                decimal_digits=decimal_digits,
                magnitude_multiplier=magnitude_mult,
            )
        )

    claims.sort(key=lambda c: c.span.start)
    return claims


def match_claim_to_evidence(
    claim: ExtractedNumericClaim | NumericClaim,
    evidence_numbers: list[EvidenceNumber],
    config: ClaimValidationConfig,
) -> tuple[ClaimStatus, str, str | None, float | None]:
    """Match a single claim value against a list of evidence numbers using tolerance and recomputations."""
    mult = 1.0
    if isinstance(claim, NumericClaim):
        raw_val = claim.value
        if claim.unit and claim.unit.lower() in _MAGNITUDE_MULTIPLIERS:
            mult = _MAGNITUDE_MULTIPLIERS[claim.unit.lower()]
        elif isinstance(raw_val, str):
            for suffix, m_val in _MAGNITUDE_MULTIPLIERS.items():
                if raw_val.strip().lower().endswith(suffix):
                    mult = m_val
                    break

        if isinstance(raw_val, (int, float)):
            claim_val = float(raw_val)
            digits = (
                len(str(raw_val).split(".")[1])
                if isinstance(raw_val, float) and "." in str(raw_val)
                else 0
            )
        else:
            cleaned_str = (
                str(raw_val)
                .replace("$", "")
                .replace("€", "")
                .replace("£", "")
                .replace(",", "")
                .strip()
            )
            for suffix in _MAGNITUDE_MULTIPLIERS:
                if cleaned_str.lower().endswith(suffix):
                    cleaned_str = cleaned_str[: -len(suffix)].strip()
                    break
            try:
                claim_val = float(cleaned_str)
            except ValueError:
                norm = normalize_claim_number(str(raw_val))
                claim_val = norm if norm is not None else float("nan")
            digits = len(cleaned_str.split(".")[1]) if "." in cleaned_str else 0

        is_pct = claim.unit in ("%", "percent") or (
            isinstance(raw_val, str) and "%" in str(raw_val)
        )
    else:
        claim_val = claim.value
        digits = claim.decimal_digits
        is_pct = claim.is_percentage
        mult = getattr(claim, "magnitude_multiplier", 1.0)

    if not math.isfinite(claim_val):
        return (
            ClaimStatus.UNSUPPORTED,
            f"Non-finite or invalid claim value: {claim}",
            None,
            None,
        )

    # Stated precision tolerance: follows claim's stated precision
    if mult > 1.0 and digits is not None and digits > 0:
        effective_atol = 0.5 * (10**-digits)
    elif digits is not None and digits < config.rounding_digits:
        effective_atol = max(config.atol, 0.5 * (10**-digits))
    else:
        effective_atol = config.atol

    # 1. Direct matches
    direct_matches: list[tuple[EvidenceNumber, float]] = []
    for ev_num in evidence_numbers:
        ev_val = ev_num.value
        candidates = [ev_val]
        if mult > 1.0:
            candidates.append(ev_val / mult)
        if is_pct:
            candidates.append(ev_val * 100.0)
            if mult > 1.0:
                candidates.append((ev_val / mult) * 100.0)
        elif abs(claim_val) <= 1.0 and abs(ev_val) > 1.0:
            candidates.append(ev_val / 100.0)

        matched_cand = None
        for cand in candidates:
            if math.isclose(claim_val, cand, rel_tol=config.rtol, abs_tol=effective_atol):
                matched_cand = cand
                break
            if digits is not None and digits < config.rounding_digits:
                rounded_cand = round(cand, digits)
                if math.isclose(
                    claim_val, rounded_cand, rel_tol=config.rtol, abs_tol=effective_atol
                ):
                    matched_cand = cand
                    break
        if matched_cand is not None:
            direct_matches.append((ev_num, matched_cand))

    if len(direct_matches) == 1:
        ev_num, _ = direct_matches[0]
        return (
            ClaimStatus.SUPPORTED,
            f"Matches evidence value {ev_num.value} at '{ev_num.path}' within tolerance",
            ev_num.path,
            ev_num.value,
        )
    elif len(direct_matches) > 1:
        distinct_paths = list(dict.fromkeys(m[0].path for m in direct_matches))
        if len(distinct_paths) > 1:
            return (
                ClaimStatus.AMBIGUOUS,
                f"Ambiguous match: multiple distinct evidence paths matched {distinct_paths}",
                None,
                None,
            )
        else:
            ev_num = direct_matches[0][0]
            return (
                ClaimStatus.SUPPORTED,
                f"Matches evidence value {ev_num.value} at '{ev_num.path}' within tolerance",
                ev_num.path,
                ev_num.value,
            )

    # 2. Recomputation
    if config.allow_recomputation:
        unique_nums: list[EvidenceNumber] = []
        seen: set[float] = set()
        for en in evidence_numbers:
            if en.value not in seen:
                seen.add(en.value)
                unique_nums.append(en)
            if len(unique_nums) >= 25:
                break

        recomputed_matches = []
        n = len(unique_nums)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                e1, e2 = unique_nums[i], unique_nums[j]
                v1, v2 = e1.value, e2.value

                # Sum
                if i < j:
                    val_sum = v1 + v2
                    if math.isclose(claim_val, val_sum, rel_tol=config.rtol, abs_tol=config.atol):
                        recomputed_matches.append(
                            (
                                f"sum({e1.path} + {e2.path})",
                                val_sum,
                                f"{v1} + {v2} = {val_sum}",
                            )
                        )

                # Difference
                val_diff = v1 - v2
                if math.isclose(claim_val, val_diff, rel_tol=config.rtol, abs_tol=config.atol):
                    recomputed_matches.append(
                        (
                            f"difference({e1.path} - {e2.path})",
                            val_diff,
                            f"{v1} - {v2} = {val_diff}",
                        )
                    )

                # Share
                if v2 != 0:
                    raw_share = v1 / v2
                    share_cand = raw_share * 100.0 if is_pct else raw_share
                    matched = math.isclose(
                        claim_val, share_cand, rel_tol=config.rtol, abs_tol=config.atol
                    ) or (
                        digits is not None
                        and digits < config.rounding_digits
                        and math.isclose(
                            claim_val,
                            round(share_cand, digits),
                            rel_tol=config.rtol,
                            abs_tol=config.atol,
                        )
                    )
                    if matched:
                        pct_suffix = "%" if is_pct else ""
                        recomputed_matches.append(
                            (
                                f"share({e1.path} / {e2.path})",
                                share_cand,
                                f"{v1} / {v2} = {share_cand}{pct_suffix}",
                            )
                        )

                # Percentage change
                if v1 != 0:
                    raw_change = (v2 - v1) / abs(v1)
                    change_cand = raw_change * 100.0 if is_pct else raw_change
                    matched = math.isclose(
                        claim_val, change_cand, rel_tol=config.rtol, abs_tol=config.atol
                    ) or (
                        digits is not None
                        and digits < config.rounding_digits
                        and math.isclose(
                            claim_val,
                            round(change_cand, digits),
                            rel_tol=config.rtol,
                            abs_tol=config.atol,
                        )
                    )
                    if matched:
                        pct_suffix = "%" if is_pct else ""
                        recomputed_matches.append(
                            (
                                f"pct_change(({e2.path} - {e1.path}) / abs({e1.path}))",
                                change_cand,
                                f"({v2} - {v1}) / |{v1}| = {change_cand}{pct_suffix}",
                            )
                        )

        if len(recomputed_matches) == 1:
            formula, derived_val, expr = recomputed_matches[0]
            return (
                ClaimStatus.RECOMPUTED,
                f"Recomputed as {formula}: {expr} (matches claim within tolerance)",
                formula,
                derived_val,
            )
        elif len(recomputed_matches) > 1:
            formulas = [m[0] for m in recomputed_matches]
            return (
                ClaimStatus.AMBIGUOUS,
                f"Ambiguous recomputation: multiple derivations matched {formulas}",
                None,
                None,
            )

    return (
        ClaimStatus.UNSUPPORTED,
        f"No matching value or recomputed derivation found in linked evidence for claim {claim_val}",
        None,
        None,
    )


def validate_single_claim(
    claim: ExtractedNumericClaim | NumericClaim,
    evidence_record: EvidenceRecord | dict[str, Any] | None,
    config: ClaimValidationConfig,
    evidence_id: str | None = None,
) -> ValidatedClaimRecord:
    """Validate one claim against a specified evidence record."""
    raw_text = claim.raw_text if isinstance(claim, ExtractedNumericClaim) else str(claim.value)
    val = (
        claim.value
        if isinstance(claim, ExtractedNumericClaim)
        else (normalize_claim_number(str(claim.value)) or 0.0)
    )
    unit = claim.unit

    if evidence_record is None:
        return ValidatedClaimRecord(
            raw_text=raw_text,
            value=val,
            unit=unit,
            evidence_id=evidence_id,
            status=ClaimStatus.UNSUPPORTED,
            reason=f"Linked evidence record '{evidence_id}' not found in evidence store",
        )

    # Check evidence validity
    is_valid = True
    invalidated_by = None
    if isinstance(evidence_record, EvidenceRecord):
        is_valid = evidence_record.valid
        invalidated_by = evidence_record.invalidated_by
    elif isinstance(evidence_record, dict):
        is_valid = evidence_record.get("valid", True)
        invalidated_by = evidence_record.get("invalidated_by")

    if not is_valid or invalidated_by:
        inv_reason = (
            f" (invalidated by {invalidated_by})" if invalidated_by else " (marked valid=False)"
        )
        return ValidatedClaimRecord(
            raw_text=raw_text,
            value=val,
            unit=unit,
            evidence_id=evidence_id,
            status=ClaimStatus.UNSUPPORTED,
            reason=f"Linked evidence record '{evidence_id}' is invalid{inv_reason}",
        )

    ev_numbers = extract_evidence_numbers(evidence_record)
    status, reason, matched_path, matched_value = match_claim_to_evidence(claim, ev_numbers, config)

    return ValidatedClaimRecord(
        raw_text=raw_text,
        value=val,
        unit=unit,
        evidence_id=evidence_id,
        status=status,
        matched_path=matched_path,
        matched_value=matched_value,
        reason=reason,
        is_recomputed=(status == ClaimStatus.RECOMPUTED),
        recomputation_formula=matched_path if status == ClaimStatus.RECOMPUTED else None,
    )


def validate_findings(
    findings: list[Finding],
    evidence_store: dict[str, EvidenceRecord | dict[str, Any]],
    config: ClaimValidationConfig | None = None,
    trace_writer: RunTraceWriter | None = None,
) -> ClaimValidationResult:
    """Validate numerical claims across findings against recorded evidence.

    Returns validated findings (excluding unsupported claims) and rejected findings with reasons.
    """
    cfg = config or ClaimValidationConfig()
    validated_findings: list[Finding] = []
    rejected_findings: list[RejectedFinding] = []
    all_claim_records: list[ValidatedClaimRecord] = []

    for finding in findings:
        finding_claims: list[ValidatedClaimRecord] = []
        unsupported_for_this_finding: list[ValidatedClaimRecord] = []
        reasons: list[str] = []

        # 1. Validate explicit numeric_claims
        if finding.numeric_claims:
            for num_claim in finding.numeric_claims:
                ev_rec = evidence_store.get(num_claim.evidence_id)
                record = validate_single_claim(
                    num_claim, ev_rec, cfg, evidence_id=num_claim.evidence_id
                )
                finding_claims.append(record)
                all_claim_records.append(record)
                if record.status not in (ClaimStatus.SUPPORTED, ClaimStatus.RECOMPUTED):
                    unsupported_for_this_finding.append(record)
                    reasons.append(
                        f"Claim {record.raw_text} (evidence {record.evidence_id}): {record.reason}"
                    )

        # 2. Extract and validate narrative claims from statement
        statement_extracted = extract_numeric_claims(finding.statement)
        for ext_claim in statement_extracted:
            # Check if this extracted value was already covered and supported in numeric_claims
            already_supported = any(
                c.status in (ClaimStatus.SUPPORTED, ClaimStatus.RECOMPUTED)
                and math.isclose(c.value, ext_claim.value, rel_tol=cfg.rtol, abs_tol=cfg.atol)
                for c in finding_claims
            )
            if already_supported:
                continue

            # Otherwise, validate against finding's evidence_ids
            matched_record = None
            if not finding.evidence_ids:
                matched_record = ValidatedClaimRecord(
                    raw_text=ext_claim.raw_text,
                    value=ext_claim.value,
                    unit=ext_claim.unit,
                    evidence_id=None,
                    status=ClaimStatus.UNSUPPORTED,
                    reason="Finding statement asserts numeric claim without linked evidence_ids",
                )
            else:
                # Try finding a match across all linked evidence records
                candidate_records: list[ValidatedClaimRecord] = []
                for ev_id in finding.evidence_ids:
                    ev_rec = evidence_store.get(ev_id)
                    rec = validate_single_claim(ext_claim, ev_rec, cfg, evidence_id=ev_id)
                    candidate_records.append(rec)
                    if rec.status in (ClaimStatus.SUPPORTED, ClaimStatus.RECOMPUTED):
                        matched_record = rec
                        break

                if matched_record is None and candidate_records:
                    matched_record = candidate_records[0]

            if matched_record is not None:
                finding_claims.append(matched_record)
                all_claim_records.append(matched_record)
                if matched_record.status not in (ClaimStatus.SUPPORTED, ClaimStatus.RECOMPUTED):
                    unsupported_for_this_finding.append(matched_record)
                    reasons.append(
                        f"Narrative claim '{matched_record.raw_text}': {matched_record.reason}"
                    )

        # Decide whether to drop the finding or remove the claim
        if not unsupported_for_this_finding:
            validated_findings.append(finding)
        else:
            if cfg.drop_policy == FindingDropPolicy.DROP_FINDING:
                rejected_findings.append(
                    RejectedFinding(
                        finding=finding,
                        reasons=reasons,
                        unsupported_claims=unsupported_for_this_finding,
                    )
                )
            elif cfg.drop_policy == FindingDropPolicy.REMOVE_CLAIM:
                # Keep only supported numeric claims
                supported_numeric_claims = [
                    nc
                    for nc in finding.numeric_claims
                    if any(
                        r.status in (ClaimStatus.SUPPORTED, ClaimStatus.RECOMPUTED)
                        and r.evidence_id == nc.evidence_id
                        and math.isclose(
                            r.value,
                            float(nc.value)
                            if isinstance(nc.value, (int, float))
                            else (normalize_claim_number(str(nc.value)) or 0.0),
                            rel_tol=cfg.rtol,
                            abs_tol=cfg.atol,
                        )
                        for r in finding_claims
                    )
                ]
                # If there are supported claims, retain the finding with filtered claims
                if supported_numeric_claims:
                    pruned_finding = finding.model_copy(
                        update={"numeric_claims": supported_numeric_claims}
                    )
                    validated_findings.append(pruned_finding)
                else:
                    # All claims were removed; reject finding
                    rejected_findings.append(
                        RejectedFinding(
                            finding=finding,
                            reasons=["All numeric claims were unsupported and removed", *reasons],
                            unsupported_claims=unsupported_for_this_finding,
                        )
                    )

    # Log additive validation event to run trace if writer is provided
    if trace_writer:
        trace_writer.log_event(
            "claim_validation",
            {
                "total_findings": len(findings),
                "validated_findings_count": len(validated_findings),
                "rejected_findings_count": len(rejected_findings),
                "total_claims": len(all_claim_records),
                "supported_claims_count": sum(
                    1 for c in all_claim_records if c.status == ClaimStatus.SUPPORTED
                ),
                "recomputed_claims_count": sum(
                    1 for c in all_claim_records if c.status == ClaimStatus.RECOMPUTED
                ),
                "unsupported_claims_count": sum(
                    1 for c in all_claim_records if c.status == ClaimStatus.UNSUPPORTED
                ),
                "ambiguous_claims_count": sum(
                    1 for c in all_claim_records if c.status == ClaimStatus.AMBIGUOUS
                ),
                "drop_policy": cfg.drop_policy.value,
            },
        )

    return ClaimValidationResult(
        validated_findings=validated_findings,
        rejected_findings=rejected_findings,
        claim_records=all_claim_records,
    )
