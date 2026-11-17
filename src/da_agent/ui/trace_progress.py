"""Human-readable summaries of run-trace events for Streamlit progress."""

from __future__ import annotations

from da_agent.core.trace import TraceEvent


def describe_trace_event(event: TraceEvent) -> str | None:
    """Map a trace event to a short progress line, or None if too noisy."""
    kind = event.event_type
    payload = event.payload
    if kind == "resolved_question":
        return "Parsed your question"
    if kind == "plan":
        task_count = len(payload.get("tasks") or [])
        version = payload.get("plan_version", 1)
        return f"Plan v{version}: {task_count} task(s)"
    if kind == "plan_revision":
        return "Revised plan after intermediate results"
    if kind == "replan_attempt":
        return "Replanning"
    if kind == "planner_llm_call":
        return "Planner model call"
    if kind == "answer_llm_call":
        return "Answer model call"
    if kind == "tool_call":
        tool = payload.get("tool", "unknown")
        task_id = payload.get("task_id", "")
        suffix = f" ({task_id})" if task_id else ""
        return f"Running tool {tool}{suffix}"
    if kind == "evidence":
        evidence_id = str(payload.get("evidence_id", ""))[:8]
        return f"Recorded evidence {evidence_id}…"
    if kind == "evidence_invalidation":
        return "Evidence invalidated — plan may change"
    if kind == "failure":
        code = payload.get("code") or payload.get("kind") or "error"
        return f"Handled failure: {code}"
    if kind == "follow_up_reuse":
        count = len(payload.get("items") or [])
        return f"Reusing {count} prior evidence item(s)"
    if kind == "evidence_reused":
        eid = str(payload.get("evidence_id", ""))[:8]
        return f"Carried forward evidence {eid}…"
    if kind == "report_written":
        return "Wrote report.json and report.html"
    if kind == "status":
        return f"Finished with status {payload.get('status', 'unknown')}"
    return None


def trace_progress_messages(events: list[TraceEvent]) -> list[str]:
    """Chronological progress lines for display in the UI."""
    lines: list[str] = []
    for event in events:
        line = describe_trace_event(event)
        if line:
            lines.append(line)
    return lines