"""Unit tests for statistical analytical tools (correlation and detect_anomalies_iqr).

Edge cases tested:
- E01: Empty input DataFrame -> ToolError(EMPTY_RESULT)
- E02: Unknown column -> ToolError(INVALID_ARGS)
- E23: Correlation with fewer than 3 valid paired rows -> status=INSUFFICIENT_DATA, undefined_reason=TOO_FEW_PAIRS
- E24: Correlation with constant column (zero variance) -> status=UNDEFINED, undefined_reason=CONSTANT_COLUMN
- E25: IQR anomaly detection with fewer than 4 valid non-null values -> status=INSUFFICIENT_DATA
- E26: IQR anomaly detection with constant values (IQR == 0.0) -> caveat='zero_iqr', fences computed
- E27: IQR anomaly detection truncation (capped max_flagged_items, flagged_count preserved, flagged_items_truncated=True)
- Limitations documented in both docstring and result model
"""

import pandas as pd
import pytest

from da_agent.contracts.models import FailureClass
from da_agent.tools.errors import ToolError
from da_agent.tools.models import (
    AnomaliesIQRArgs,
    AnomalyStatus,
    CorrelationArgs,
    CorrelationStatus,
    CorrelationUndefinedReason,
)
from da_agent.tools.statistics import (
    correlation,
    detect_anomalies_iqr,
)

# ---------------------------------------------------------------------------
# 1. correlation Tests
# ---------------------------------------------------------------------------


def test_correlation_standard_positive_and_negative() -> None:
    """Test standard Pearson correlation with positive and negative relationships."""
    df_pos = pd.DataFrame({"X": [1.0, 2.0, 3.0, 4.0, 5.0], "Y": [2.0, 4.0, 6.0, 8.0, 10.0]})
    envelope_pos = correlation(df_pos, CorrelationArgs(x_column="X", y_column="Y"))
    res_pos = envelope_pos.result

    assert envelope_pos.tool_name == "correlation"
    assert res_pos.status == CorrelationStatus.OK
    assert res_pos.correlation is not None
    assert abs(res_pos.correlation - 1.0) < 1e-9
    assert res_pos.valid_pairs_count == 5
    assert len(res_pos.limitations) >= 3

    # Negative correlation
    df_neg = pd.DataFrame({"X": [1.0, 2.0, 3.0, 4.0, 5.0], "Y": [10.0, 8.0, 6.0, 4.0, 2.0]})
    res_neg = correlation(df_neg, CorrelationArgs(x_column="X", y_column="Y")).result
    assert res_neg.correlation is not None
    assert abs(res_neg.correlation - (-1.0)) < 1e-9


def test_correlation_fewer_than_three_pairs() -> None:
    """E23: Fewer than 3 valid paired rows produces INSUFFICIENT_DATA."""
    df = pd.DataFrame({"X": [1.0, 2.0, None], "Y": [10.0, None, 30.0]})
    envelope = correlation(df, CorrelationArgs(x_column="X", y_column="Y"))
    res = envelope.result

    assert res.status == CorrelationStatus.INSUFFICIENT_DATA
    assert res.correlation is None
    assert res.valid_pairs_count == 1
    assert res.undefined_reason == CorrelationUndefinedReason.TOO_FEW_PAIRS


def test_correlation_constant_column() -> None:
    """E24: Constant column (zero variance) produces UNDEFINED with CONSTANT_COLUMN reason."""
    df = pd.DataFrame({"X": [5.0, 5.0, 5.0, 5.0], "Y": [1.0, 2.0, 3.0, 4.0]})
    envelope = correlation(df, CorrelationArgs(x_column="X", y_column="Y"))
    res = envelope.result

    assert res.status == CorrelationStatus.UNDEFINED
    assert res.correlation is None
    assert res.valid_pairs_count == 4
    assert res.undefined_reason == CorrelationUndefinedReason.CONSTANT_COLUMN


