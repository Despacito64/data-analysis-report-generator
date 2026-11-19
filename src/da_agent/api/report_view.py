"""Map run artifacts to API presentation fields."""

from __future__ import annotations

import json
import re

from da_agent.api.session import RunJob

_GENERIC_SUMMARY = re.compile(r"^\d+ supported finding", re.IGNORECASE)


def report_has_numeric_claims(job: RunJob) -> bool:
    writer = job.trace_writer
    if writer is None:
        return False
    report_json = writer.run_dir / "report.json"
    if not report_json.is_file():
        return False
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    for finding in payload.get("findings") or []:
        if finding.get("numeric_claims"):
            return True
    return False


def _rows_from_findings(findings: list[dict]) -> list[dict[str, str | float]]:
    rows: list[dict[str, str | float]] = []
    for finding in findings:
        for claim in finding.get("numeric_claims") or []:
            value = claim.get("value")
            if not isinstance(value, (int, float)):
                continue
            label = str(claim.get("label", "Value"))
            rows.append(
                {
                    "category": label.split(" — ")[0],
                    "amount": round(float(value), 2),
                }
            )
    if len(rows) >= 2:
        rows.sort(key=lambda r: float(r["amount"]), reverse=True)
    return rows


def report_view(
    job: RunJob,
) -> tuple[str | None, list[dict[str, str | float]] | None, list[str] | None]:
    writer = job.trace_writer
    if writer is None:
        return None, None, None
    report_json = writer.run_dir / "report.json"
    if not report_json.is_file():
        return None, None, None
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    highlights = list(payload.get("highlights") or [])
    findings = payload.get("findings") or []
    rows = _rows_from_findings(findings)
    table_rows: list[dict[str, str | float]] | None = rows or None

    if summary and _GENERIC_SUMMARY.search(str(summary)) and rows:
        label, amount = rows[0]["category"], rows[0]["amount"]
        if len(rows) == 1:
            summary = f"{label}: {amount:,.2f}."
        else:
            best = max(rows, key=lambda r: float(r["amount"]))
            summary = (
                f"{best['category']} is highest at {float(best['amount']):,.2f} "
                f"({len(rows)} values)."
            )
    if not highlights and rows:
        highlights = [f"{r['category']}: {float(r['amount']):,.2f}" for r in rows]

    return summary, table_rows, highlights or None
