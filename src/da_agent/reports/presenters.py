"""Deterministic reader-layer findings from typed tool evidence summaries."""

from __future__ import annotations

from collections.abc import Callable

from da_agent.contracts.models import EvidenceRecord, Finding, NumericClaim


def _group_label(group_keys: dict[str, object]) -> str:
    if not group_keys:
        return "Group"
    if len(group_keys) == 1:
        return str(next(iter(group_keys.values())))
    parts = [f"{key}: {value}" for key, value in group_keys.items()]
    return ", ".join(str(part) for part in parts)


def present_group_aggregate_findings(
    record: EvidenceRecord,
) -> tuple[list[Finding], list[str]]:
    """One consolidated finding per group_aggregate evidence (no per-row duplication)."""
    if record.tool != "group_aggregate" or not record.valid or record.invalidated_by:
        return [], []
    summary = record.result_summary
    groups = summary.get("sample_groups") or summary.get("rows") or []
    metric = str(summary.get("metric_column") or "Value")
    agg = str(summary.get("aggregation") or "sum")
    display_metric = f"{metric} ({agg})"
    claims: list[NumericClaim] = []
    highlights: list[str] = []
    for item in groups:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)):
            continue
        keys = item.get("group_keys") or {}
        if not isinstance(keys, dict):
            keys = {}
        label = _group_label(keys)
        claims.append(
            NumericClaim(
                value=value,
                label=f"{label} — {display_metric}",
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"{label}: {value:,.2f}")
    if not claims:
        return [], []
    findings = [
        Finding(
            statement=f"Total {display_metric} by group",
            numeric_claims=claims,
            evidence_ids=[record.evidence_id],
        )
    ]
    return findings, highlights


def present_rank_findings(record: EvidenceRecord) -> tuple[list[Finding], list[str]]:
    if record.tool != "rank" or not record.valid or record.invalidated_by:
        return [], []
    summary = record.result_summary
    rows = summary.get("top_rows") or []
    claims: list[NumericClaim] = []
    highlights: list[str] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        if not isinstance(value, (int, float)):
            continue
        entity = item.get("entity", item.get("entity_label", "Item"))
        rank = item.get("rank")
        rank_prefix = f"#{rank} " if rank is not None else ""
        label = f"{rank_prefix}{entity}"
        claims.append(
            NumericClaim(
                value=value,
                label=label,
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"{label}: {value:,.2f}")
    if not claims:
        return [], []
    finding = Finding(
        statement="Ranked results",
        numeric_claims=claims,
        evidence_ids=[record.evidence_id],
    )
    return [finding], highlights


def present_period_compare_findings(record: EvidenceRecord) -> tuple[list[Finding], list[str]]:
    if record.tool != "period_compare" or not record.valid or record.invalidated_by:
        return [], []
    summary = record.result_summary
    base = summary.get("base_period") if isinstance(summary.get("base_period"), dict) else {}
    compare = (
        summary.get("compare_period") if isinstance(summary.get("compare_period"), dict) else {}
    )
    claims: list[NumericClaim] = []
    highlights: list[str] = []
    base_val = base.get("value")
    if isinstance(base_val, (int, float)):
        claims.append(
            NumericClaim(
                value=base_val,
                label="Base period",
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"Base period: {base_val:,.2f}")
    compare_val = compare.get("value")
    if isinstance(compare_val, (int, float)):
        claims.append(
            NumericClaim(
                value=compare_val,
                label="Compare period",
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"Compare period: {compare_val:,.2f}")
    abs_change = summary.get("absolute_change")
    if isinstance(abs_change, (int, float)):
        claims.append(
            NumericClaim(
                value=abs_change,
                label="Absolute change",
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"Change: {abs_change:+,.2f}")
    rel_growth = summary.get("relative_growth")
    if isinstance(rel_growth, (int, float)):
        claims.append(
            NumericClaim(
                value=rel_growth,
                label="Relative growth (fraction)",
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"Growth: {rel_growth * 100:,.1f}%")
    if not claims:
        return [], []
    finding = Finding(
        statement="Period-over-period comparison",
        numeric_claims=claims,
        evidence_ids=[record.evidence_id],
    )
    return [finding], highlights


def present_trend_findings(record: EvidenceRecord) -> tuple[list[Finding], list[str]]:
    if record.tool != "trend" or not record.valid or record.invalidated_by:
        return [], []
    summary = record.result_summary
    direction = str(summary.get("direction") or "unknown")
    claims: list[NumericClaim] = []
    highlights: list[str] = [f"Trend direction: {direction}"]
    slope = summary.get("slope")
    if isinstance(slope, (int, float)):
        claims.append(
            NumericClaim(
                value=slope,
                label=f"Trend slope ({summary.get('grain', 'period')})",
                evidence_id=record.evidence_id,
            )
        )
        highlights.append(f"Slope: {slope:,.4f}")
    points = summary.get("sample_points") or []
    for item in points[-3:]:
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        period = item.get("period_label") or item.get("period")
        if isinstance(value, (int, float)) and period is not None:
            claims.append(
                NumericClaim(
                    value=value,
                    label=f"{period}",
                    evidence_id=record.evidence_id,
                )
            )
    if not claims:
        return [], highlights
    finding = Finding(
        statement=f"Time-series trend ({direction})",
        numeric_claims=claims,
        evidence_ids=[record.evidence_id],
    )
    return [finding], highlights


_PRESENTERS: dict[str, Callable[[EvidenceRecord], tuple[list[Finding], list[str]]]] = {
    "group_aggregate": present_group_aggregate_findings,
    "rank": present_rank_findings,
    "period_compare": present_period_compare_findings,
    "trend": present_trend_findings,
}


def present_findings_from_evidence(
    evidence_records: dict[str, EvidenceRecord],
) -> tuple[list[Finding], list[str], set[str]]:
    """Collect presenter findings; return evidence ids consumed by presenters."""
    findings: list[Finding] = []
    highlights: list[str] = []
    used: set[str] = set()
    for record in evidence_records.values():
        presenter = _PRESENTERS.get(record.tool)
        if presenter is None:
            continue
        chunk, chunk_highlights = presenter(record)
        if chunk:
            findings.extend(chunk)
            highlights.extend(chunk_highlights)
            used.add(record.evidence_id)
    return findings, highlights, used


def executive_summary_from_findings(findings: list[Finding]) -> str:
    """One-sentence headline (pyramid top); details belong in the table/chart."""
    if not findings:
        return "No supported results to summarize."
    rows: list[tuple[str, float]] = []
    for finding in findings:
        for claim in finding.numeric_claims:
            if not isinstance(claim.value, (int, float)):
                continue
            label = claim.label.split(" — ")[0]
            rows.append((label, float(claim.value)))
    if not rows:
        return "No supported results to summarize."
    if len(rows) == 1:
        label, value = rows[0]
        return f"{label}: {value:,.2f}."
    best_label, best_value = max(rows, key=lambda item: item[1])
    metric_hint = findings[0].statement.replace("Total ", "").replace(" by group", "")
    return (
        f"{best_label} is highest for {metric_hint} at {best_value:,.2f} "
        f"({len(rows)} groups compared)."
    )