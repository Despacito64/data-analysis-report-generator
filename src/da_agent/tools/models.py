"""Pydantic v2 data models for analytical tools arguments, results, and envelope.

Each tool defines:
- One Args model (e.g. FilterArgs)
- One Result model (e.g. FilterResult)
- Envelope wrapping tool_name, args, input_row_count, and typed result with canonical serialization.
"""

import json
import math
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Canonical Serialization Helpers
# ---------------------------------------------------------------------------


def normalize_canonical_value(val: Any) -> Any:
    """Normalize floats and structures for canonical hashing and JSON serialization.

    - Replaces NaN and +/-Inf with None.
    - Normalizes -0.0 to 0.0.
    - Recursively traverses dicts and lists.
    - Preserves exact floating-point precision without premature display rounding.
    """
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
        if val == 0.0:
            return 0.0
        return val
    if isinstance(val, dict):
        return {k: normalize_canonical_value(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [normalize_canonical_value(v) for v in val]
    return val


def canonical_dumps(model: BaseModel) -> str:
    """Serialize a Pydantic model to a canonical, deterministic JSON string.

    Ensures sorted keys, normalized float edge cases (-0.0 -> 0.0, NaN -> None),
    compact separators (`,`, `:`), and no trailing whitespace.
    """
    raw_dict = model.model_dump(mode="json")
    normalized = normalize_canonical_value(raw_dict)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


TResult = TypeVar("TResult", bound=BaseModel)


class ToolResultEnvelope(BaseModel, Generic[TResult]):
    """Standard audit envelope returned by all deterministic analytical tools."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    args: Any  # BaseModel instance
    input_row_count: int = Field(ge=0)
    result: TResult


# ---------------------------------------------------------------------------
# Shared Enumerations
# ---------------------------------------------------------------------------


class AggregationType(str, Enum):
    """Supported deterministic numeric aggregations."""

    SUM = "sum"
    MEAN = "mean"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


class FilterOperator(str, Enum):
    """Supported deterministic filter operators."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    ISIN = "isin"
    NOTIN = "notin"
    BETWEEN = "between"
    ISNULL = "isnull"
    NOTNULL = "notnull"


# ---------------------------------------------------------------------------
# 1. Filter Tool Models
# ---------------------------------------------------------------------------


class FilterCondition(BaseModel):
    """Single column filtering predicate."""

    model_config = ConfigDict(extra="forbid")

    column: str
    operator: FilterOperator
    value: Any = None


class FilterArgs(BaseModel):
    """Arguments for data frame filtering."""

    model_config = ConfigDict(extra="forbid")

    conditions: list[FilterCondition]


class FilterResult(BaseModel):
    """Result summary of a filtering operation."""

    model_config = ConfigDict(extra="forbid")

    output_row_count: int = Field(ge=0)
    matched_indices: list[int]


# ---------------------------------------------------------------------------
# 2. Group and Aggregate Tool Models
# ---------------------------------------------------------------------------


class GroupAggregateArgs(BaseModel):
    """Arguments for group-by aggregation."""

    model_config = ConfigDict(extra="forbid")

    by: list[str] = Field(min_length=1)
    metric_column: str
    aggregation: AggregationType


class GroupAggregateRow(BaseModel):
    """Aggregated row for a group-by bucket."""

    model_config = ConfigDict(extra="forbid")

    group_keys: dict[str, str | int | float | None]
    value: float | int | None
    valid_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)


class GroupAggregateResult(BaseModel):
    """Result of group and aggregate execution."""

    model_config = ConfigDict(extra="forbid")

    metric_column: str
    aggregation: AggregationType
    total_groups: int = Field(ge=0)
    rows: list[GroupAggregateRow]


# ---------------------------------------------------------------------------
# 3. Rank Tool Models
# ---------------------------------------------------------------------------


class RankArgs(BaseModel):
    """Arguments for deterministic competition ranking."""

    model_config = ConfigDict(extra="forbid")

    entity_column: str
    metric_column: str
    ascending: bool = False
    top_n: int | None = Field(default=None, gt=0)
    tie_decimals: int = Field(default=9, ge=0)


class RankRow(BaseModel):
    """Single ranked entity."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    entity: str | int | float
    value: float | int
    is_tied: bool


class TieGroup(BaseModel):
    """Group of entities sharing the exact same competition rank."""

    model_config = ConfigDict(extra="forbid")

    rank: int = Field(ge=1)
    rounded_value: float
    tied_entities: list[str | int | float]


class RankResult(BaseModel):
    """Result of deterministic competition ranking."""

    model_config = ConfigDict(extra="forbid")

    entity_column: str
    metric_column: str
    ascending: bool
    top_n: int | None
    tie_decimals: int
    rows: list[RankRow]
    tie_groups: list[TieGroup]
    ties_at_cutoff: bool
    cutoff_tied_labels_omitted: list[str | int | float]
    null_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# 4. Period Compare Tool Models
# ---------------------------------------------------------------------------


class GrowthUndefinedReason(str, Enum):
    """Classification of why relative growth cannot be computed."""

    ZERO_BASE = "ZERO_BASE"
    MISSING_BASE = "MISSING_BASE"
    MISSING_CURRENT = "MISSING_CURRENT"


class PeriodMetric(BaseModel):
    """Aggregated status and metric for a discrete time window."""

    model_config = ConfigDict(extra="forbid")

    present: bool
    value: float | None
    row_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)


class PeriodCompareArgs(BaseModel):
    """Arguments for period-over-period comparison."""

    model_config = ConfigDict(extra="forbid")

    date_column: str
    metric_column: str
    aggregation: AggregationType = AggregationType.SUM
    base_period: tuple[str, str]  # (start_iso, end_iso)
    compare_period: tuple[str, str]  # (start_iso, end_iso)


class PeriodCompareResult(BaseModel):
    """Result of period comparison with growth rate and diagnostics."""

    model_config = ConfigDict(extra="forbid")

    base_period: PeriodMetric
    compare_period: PeriodMetric
    absolute_change: float | None
    relative_growth: float | None
    undefined_reason: GrowthUndefinedReason | None = None
    undefined_message: str | None = None
    base_negative: bool = False


# ---------------------------------------------------------------------------
# 5. Trend Tool Models
# ---------------------------------------------------------------------------


class TimeGrain(str, Enum):
    """Temporal bucketing granularities."""

    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class TrendDirection(str, Enum):
    """Qualitative classification of a trend direction."""

    INCREASING = "increasing"
    DECREASING = "decreasing"
    FLAT = "flat"
    VOLATILE = "volatile"
    INSUFFICIENT_DATA = "insufficient_data"


class TrendPoint(BaseModel):
    """Single period observation along a chronological series."""

    model_config = ConfigDict(extra="forbid")

    period: str
    value: float | None
    row_count: int = Field(ge=0)
    present: bool


class TrendArgs(BaseModel):
    """Arguments for time-series trend calculation."""

    model_config = ConfigDict(extra="forbid")

    date_column: str
    metric_column: str
    aggregation: AggregationType = AggregationType.SUM
    grain: TimeGrain = TimeGrain.MONTHLY


class TrendResult(BaseModel):
    """Result of time-series trend analysis."""

    model_config = ConfigDict(extra="forbid")

    grain: TimeGrain
    points: list[TrendPoint]
    direction: TrendDirection
    slope: float | None
    total_periods: int = Field(ge=0)
    missing_periods_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# 6. Segment Contribution Tool Models
# ---------------------------------------------------------------------------


class ContributionUndefinedReason(str, Enum):
    """Reason why contribution shares cannot be computed."""

    ZERO_TOTAL = "ZERO_TOTAL"


class SegmentShareRow(BaseModel):
    """Contribution share of an individual dimension segment."""

    model_config = ConfigDict(extra="forbid")

    segment: str
    value: float
    share: float | None


class SegmentContributionArgs(BaseModel):
    """Arguments for segment contribution decomposition."""

    model_config = ConfigDict(extra="forbid")

    segment_column: str
    metric_column: str
    tolerance_applied: float = Field(default=1e-9, gt=0)


class SegmentContributionResult(BaseModel):
    """Result of segment contribution breakdown and reconciliation."""

    model_config = ConfigDict(extra="forbid")

    segment_column: str
    metric_column: str
    total_value: float
    segments: list[SegmentShareRow]
    shares_sum: float | None
    tolerance_applied: float
    reconciles: bool
    has_negative_segments: bool
    undefined_reason: ContributionUndefinedReason | None = None
    undefined_message: str | None = None


# ---------------------------------------------------------------------------
# 7. Correlation Tool Models
# ---------------------------------------------------------------------------


class CorrelationStatus(str, Enum):
    """Status outcome of bivariate correlation."""

    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    UNDEFINED = "undefined"


class CorrelationUndefinedReason(str, Enum):
    """Reason why Pearson correlation cannot be computed."""

    CONSTANT_COLUMN = "CONSTANT_COLUMN"
    TOO_FEW_PAIRS = "TOO_FEW_PAIRS"


class CorrelationArgs(BaseModel):
    """Arguments for bivariate Pearson correlation."""

    model_config = ConfigDict(extra="forbid")

    x_column: str
    y_column: str
    method: Literal["pearson"] = "pearson"


class CorrelationResult(BaseModel):
    """Bivariate correlation result with documented limitations."""

    model_config = ConfigDict(extra="forbid")

    x_column: str
    y_column: str
    correlation: float | None
    status: CorrelationStatus
    valid_pairs_count: int = Field(ge=0)
    undefined_reason: CorrelationUndefinedReason | None = None
    limitations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 8. Anomaly Detection (IQR) Tool Models
# ---------------------------------------------------------------------------


class AnomalyStatus(str, Enum):
    """Status outcome of IQR anomaly detection."""

    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"


class AnomalyPoint(BaseModel):
    """Flagged anomaly item."""

    model_config = ConfigDict(extra="forbid")

    original_index: int = Field(ge=0)
    ascending_position: int = Field(ge=0)
    value: float
    fence_violated: Literal["lower", "upper"]


class AnomaliesIQRArgs(BaseModel):
    """Arguments for IQR anomaly detection."""

    model_config = ConfigDict(extra="forbid")

    metric_column: str
    k: float = Field(default=1.5, gt=0)
    max_flagged_items: int = Field(default=100, gt=0)


class AnomaliesIQRResult(BaseModel):
    """Result of IQR anomaly detection with fences and documented limitations."""

    model_config = ConfigDict(extra="forbid")

    metric_column: str
    status: AnomalyStatus
    q1: float | None
    median: float | None
    q3: float | None
    iqr: float | None
    lower_fence: float | None
    upper_fence: float | None
    k: float
    valid_count: int = Field(ge=0)
    flagged_count: int = Field(ge=0)
    flagged_items_truncated: bool
    flagged_items: list[AnomalyPoint]
    caveat: str | None = None
    limitations: list[str] = Field(default_factory=list)
