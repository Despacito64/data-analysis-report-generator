"""Unit tests for dependent-evidence invalidation cascade."""

import tempfile
from datetime import UTC, datetime

from da_agent.contracts.models import (
    EvidenceRecord,
    Finding,
    NumericClaim,
    Task,
    TaskStatus,
)
from da_agent.core.config import ClaimValidationConfig, FindingDropPolicy
from da_agent.core.trace import RunTraceWriter
from da_agent.validation.claims import ClaimStatus, validate_findings, validate_single_claim
from da_agent.validation.invalidation import (
    invalidate_evidence,
)


def _make_evidence(
    ev_id: str,
    task_id: str,
    valid: bool = True,
    invalidated_by: str | None = None,
    summary: dict | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=ev_id,
        task_id=task_id,
        tool="group_aggregate",
        args_hash="hash_abc",
        dataset_hash="dataset_123",
        input_row_count=100,
        result_summary=summary or {"total": 500.0},
        result_schema_version="0.1.0",
        valid=valid,
        invalidated_by=invalidated_by,
        created_at=datetime.now(UTC),
    )


def test_linear_chain_invalidation() -> None:
    """Invalidating root evidence in A -> B -> C cascades through all downstream tasks and evidence."""
    t_a = Task(
        id="t_a", tool="filter", args={"col": "Region"}, status=TaskStatus.DONE, rationale="A"
    )
    t_b = Task(
        id="t_b", tool="group_aggregate", depends_on=["t_a"], status=TaskStatus.DONE, rationale="B"
    )
    t_c = Task(id="t_c", tool="rank", depends_on=["t_b"], status=TaskStatus.DONE, rationale="C")

    ev_store = {
        "ev_a": _make_evidence("ev_a", "t_a"),
        "ev_b": _make_evidence("ev_b", "t_b"),
        "ev_c": _make_evidence("ev_c", "t_c"),
    }

    finding = Finding(
        statement="Top category had 500.0 sales",
        numeric_claims=[
            NumericClaim(value=500.0, label="sales", evidence_id="ev_c"),
        ],
        evidence_ids=["ev_c"],
    )

    res = invalidate_evidence(
        root_evidence_id="ev_a",
        tasks=[t_a, t_b, t_c],
        evidence_store=ev_store,
        findings=[finding],
        reason="Upstream filter threshold incorrect",
    )

    # All three evidence records marked invalid
    assert res.invalidated_evidence_ids == ["ev_a", "ev_b", "ev_c"]
    assert ev_store["ev_a"].valid is False
    assert ev_store["ev_b"].valid is False
    assert ev_store["ev_c"].valid is False
    assert ev_store["ev_a"].invalidated_by == "ev_a"
    assert ev_store["ev_b"].invalidated_by == "ev_a"
    assert ev_store["ev_c"].invalidated_by == "ev_a"

    # Downstream tasks t_b and t_c marked cancelled
    assert res.invalidated_task_ids == ["t_b", "t_c"]
    assert t_b.status == TaskStatus.CANCELLED
    assert t_c.status == TaskStatus.CANCELLED

    # Finding and its claim invalidated
    assert res.invalidated_finding_indices == [0]
    assert len(res.invalidated_claims) == 1
    assert res.invalidated_claims[0]["evidence_id"] == "ev_c"

    # Paths trace provenance back to root_evidence_id
    paths = {p.target_id: p.path for p in res.cascade_paths}
    assert paths["ev_a"] == ["ev_a"]
    assert "ev_a" in paths["t_b"]
    assert "ev_a" in paths["t_c"]


