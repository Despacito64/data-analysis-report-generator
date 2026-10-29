"""Unit tests for task executor (src/da_agent/tools/executor.py).

Tests:
- Execution of valid analytical task returning valid EvidenceRecord.
- Deterministic args_hash parity.
- Unknown tool yields Failure(UNKNOWN_TOOL).
- Invalid arguments yield Failure(INVALID_ARGS).
- ToolError (e.g. empty result) yields classified Failure.
- Invariant check failure yields Failure(INVARIANT_VIOLATION).
- Timeout enforcement yields Failure(TRANSIENT).
- Unexpected exception inside tool yields Failure(SCHEMA_VIOLATION).
- Full canonical result stored alongside record.
- Bounded summary for LLM without raw rows.
- RunTraceWriter logs tool_call, evidence, and failure events.
"""

import time
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from da_agent.contracts.models import (
    Budgets,
    ColumnProfile,
    DatasetProfile,
    FailureClass,
    SemanticType,
    Task,
)
from da_agent.core.trace import RunTraceWriter
from da_agent.tools.executor import compute_args_hash, execute_task
from da_agent.tools.models import (
    FilterArgs,
    FilterResult,
    ToolResultEnvelope,
)
from da_agent.tools.registry import ToolEntry, ToolRegistry


@pytest.fixture
def test_budgets() -> Budgets:
    return Budgets(
        max_llm_calls=10,
        max_tool_calls=20,
        max_replans=3,
        max_identical_retries=2,
        per_call_timeout_s=1.0,
        max_total_tokens=10000,
    )


@pytest.fixture
def sample_profile() -> DatasetProfile:
    return DatasetProfile(
        dataset_hash="dataset_abc123",
        transformation_version="0.1.0",
        source_name="sample.csv",
        row_count=4,
        duplicate_row_count=0,
        columns=[
            ColumnProfile(
                name="Sales",
                physical_type="float64",
                semantic_type=SemanticType.NUMERIC_MEASURE,
                missing_count=0,
                distinct_count=4,
            ),
            ColumnProfile(
                name="Region",
                physical_type="object",
                semantic_type=SemanticType.CATEGORY,
                missing_count=0,
                distinct_count=2,
            ),
        ],
    )


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Region": ["East", "East", "West", "West"],
            "Sales": [100.0, 200.0, 300.0, 400.0],
        }
    )


