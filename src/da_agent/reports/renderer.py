"""Escape report content into a downloadable HTML page."""

from __future__ import annotations

import html

from plotly.graph_objects import Figure

from da_agent.contracts.models import Report


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


def render_report_html(report: Report, charts: list[tuple[str, Figure]] | None = None) -> str:
    """Render a report. Chart series that are not in the validated findings are omitted."""
    allowed = {
        float(claim.value)
        for finding in report.findings
        for claim in finding.numeric_claims
        if isinstance(claim.value, (int, float))
    }
    chart_blocks: list[str] = []
    for title, figure in charts or []:
        if not _chart_is_grounded(figure, allowed):
            continue
        chart_blocks.append(
            "<section><h2>"
            + html.escape(title)
            + "</h2>"
            + figure.to_html(full_html=False, include_plotlyjs="cdn")
            + "</section>"
        )

    finding_blocks: list[str] = []
    for finding in report.findings:
        claims = "".join(
            "<li>"
            + html.escape(claim.label)
            + ": "
            + html.escape(str(claim.value))
            + (" " + html.escape(claim.unit) if claim.unit else "")
            + ' <a href="#evidence-'
            + html.escape(claim.evidence_id)
            + '">evidence</a></li>'
            for claim in finding.numeric_claims
        )
        caveat = "<p>" + html.escape(finding.caveat) + "</p>" if finding.caveat else ""
        finding_blocks.append("<article><ul>" + claims + "</ul>" + caveat + "</article>")

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
    dropped = "".join("<li>" + html.escape(item) + "</li>" for item in report.status.dropped_claims)
    body = "".join(
        [
            "<h1>" + html.escape(report.question) + "</h1>",
            "<p>" + html.escape(report.summary) + "</p>",
            "<p>Status: " + html.escape(report.status.status.value) + "</p>",
            "".join(finding_blocks),
            "".join(chart_blocks),
            "<h2>Evidence</h2><ul>" + appendix + "</ul>",
            "<h2>Dropped claims</h2><ul>" + dropped + "</ul>",
        ]
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>'
        + html.escape(report.run_id)
        + "</title></head><body>"
        + body
        + "</body></html>"
    )
