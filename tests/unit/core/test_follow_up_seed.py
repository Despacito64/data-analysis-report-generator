"""Follow-up evidence is pre-seeded into a new run trace and store."""

import json

from da_agent.contracts.models import EvidenceRecord
from da_agent.core.follow_up import ReusedEvidence, seed_reused_evidence
from da_agent.core.trace import RunTraceWriter


def _record(evidence_id: str, dataset_hash: str) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        task_id="t1",
        tool="group_aggregate",
        args_hash="ab12cd34",
        dataset_hash=dataset_hash,
        input_row_count=1,
        result_summary={"total_groups": 1, "sample_groups": [{"value": 42.0}]},
        result_schema_version="0.1.0",
    )


def test_seed_reused_evidence_logs_and_populates_store(tmp_path) -> None:
    writer = RunTraceWriter(run_id="new", base_dir=tmp_path)
    prior_dir = tmp_path / "prior"
    prior_dir.mkdir(parents=True)
    ev_dir = prior_dir / "evidence"
    ev_dir.mkdir()
    (ev_dir / "ev1.json").write_text(
        json.dumps({"rows": [{"group_keys": {"Category": "Tech"}, "value": 99.0}]}),
        encoding="utf-8",
    )
    reused = [
        ReusedEvidence(
            evidence_id="ev1",
            reused_from_run_id="prior",
            record=_record("ev1", "hash-a"),
        )
    ]
    records, ids, store = seed_reused_evidence(
        reused,
        current_dataset_hash="hash-a",
        trace_writer=writer,
        prior_run_dir=prior_dir,
    )
    assert ids == ["ev1"]
    assert "ev1" in records
    assert store["ev1"]["rows"][0]["value"] == 99.0
    event_types = [e.event_type for e in writer.read_events()]
    assert "evidence_reused" in event_types
    assert "evidence" in event_types


def test_seed_skips_hash_mismatch() -> None:
    reused = [
        ReusedEvidence(
            evidence_id="ev1",
            reused_from_run_id="prior",
            record=_record("ev1", "hash-a"),
        )
    ]
    records, ids, store = seed_reused_evidence(
        reused,
        current_dataset_hash="hash-b",
    )
    assert ids == []
    assert records == {}
    assert store == {}