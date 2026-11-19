"""In-memory API sessions (dataset + symbolic dialogue)."""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from da_agent.contracts.models import DatasetProfile, DialogueState
from da_agent.core.chat_thread import ChatThread, chat_for_hash
from da_agent.core.dialogue import dialogue_for_hash
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.ui.demo import load_demo_dataset


@dataclass
class AnalysisSession:
    """One browser session's dataset and symbolic follow-up state."""

    session_id: str
    df: pd.DataFrame
    profile: DatasetProfile
    data_source: str
    dialogue: DialogueState = field(default_factory=DialogueState)
    chat_thread: ChatThread = field(default_factory=ChatThread)


@dataclass
class RunJob:
    """Background agent run."""

    run_id: str
    session_id: str
    question: str
    status: str = "pending"  # pending | running | complete | failed
    error: str | None = None
    result_status: str | None = None
    answer_text: str | None = None
    progress: list[str] = field(default_factory=list)
    trace_writer: Any = None
    result: Any = None


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AnalysisSession] = {}
        self._jobs: dict[str, RunJob] = {}

    def create_session_id(self) -> str:
        return uuid.uuid4().hex

    def put_session(self, session: AnalysisSession) -> None:
        self._sessions[session.session_id] = session

    def get_session(self, session_id: str) -> AnalysisSession | None:
        return self._sessions.get(session_id)

    def put_job(self, job: RunJob) -> None:
        self._jobs[job.run_id] = job

    def get_job(self, run_id: str) -> RunJob | None:
        return self._jobs.get(run_id)

    def _keep_dialogue(self, sid: str, new_hash: str) -> DialogueState:
        old = self.get_session(sid)
        if old is None:
            return DialogueState()
        return dialogue_for_hash(old.dialogue, old.profile.dataset_hash, new_hash)

    def _keep_chat(self, sid: str, new_hash: str) -> ChatThread:
        old = self.get_session(sid)
        if old is None:
            return ChatThread()
        return chat_for_hash(old.chat_thread, old.profile.dataset_hash, new_hash)

    def session_demo(self, session_id: str | None = None) -> AnalysisSession:
        df, profile = load_demo_dataset()
        sid = session_id or self.create_session_id()
        session = AnalysisSession(
            session_id=sid,
            df=df,
            profile=profile,
            data_source="Sample-Superstore.csv (demo)",
            dialogue=self._keep_dialogue(sid, profile.dataset_hash),
            chat_thread=self._keep_chat(sid, profile.dataset_hash),
        )
        self.put_session(session)
        return session

    def session_from_upload(
        self,
        *,
        session_id: str | None,
        filename: str,
        payload: bytes,
        sheet_name: str | None,
    ) -> AnalysisSession:
        suffix = Path(filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        sheet: str | int | None = sheet_name.strip() if sheet_name and sheet_name.strip() else None
        if sheet is not None and sheet.isdigit():
            sheet = int(sheet)
        try:
            df = load_data(temp_path, sheet_name=sheet)
            profile = compute_profile(df, file_path=filename)
        finally:
            temp_path.unlink(missing_ok=True)
        sid = session_id or self.create_session_id()
        session = AnalysisSession(
            session_id=sid,
            df=df,
            profile=profile,
            data_source=filename,
            dialogue=self._keep_dialogue(sid, profile.dataset_hash),
            chat_thread=self._keep_chat(sid, profile.dataset_hash),
        )
        self.put_session(session)
        return session


STORE = SessionStore()
