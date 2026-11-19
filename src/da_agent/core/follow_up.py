"""Follow-up session rules: explicit evidence selection and dataset-hash equality."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts.models import EvidenceRecord
from da_agent.core.trace import RunTraceWriter


class PriorRunSnapshot(BaseModel):
    """Prior run context the UI may offer for an explicit follow-up."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset_hash: str
    question: str
    evidence_records: dict[str, EvidenceRecord] = Field(default_factory=dict)


class ReusedEvidence(BaseModel):
    """Evidence explicitly carried into a follow-up run."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    reused_from_run_id: str
    record: EvidenceRecord


def apply_new_dataset_hash(
    prior: PriorRunSnapshot | None,
    new_dataset_hash: str,
) -> PriorRunSnapshot | None:
    """Drop prior context when the uploaded dataset identity changes."""
    if prior is None:
        return None
    if prior.dataset_hash != new_dataset_hash:
        return None
    return prior


def select_reusable_evidence(
    prior: PriorRunSnapshot | None,
    *,
    current_dataset_hash: str,
    selected_ids: set[str],
) -> list[ReusedEvidence]:
    """Return evidence that may be reused; empty when the dataset hash differs."""
    if prior is None or prior.dataset_hash != current_dataset_hash:
        return []
    reused: list[ReusedEvidence] = []
    for evidence_id in selected_ids:
        record = prior.evidence_records.get(evidence_id)
        if record is None:
            continue
        if record.dataset_hash != current_dataset_hash:
            continue
        reused.append(
            ReusedEvidence(
                evidence_id=evidence_id,
                reused_from_run_id=prior.run_id,
                record=record,
            )
        )
    return reused


def _evidence_store_payload(
    record: EvidenceRecord,
    *,
    prior_run_dir: Path | None,
) -> dict[str, Any]:
    """Prefer full canonical tool JSON from a prior run when available."""
    if prior_run_dir is not None:
        evidence_file = prior_run_dir / "evidence" / f"{record.evidence_id}.json"
        if evidence_file.is_file():
            loaded = json.loads(evidence_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
    return dict(record.result_summary)


def seed_reused_evidence(
    reused: list[ReusedEvidence],
    *,
    current_dataset_hash: str,
    trace_writer: RunTraceWriter | None = None,
    prior_run_dir: Path | None = None,
) -> tuple[dict[str, EvidenceRecord], list[str], dict[str, Any]]:
    """Pre-seed graph executor state from explicitly selected prior evidence."""
    records: dict[str, EvidenceRecord] = {}
    evidence_ids: list[str] = []
    evidence_store: dict[str, Any] = {}
    for item in reused:
        record = item.record
        if record.dataset_hash != current_dataset_hash:
            continue
        if record.evidence_id in records:
            continue
        records[record.evidence_id] = record
        evidence_ids.append(record.evidence_id)
        evidence_store[record.evidence_id] = _evidence_store_payload(
            record,
            prior_run_dir=prior_run_dir,
        )
        if trace_writer is not None:
            trace_writer.log_event(
                "evidence_reused",
                {
                    "evidence_id": record.evidence_id,
                    "reused_from_run_id": item.reused_from_run_id,
                    "tool": record.tool,
                },
            )
            trace_writer.log_evidence(record)
    return records, evidence_ids, evidence_store
