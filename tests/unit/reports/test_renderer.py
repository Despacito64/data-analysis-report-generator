"""M8 report tests: validated numbers, rejected alterations, and escaped HTML."""

from __future__ import annotations

from da_agent.contracts.models import EvidenceRecord, ExecutionStatus, NumericClaim, RunStatus
from da_agent.reports.generator import build_report
from da_agent.reports.renderer import render_report_html
from da_agent.tools.charts import build_rank_chart
from da_agent.tools.models import RankResult, RankRow


def _evidence(evidence_id: str, value: float) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        task_id="t1",
        tool="rank",
        args_hash="abc12345",
        dataset_hash="dataset-hash",
        input_row_count=2,
        result_summary={"value": value, "entity": "East"},
        result_schema_version="0.1.0",
    )


def _rank_result() -> RankResult:
    return RankResult(
        entity_column="Region",
        metric_column="Sales",
        ascending=False,
        top_n=1,
        tie_decimals=2,
        rows=[RankRow(rank=1, entity="East", value=42.5, is_tied=False)],
        tie_groups=[],
        ties_at_cutoff=False,
        cutoff_tied_labels_omitted=[],
        null_count=0,
    )


def test_html_report_shows_validated_number_unit_and_evidence_link() -> None:
    evidence = _evidence("ev_sales", 42.5)
    report = build_report(
        run_id="report-1",
        dataset_hash="dataset-hash",
        question="What is East sales?",
        claims=[
            NumericClaim(value=42.5, unit="USD", label="Sales", evidence_id="ev_sales"),
        ],
        evidence_records={"ev_sales": evidence},
        status=RunStatus(status=ExecutionStatus.COMPLETE, reason_text="ok"),
    )
    chart = build_rank_chart(_rank_result(), unit="USD")
    html = render_report_html(report, charts=[("Sales by region", chart)])

    assert "42.5" in html
    assert "USD" in html
    assert 'href="#evidence-ev_sales"' in html
    assert "Sales by region" in html or "Rank: Sales by Region" in html
    assert "East" in html
    assert report.findings[0].numeric_claims[0].value == 42.5


def test_altered_number_is_removed_before_render() -> None:
    evidence = _evidence("ev_sales", 42.5)
    report = build_report(
        run_id="report-2",
        dataset_hash="dataset-hash",
        question="What is East sales?",
        claims=[
            NumericClaim(value=999, unit="USD", label="Sales", evidence_id="ev_sales"),
        ],
        evidence_records={"ev_sales": evidence},
        status=RunStatus(status=ExecutionStatus.COMPLETE, reason_text="ok"),
    )
    html = render_report_html(report)

    assert report.findings == []
    assert any("999" in item for item in report.status.dropped_claims)
    assert "<article>" not in html
    assert "Dropped claims" in html


def test_html_in_a_cell_value_is_escaped() -> None:
    evidence = EvidenceRecord(
        evidence_id="ev_name",
        task_id="t1",
        tool="rank",
        args_hash="abc12345",
        dataset_hash="dataset-hash",
        input_row_count=1,
        result_summary={"value": 1, "entity": "<script>alert(1)</script>"},
        result_schema_version="0.1.0",
    )
    report = build_report(
        run_id="report-3",
        dataset_hash="dataset-hash",
        question="Which name is first? <img src=x onerror=alert(1)>",
        claims=[NumericClaim(value=1, unit=None, label="count", evidence_id="ev_name")],
        evidence_records={"ev_name": evidence},
        status=RunStatus(status=ExecutionStatus.COMPLETE, reason_text="ok"),
        caveat="<script>alert(1)</script>",
    )
    html = render_report_html(report)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<img src=x" not in html
