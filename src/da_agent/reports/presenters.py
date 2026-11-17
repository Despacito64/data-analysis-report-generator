"""Deterministic reader-layer findings from typed tool evidence summaries."""

from __future__ import annotations

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


def present_findings_from_evidence(
    evidence_records: dict[str, EvidenceRecord],
) -> tuple[list[Finding], list[str], set[str]]:
    """Collect presenter findings; return evidence ids consumed by presenters."""
    findings: list[Finding] = []
    highlights: list[str] = []
    used: set[str] = set()
    for record in evidence_records.values():
        if record.tool == "group_aggregate":
            chunk, chunk_highlights = present_group_aggregate_findings(record)
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