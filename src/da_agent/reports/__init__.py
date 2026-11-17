"""Report generation and HTML rendering."""

from da_agent.reports.assembler import assemble_report
from da_agent.reports.delivery import finalize_run_report
from da_agent.reports.generator import build_report
from da_agent.reports.renderer import render_report_html

__all__ = ["assemble_report", "build_report", "finalize_run_report", "render_report_html"]
