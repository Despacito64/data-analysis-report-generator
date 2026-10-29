"""Tests for ToolError and canonical serialization envelope.

Edge-Case Table Reference:
- E01: Input DataFrame has 0 rows -> ToolError(EMPTY_RESULT)
- E02: Referenced column not in DataFrame -> ToolError(INVALID_ARGS)
- E29: Envelope canonical serialization (sorted keys, NaN/inf to None, -0.0 to 0.0, byte parity)
- E30: ToolError context JSON-serializability
"""

import json
import math
from typing import Literal

from pydantic import BaseModel

from da_agent.contracts.models import FailureClass
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    ToolResultEnvelope,
    canonical_dumps,
    normalize_canonical_value,
)


class DummyArgs(BaseModel):
    column: str
    threshold: float


class DummyResult(BaseModel):
    status: Literal["ok", "warning"]
    value: float | None
    values_list: list[float | None]


def test_tool_error_properties_and_recoverability() -> None:
    """Test ToolError attributes and derived recoverability."""
    err_invalid = ToolError(
        failure_class=FailureClass.INVALID_ARGS,
        message="Column 'sales' does not exist",
        context={"missing_columns": ["sales"], "available_columns": ["Sales", "Profit"]},
    )
    assert err_invalid.failure_class == FailureClass.INVALID_ARGS
    assert err_invalid.message == "Column 'sales' does not exist"
    assert err_invalid.recoverable is True
    assert err_invalid.context["missing_columns"] == ["sales"]

    err_empty = ToolError(
        failure_class=FailureClass.EMPTY_RESULT,
        message="Filter returned 0 rows",
        context={"row_count": 0},
    )
    assert err_empty.failure_class == FailureClass.EMPTY_RESULT
    assert err_empty.recoverable is True

    # Test non-recoverable failure classes
    err_schema = ToolError(
        failure_class=FailureClass.SCHEMA_VIOLATION,
        message="Output schema mismatch",
    )
    assert err_schema.recoverable is False


def test_tool_error_context_json_serializable() -> None:
    """Verify ToolError context is strictly JSON serializable."""
    context_data = {
        "missing_columns": ["sales", "date"],
        "available_columns": ["Sales", "Order Date"],
        "row_count": 0,
        "tolerance": 1e-9,
        "none_value": None,
        "is_active": True,
    }
    err = ToolError(
        failure_class=FailureClass.INVALID_ARGS,
        message="Invalid columns requested",
        context=context_data,
    )
    serialized = json.dumps(err.context)
    deserialized = json.loads(serialized)
    assert deserialized == context_data


def test_normalize_canonical_value() -> None:
    """Verify NaN/inf to None and -0.0 normalization."""
    assert normalize_canonical_value(-0.0) == 0.0
    assert math.copysign(1.0, normalize_canonical_value(-0.0)) == 1.0
    assert normalize_canonical_value(float("nan")) is None
    assert normalize_canonical_value(float("inf")) is None
    assert normalize_canonical_value(float("-inf")) is None
    assert normalize_canonical_value(42.5) == 42.5
    assert normalize_canonical_value("test") == "test"
    assert normalize_canonical_value([float("nan"), -0.0]) == [None, 0.0]
    assert normalize_canonical_value({"a": float("inf"), "b": -0.0}) == {"a": None, "b": 0.0}


def test_tool_result_envelope_canonical_serialization_parity() -> None:
    """Verify identical inputs produce byte-identical JSON with sorted keys."""
    args1 = DummyArgs(column="Sales", threshold=100.5)
    res1 = DummyResult(status="ok", value=-0.0, values_list=[1.0, float("nan"), -0.0])
    envelope1 = ToolResultEnvelope(
        tool_name="dummy_tool",
        args=args1,
        input_row_count=50,
        result=res1,
    )

    args2 = DummyArgs(column="Sales", threshold=100.5)
    res2 = DummyResult(status="ok", value=0.0, values_list=[1.0, None, 0.0])
    envelope2 = ToolResultEnvelope(
        tool_name="dummy_tool",
        args=args2,
        input_row_count=50,
        result=res2,
    )

    json1 = canonical_dumps(envelope1)
    json2 = canonical_dumps(envelope2)

    assert json1 == json2
    # Verify sorted keys: "args" comes before "input_row_count", etc.
    data = json.loads(json1)
    assert list(data.keys()) == sorted(data.keys())
    assert data["result"]["value"] == 0.0
    assert data["result"]["values_list"] == [1.0, None, 0.0]
