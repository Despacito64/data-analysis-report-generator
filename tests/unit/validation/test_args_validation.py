"""Unit tests for task argument validation (src/da_agent/validation/args.py).

Covers Table 1 Rejection Cases:
- R01: Unknown tool -> UNKNOWN_TOOL
- R02: Malformed arguments (missing field, bad type) -> INVALID_ARGS
- R03: Extra arguments (extra='forbid') -> INVALID_ARGS
- R04: Column not in profile -> INVALID_ARGS
- R05: Incompatible metric type (e.g. sum on postal code identifier) -> INVALID_ARGS
- R06: Incompatible date column -> INVALID_ARGS
- R07: Out-of-bounds period -> INVALID_ARGS
- R08: Incompatible grouping on free text -> INVALID_ARGS
"""

import pytest

from da_agent.contracts.models import (
    ColumnProfile,
    DatasetProfile,
    DateCoverage,
    FailureClass,
    SemanticType,
)
from da_agent.tools.models import (
    AggregationType,
    GroupAggregateArgs,
    PeriodCompareArgs,
)
from da_agent.validation.args import validate_task_args


@pytest.fixture
def mock_profile() -> DatasetProfile:
    """Standard profile with known semantic types and date coverage."""
    return DatasetProfile(
        dataset_hash="mock_hash_123",
        transformation_version="0.1.0",
        source_name="mock.csv",
        row_count=100,
        duplicate_row_count=0,
        columns=[
            ColumnProfile(
                name="Sales",
                physical_type="float64",
                semantic_type=SemanticType.NUMERIC_MEASURE,
                missing_count=0,
                distinct_count=90,
            ),
            ColumnProfile(
                name="Postal Code",
                physical_type="int64",
                semantic_type=SemanticType.IDENTIFIER,
                missing_count=0,
                distinct_count=50,
            ),
            ColumnProfile(
                name="Region",
                physical_type="object",
                semantic_type=SemanticType.CATEGORY,
                missing_count=0,
                distinct_count=4,
            ),
            ColumnProfile(
                name="Order Date",
                physical_type="object",
                semantic_type=SemanticType.DATE,
                missing_count=0,
                distinct_count=80,
            ),
            ColumnProfile(
                name="Customer Notes",
                physical_type="object",
                semantic_type=SemanticType.TEXT,
                missing_count=10,
                distinct_count=85,
            ),
        ],
        date_coverage=[
            DateCoverage(
                column="Order Date",
                min="2023-01-01",
                max="2023-12-31",
                parse_failures=0,
            )
        ],
    )


