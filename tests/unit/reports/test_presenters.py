"""Reader-layer presenters produce human labels from evidence summaries."""

from da_agent.contracts.models import EvidenceRecord, ExecutionStatus, RunStatus
from da_agent.reports.generator import build_report
from da_agent.reports.renderer import render_report_html


def _group_evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="ev_ga",
        task_id="t1",
        tool="group_aggregate",
        args_hash="ab12cd34",
        dataset_hash="hash",
        input_row_count=100,
        result_schema_version="0.1.0",
        result_summary={
            "total_groups": 3,
            "metric_column": "Sales",
            "aggregation": "sum",
            "sample_groups": [
                {
                    "group_keys": {"Category": "Furniture"},
                    "value": 741999.7953,
                    "valid_count": 2121,
                    "missing_count": 0,
                },
                {
                    "group_keys": {"Category": "Office Supplies"},
                    "value": 719047.032,
                    "valid_count": 6026,
                    "missing_count": 0,
                },
                {
                    "group_keys": {"Category": "Technology"},
                    "value": 836154.033,
                    "valid_count": 1847,
                    "missing_count": 0,
                },
            ],
        },
    )


def test_group_aggregate_report_uses_category_labels() -> None:
    evidence = _group_evidence()
    report = build_report(
        run_id="r1",
        dataset_hash="hash",
        question="What are total sales by category?",
        claims=[],
        evidence_records={"ev_ga": evidence},
        status=RunStatus(status=ExecutionStatus.COMPLETE),
    )
    html = render_report_html(report)

    assert "Technology" in report.summary
    assert "836" in report.summary
    assert "Furniture" in html
    assert "group_aggregate.sample_groups[0].value" not in html
    assert "<details>" in html
    assert "<table" in html
    assert len(report.findings) == 1
    assert len(report.findings[0].numeric_claims) == 3
    assert report.summary.count(";") == 0