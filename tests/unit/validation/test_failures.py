"""Unit tests for failure classification, retry policies, and factual recovery context."""

from da_agent.contracts.models import (
    ColumnProfile,
    DatasetProfile,
    Failure,
    FailureClass,
    RecoveryFailureClass,
    RetryPolicy,
    SemanticType,
)
from da_agent.tools.errors import ToolError
from da_agent.validation.failures import (
    RETRY_POLICY_MAP,
    classify_failure,
    render_recovery_context,
)


def _make_dummy_profile() -> DatasetProfile:
    return DatasetProfile(
        dataset_hash="hash_123",
        transformation_version="1.0.0",
        source_name="superstore.csv",
        row_count=9994,
        columns=[
            ColumnProfile(
                name="Sales",
                physical_type="float64",
                semantic_type=SemanticType.NUMERIC_MEASURE,
                missing_count=0,
                distinct_count=5000,
            ),
            ColumnProfile(
                name="Profit",
                physical_type="float64",
                semantic_type=SemanticType.NUMERIC_MEASURE,
                missing_count=0,
                distinct_count=4000,
            ),
            ColumnProfile(
                name="Category",
                physical_type="object",
                semantic_type=SemanticType.CATEGORY,
                missing_count=0,
                distinct_count=3,
            ),
            ColumnProfile(
                name="Order Date",
                physical_type="object",
                semantic_type=SemanticType.DATE,
                missing_count=0,
                distinct_count=1400,
            ),
        ],
        duplicate_row_count=0,
    )


