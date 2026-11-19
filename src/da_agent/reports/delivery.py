"""Persist report JSON and HTML into the run trace directory."""

from __future__ import annotations

from pathlib import Path

from plotly.graph_objects import Figure

from da_agent.contracts.models import AnalysisRun
from da_agent.core.config import ClaimValidationConfig
from da_agent.core.trace import RunTraceWriter
from da_agent.reports.assembler import assemble_report
from da_agent.reports.renderer import render_report_html
from da_agent.tools.charts import build_group_aggregate_chart


def _charts_for_evidence(run: AnalysisRun) -> list[tuple[str, Figure]]:
    charts: list[tuple[str, Figure]] = []
    for record in run.evidence_records.values():
        if record.tool != "group_aggregate" or not record.valid:
            continue
        figure = build_group_aggregate_chart(record.result_summary)
        if figure is None:
            continue
        metric = str(record.result_summary.get("metric_column") or "Value")
        charts.append((f"{metric} by category", figure))
        break
    return charts


def finalize_run_report(
    run: AnalysisRun,
    trace_writer: RunTraceWriter,
    *,
    claim_config: ClaimValidationConfig | None = None,
) -> tuple[Path, Path]:
    """Assemble, save report.json, render HTML, and record a trace event."""
    report = assemble_report(run, claim_config=claim_config)
    json_path = trace_writer.save_report(report)
    html = render_report_html(report, charts=_charts_for_evidence(run))
    html_path = trace_writer.save_report_html(html)
    trace_writer.log_event(
        "report_written",
        {
            "report_json": str(json_path),
            "report_html": str(html_path),
            "finding_count": len(report.findings),
        },
    )
    return json_path, html_path
