"""Run trace writer for auditable execution history."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from da_agent.contracts import (
    EvidenceRecord,
    Failure,
    PlanRevision,
    Report,
    RunStatus,
    Task,
)


class TraceEvent(BaseModel):
    """Single envelope entry in the run-trace JSONL stream."""

    timestamp: str
    run_id: str
    event_type: str
    payload: dict[str, Any]


class RunTraceWriter:
    """Writes and reads run traces to/from runs/<run_id>/trace.jsonl."""

    def __init__(self, run_id: str, base_dir: str | Path = "runs"):
        self.run_id = run_id
        self.base_dir = Path(base_dir)
        self.run_dir = self.base_dir / run_id
        self.trace_file = self.run_dir / "trace.jsonl"
        self._initialized = False

    def _ensure_dir(self) -> None:
        if not self._initialized:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            self._initialized = True

    def _write_event(self, event_type: str, payload: dict[str, Any]) -> TraceEvent:
        self._ensure_dir()
        event = TraceEvent(
            timestamp=datetime.now(UTC).isoformat(),
            run_id=self.run_id,
            event_type=event_type,
            payload=payload,
        )
        line = json.dumps(event.model_dump(), default=str)
        with self.trace_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return event

    def log_plan(self, plan_version: int, tasks: list[Task]) -> TraceEvent:
        """Record initial or active plan."""
        return self._write_event(
            event_type="plan",
            payload={
                "plan_version": plan_version,
                "tasks": [t.model_dump(mode="json") for t in tasks],
            },
        )

    def log_plan_revision(self, revision: PlanRevision) -> TraceEvent:
        """Record a plan revision."""
        return self._write_event(
            event_type="plan_revision",
            payload=revision.model_dump(mode="json"),
        )

    def log_tool_call(
        self,
        task_id: str,
        tool: str,
        args: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> TraceEvent:
        """Record a dispatched tool call."""
        payload: dict[str, Any] = {
            "task_id": task_id,
            "tool": tool,
            "args": args,
        }
        if extra:
            payload["extra"] = extra
        return self._write_event(event_type="tool_call", payload=payload)

    def log_evidence(self, evidence: EvidenceRecord) -> TraceEvent:
        """Record an immutable evidence record."""
        return self._write_event(
            event_type="evidence",
            payload=evidence.model_dump(mode="json"),
        )

    def log_failure(self, failure: Failure) -> TraceEvent:
        """Record an execution failure."""
        return self._write_event(
            event_type="failure",
            payload=failure.model_dump(mode="json"),
        )

    def log_event(self, event_type: str, payload: dict[str, Any]) -> TraceEvent:
        """Record an arbitrary typed event in the trace stream."""
        return self._write_event(event_type=event_type, payload=payload)

    def log_status(self, status: RunStatus) -> TraceEvent:
        """Record terminal run status."""
        return self._write_event(
            event_type="status",
            payload=status.model_dump(mode="json"),
        )

    def save_report(self, report: Report) -> Path:
        """Save final report JSON into the run directory."""
        self._ensure_dir()
        report_path = self.run_dir / "report.json"
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report.model_dump(mode="json"), f, indent=2, default=str)
        return report_path

    def read_events(self) -> list[TraceEvent]:
        """Read all events from trace.jsonl in chronological order."""
        if not self.trace_file.is_file():
            return []
        events: list[TraceEvent] = []
        with self.trace_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(TraceEvent.model_validate_json(line))
        return events