def test_every_failure_class_mapping() -> None:
    """Test mapping of each known failure condition to the closed taxonomy."""
    profile = _make_dummy_profile()

    # 1. Invalid argument (generic schema/argument validation)
    f_arg = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=True,
        message="Argument schema validation failed for tool 'filter'",
        context={"validation_errors": [{"loc": ["threshold"], "msg": "field required"}]},
        task_id="t1",
    )
    res_arg = classify_failure(f_arg, profile=profile)
    assert res_arg.failure_class == RecoveryFailureClass.INVALID_ARGUMENT
    assert res_arg.retry_policy == RetryPolicy.REPAIRABLE
    assert res_arg.recovery_context.failing_parameter == "threshold"

    # 2. Unknown column
    f_col = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=True,
        message="Column 'NonExistent' does not exist in dataset profile",
        context={"missing_column": "NonExistent", "available_columns": ["Sales", "Profit"]},
        task_id="t2",
    )
    res_col = classify_failure(f_col, profile=profile)
    assert res_col.failure_class == RecoveryFailureClass.UNKNOWN_COLUMN
    assert res_col.retry_policy == RetryPolicy.REPAIRABLE
    assert res_col.recovery_context.failing_parameter == "NonExistent"
    assert "Sales" in res_col.recovery_context.valid_columns

    # 3. Type mismatch
    f_type = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=True,
        message="Column 'Category' has semantic type 'category', expected 'numeric_measure'",
        context={
            "column": "Category",
            "actual_type": "category",
            "required_types": ["numeric_measure"],
        },
        task_id="t3",
    )
    res_type = classify_failure(f_type, profile=profile)
    assert res_type.failure_class == RecoveryFailureClass.TYPE_MISMATCH
    assert res_type.retry_policy == RetryPolicy.REPAIRABLE
    assert res_type.recovery_context.actual_type == "category"
    assert res_type.recovery_context.expected_type == "numeric_measure"

    # 4. Empty result (ToolError and Failure)
    te_empty = ToolError(
        FailureClass.EMPTY_RESULT, "Filter matched 0 rows", {"output_row_count": 0}
    )
    res_empty = classify_failure(te_empty, task_id="t4")
    assert res_empty.failure_class == RecoveryFailureClass.EMPTY_RESULT
    assert res_empty.retry_policy == RetryPolicy.REPAIRABLE
    assert res_empty.recovery_context.observed_row_count == 0

    # 5. Invariant violation
    f_inv = Failure(
        failure_class=FailureClass.INVARIANT_VIOLATION,
        recoverable=False,
        message="Invariant violation: shares_sum does not equal 1.0 within tolerance",
        context={"invariant": "contribution_shares_sum"},
        task_id="t5",
    )
    res_inv = classify_failure(f_inv)
    assert res_inv.failure_class == RecoveryFailureClass.INVARIANT_VIOLATION
    assert res_inv.retry_policy == RetryPolicy.TERMINAL

    # 6. Tool timeout
    f_timeout = Failure(
        failure_class=FailureClass.TRANSIENT,
        recoverable=True,
        message="Tool 'group_aggregate' exceeded per-call timeout of 60.0s",
        context={"timeout_s": 60.0},
        task_id="t6",
    )
    res_timeout = classify_failure(f_timeout)
    assert res_timeout.failure_class == RecoveryFailureClass.TOOL_TIMEOUT
    assert res_timeout.retry_policy == RetryPolicy.RETRYABLE_IDENTICAL

    # 7. Transient/runtime error (connection or generic transient)
    f_transient = Failure(
        failure_class=FailureClass.TRANSIENT,
        recoverable=True,
        message="Connection reset by peer during RPC call",
        context={},
        task_id="t7",
    )
    res_transient = classify_failure(f_transient)
    assert res_transient.failure_class == RecoveryFailureClass.TRANSIENT_ERROR
    assert res_transient.retry_policy == RetryPolicy.RETRYABLE_IDENTICAL

    # 8. Runtime error / schema violation
    f_schema = Failure(
        failure_class=FailureClass.SCHEMA_VIOLATION,
        recoverable=False,
        message="Unhandled tool execution exception: ZeroDivisionError",
        context={"exception_type": "ZeroDivisionError"},
        task_id="t8",
    )
    res_schema = classify_failure(f_schema)
    assert res_schema.failure_class == RecoveryFailureClass.RUNTIME_ERROR
    assert res_schema.retry_policy == RetryPolicy.TERMINAL

    # 9. Unsupported operation / unknown tool
    f_tool = Failure(
        failure_class=FailureClass.UNKNOWN_TOOL,
        recoverable=True,
        message="Tool 'unsupported_ml_regressor' is not allowlisted in registry",
        context={
            "requested_tool": "unsupported_ml_regressor",
            "available_tools": ["filter", "rank"],
        },
        task_id="t9",
    )
    res_tool = classify_failure(f_tool)
    assert res_tool.failure_class == RecoveryFailureClass.UNSUPPORTED_OPERATION
    assert res_tool.retry_policy == RetryPolicy.REPAIRABLE
    assert "filter" in res_tool.recovery_context.available_tools

    # 10. Dependency failure (upstream task failed)
    res_dep = classify_failure(
        "Task skipped: dependency 't1' failed with error",
        task_id="t10",
        context={"failed_upstream_task_id": "t1"},
    )
    assert res_dep.failure_class == RecoveryFailureClass.DEPENDENCY_FAILURE
    assert res_dep.retry_policy == RetryPolicy.TERMINAL
    assert res_dep.recovery_context.failed_upstream_task_id == "t1"


def test_unknown_error_default_and_never_raises() -> None:
    """Unknown, malformed, or arbitrary exceptions safely map to UNKNOWN without raising."""

    # Arbitrary exception
    class WeirdCustomError(Exception):
        pass

    res_exc = classify_failure(WeirdCustomError("Unusual low-level failure"), task_id="t_err")
    assert res_exc.failure_class == RecoveryFailureClass.UNKNOWN
    assert res_exc.retry_policy == RetryPolicy.TERMINAL
    assert "Unusual low-level failure" in res_exc.message

    # Malformed objects
    res_none = classify_failure(None)
    assert res_none.failure_class == RecoveryFailureClass.UNKNOWN
    assert res_none.retry_policy == RetryPolicy.TERMINAL

    res_int = classify_failure(42)
    assert res_int.failure_class == RecoveryFailureClass.UNKNOWN
    assert res_int.retry_policy == RetryPolicy.TERMINAL


