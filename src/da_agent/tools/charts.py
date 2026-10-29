"""Plotly chart builders that consume typed analytical tool results.

Rules:
- Pure functions that consume typed tool results only, never raw DataFrames.
- Reject raw DataFrames or improper types with TypeError.
- Include units in labels (axis titles, figure titles, tooltips).
- Handle missing or undefined tool result values gracefully without crashing.
"""

import plotly.graph_objects as go

from da_agent.tools.models import (
    AnomaliesIQRResult,
    PeriodCompareResult,
    RankResult,
    SegmentContributionResult,
    TrendResult,
)


def build_rank_chart(result: RankResult, unit: str = "") -> go.Figure:
    """Build a deterministic bar chart from a RankResult."""
    if not isinstance(result, RankResult):
        raise TypeError(f"build_rank_chart expects RankResult, got {type(result).__name__}")

    x_vals = [r.entity for r in result.rows]
    y_vals = [r.value for r in result.rows]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x_vals,
            y=y_vals,
            name=result.metric_column,
            marker_color="#1f77b4",
        )
    )

    y_label = f"{result.metric_column} ({unit})" if unit else result.metric_column
    fig.update_layout(
        title=f"Rank: {result.metric_column} by {result.entity_column}",
        xaxis_title=result.entity_column,
        yaxis_title=y_label,
        template="plotly_white",
    )
    return fig


def build_trend_chart(result: TrendResult, unit: str = "") -> go.Figure:
    """Build a chronological line chart from a TrendResult."""
    if not isinstance(result, TrendResult):
        raise TypeError(f"build_trend_chart expects TrendResult, got {type(result).__name__}")

    x_vals = [p.period for p in result.points]
    y_vals = [p.value for p in result.points]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="lines+markers",
            name="Trend",
            line={"color": "#2ca02c", "width": 2},
        )
    )

    y_label = f"Value ({unit})" if unit else "Value"
    fig.update_layout(
        title=f"Trend ({result.grain.value.capitalize()}) - Direction: {result.direction.value}",
        xaxis_title="Period",
        yaxis_title=y_label,
        template="plotly_white",
    )
    return fig


def build_contribution_chart(result: SegmentContributionResult, unit: str = "") -> go.Figure:
    """Build a segment contribution bar chart from a SegmentContributionResult."""
    if not isinstance(result, SegmentContributionResult):
        raise TypeError(
            f"build_contribution_chart expects SegmentContributionResult, got {type(result).__name__}"
        )

    x_vals = [s.segment for s in result.segments]
    y_vals = [s.value for s in result.segments]
    text_labels = [
        f"{s.share * 100:.1f}%" if s.share is not None else "N/A" for s in result.segments
    ]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x_vals,
            y=y_vals,
            text=text_labels,
            textposition="auto",
            marker_color="#ff7f0e",
        )
    )

    y_label = f"{result.metric_column} ({unit})" if unit else result.metric_column
    fig.update_layout(
        title=f"Segment Contribution: {result.metric_column} by {result.segment_column}",
        xaxis_title=result.segment_column,
        yaxis_title=y_label,
        template="plotly_white",
    )
    return fig


def build_period_compare_chart(result: PeriodCompareResult, unit: str = "") -> go.Figure:
    """Build a period comparison bar chart from a PeriodCompareResult."""
    if not isinstance(result, PeriodCompareResult):
        raise TypeError(
            f"build_period_compare_chart expects PeriodCompareResult, got {type(result).__name__}"
        )

    x_vals = ["Base Period", "Compare Period"]
    y_vals = [result.base_period.value, result.compare_period.value]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=x_vals,
            y=y_vals,
            marker_color=["#7f7f7f", "#1f77b4"],
        )
    )

    y_label = f"Value ({unit})" if unit else "Value"
    growth_str = (
        f"{result.relative_growth * 100:+.1f}%"
        if result.relative_growth is not None
        else f"N/A ({result.undefined_reason.value if result.undefined_reason else 'undefined'})"
    )

    fig.update_layout(
        title=f"Period Comparison (Growth: {growth_str})",
        yaxis_title=y_label,
        template="plotly_white",
    )
    return fig


def build_anomalies_chart(result: AnomaliesIQRResult, unit: str = "") -> go.Figure:
    """Build a scatter chart highlighting flagged anomalies and IQR fences."""
    if not isinstance(result, AnomaliesIQRResult):
        raise TypeError(
            f"build_anomalies_chart expects AnomaliesIQRResult, got {type(result).__name__}"
        )

    x_vals = [p.original_index for p in result.flagged_items]
    y_vals = [p.value for p in result.flagged_items]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_vals,
            y=y_vals,
            mode="markers",
            marker={"size": 10, "color": "#d62728", "symbol": "diamond"},
            name="Flagged Anomalies",
        )
    )

    shapes = []
    if result.lower_fence is not None:
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": result.lower_fence,
                "y1": result.lower_fence,
                "line": {"color": "#7f7f7f", "width": 1.5, "dash": "dash"},
            }
        )
    if result.upper_fence is not None:
        shapes.append(
            {
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": result.upper_fence,
                "y1": result.upper_fence,
                "line": {"color": "#7f7f7f", "width": 1.5, "dash": "dash"},
            }
        )

    y_label = f"{result.metric_column} ({unit})" if unit else result.metric_column
    fig.update_layout(
        title=f"Anomalies (1.5 x IQR): {result.metric_column} - Flagged: {result.flagged_count}",
        xaxis_title="Original Row Index",
        yaxis_title=y_label,
        shapes=shapes,
        template="plotly_white",
    )
    return fig
