"""Start agent runs in a background thread (same pattern as Streamlit)."""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from uuid import uuid4

from da_agent.agent.planner import OllamaClient
from da_agent.api.chat_narrative import chat_user_narrative
from da_agent.api.report_view import report_view
from da_agent.api.session import STORE, AnalysisSession, RunJob
from da_agent.core.chat_thread import append_assistant_message, append_user_message
from da_agent.core.config import AppConfig, load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.pipeline import run_agent
from da_agent.ui.trace_progress import trace_progress_messages


def _ollama_client(config: AppConfig) -> OllamaClient:
    return OllamaClient(
        base_url=config.model.base_url,
        model=config.model.name,
        temperature=config.model.temperature,
        seed=config.model.seed,
        timeout_s=config.budgets.per_call_timeout_s,
        thinking_enabled=config.evaluation.thinking_enabled,
        keep_alive=config.evaluation.keep_alive,
    )


def _metric_from_report(writer: RunTraceWriter) -> tuple[str | None, str | None]:
    report_json = writer.run_dir / "report.json"
    if not report_json.is_file():
        return None, None
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    for finding in payload.get("findings") or []:
        for claim in finding.get("numeric_claims") or []:
            label = str(claim.get("label", ""))
            if " — " in label:
                _, metric_part = label.split(" — ", 1)
                if "(" in metric_part and metric_part.endswith(")"):
                    col, agg = metric_part[:-1].split(" (", 1)
                    return col.strip(), agg.strip()
    return None, None


def _grouping_column_from_report(writer: RunTraceWriter) -> str | None:
    report_json = writer.run_dir / "report.json"
    if not report_json.is_file():
        return None
    payload = json.loads(report_json.read_text(encoding="utf-8"))
    for finding in payload.get("findings") or []:
        for claim in finding.get("numeric_claims") or []:
            label = str(claim.get("label", ""))
            if " — " in label:
                return None
            if " by " in label.lower():
                continue
    return "Category"


def start_run(session: AnalysisSession, *, question: str) -> RunJob:
    """Run one chat turn (D-047). Prior evidence is not forwarded."""
    config = load_config()
    run_id = uuid4().hex
    writer = RunTraceWriter(run_id=run_id, base_dir=config.run_trace.base_dir)
    client = _ollama_client(config)

    thread = append_user_message(session.chat_thread, question)
    session.chat_thread = thread
    STORE.put_session(session)

    df = session.df
    profile = session.profile
    job = RunJob(
        run_id=run_id,
        session_id=session.session_id,
        question=question,
        status="running",
        trace_writer=writer,
    )
    STORE.put_job(job)

    run_state: dict[str, Any] = {}
    run_error: list[BaseException] = []

    def _worker() -> None:
        try:
            run_state["result"] = run_agent(
                question,
                df,
                config,
                client,
                profile=profile,
                run_id=run_id,
                trace_writer=writer,
                chat_thread=thread,
            )
        except BaseException as exc:  # noqa: BLE001
            run_error.append(exc)

    thread_bg = threading.Thread(target=_worker, daemon=True)
    thread_bg.start()

    def _watch() -> None:
        seen = 0
        while thread_bg.is_alive():
            events = writer.read_events()
            if len(events) > seen:
                seen = len(events)
                job.progress = trace_progress_messages(events)[-12:]
            time.sleep(0.35)
        thread_bg.join()
        if run_error:
            job.status = "failed"
            job.error = str(run_error[0])
            return
        result = run_state["result"]
        job.result = result
        job.result_status = str(result.status)
        job.progress = trace_progress_messages(writer.read_events())
        job.status = "complete"
        summary, table_rows, _highlights = report_view(job)
        tool_dump = result.answer_text.startswith("Tool results:")
        fallback_narrative = chat_user_narrative(question, summary, table_rows)
        job.answer_text = (
            result.answer_text
            if result.answer_text and not tool_dump
            else (fallback_narrative or summary or result.answer_text or "")
        )
        labels = [str(r["category"]) for r in table_rows or []]
        metric_column, aggregation = _metric_from_report(writer)
        assistant_text = job.answer_text
        session.chat_thread = append_assistant_message(
            session.chat_thread,
            text=assistant_text,
            summary=summary,
            group_labels=labels,
            grouping_column=_grouping_column_from_report(writer)
            or ("Category" if labels else None),
            metric_column=metric_column,
            aggregation=aggregation,
        )
        STORE.put_session(session)

    threading.Thread(target=_watch, daemon=True).start()
    return job