def test_retry_policy_rules() -> None:
    """Only transient and tool timeout classes may be retryable-identical."""
    identical_retries = {
        cls for cls, policy in RETRY_POLICY_MAP.items() if policy == RetryPolicy.RETRYABLE_IDENTICAL
    }
    assert identical_retries == {
        RecoveryFailureClass.TOOL_TIMEOUT,
        RecoveryFailureClass.TRANSIENT_ERROR,
    }

    # Invariant violation and dependency failure must be TERMINAL
    assert RETRY_POLICY_MAP[RecoveryFailureClass.INVARIANT_VIOLATION] == RetryPolicy.TERMINAL
    assert RETRY_POLICY_MAP[RecoveryFailureClass.DEPENDENCY_FAILURE] == RetryPolicy.TERMINAL
    assert RETRY_POLICY_MAP[RecoveryFailureClass.RUNTIME_ERROR] == RetryPolicy.TERMINAL
    assert RETRY_POLICY_MAP[RecoveryFailureClass.UNKNOWN] == RetryPolicy.TERMINAL

    # Repairables require changing an argument or replanning
    repairables = {
        cls for cls, policy in RETRY_POLICY_MAP.items() if policy == RetryPolicy.REPAIRABLE
    }
    assert repairables == {
        RecoveryFailureClass.INVALID_ARGUMENT,
        RecoveryFailureClass.UNKNOWN_COLUMN,
        RecoveryFailureClass.TYPE_MISMATCH,
        RecoveryFailureClass.EMPTY_RESULT,
        RecoveryFailureClass.UNSUPPORTED_OPERATION,
    }


def test_to_contract_failure_conversion() -> None:
    """ClassifiedFailure correctly converts to canonical contract Failure."""
    classified = classify_failure(
        Failure(
            failure_class=FailureClass.INVALID_ARGS,
            recoverable=True,
            message="Column 'Region' does not exist",
            context={"missing_column": "Region", "available_columns": ["Sales", "Profit"]},
            task_id="t_col",
        ),
        failing_args={"column": "Region"},
    )
    contract_f = classified.to_contract_failure()
    assert isinstance(contract_f, Failure)
    assert contract_f.failure_class == FailureClass.INVALID_ARGS
    assert contract_f.recoverable is True
    assert contract_f.task_id == "t_col"
    assert contract_f.detailed_class == RecoveryFailureClass.UNKNOWN_COLUMN
    assert contract_f.failing_args == {"column": "Region"}
    assert "Region" in str(contract_f.context)


def test_render_recovery_context_structure_and_no_leakage() -> None:
    """Rendered recovery context contains only factual observations without benchmark leakage."""
    profile = _make_dummy_profile()
    f = Failure(
        failure_class=FailureClass.INVALID_ARGS,
        recoverable=True,
        message="Column 'Discount_Rate' does not exist in dataset profile",
        context={"missing_column": "Discount_Rate", "available_columns": ["Sales", "Profit"]},
        task_id="task_calc",
    )
    classified = classify_failure(
        f,
        failing_args={"metric_column": "Discount_Rate"},
        profile=profile,
        input_row_count=1000,
        observed_row_count=0,
    )
    rendered = render_recovery_context(classified)

    # Check allowed structured keys
    allowed_keys = {
        "failure_class",
        "retry_policy",
        "task_id",
        "message",
        "failing_args",
        "valid_columns",
        "observed_row_count",
        "input_row_count",
        "failing_parameter",
        "expected_type",
        "actual_type",
        "available_tools",
        "failed_upstream_task_id",
        "guidance",
    }
    assert set(rendered.keys()) == allowed_keys
    assert rendered["failure_class"] == "unknown_column"
    assert rendered["retry_policy"] == "repairable"
    assert rendered["failing_parameter"] == "Discount_Rate"
    assert "Sales" in rendered["valid_columns"]
    assert "Profit" in rendered["valid_columns"]
    assert rendered["input_row_count"] == 1000

    # Leakage checks: no benchmark question ids (q01-q20) or oracle keywords
    dumped_str = str(rendered).lower()
    for q_num in range(1, 21):
        assert f"q{q_num:02d}" not in dumped_str
    assert "oracle" not in dumped_str
    assert "ground_truth" not in dumped_str
    assert "expected_answer" not in dumped_str