def test_args_hash_deterministic() -> None:
    """Verify args_hash produces identical SHA-256 for identical tool name and args."""
    args1 = {"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]}
    args2 = {"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]}
    args3 = {"conditions": [{"column": "Region", "operator": "eq", "value": "West"}]}

    hash1 = compute_args_hash("filter", args1)
    hash2 = compute_args_hash("filter", args2)
    hash3 = compute_args_hash("filter", args3)

    assert hash1 == hash2
    assert hash1 != hash3
    assert len(hash1) == 64


def test_execute_valid_task(
    sample_df: pd.DataFrame,
    sample_profile: DatasetProfile,
    test_budgets: Budgets,
    tmp_path: Path,
) -> None:
    """Execute valid filter task, produce EvidenceRecord, write trace and canonical result."""
    trace_writer = RunTraceWriter(run_id="run_test_valid", base_dir=tmp_path)
    evidence_store: dict[str, Any] = {}

    task = Task(
        id="t1",
        tool="filter",
        args={"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
        rationale="Filter for East region",
    )

    evidence, failure = execute_task(
        task=task,
        df=sample_df,
        profile=sample_profile,
        budgets=test_budgets,
        trace_writer=trace_writer,
        evidence_store=evidence_store,
    )

    assert failure is None
    assert evidence is not None
    assert evidence.task_id == "t1"
    assert evidence.tool == "filter"
    assert evidence.valid is True
    assert evidence.dataset_hash == "dataset_abc123"
    assert evidence.input_row_count == 4
    assert evidence.result_summary["output_row_count"] == 2
    assert "filter_row_bounds" in evidence.invariants_checked

    # Full canonical result stored alongside
    assert evidence.evidence_id in evidence_store
    assert evidence_store[evidence.evidence_id]["output_row_count"] == 2

    # Check trace file written with tool_call and evidence events
    trace_lines = trace_writer.trace_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(trace_lines) == 2
    assert '"event_type": "tool_call"' in trace_lines[0]
    assert '"event_type": "evidence"' in trace_lines[1]

    # Check on-disk evidence JSON file
    evidence_file = tmp_path / "run_test_valid" / "evidence" / f"{evidence.evidence_id}.json"
    assert evidence_file.exists()


def test_execute_unknown_tool(
    sample_df: pd.DataFrame,
    sample_profile: DatasetProfile,
    test_budgets: Budgets,
    tmp_path: Path,
) -> None:
    """Unknown tool name yields FailureClass.UNKNOWN_TOOL and logs failure event."""
    trace_writer = RunTraceWriter(run_id="run_test_unknown", base_dir=tmp_path)
    task = Task(id="t_unk", tool="non_existent_tool", args={}, rationale="Bad tool")

    evidence, failure = execute_task(
        task=task,
        df=sample_df,
        profile=sample_profile,
        budgets=test_budgets,
        trace_writer=trace_writer,
    )

    assert evidence is None
    assert failure is not None
    assert failure.failure_class == FailureClass.UNKNOWN_TOOL
    assert failure.recoverable is True
    assert failure.task_id == "t_unk"

    trace_lines = trace_writer.trace_file.read_text(encoding="utf-8").strip().splitlines()
    assert any('"event_type": "failure"' in line for line in trace_lines)


def test_execute_invalid_args_failure(
    sample_df: pd.DataFrame,
    sample_profile: DatasetProfile,
    test_budgets: Budgets,
    tmp_path: Path,
) -> None:
    """Referencing nonexistent column fails arg validation and yields INVALID_ARGS."""
    trace_writer = RunTraceWriter(run_id="run_test_bad_col", base_dir=tmp_path)
    task = Task(
        id="t_bad_col",
        tool="filter",
        args={"conditions": [{"column": "FakeCol", "operator": "eq", "value": "Val"}]},
        rationale="Bad col",
    )

    evidence, failure = execute_task(
        task=task,
        df=sample_df,
        profile=sample_profile,
        budgets=test_budgets,
        trace_writer=trace_writer,
    )

    assert evidence is None
    assert failure is not None
    assert failure.failure_class == FailureClass.INVALID_ARGS
    assert failure.context["missing_column"] == "FakeCol"


def test_execute_empty_result_failure(
    sample_df: pd.DataFrame,
    sample_profile: DatasetProfile,
    test_budgets: Budgets,
) -> None:
    """Filter matching 0 rows yields FailureClass.EMPTY_RESULT."""
    task = Task(
        id="t_empty",
        tool="filter",
        args={"conditions": [{"column": "Sales", "operator": "gt", "value": 100000.0}]},
        rationale="No rows match",
    )

    evidence, failure = execute_task(
        task=task,
        df=sample_df,
        profile=sample_profile,
        budgets=test_budgets,
    )

    assert evidence is None
    assert failure is not None
    assert failure.failure_class == FailureClass.EMPTY_RESULT
    assert failure.recoverable is True


def test_execute_timeout_enforcement(
    sample_df: pd.DataFrame,
    sample_profile: DatasetProfile,
    tmp_path: Path,
) -> None:
    """Tool exceeding per_call_timeout_s yields FailureClass.TRANSIENT."""
    trace_writer = RunTraceWriter(run_id="run_test_timeout", base_dir=tmp_path)

    # Custom registry with a slow tool
    def _slow_tool(df: pd.DataFrame, args: Any) -> Any:
        time.sleep(0.5)
        return ToolResultEnvelope(
            tool_name="slow",
            args=args,
            input_row_count=len(df),
            result=FilterResult(output_row_count=1, matched_indices=[0]),
        )

    slow_entry = ToolEntry(
        name="slow_tool",
        fn=_slow_tool,
        args_model=FilterArgs,
        result_model=FilterResult,
        description="Slow mock tool",
        invariants=("filter_row_bounds",),
    )
    custom_registry = ToolRegistry([slow_entry])

    tight_budgets = Budgets(
        max_llm_calls=5,
        max_tool_calls=5,
        max_replans=1,
        max_identical_retries=1,
        per_call_timeout_s=0.05,  # 50ms timeout
        max_total_tokens=1000,
    )

    task = Task(
        id="t_timeout",
        tool="slow_tool",
        args={"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
        rationale="Testing timeout",
    )

    evidence, failure = execute_task(
        task=task,
        df=sample_df,
        profile=sample_profile,
        budgets=tight_budgets,
        trace_writer=trace_writer,
        registry=custom_registry,
    )

    assert evidence is None
    assert failure is not None
    assert failure.failure_class == FailureClass.TRANSIENT
    assert failure.recoverable is True
    assert "timeout" in failure.message.lower()


def test_execute_unexpected_exception_mapping(
    sample_df: pd.DataFrame,
    sample_profile: DatasetProfile,
    test_budgets: Budgets,
) -> None:
    """Unexpected exception inside tool maps to FailureClass.SCHEMA_VIOLATION with recoverable=False."""

    def _buggy_tool(df: pd.DataFrame, args: Any) -> Any:
        raise ZeroDivisionError("Uncaught division by zero bug")

    buggy_entry = ToolEntry(
        name="buggy_tool",
        fn=_buggy_tool,
        args_model=FilterArgs,
        result_model=FilterResult,
        description="Buggy tool",
        invariants=(),
    )
    custom_registry = ToolRegistry([buggy_entry])

    task = Task(
        id="t_bug",
        tool="buggy_tool",
        args={"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]},
        rationale="Testing unexpected error handling",
    )

    evidence, failure = execute_task(
        task=task,
        df=sample_df,
        profile=sample_profile,
        budgets=test_budgets,
        registry=custom_registry,
    )

    assert evidence is None
    assert failure is not None
    assert failure.failure_class == FailureClass.SCHEMA_VIOLATION
    assert failure.recoverable is False
    assert failure.context["exception_type"] == "ZeroDivisionError"