def test_diamond_shaped_dependency_cascade_no_duplicates() -> None:
    """Diamond graph A -> (B, C) -> D: invalidating A visits D exactly once without duplicates."""
    t_a = Task(id="t_a", tool="filter", status=TaskStatus.DONE, rationale="Root")
    t_b = Task(
        id="t_b",
        tool="group_aggregate",
        depends_on=["t_a"],
        status=TaskStatus.DONE,
        rationale="Branch 1",
    )
    t_c = Task(
        id="t_c",
        tool="group_aggregate",
        depends_on=["t_a"],
        status=TaskStatus.DONE,
        rationale="Branch 2",
    )
    t_d = Task(
        id="t_d", tool="rank", depends_on=["t_b", "t_c"], status=TaskStatus.DONE, rationale="Join"
    )

    ev_store = {
        "ev_a": _make_evidence("ev_a", "t_a"),
        "ev_b": _make_evidence("ev_b", "t_b"),
        "ev_c": _make_evidence("ev_c", "t_c"),
        "ev_d": _make_evidence("ev_d", "t_d"),
    }

    res = invalidate_evidence(
        root_evidence_id="ev_a",
        tasks=[t_a, t_b, t_c, t_d],
        evidence_store=ev_store,
        reason="Filter corrupted",
    )

    # t_d appears exactly once in invalidated_task_ids
    assert res.invalidated_task_ids == ["t_b", "t_c", "t_d"]
    assert res.total_invalidated_tasks == 3
    assert res.invalidated_evidence_ids == ["ev_a", "ev_b", "ev_c", "ev_d"]
    assert res.total_invalidated_evidence == 4


def test_independent_branch_stays_valid() -> None:
    """Tasks and evidence on an independent DAG branch stay valid when another branch is invalidated."""
    # Branch 1: t_a -> t_b
    t_a = Task(id="t_a", tool="filter", status=TaskStatus.DONE, rationale="A")
    t_b = Task(
        id="t_b", tool="group_aggregate", depends_on=["t_a"], status=TaskStatus.DONE, rationale="B"
    )

    # Branch 2 (independent): t_x -> t_y
    t_x = Task(id="t_x", tool="group_aggregate", status=TaskStatus.DONE, rationale="X")
    t_y = Task(id="t_y", tool="rank", depends_on=["t_x"], status=TaskStatus.DONE, rationale="Y")

    ev_store = {
        "ev_a": _make_evidence("ev_a", "t_a"),
        "ev_b": _make_evidence("ev_b", "t_b"),
        "ev_x": _make_evidence("ev_x", "t_x"),
        "ev_y": _make_evidence("ev_y", "t_y"),
    }

    finding_y = Finding(
        statement="Top product had 200.0",
        numeric_claims=[NumericClaim(value=200.0, label="sales", evidence_id="ev_y")],
        evidence_ids=["ev_y"],
    )

    res = invalidate_evidence(
        root_evidence_id="ev_a",
        tasks=[t_a, t_b, t_x, t_y],
        evidence_store=ev_store,
        findings=[finding_y],
    )

    # Only branch 1 is affected
    assert res.invalidated_task_ids == ["t_b"]
    assert res.invalidated_evidence_ids == ["ev_a", "ev_b"]

    # Branch 2 stays completely valid
    assert ev_store["ev_x"].valid is True
    assert ev_store["ev_x"].invalidated_by is None
    assert ev_store["ev_y"].valid is True
    assert ev_store["ev_y"].invalidated_by is None
    assert t_x.status == TaskStatus.DONE
    assert t_y.status == TaskStatus.DONE
    assert res.invalidated_finding_indices == []
    assert res.invalidated_claims == []


def test_finding_with_two_evidence_links_where_one_is_invalidated() -> None:
    """A finding that cites two evidence records is invalidated if either one is invalidated."""
    ev_store = {
        "ev_1": _make_evidence("ev_1", "t_1"),
        "ev_2": _make_evidence("ev_2", "t_2"),
    }
    t_1 = Task(id="t_1", tool="group_aggregate", status=TaskStatus.DONE, rationale="T1")
    t_2 = Task(id="t_2", tool="group_aggregate", status=TaskStatus.DONE, rationale="T2")

    finding = Finding(
        statement="Comparison between region 1 (500) and region 2 (300)",
        numeric_claims=[
            NumericClaim(value=500.0, label="region1", evidence_id="ev_1"),
            NumericClaim(value=300.0, label="region2", evidence_id="ev_2"),
        ],
        evidence_ids=["ev_1", "ev_2"],
    )

    res = invalidate_evidence(
        root_evidence_id="ev_1",
        tasks=[t_1, t_2],
        evidence_store=ev_store,
        findings=[finding],
    )

    assert 0 in res.invalidated_finding_indices
    # Claim linking to ev_1 is invalidated
    invalidated_labels = [c["label"] for c in res.invalidated_claims]
    assert "region1" in invalidated_labels
    # ev_2 remains valid
    assert ev_store["ev_2"].valid is True


