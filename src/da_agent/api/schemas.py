"""HTTP request/response shapes for the React UI (not cross-module contracts)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    data_source: str
    dataset_hash: str
    row_count: int
    model_name: str
    demo_question: str | None = None


class StartRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str


class StartRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str


class RunStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: str
    progress: list[str] = Field(default_factory=list)
    result_status: str | None = None
    answer_text: str | None = None
    error: str | None = None
    report_ready: bool = False
    summary: str | None = None
    table_rows: list[dict[str, str | float]] | None = None
    highlights: list[str] | None = None
