"""Unit tests for tool registry (src/da_agent/tools/registry.py)."""

from da_agent.contracts.models import ToolSpec
from da_agent.tools.registry import DEFAULT_REGISTRY, export_tool_specs


def test_registry_contains_all_eight_analytical_tools() -> None:
    """Verify registry has exactly the 8 allowlisted analytical tools."""
    expected_tools = [
        "correlation",
        "detect_anomalies_iqr",
        "filter",
        "group_aggregate",
        "period_compare",
        "rank",
        "segment_contribution",
        "trend",
    ]
    assert DEFAULT_REGISTRY.list_tools() == expected_tools
    assert len(DEFAULT_REGISTRY) == 8


def test_registry_lookup_success() -> None:
    """Lookup registered tool returns valid ToolEntry."""
    entry = DEFAULT_REGISTRY.get("filter")
    assert entry is not None
    assert entry.name == "filter"
    assert entry.args_model.__name__ == "FilterArgs"
    assert entry.result_model.__name__ == "FilterResult"
    assert "filter_row_bounds" in entry.invariants


def test_registry_lookup_unknown_returns_none() -> None:
    """Lookup of unknown tool returns None."""
    assert DEFAULT_REGISTRY.get("unknown_tool") is None
    assert not DEFAULT_REGISTRY.is_registered("unknown_tool")
    assert "unknown_tool" not in DEFAULT_REGISTRY


def test_chart_builders_not_in_registry() -> None:
    """Verify chart builders are strictly not registered in analytical registry."""
    assert not DEFAULT_REGISTRY.is_registered("build_rank_chart")
    assert not DEFAULT_REGISTRY.is_registered("build_trend_chart")
    assert not DEFAULT_REGISTRY.is_registered("build_contribution_chart")
    assert not DEFAULT_REGISTRY.is_registered("build_period_compare_chart")
    assert not DEFAULT_REGISTRY.is_registered("build_anomalies_chart")


def test_export_tool_specs() -> None:
    """Verify tool specs export matches ToolSpec contract and contains no data values."""
    specs = export_tool_specs()
    assert len(specs) == 8
    tool_names = [s.name for s in specs]
    assert tool_names == DEFAULT_REGISTRY.list_tools()

    for spec in specs:
        assert isinstance(spec, ToolSpec)
        assert spec.description and len(spec.description) > 10
        assert spec.args_schema.get("type") == "object"
        assert spec.result_schema.get("type") == "object"
        assert isinstance(spec.invariants, list)
        assert len(spec.invariants) >= 1
