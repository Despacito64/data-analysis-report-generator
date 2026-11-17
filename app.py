"""Streamlit UI: upload, question, run progress, report download, follow-ups (M9)."""

from __future__ import annotations

import json
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from da_agent.agent.planner import OllamaClient
from da_agent.contracts.models import EvidenceRecord
from da_agent.core.config import AppConfig, load_config
from da_agent.core.follow_up import (
    PriorRunSnapshot,
    apply_new_dataset_hash,
    select_reusable_evidence,
)
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import DataLoadError, load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_agent
from da_agent.ui.demo import DEMO_QUESTION, load_demo_dataset
from da_agent.ui.sheets import list_excel_sheet_names
from da_agent.ui.trace_progress import trace_progress_messages


def _load_uploaded_file(
    uploaded_name: str,
    payload: bytes,
    *,
    sheet_name: str | None,
) -> pd.DataFrame:
    suffix = Path(uploaded_name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    sheet: str | int | None = sheet_name.strip() if sheet_name and sheet_name.strip() else None
    if sheet is not None and sheet.isdigit():
        sheet = int(sheet)
    return load_data(temp_path, sheet_name=sheet)


def _apply_profile(df: pd.DataFrame, *, file_label: str) -> None:
    profile = compute_profile(df, file_path=file_label)
    st.session_state["prior_run"] = apply_new_dataset_hash(
        st.session_state.get("prior_run"),
        profile.dataset_hash,
    )
    st.session_state["dataset_hash"] = profile.dataset_hash
    st.session_state["profile"] = profile
    st.session_state["df"] = df
    st.session_state["data_source"] = file_label


def _snapshot_from_run(
    *,
    run_id: str,
    dataset_hash: str,
    question: str,
    writer: RunTraceWriter,
) -> PriorRunSnapshot:
    records: dict[str, EvidenceRecord] = {}
    for event in writer.read_events():
        if event.event_type == "evidence":
            record = EvidenceRecord.model_validate(event.payload)
            records[record.evidence_id] = record
    return PriorRunSnapshot(
        run_id=run_id,
        dataset_hash=dataset_hash,
        question=question,
        evidence_records=records,
    )


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


def main() -> None:
    st.set_page_config(page_title="Data analysis agent", layout="wide")
    st.title("Data analysis agent")
    config = load_config()

    for key, default in (
        ("dataset_hash", None),
        ("profile", None),
        ("df", None),
        ("prior_run", None),
        ("last_result", None),
        ("last_writer", None),
        ("last_run_id", None),
        ("data_source", None),
        ("question_text", ""),
    ):
        st.session_state.setdefault(key, default)

    with st.sidebar:
        st.header("Dataset")
        demo_mode = st.toggle(
            "Demo mode",
            value=True,
            help="Loads Sample Superstore, prefills a starter question, and still uses Ollama from config.yaml.",
        )
        if demo_mode:
            st.caption("Real LLM only — demo mode does not disable Ollama.")
        uploaded = st.file_uploader(
            "CSV or XLSX (optional in demo mode)",
            type=["csv", "xlsx"],
            disabled=demo_mode,
        )
        sheet_name = st.text_input(
            "Excel sheet (name or index)",
            value="",
            disabled=demo_mode,
        )

    if demo_mode:
        try:
            df, profile = load_demo_dataset()
            st.session_state["prior_run"] = apply_new_dataset_hash(
                st.session_state.get("prior_run"),
                profile.dataset_hash,
            )
            st.session_state["dataset_hash"] = profile.dataset_hash
            st.session_state["profile"] = profile
            st.session_state["df"] = df
            st.session_state["data_source"] = "Sample-Superstore.csv (demo)"
            if not str(st.session_state.get("question_text", "")).strip():
                st.session_state["question_text"] = DEMO_QUESTION
            st.info(
                f"Demo: **Sample Superstore** ({len(df):,} rows, hash `{profile.dataset_hash[:12]}…`). "
                f"Model: **{config.model.name}** via Ollama."
            )
        except (DataLoadError, FileNotFoundError) as exc:
            st.error(str(exc))
    elif uploaded is not None:
        if uploaded.name.lower().endswith(".xlsx"):
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
                handle.write(uploaded.getvalue())
                peek_path = Path(handle.name)
            try:
                names = list_excel_sheet_names(peek_path)
                st.caption(
                    f"Workbook sheets: **{', '.join(names)}** "
                    f"(loads **{sheet_name.strip() or names[0]}**)."
                )
            except DataLoadError as exc:
                st.warning(str(exc))
            finally:
                peek_path.unlink(missing_ok=True)
        try:
            df = _load_uploaded_file(
                uploaded.name,
                uploaded.getvalue(),
                sheet_name=sheet_name or None,
            )
            _apply_profile(df, file_label=uploaded.name)
            st.success(f"Loaded {len(df):,} rows. Dataset hash: {st.session_state['dataset_hash'][:12]}…")
        except DataLoadError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 — surface loader failures to the user
            st.error(f"Could not load file: {exc}")

    st.text_area(
        "Question",
        height=120,
        placeholder="Ask about the uploaded dataset…",
        key="question_text",
    )
    question = str(st.session_state.get("question_text", ""))

    prior: PriorRunSnapshot | None = st.session_state.get("prior_run")
    selected_ids: set[str] = set()
    if prior and prior.evidence_records:
        st.subheader("Follow-up context")
        st.caption(f"Prior run {prior.run_id[:8]}… on the same dataset only.")
        for evidence_id in sorted(prior.evidence_records):
            if st.checkbox(evidence_id, key=f"reuse_{evidence_id}"):
                selected_ids.add(evidence_id)
        if st.session_state.get("dataset_hash"):
            preview = select_reusable_evidence(
                prior,
                current_dataset_hash=st.session_state["dataset_hash"],
                selected_ids=selected_ids,
            )
            if selected_ids and not preview and prior.dataset_hash != st.session_state["dataset_hash"]:
                st.warning("Dataset changed — prior evidence cannot be reused.")

    run_clicked = st.button("Run analysis", type="primary")
    if run_clicked:
        if st.session_state.get("df") is None or st.session_state.get("profile") is None:
            st.error("Upload a dataset or enable demo mode.")
        elif not question.strip():
            st.error("Enter a question.")
        else:
            run_id = uuid4().hex
            writer = RunTraceWriter(run_id=run_id, base_dir=config.run_trace.base_dir)
            client = _ollama_client(config)
            reuse = select_reusable_evidence(
                prior,
                current_dataset_hash=st.session_state["profile"].dataset_hash,
                selected_ids=selected_ids,
            )
            if reuse:
                writer.log_event(
                    "follow_up_reuse",
                    {
                        "items": [
                            {
                                "evidence_id": item.evidence_id,
                                "reused_from_run_id": item.reused_from_run_id,
                            }
                            for item in reuse
                        ],
                    },
                )
            # Capture run inputs on the main thread; Streamlit session_state is not
            # available from background threads.
            df_for_run = st.session_state["df"]
            profile_for_run = st.session_state["profile"]
            question_for_run = question.strip()

            prior_run_dir: Path | None = None
            if reuse and prior is not None:
                prior_run_dir = Path(config.run_trace.base_dir) / prior.run_id

            run_state: dict[str, Any] = {}
            run_error: list[BaseException] = []

            def _run_agent() -> None:
                try:
                    run_state["result"] = run_agent(
                        question_for_run,
                        df_for_run,
                        config,
                        client,
                        profile=profile_for_run,
                        run_id=run_id,
                        trace_writer=writer,
                        reused_evidence=reuse or None,
                        prior_run_dir=prior_run_dir,
                    )
                except BaseException as exc:  # noqa: BLE001 — propagate to main thread
                    run_error.append(exc)

            with st.status(
                f"Running agent with {config.model.name}…",
                expanded=True,
            ) as status:
                worker = threading.Thread(target=_run_agent, daemon=True)
                worker.start()
                progress_slot = st.empty()
                seen = 0
                while worker.is_alive():
                    events = writer.read_events()
                    if len(events) > seen:
                        seen = len(events)
                        lines = trace_progress_messages(events)
                        progress_slot.markdown(
                            "\n".join(f"- {line}" for line in lines[-12:])
                        )
                    time.sleep(0.35)
                worker.join()
                if run_error:
                    raise run_error[0]
                result = run_state["result"]
                final_lines = trace_progress_messages(writer.read_events())
                if final_lines:
                    progress_slot.markdown(
                        "\n".join(f"- {line}" for line in final_lines[-12:])
                    )
                status.update(
                    label=f"Run finished — {result.status}",
                    state="complete",
                )
            st.session_state["last_result"] = result
            st.session_state["last_writer"] = writer
            st.session_state["last_run_id"] = run_id
            st.session_state["prior_run"] = _snapshot_from_run(
                run_id=run_id,
                dataset_hash=st.session_state["profile"].dataset_hash,
                question=question.strip(),
                writer=writer,
            )

    result = st.session_state.get("last_result")
    writer: RunTraceWriter | None = st.session_state.get("last_writer")
    if result is not None and writer is not None:
        st.subheader("Answer")
        st.write(f"**Status:** {result.status}")
        report_json = writer.run_dir / "report.json"
        if report_json.is_file():
            payload = json.loads(report_json.read_text(encoding="utf-8"))
            legacy = "supported finding(s)" in str(payload.get("summary", "")) and not payload.get(
                "highlights"
            )
            if legacy:
                st.warning(
                    "This report is from an **older build** (audit-style). "
                    "Restart the app (`Ctrl+C`, then `uv run streamlit run app.py`) and click **Run analysis** again."
                )
            if payload.get("summary"):
                st.markdown(f"**{payload['summary']}**")
            findings = payload.get("findings") or []
            multi = next(
                (f for f in findings if len(f.get("numeric_claims") or []) >= 2),
                None,
            )
            if multi:
                rows = sorted(
                    multi["numeric_claims"],
                    key=lambda c: float(c["value"]),
                    reverse=True,
                )
                st.table(
                    {
                        "Category": [
                            str(c["label"]).split(" — ")[0] for c in rows
                        ],
                        "Amount": [f'{float(c["value"]):,.2f}' for c in rows],
                    }
                )
            elif payload.get("highlights"):
                for line in payload["highlights"]:
                    st.markdown(f"- {line}")
        else:
            st.write(result.answer_text)
        with st.expander("Technical answer (agent template)"):
            st.write(result.answer_text)
        if result.dropped_claims:
            with st.expander("Dropped claims (audit)"):
                st.write(", ".join(result.dropped_claims))

        progress_lines = trace_progress_messages(writer.read_events())
        if progress_lines:
            with st.expander("Run progress (summary)"):
                for line in progress_lines:
                    st.markdown(f"- {line}")
        with st.expander("Run trace (raw events)"):
            for event in writer.read_events():
                st.text(f"{event.timestamp}  {event.event_type}")

        report_html = writer.run_dir / "report.html"
        if report_json.is_file():
            with st.expander("Report JSON (full)"):
                st.json(json.loads(report_json.read_text(encoding="utf-8")))
        if report_html.is_file():
            st.download_button(
                "Download HTML report",
                data=report_html.read_bytes(),
                file_name=f"{st.session_state['last_run_id']}_report.html",
                mime="text/html",
            )


if __name__ == "__main__":
    main()