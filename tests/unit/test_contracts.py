"""Unit tests verifying that all Pydantic contracts enforce their schemas and reject malformed data."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from da_agent.contracts import (
    CONTRACT_VERSION,
    Budgets,
    ColumnProfile,
    DatasetProfile,
    DateCoverage,
    EvidenceRecord,
    ExecutionStatus,
    Failure,
    FailureClass,
    Finding,
    NumericClaim,
    PlanRevision,
    Report,
    ResolvedQuestion,
    RevisionChangeType,
    RunStatus,
    SemanticType,
    StatBlock,
    Task,
    TaskStatus,
    ToolSpec,
)


def test_contract_version() -> None:
    assert CONTRACT_VERSION == "0.1.0"


def test_column_profile_valid() -> None:
    cp = ColumnProfile(
        name="Sales",
        physical_type="float64",
        semantic_type=SemanticType.NUMERIC_MEASURE,
        missing_count=0,
        distinct_count=100,
        examples=[10.5, 20.0],
    )
    assert cp.name == "Sales"
    assert cp.semantic_type == SemanticType.NUMERIC_MEASURE


def test_column_profile_rejects_invalid_semantic_type() -> None:
    with pytest.raises(ValidationError):
        ColumnProfile(
            name="Sales",
            physical_type="float64",
            semantic_type="invalid_type",  # type: ignore[arg-type]
            missing_count=0,
            distinct_count=10,
        )


def test_column_profile_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        ColumnProfile(
            name="Sales",
            physical_type="float64",
            semantic_type=SemanticType.NUMERIC_MEASURE,
            missing_count=-1,
            distinct_count=10,
        )


def test_column_profile_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ColumnProfile(
            name="Sales",
            physical_type="float64",
            semantic_type=SemanticType.NUMERIC_MEASURE,
            missing_count=0,
            distinct_count=10,
            unknown_extra_field=True,  # type: ignore[call-arg]
        )


def test_date_coverage_validation() -> None:
    dc = DateCoverage(column="Order Date", min="2020-01-01", max="2023-12-31", parse_failures=0)
    assert dc.parse_failures == 0

    with pytest.raises(ValidationError):
        DateCoverage(column="Order Date", parse_failures=-5)


def test_stat_block_validation() -> None:
    sb = StatBlock(count=100, mean=50.2, min=1.0, max=100.0)
    assert sb.count == 100

    with pytest.raises(ValidationError):
        StatBlock(count=-1)


def test_dataset_profile_validation() -> None:
    col = ColumnProfile(
        name="Category",
        physical_type="object",
        semantic_type=SemanticType.CATEGORY,
        missing_count=0,
        distinct_count=3,
        examples=["Furniture", "Office Supplies"],
    )
    dp = DatasetProfile(
        dataset_hash="hash123",
        transformation_version="1.0.0",
        source_name="Sample-Superstore.csv",
        row_count=9994,
        columns=[col],
        duplicate_row_count=0,
    )
    assert dp.row_count == 9994

    with pytest.raises(ValidationError):
        DatasetProfile(
            dataset_hash="hash123",
            transformation_version="1.0.0",
            source_name="Sample-Superstore.csv",
            row_count=-10,
            columns=[col],
            duplicate_row_count=0,
        )


def test_resolved_question_requires_decline_reason_when_unanswerable() -> None:
    # Answerable question without decline reason is valid
    rq = ResolvedQuestion(
        question_text="What are total sales by region?",
        intent="group_aggregate",
        metric="sum(Sales)",
        grouping=["Region"],
        answerable=True,
    )
    assert rq.answerable is True

    # Unanswerable question WITH decline reason is valid
    rq_declined = ResolvedQuestion(
        question_text="What will sales be next quarter?",
        intent="forecast",
        answerable=False,
        decline_reason="Forecasting is out of scope",
    )
    assert rq_declined.answerable is False

    # Unanswerable question WITHOUT decline reason must be rejected
    with pytest.raises(ValidationError):
        ResolvedQuestion(
            question_text="Predict future churn rate",
            intent="forecast",
            answerable=False,
            decline_reason=None,
        )

    with pytest.raises(ValidationError):
        ResolvedQuestion(
            question_text="Predict future churn rate",
            intent="forecast",
            answerable=False,
            decline_reason="   ",
        )


def test_tool_spec_validation() -> None:
    spec = ToolSpec(
        name="group_aggregate",
        description="Groups and aggregates columns",
        args_model="GroupAggregateArgs",
        args_schema={"type": "object"},
        result_schema={"type": "object"},
        invariants=["row_count_positive"],
    )
    assert spec.name == "group_aggregate"


def test_task_status_and_defaults() -> None:
    task = Task(
        id="t-1",
        tool="group_aggregate",
        args={"group_by": "Region", "metric": "Sales"},
        rationale="Aggregate sales by region",
    )
    assert task.status == TaskStatus.PENDING
    assert task.plan_version == 1

    with pytest.raises(ValidationError):
        Task(
            id="t-2",
            tool="group_aggregate",
            status="not_a_valid_status",  # type: ignore[arg-type]
            rationale="Test",
        )


def test_evidence_record_validation() -> None:
    ev = EvidenceRecord(
        evidence_id="ev-1",
        task_id="t-1",
        tool="group_aggregate",
        args_hash="args-hash-abc",
        dataset_hash="data-hash-123",
        input_row_count=500,
        result_summary={"rows": 4},
        result_schema_version="1.0.0",
        created_at=datetime.now(UTC),
    )
    assert ev.valid is True

    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="ev-2",
            task_id="t-1",
            tool="group_aggregate",
            args_hash="args-hash-abc",
            dataset_hash="data-hash-123",
            input_row_count=-1,  # Negative input row count
            result_summary={},
            result_schema_version="1.0.0",
        )


def test_failure_classification() -> None:
    fail = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=True,
        message="Column 'Revenue' does not exist",
        context={"valid_columns": ["Sales", "Profit"]},
    )
    assert fail.recoverable is True

    with pytest.raises(ValidationError):
        Failure(
            failure_class="unknown_failure_class",  # type: ignore[arg-type]
            recoverable=False,
            message="Test",
        )


def test_plan_revision_validation() -> None:
    # Valid revision
    rev = PlanRevision(
        from_version=1,
        to_version=2,
        change=RevisionChangeType.ADDED,
        observed_result="Central region had steepest loss",
        affected_tasks=["t-2"],
    )
    assert rev.to_version == 2

    # to_version <= from_version must be rejected
    with pytest.raises(ValidationError):
        PlanRevision(
            from_version=2,
            to_version=2,
            change=RevisionChangeType.REPLACED,
            observed_result="No version bump",
            affected_tasks=["t-2"],
        )

    # Empty affected_tasks must be rejected
    with pytest.raises(ValidationError):
        PlanRevision(
            from_version=1,
            to_version=2,
            change=RevisionChangeType.ADDED,
            observed_result="No tasks affected",
            affected_tasks=[],
        )


def test_budgets_validation() -> None:
    b = Budgets(
        max_llm_calls=15,
        max_tool_calls=25,
        max_replans=3,
        max_identical_retries=2,
        per_call_timeout_s=30.0,
        max_total_tokens=20000,
    )
    assert b.max_llm_calls == 15

    # Non-positive max_llm_calls must fail
    with pytest.raises(ValidationError):
        Budgets(
            max_llm_calls=0,
            max_tool_calls=25,
            max_replans=3,
            max_identical_retries=2,
            per_call_timeout_s=30.0,
            max_total_tokens=20000,
        )


def test_numeric_claim_requires_evidence_id() -> None:
    claim = NumericClaim(value=123.45, unit="USD", label="Total Sales", evidence_id="ev-1")
    assert claim.evidence_id == "ev-1"

    with pytest.raises(ValidationError):
        NumericClaim(value=123.45, label="Total Sales", evidence_id="")


def test_report_and_finding_structure() -> None:
    status = RunStatus(status=ExecutionStatus.COMPLETE)
    claim = NumericClaim(value=123.45, label="Total Sales", evidence_id="ev-1")
    finding = Finding(
        statement="Total sales reached 123.45 USD",
        numeric_claims=[claim],
        evidence_ids=["ev-1"],
    )
    report = Report(
        run_id="run-001",
        dataset_hash="hash-123",
        question="What is total sales?",
        summary="Sales analyzed successfully.",
        findings=[finding],
        status=status,
    )
    assert report.run_id == "run-001"
    assert len(report.findings) == 1
