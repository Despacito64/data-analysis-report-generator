"""Escape report content into a downloadable HTML page."""

from __future__ import annotations

import html

from plotly.graph_objects import Figure

from da_agent.contracts.models import Finding, Report


def _chart_is_grounded(figure: Figure, allowed: set[float]) -> bool:
    for trace in figure.data:
        values = list(getattr(trace, "y", None) or [])
        for value in values:
            if isinstance(value, bool) or value is None:
                continue
            if isinstance(value, (int, float)) and not any(
                abs(float(value) - item) <= 0.01 for item in allowed
            ):
                return False
    return True


def _compact_table_html(finding: Finding) -> str:
    """Single table for multi-claim group findings (one section, no duplicate bullets)."""
    if len(finding.numeric_claims) < 2:
        return ""
    header_metric = finding.statement or "Value"
    rows: list[str] = []
    for claim in sorted(
        finding.numeric_claims,
        key=lambda c: float(c.value) if isinstance(c.value, (int, float)) else 0.0,
        reverse=True,
    ):
        group = html.escape(claim.label.split(" — ")[0])
        val = html.escape(f"{float(claim.value):,.2f}" if isinstance(claim.value, (int, float)) else str(claim.value))
        link = (
            '<a href="#evidence-'
            + html.escape(claim.evidence_id)
            + '">source</a>'
        )
        rows.append(f"<tr><td>{group}</td><td>{val}</td><td>{link}</td></tr>")
    return (
        "<h2>"
        + html.escape(header_metric)
        + "</h2>"
        + '<table class="results"><thead><tr><th>Group</th><th>Amount</th><th></th></tr></thead><tbody>'
        + "".join(rows)
        + "</tbody></table>"
    )


def render_report_html(report: Report, charts: list[tuple[str, Figure]] | None = None) -> str:
    """Answer-first layout: headline, one table, one chart, audit in details."""
    allowed = {
        float(claim.value)
        for finding in report.findings
        for claim in finding.numeric_claims
        if isinstance(claim.value, (int, float))
    }

    compact_finding = next(
        (f for f in report.findings if len(f.numeric_claims) >= 2 and f.statement.endswith("by group")),
        None,
    )

    chart_blocks: list[str] = []
    for title, figure in charts or []:
        if not _chart_is_grounded(figure, allowed):
            continue
        chart_blocks.append(
            "<section><h2>Chart</h2>"
            + figure.to_html(full_html=False, include_plotlyjs="cdn")
            + "</section>"
        )

    table_block = _compact_table_html(compact_finding) if compact_finding else ""

    finding_blocks: list[str] = []
    if not compact_finding:
        for finding in report.findings:
            claims = "".join(
                "<li>"
                + html.escape(claim.label)
                + ": "
                + html.escape(str(claim.value))
                + ' <a href="#evidence-'
                + html.escape(claim.evidence_id)
                + '">source</a></li>'
                for claim in finding.numeric_claims
            )
            finding_blocks.append("<article><ul>" + claims + "</ul></article>")

    appendix = "".join(
        '<li id="evidence-'
        + html.escape(record.evidence_id)
        + '">'
        + html.escape(record.evidence_id)
        + " "
        + html.escape(record.tool)
        + " "
        + html.escape(str(record.result_summary))
        + "</li>"
        for record in report.evidence_appendix
    )
    dropped_items = report.status.dropped_claims[:15]
    dropped = "".join("<li>" + html.escape(item) + "</li>" for item in dropped_items)
    if len(report.status.dropped_claims) > 15:
        dropped += "<li>…</li>"

    audit_sections = (
        "<details><summary>Technical evidence (audit)</summary><ul>"
        + appendix
        + "</ul></details>"
    )
    if dropped:
        audit_sections += (
            "<details><summary>Dropped claims (audit)</summary><ul>" + dropped + "</ul></details>"
        )

    body = "".join(
        [
            "<h1>" + html.escape(report.question) + "</h1>",
            "<p class='headline'>" + html.escape(report.summary) + "</p>",
            "<p class='meta'>Status: " + html.escape(report.status.status.value) + "</p>",
            table_block,
            "".join(finding_blocks),
            "".join(chart_blocks),
            audit_sections,
        ]
    )
    styles = (
        "body{font-family:system-ui,sans-serif;max-width:42rem;margin:1.5rem auto;line-height:1.5}"
        ".headline{font-size:1.15rem;font-weight:500}"
        ".meta{color:#555;font-size:0.9rem}"
        "table.results{border-collapse:collapse;width:100%}"
        "table.results th,table.results td{border:1px solid #ddd;padding:0.4rem 0.6rem;text-align:left}"
        "table.results th{background:#f6f6f8}"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>'
        + html.escape(report.run_id)
        + "</title><style>"
        + styles
        + "</style></head><body>"
        + body
        + "</body></html>"
    )