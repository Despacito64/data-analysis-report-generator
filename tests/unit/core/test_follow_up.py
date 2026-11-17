"""M9: follow-up runs must not reuse evidence across dataset identity changes."""

from da_agent.contracts.models import EvidenceRecord
from da_agent.core.follow_up import PriorRunSnapshot, apply_new_dataset_hash, select_reusable_evidence


def _record(evidence_id: str, dataset_hash: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        task_id="t1",
        tool="group_aggregate",
        args_hash="ab12cd34",
        dataset_hash=dataset_hash,
        input_row_count=1,
        result_summary={"value": 1.0},
        result_schema_version="0.1.0",
    )


def test_reuse_requires_matching_dataset_hash_and_explicit_selection() -> None:
    prior = PriorRunSnapshot(
        run_id="r1",
        dataset_hash="hash-a",
        question="Q1",
        evidence_records={"ev1": _record("ev1", "hash-a")},
    )
    selected = select_reusable_evidence(
        prior,
        current_dataset_hash="hash-a",
        selected_ids={"ev1"},
    )
    assert len(selected) == 1
    assert selected[0].evidence_id == "ev1"
    assert selected[0].reused_from_run_id == "r1"

    blocked = select_reusable_evidence(
        prior,
        current_dataset_hash="hash-b",
        selected_ids={"ev1"},
    )
    assert blocked == []


def test_changed_file_clears_prior_run_context() -> None:
    prior = PriorRunSnapshot(
        run_id="r1",
        dataset_hash="hash-a",
        question="Q1",
        evidence_records={"ev1": _record("ev1", "hash-a")},
    )
    assert apply_new_dataset_hash(prior, "hash-b") is None
    assert apply_new_dataset_hash(prior, "hash-a") is prior