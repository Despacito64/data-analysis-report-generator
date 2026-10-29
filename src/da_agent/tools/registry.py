"""Allowlisted analytical tool registry.

Layer 5 module: registers pure analytical tool functions with their typed Pydantic
argument models, result models, descriptions, and numerical invariant checkers.
Immutable after construction. Chart builders are NOT registered as planner tools.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from da_agent.contracts.models import ToolSpec
from da_agent.tools.models import (
    AnomaliesIQRArgs,
    AnomaliesIQRResult,
    CorrelationArgs,
    CorrelationResult,
    FilterArgs,
    FilterResult,
    GroupAggregateArgs,
    GroupAggregateResult,
    PeriodCompareArgs,
    PeriodCompareResult,
    RankArgs,
    RankResult,
    SegmentContributionArgs,
    SegmentContributionResult,
    TrendArgs,
    TrendResult,
)
from da_agent.tools.pandas_tools import (
    filter_data,
    group_aggregate,
    period_compare,
    rank,
)
from da_agent.tools.statistics import (
    correlation,
    detect_anomalies_iqr,
    segment_contribution,
    trend,
)


@dataclass(frozen=True)
class ToolEntry:
    """Immutable metadata and function reference for a registered tool."""

    name: str
    fn: Callable[..., Any]
    args_model: type[BaseModel]
    result_model: type[BaseModel]
    description: str
    invariants: tuple[str, ...]


class ToolRegistry:
    """Immutable allowlisted registry of analytical tools."""

    def __init__(self, entries: list[ToolEntry]) -> None:
        self._entries: dict[str, ToolEntry] = {e.name: e for e in entries}

    def get(self, name: str) -> ToolEntry | None:
        """Retrieve a tool entry by name, returning None if unregistered."""
        return self._entries.get(name)

    def is_registered(self, name: str) -> bool:
        """Check if a tool name is allowlisted."""
        return name in self._entries

    def list_tools(self) -> list[str]:
        """Return sorted list of allowlisted tool names."""
        return sorted(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def export_tool_specs(self) -> list[ToolSpec]:
        """Export ToolSpec metadata for all registered tools, generated from registry only."""
        specs: list[ToolSpec] = []
        for name in self.list_tools():
            entry = self._entries[name]
            specs.append(
                ToolSpec(
                    name=entry.name,
                    description=entry.description,
                    args_model=entry.args_model.__name__,
                    args_schema=entry.args_model.model_json_schema(),
                    result_schema=entry.result_model.model_json_schema(),
                    invariants=list(entry.invariants),
                )
            )
        return specs


# Allowlisted tool entries matching Table 2 invariants
_REGISTERED_TOOLS: list[ToolEntry] = [
    ToolEntry(
        name="filter",
        fn=filter_data,
        args_model=FilterArgs,
        result_model=FilterResult,
        description="Filter DataFrame rows deterministically by column conditions.",
        invariants=("filter_row_bounds",),
    ),
    ToolEntry(
        name="group_aggregate",
        fn=group_aggregate,
        args_model=GroupAggregateArgs,
        result_model=GroupAggregateResult,
        description="Group by dimension columns and compute aggregate metric values.",
        invariants=("group_aggregate_reconciliation", "group_aggregate_group_count"),
    ),
    ToolEntry(
        name="rank",
        fn=rank,
        args_model=RankArgs,
        result_model=RankResult,
        description="Compute standard competition rankings (1, 2, 2, 4) with tie groups.",
        invariants=(
            "rank_monotonicity",
            "rank_tie_consistency",
            "rank_cutoff_integrity",
            "rank_null_exclusion",
        ),
    ),
    ToolEntry(
        name="period_compare",
        fn=period_compare,
        args_model=PeriodCompareArgs,
        result_model=PeriodCompareResult,
        description="Compare metrics across two discrete date windows with growth rates.",
        invariants=(
            "period_compare_abs_change",
            "period_compare_growth",
            "period_compare_undefined_reason",
        ),
    ),
    ToolEntry(
        name="trend",
        fn=trend,
        args_model=TrendArgs,
        result_model=TrendResult,
        description="Aggregate metrics chronologically across grain periods to evaluate trend direction.",
        invariants=("trend_chronological_order", "trend_points_integrity"),
    ),
    ToolEntry(
        name="segment_contribution",
        fn=segment_contribution,
        args_model=SegmentContributionArgs,
        result_model=SegmentContributionResult,
        description="Decompose metric values across dimension segments and calculate contribution shares.",
        invariants=(
            "contribution_shares_sum",
            "contribution_total_reconciliation",
            "contribution_reconciles_flag",
        ),
    ),
    ToolEntry(
        name="correlation",
        fn=correlation,
        args_model=CorrelationArgs,
        result_model=CorrelationResult,
        description="Calculate bivariate Pearson correlation with documented limitations.",
        invariants=("correlation_bounds", "correlation_status_consistency"),
    ),
    ToolEntry(
        name="detect_anomalies_iqr",
        fn=detect_anomalies_iqr,
        args_model=AnomaliesIQRArgs,
        result_model=AnomaliesIQRResult,
        description="Detect univariate outliers using the 1.5 x IQR fence rule with documented limitations.",
        invariants=(
            "anomalies_fence_order",
            "anomalies_flagged_bounds",
            "anomalies_truncation_consistency",
        ),
    ),
]

DEFAULT_REGISTRY = ToolRegistry(_REGISTERED_TOOLS)


def export_tool_specs(registry: ToolRegistry = DEFAULT_REGISTRY) -> list[ToolSpec]:
    """Export allowlisted tool specifications for planner prompt consumption."""
    return registry.export_tool_specs()
