"""Follow-up session rules: explicit evidence selection and dataset-hash equality."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts.models import EvidenceRecord


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