"""Streamlit UI: upload, question, run progress, report download, follow-ups (M9)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from da_agent.agent.planner import OllamaClient
from da_agent.contracts.models import EvidenceRecord
from da_agent.core.config import load_config
from da_agent.core.follow_up import (
    PriorRunSnapshot,
    apply_new_dataset_hash,
    select_reusable_evidence,
)
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import DataLoadError, load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_agent


def _load_uploaded_file(
    uploaded_name: str,
    payload: bytes,
    *,
    sheet_name: str | None,
) -> tuple[pd.DataFrame, Path]:
    suffix = Path(uploaded_name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(payload)
        temp_path = Path(handle.name)
    sheet: str | int | None = sheet_name.strip() if sheet_name and sheet_name.strip() else None
    if sheet is not None and sheet.isdigit():
        sheet = int(sheet)
    df = load_data(temp_path, sheet_name=sheet)
    return df, temp_path


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


def main() -> None:
    st.set_page_config(page_title="Data analysis agent", layout="wide")
    st.title("Data analysis agent")
    config = load_config()

    if "dataset_hash" not in st.session_state:
        st.session_state["dataset_hash"] = None
        st.session_state["profile"] = None
        st.session_state["df"] = None
        st.session_state["prior_run"] = None
        st.session_state["last_result"] = None
        st.session_state["last_writer"] = None
        st.session_state["last_run_id"] = None

    with st.sidebar:
        st.header("Dataset")
        uploaded = st.file_uploader("CSV or XLSX", type=["csv", "xlsx"])
        sheet_name = st.text_input("Excel sheet (name or index)", value="")

    if uploaded is not None:
        try:
            df, _path = _load_uploaded_file(
                uploaded.name,
                uploaded.getvalue(),
                sheet_name=sheet_name or None,
            )
            profile = compute_profile(df, file_path=uploaded.name)
            st.session_state["prior_run"] = apply_new_dataset_hash(
                st.session_state.get("prior_run"),
                profile.dataset_hash,
            )
            st.session_state["dataset_hash"] = profile.dataset_hash
            st.session_state["profile"] = profile
            st.session_state["df"] = df
            st.success(f"Loaded {len(df):,} rows. Dataset hash: {profile.dataset_hash[:12]}…")
        except DataLoadError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001 — surface loader failures to the user
            st.error(f"Could not load file: {exc}")

    question = st.text_area("Question", height=120, placeholder="Ask about the uploaded dataset…")

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
            st.error("Upload a dataset first.")
        elif not question.strip():
            st.error("Enter a question.")
        else:
            run_id = uuid4().hex
            writer = RunTraceWriter(run_id=run_id, base_dir=config.run_trace.base_dir)
            client = OllamaClient(
                base_url=config.model.base_url,
                model=config.model.name,
                temperature=config.model.temperature,
                seed=config.model.seed,
                timeout_s=config.budgets.per_call_timeout_s,
                thinking_enabled=config.evaluation.thinking_enabled,
                keep_alive=config.evaluation.keep_alive,
            )
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
            with st.spinner("Running agent…"):
                result = run_agent(
                    question.strip(),
                    st.session_state["df"],
                    config,
                    client,
                    profile=st.session_state["profile"],
                    run_id=run_id,
                    trace_writer=writer,
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
        st.write(result.answer_text)
        if result.dropped_claims:
            st.warning("Dropped claims: " + ", ".join(result.dropped_claims))

        with st.expander("Run trace"):
            for event in writer.read_events():
                st.text(f"{event.timestamp}  {event.event_type}")

        report_json = writer.run_dir / "report.json"
        report_html = writer.run_dir / "report.html"
        if report_json.is_file():
            with st.expander("Report preview"):
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