def test_correlation_empty_and_missing_column() -> None:
    """E01 & E02: Empty input and unknown column handling."""
    empty_df = pd.DataFrame(columns=["X", "Y"])
    with pytest.raises(ToolError) as exc_info_empty:
        correlation(empty_df, CorrelationArgs(x_column="X", y_column="Y"))
    assert exc_info_empty.value.failure_class == FailureClass.EMPTY_RESULT

    df = pd.DataFrame({"X": [1.0, 2.0, 3.0], "Y": [4.0, 5.0, 6.0]})
    with pytest.raises(ToolError) as exc_info_col:
        correlation(df, CorrelationArgs(x_column="X", y_column="Z"))
    assert exc_info_col.value.failure_class == FailureClass.INVALID_ARGS


# ---------------------------------------------------------------------------
# 2. detect_anomalies_iqr Tests
# ---------------------------------------------------------------------------


def test_detect_anomalies_iqr_standard() -> None:
    """Test standard 1.5 x IQR outlier detection on a known dataset."""
    # Data: 10, 12, 13, 14, 15, 16, 17, 18, 19, 100
    # Q1 = 13.25, Median = 15.5, Q3 = 17.75, IQR = 4.5
    # Upper fence = 17.75 + 1.5 * 4.5 = 24.5
    # 100 is an outlier!
    df = pd.DataFrame({"Metric": [10.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0, 100.0]})
    envelope = detect_anomalies_iqr(df, AnomaliesIQRArgs(metric_column="Metric", k=1.5))
    res = envelope.result

    assert envelope.tool_name == "detect_anomalies_iqr"
    assert res.status == AnomalyStatus.OK
    assert res.valid_count == 10
    assert res.flagged_count == 1
    assert len(res.flagged_items) == 1
    point = res.flagged_items[0]
    assert point.original_index == 9
    assert point.value == 100.0
    assert point.fence_violated == "upper"
    assert res.q1 is not None and res.q3 is not None and res.iqr is not None
    assert res.upper_fence is not None and res.upper_fence < 100.0
    assert len(res.limitations) >= 3


def test_detect_anomalies_iqr_fewer_than_four_values() -> None:
    """E25: Fewer than 4 valid non-null values returns INSUFFICIENT_DATA."""
    df = pd.DataFrame({"Metric": [10.0, 20.0, None, 30.0]})
    envelope = detect_anomalies_iqr(df, AnomaliesIQRArgs(metric_column="Metric"))
    res = envelope.result

    assert res.status == AnomalyStatus.INSUFFICIENT_DATA
    assert res.valid_count == 3
    assert res.flagged_count == 0
    assert len(res.flagged_items) == 0


def test_detect_anomalies_iqr_zero_iqr() -> None:
    """E26: Constant values with IQR == 0.0 computes fences and sets caveat='zero_iqr'."""
    df = pd.DataFrame({"Metric": [50.0, 50.0, 50.0, 50.0, 50.0, 200.0]})
    envelope = detect_anomalies_iqr(df, AnomaliesIQRArgs(metric_column="Metric"))
    res = envelope.result

    assert res.status == AnomalyStatus.OK
    assert res.caveat == "zero_iqr"
    assert res.iqr == 0.0
    assert res.flagged_count == 1
    assert res.flagged_items[0].value == 200.0


def test_detect_anomalies_iqr_truncation() -> None:
    """E27: Truncates flagged items list when exceeding max_flagged_items but preserves total count."""
    # 90 normal values (10 to 19) and 10 extreme outliers (500.0)
    values = [10.0 + i * 0.1 for i in range(90)] + [500.0] * 10
    df = pd.DataFrame({"Metric": values})
    envelope = detect_anomalies_iqr(
        df,
        AnomaliesIQRArgs(metric_column="Metric", max_flagged_items=3),
    )
    res = envelope.result

    assert res.flagged_count == 10
    assert len(res.flagged_items) == 3
    assert res.flagged_items_truncated is True
