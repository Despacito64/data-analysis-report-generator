"""Tests for AnalysisRun → Report assembly."""

from da_agent.contracts.models import (
    AnalysisRun,
    EvidenceRecord,
    ExecutionStatus,
    KeyNumberCitation,
)
from da_agent.reports.assembler import assemble_report


def test_assemble_report_maps_key_numbers_to_findings() -> None:
    evidence_id = "ev-cat-sales"
    record = EvidenceRecord(
        evidence_id=evidence_id,
        task_id="t1",
        tool="group_aggregate",
        args_hash="abc12345",
        dataset_hash="hash123",
        input_row_count=10,
        result_summary={"total": 100.0},
        result_schema_version="0.1.0",
    )
    run = AnalysisRun(
        run_id="asm-1",
        question="Sales by category?",
        dataset_hash="hash123",
        execution_status=ExecutionStatus.COMPLETE,
        key_numbers=[
            KeyNumberCitation(
                label="group_aggregate.total",
                value=100.0,
                task_id="t1",
                evidence_id=evidence_id,
            )
        ],
        evidence_records={evidence_id: record},
    )
    report = assemble_report(run)
    assert report.run_id == "asm-1"
    assert report.findings
    assert report.findings[0].numeric_claims[0].value == 100.0