def test_invalidating_leaf_invalidates_only_itself_and_findings() -> None:
    """Invalidating a leaf evidence record does not invalidate upstream tasks or evidence."""
    t_parent = Task(id="t_p", tool="filter", status=TaskStatus.DONE, rationale="Parent")
    t_leaf = Task(
        id="t_l", tool="rank", depends_on=["t_p"], status=TaskStatus.DONE, rationale="Leaf"
    )

    ev_store = {
        "ev_p": _make_evidence("ev_p", "t_p"),
        "ev_l": _make_evidence("ev_l", "t_l"),
    }

    finding_leaf = Finding(
        statement="Leaf rank result was 10.0",
        numeric_claims=[NumericClaim(value=10.0, label="rank", evidence_id="ev_l")],
        evidence_ids=["ev_l"],
    )

    res = invalidate_evidence(
        root_evidence_id="ev_l",
        tasks=[t_parent, t_leaf],
        evidence_store=ev_store,
        findings=[finding_leaf],
    )

    # Only leaf is invalidated
    assert res.invalidated_evidence_ids == ["ev_l"]
    assert res.invalidated_task_ids == []  # No downstream tasks exist
    assert ev_store["ev_p"].valid is True
    assert t_parent.status == TaskStatus.DONE
    assert res.invalidated_finding_indices == [0]


def test_invalidation_wire_to_claim_validator() -> None:
    """Claim validator rejects claims and findings when evidence is invalidated."""
    ev_store = {
        "ev_valid": _make_evidence("ev_valid", "t_v", summary={"sales": 100.0}),
        "ev_inv": _make_evidence("ev_inv", "t_i", summary={"sales": 200.0}),
    }

    t_i = Task(id="t_i", tool="group_aggregate", status=TaskStatus.DONE, rationale="Ti")

    # Invalidate ev_inv
    invalidate_evidence(root_evidence_id="ev_inv", tasks=[t_i], evidence_store=ev_store)

    config = ClaimValidationConfig(drop_policy=FindingDropPolicy.DROP_FINDING)

    # 1. Single claim check directly
    claim_inv = NumericClaim(value=200.0, label="sales", evidence_id="ev_inv")
    claim_rec = validate_single_claim(claim_inv, ev_store["ev_inv"], config, evidence_id="ev_inv")
    assert claim_rec.status == ClaimStatus.UNSUPPORTED
    assert "is invalid" in claim_rec.reason or "invalidated by" in claim_rec.reason

    # 2. validate_findings drops finding that depends on invalidated evidence
    f_good = Finding(
        statement="Good finding with 100.0",
        numeric_claims=[NumericClaim(value=100.0, label="sales", evidence_id="ev_valid")],
        evidence_ids=["ev_valid"],
    )
    f_bad = Finding(
        statement="Bad finding with 200.0",
        numeric_claims=[NumericClaim(value=200.0, label="sales", evidence_id="ev_inv")],
        evidence_ids=["ev_inv"],
    )

    res = validate_findings([f_good, f_bad], ev_store, config)
    assert len(res.validated_findings) == 1
    assert res.validated_findings[0].statement == "Good finding with 100.0"
    assert len(res.rejected_findings) == 1
    assert res.rejected_findings[0].finding.statement == "Bad finding with 200.0"


def test_invalidation_trace_logging() -> None:
    """Invalidation logs additive evidence_invalidation event to RunTraceWriter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tw = RunTraceWriter("run_inv_test", base_dir=tmpdir)
        ev_store = {"ev_1": _make_evidence("ev_1", "t_1")}
        invalidate_evidence(root_evidence_id="ev_1", evidence_store=ev_store, trace_writer=tw)

        trace_events = tw.read_events()
        inv_events = [e for e in trace_events if e.event_type == "evidence_invalidation"]
        assert len(inv_events) == 1
        assert inv_events[0].payload["root_evidence_id"] == "ev_1"
        assert "ev_1" in inv_events[0].payload["invalidated_evidence_ids"]
