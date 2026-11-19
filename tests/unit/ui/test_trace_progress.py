"""Run-trace progress lines for Streamlit."""

from da_agent.core.trace import TraceEvent
from da_agent.ui.trace_progress import describe_trace_event, trace_progress_messages


def test_describe_plan_and_tool_call() -> None:
    plan = TraceEvent(
        timestamp="t",
        run_id="r",
        event_type="plan",
        payload={"plan_version": 1, "tasks": [{"task_id": "a"}, {"task_id": "b"}]},
    )
    tool = TraceEvent(
        timestamp="t",
        run_id="r",
        event_type="tool_call",
        payload={"tool": "group_aggregate", "task_id": "t1"},
    )
    assert describe_trace_event(plan) == "Plan v1: 2 task(s)"
    assert "group_aggregate" in (describe_trace_event(tool) or "")


def test_trace_progress_messages_skip_unknown_events() -> None:
    events = [
        TraceEvent(
            timestamp="t",
            run_id="r",
            event_type="graph_node",
            payload={"node": "plan", "phase": "start"},
        ),
        TraceEvent(
            timestamp="t",
            run_id="r",
            event_type="status",
            payload={"status": "complete"},
        ),
    ]
    lines = trace_progress_messages(events)
    assert lines == ["Finished with status complete"]