def test_r01_unknown_tool(mock_profile: DatasetProfile) -> None:
    """R01: Unknown tool name yields FailureClass.UNKNOWN_TOOL."""
    parsed, failure = validate_task_args(
        tool_name="unregistered_tool",
        args={"some": "arg"},
        profile=mock_profile,
        args_model=None,
        available_tools=["filter", "group_aggregate"],
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.UNKNOWN_TOOL
    assert failure.recoverable is True
    assert failure.context["requested_tool"] == "unregistered_tool"
    assert "filter" in failure.context["available_tools"]


def test_r02_malformed_args(mock_profile: DatasetProfile) -> None:
    """R02: Missing required field yields FailureClass.INVALID_ARGS."""
    # GroupAggregateArgs requires 'by', 'metric_column', 'aggregation'
    bad_args = {"by": ["Region"]}  # missing metric_column and aggregation
    parsed, failure = validate_task_args(
        tool_name="group_aggregate",
        args=bad_args,
        profile=mock_profile,
        args_model=GroupAggregateArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.recoverable is True
    assert len(failure.context["validation_errors"]) >= 2


def test_r03_extra_arguments_forbidden(mock_profile: DatasetProfile) -> None:
    """R03: Extra unexpected arguments yield FailureClass.INVALID_ARGS."""
    extra_args = {
        "by": ["Region"],
        "metric_column": "Sales",
        "aggregation": "sum",
        "malicious_extra": "not_allowed",
    }
    parsed, failure = validate_task_args(
        tool_name="group_aggregate",
        args=extra_args,
        profile=mock_profile,
        args_model=GroupAggregateArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert any("malicious_extra" in str(err["loc"]) for err in failure.context["validation_errors"])


def test_r04_column_not_in_profile(mock_profile: DatasetProfile) -> None:
    """R04: Column not in profile yields FailureClass.INVALID_ARGS with factual columns list."""
    args = {
        "by": ["NonExistentColumn"],
        "metric_column": "Sales",
        "aggregation": "sum",
    }
    parsed, failure = validate_task_args(
        tool_name="group_aggregate",
        args=args,
        profile=mock_profile,
        args_model=GroupAggregateArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.context["missing_column"] == "NonExistentColumn"
    assert "Sales" in failure.context["available_columns"]


def test_r05_incompatible_metric_type_identifier_rejected(mock_profile: DatasetProfile) -> None:
    """R05: Numeric aggregation on an identifier (Postal Code) yields INVALID_ARGS."""
    args = {
        "by": ["Region"],
        "metric_column": "Postal Code",  # Postal Code is an IDENTIFIER, never numeric_measure
        "aggregation": "sum",
    }
    parsed, failure = validate_task_args(
        tool_name="group_aggregate",
        args=args,
        profile=mock_profile,
        args_model=GroupAggregateArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.context["column"] == "Postal Code"
    assert failure.context["actual_type"] == "identifier"
    assert failure.context["required_types"] == ["numeric_measure"]


def test_r06_incompatible_date_column_rejected(mock_profile: DatasetProfile) -> None:
    """R06: Date operation on non-date column yields INVALID_ARGS."""
    args = {
        "date_column": "Region",  # Category, not Date!
        "metric_column": "Sales",
        "base_period": ("2023-01-01", "2023-01-31"),
        "compare_period": ("2023-02-01", "2023-02-28"),
    }
    parsed, failure = validate_task_args(
        tool_name="period_compare",
        args=args,
        profile=mock_profile,
        args_model=PeriodCompareArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.context["column"] == "Region"
    assert failure.context["actual_type"] == "category"
    assert failure.context["required_types"] == ["date"]


def test_r07_out_of_bounds_period_rejected(mock_profile: DatasetProfile) -> None:
    """R07: Period strictly outside DateCoverage min/max yields INVALID_ARGS."""
    # Profile coverage: 2023-01-01 to 2023-12-31
    args = {
        "date_column": "Order Date",
        "metric_column": "Sales",
        "base_period": ("2020-01-01", "2020-06-30"),  # entirely before 2023!
        "compare_period": ("2023-01-01", "2023-06-30"),
    }
    parsed, failure = validate_task_args(
        tool_name="period_compare",
        args=args,
        profile=mock_profile,
        args_model=PeriodCompareArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.context["column"] == "Order Date"
    assert failure.context["period_name"] == "base_period"
    assert failure.context["coverage_min"] == "2023-01-01"


def test_r08_incompatible_grouping_on_free_text(mock_profile: DatasetProfile) -> None:
    """R08: Grouping on free-form text column yields INVALID_ARGS."""
    args = {
        "by": ["Customer Notes"],  # SemanticType.TEXT
        "metric_column": "Sales",
        "aggregation": "sum",
    }
    parsed, failure = validate_task_args(
        tool_name="group_aggregate",
        args=args,
        profile=mock_profile,
        args_model=GroupAggregateArgs,
    )
    assert parsed is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.context["column"] == "Customer Notes"
    assert failure.context["actual_type"] == "text"


def test_valid_args_pass_validation(mock_profile: DatasetProfile) -> None:
    """Valid arguments pass and return typed model."""
    args = {
        "by": ["Region"],
        "metric_column": "Sales",
        "aggregation": "sum",
    }
    parsed, failure = validate_task_args(
        tool_name="group_aggregate",
        args=args,
        profile=mock_profile,
        args_model=GroupAggregateArgs,
    )
    assert failure is None
    assert isinstance(parsed, GroupAggregateArgs)
    assert parsed.by == ["Region"]
    assert parsed.metric_column == "Sales"
    assert parsed.aggregation == AggregationType.SUM
