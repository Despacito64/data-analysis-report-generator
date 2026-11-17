"""Persist report JSON and HTML into the run trace directory."""

from __future__ import annotations

from pathlib import Path

from da_agent.contracts.models import AnalysisRun
from da_agent.core.config import ClaimValidationConfig
from da_agent.core.trace import RunTraceWriter
from da_agent.reports.assembler import assemble_report
from da_agent.reports.renderer import render_report_html


def finalize_run_report(
    run: AnalysisRun,
    trace_writer: RunTraceWriter,
    *,
    claim_config: ClaimValidationConfig | None = None,
) -> tuple[Path, Path]:
    """Assemble, save report.json, render HTML, and record a trace event."""
    report = assemble_report(run, claim_config=claim_config)
    json_path = trace_writer.save_report(report)
    html = render_report_html(report)
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