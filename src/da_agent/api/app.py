"""FastAPI backend for the React analysis UI."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from da_agent.api.report_view import report_has_numeric_claims, report_view
from da_agent.api.runner import start_run
from da_agent.api.schemas import (
    RunStatusResponse,
    SessionSummary,
    StartRunRequest,
    StartRunResponse,
)
from da_agent.api.session import STORE
from da_agent.contracts.models import DialogueState
from da_agent.core.config import load_config
from da_agent.ui.demo import DEMO_QUESTION

app = FastAPI(title="Data analysis agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_session(session_id: str | None) -> None:
    if not session_id or not STORE.get_session(session_id):
        raise HTTPException(status_code=400, detail="Invalid or missing X-Session-Id")


@app.get("/api/health")
def health() -> dict[str, str]:
    config = load_config()
    return {"status": "ok", "model": config.model.name}


@app.post("/api/session/demo", response_model=SessionSummary)
def create_demo_session(
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> SessionSummary:
    session = STORE.session_demo(x_session_id)
    config = load_config()
    return SessionSummary(
        session_id=session.session_id,
        data_source=session.data_source,
        dataset_hash=session.profile.dataset_hash,
        row_count=session.profile.row_count,
        model_name=config.model.name,
        demo_question=DEMO_QUESTION,
    )


@app.post("/api/session/upload", response_model=SessionSummary)
async def upload_session(
    file: Annotated[UploadFile, File()],
    sheet_name: Annotated[str, Form()] = "",
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> SessionSummary:
    payload = await file.read()
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    session = STORE.session_from_upload(
        session_id=x_session_id,
        filename=file.filename,
        payload=payload,
        sheet_name=sheet_name or None,
    )
    config = load_config()
    return SessionSummary(
        session_id=session.session_id,
        data_source=session.data_source,
        dataset_hash=session.profile.dataset_hash,
        row_count=session.profile.row_count,
        model_name=config.model.name,
        demo_question=None,
    )


@app.get("/api/session/{session_id}/dialogue", response_model=DialogueState)
def get_dialogue(session_id: str) -> DialogueState:
    session = STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.dialogue


@app.post("/api/session/{session_id}/runs", response_model=StartRunResponse)
def create_run(session_id: str, body: StartRunRequest) -> StartRunResponse:
    session = STORE.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question is required")
    job = start_run(session, question=body.question.strip())
    return StartRunResponse(run_id=job.run_id, status=job.status)


@app.get("/api/runs/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str) -> RunStatusResponse:
    job = STORE.get_job(run_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Run not found")
    writer = job.trace_writer
    html_ready = bool(writer and (writer.run_dir / "report.html").is_file())
    summary, table_rows, highlights = (
        report_view(job) if job.status == "complete" else (None, None, None)
    )
    report_ready = html_ready and job.status == "complete" and report_has_numeric_claims(job)
    return RunStatusResponse(
        run_id=job.run_id,
        status=job.status,
        progress=job.progress,
        result_status=job.result_status,
        answer_text=job.answer_text,
        error=job.error,
        report_ready=report_ready,
        summary=summary,
        table_rows=table_rows,
        highlights=highlights,
    )


@app.get("/api/runs/{run_id}/report.html")
def download_report_html(run_id: str) -> FileResponse:
    job = STORE.get_job(run_id)
    if job is None or job.trace_writer is None:
        raise HTTPException(status_code=404, detail="Run not found")
    path = job.trace_writer.run_dir / "report.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not ready")
    return FileResponse(path, media_type="text/html", filename=f"{run_id}_report.html")


@app.get("/api/runs/{run_id}/report.json")
def download_report_json(run_id: str) -> JSONResponse:
    job = STORE.get_job(run_id)
    if job is None or job.trace_writer is None:
        raise HTTPException(status_code=404, detail="Run not found")
    path = job.trace_writer.run_dir / "report.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not ready")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
