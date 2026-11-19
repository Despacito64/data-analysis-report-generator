"""API report presentation for single-value drill-downs."""

import json
from pathlib import Path

from da_agent.api.report_view import report_view
from da_agent.api.session import RunJob
from da_agent.core.trace import RunTraceWriter


def test_single_claim_gets_summary_and_table(tmp_path: Path) -> None:
    run_id = "single-drill"
    writer = RunTraceWriter(run_id=run_id, base_dir=tmp_path)
    writer.run_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "summary": "1 supported finding(s).",
        "highlights": [],
        "findings": [
            {
                "statement": "Filtered total",
                "numeric_claims": [
                    {"label": "Furniture — Sales (sum)", "value": 741999.795, "evidence_id": "e1"}
                ],
            }
        ],
    }
    (writer.run_dir / "report.json").write_text(json.dumps(report), encoding="utf-8")
    job = RunJob(
        run_id=run_id, session_id="s", question="q", status="complete", trace_writer=writer
    )
    summary, rows, highlights = report_view(job)
    assert summary == "Furniture: 741,999.80."
    assert rows is not None and len(rows) == 1
    assert rows[0]["category"] == "Furniture"
    assert highlights is not None
