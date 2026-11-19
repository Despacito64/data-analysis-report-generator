"""HTTP API smoke tests (mock agent)."""

import time

from fastapi.testclient import TestClient

import api_main
from da_agent.agent.answer import AgentAnswerStatus, AgentResult


def test_health_and_demo_session() -> None:
    client = TestClient(api_main.app)
    health = client.get("/api/health")
    assert health.status_code == 200
    assert "model" in health.json()
    demo = client.post("/api/session/demo")
    assert demo.status_code == 200
    body = demo.json()
    assert body["row_count"] == 9994
    assert body["demo_question"]


def test_run_lifecycle_mocked(monkeypatch) -> None:
    client = TestClient(api_main.app)
    demo = client.post("/api/session/demo").json()
    session_id = demo["session_id"]

    def _fake_run_agent(*_args, **_kwargs) -> AgentResult:
        writer = _kwargs.get("trace_writer")
        if writer is not None:
            from da_agent.contracts.models import ExecutionStatus, RunStatus

            writer.log_status(RunStatus(status=ExecutionStatus.COMPLETE))
            writer.log_event("report_written", {"path": "report.json"})
        return AgentResult(
            run_id=_kwargs.get("run_id", "x"),
            question=_args[0] if _args else "q",
            status=AgentAnswerStatus.ANSWERED,
            answer_text="ok",
        )

    import da_agent.api.runner as runner_mod

    monkeypatch.setattr(runner_mod, "run_agent", _fake_run_agent)

    start = client.post(
        f"/api/session/{session_id}/runs",
        json={"question": "What is total sales by region?"},
    )
    assert start.status_code == 200
    run_id = start.json()["run_id"]

    status = "running"
    for _ in range(40):
        poll = client.get(f"/api/runs/{run_id}").json()
        status = poll["status"]
        if status in {"complete", "failed"}:
            break
        time.sleep(0.1)
    assert status == "complete"
    assert poll.get("answer_text") == "ok"
    assert poll.get("report_ready") is False

    rejected = client.post(
        f"/api/session/{session_id}/runs",
        json={"question": "by region", "reuse_evidence_ids": ["ev-old"]},
    )
    assert rejected.status_code == 422
