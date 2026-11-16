"""Dependent-evidence invalidation cascade.

Layer 4 module: strictly imports contracts and core; NEVER imports da_agent.tools,
da_agent.agent, da_agent.reports, da_agent.pipeline, or evaluation.
Given a task graph, evidence store, and findings, deterministically cascades
invalidation from a root EvidenceRecord to all downstream tasks, evidence records,
findings, and claims.
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts.models import (
    EvidenceRecord,
    Finding,
    Task,
    TaskStatus,
)
from da_agent.core.trace import RunTraceWriter


class InvalidationTargetType(str, Enum):
    """Categorization of entities invalidated during a cascade."""

    EVIDENCE = "evidence"
    TASK = "task"
    FINDING = "finding"
    CLAIM = "claim"


class InvalidationPathRecord(BaseModel):
    """Provenance path explaining why an entity was invalidated."""

    model_config = ConfigDict(extra="forbid")

    target_type: InvalidationTargetType
    target_id: str
    root_evidence_id: str
    path: list[str]
    reason: str


class InvalidationResult(BaseModel):
    """Audit report detailing all entities invalidated by an evidence invalidation."""

    model_config = ConfigDict(extra="forbid")

    root_evidence_id: str
    reason: str
    invalidated_evidence_ids: list[str] = Field(default_factory=list)
    invalidated_task_ids: list[str] = Field(default_factory=list)
    invalidated_finding_indices: list[int] = Field(default_factory=list)
    invalidated_claims: list[dict[str, Any]] = Field(default_factory=list)
    cascade_paths: list[InvalidationPathRecord] = Field(default_factory=list)
    total_invalidated_evidence: int = 0
    total_invalidated_tasks: int = 0
    total_invalidated_findings: int = 0
    total_invalidated_claims: int = 0


def _extract_referenced_task_ids(args: dict[str, Any]) -> set[str]:
    """Extract upstream task IDs referenced in task arguments ($task_id or $ref)."""
    refs: set[str] = set()

    def _traverse(item: Any) -> None:
        if isinstance(item, dict):
            if "$ref" in item and isinstance(item["$ref"], str):
                parts = item["$ref"].split(".")
                if parts:
                    refs.add(parts[0])
            for v in item.values():
                _traverse(v)
        elif isinstance(item, list):
            for v in item:
                _traverse(v)
        elif isinstance(item, str) and item.startswith("$"):
            token = item[1:].split(".")[0]
            if token:
                refs.add(token)

    _traverse(args)
    return refs


def invalidate_evidence(
    root_evidence_id: str,
    *,
    tasks: list[Task] | None = None,
    evidence_store: dict[str, EvidenceRecord],
    findings: list[Finding] | None = None,
    reason: str = "Invalidated upstream evidence",
    trace_writer: RunTraceWriter | None = None,
) -> InvalidationResult:
    """Deterministically cascade invalidation from root_evidence_id through tasks, evidence, findings, and claims.

    Guarantees:
      - Terminates on any finite DAG.
      - Handles diamond-shaped dependency graphs without duplicate paths or entities.
      - Keeps completed evidence on independent branches valid and untouched.
      - Marks invalidated evidence records (valid=False, invalidated_by=root_evidence_id).
      - Logs additive optional event to trace_writer when provided.
    """
    tasks_list = tasks or []
    tasks_by_id: dict[str, Task] = {t.id: t for t in tasks_list}

    # 1. Locate the root evidence record and its producing task
    root_record = evidence_store.get(root_evidence_id)
    root_task_id: str | None = None
    if root_record is not None:
        root_task_id = root_record.task_id
    else:
        # Fallback: scan tasks if evidence_id contains task id or matches
        for t in tasks_list:
            if t.id in root_evidence_id:
                root_task_id = t.id
                break

    # 2. Build forward adjacency graph for tasks: parent_task_id -> sorted list of child_task_ids
    dependents: dict[str, set[str]] = {t.id: set() for t in tasks_list}
    for t in tasks_list:
        # Direct depends_on
        for dep in t.depends_on:
            if dep in dependents:
                dependents[dep].add(t.id)
        # References in arguments
        for arg_ref in _extract_referenced_task_ids(t.args):
            if arg_ref in dependents:
                dependents[arg_ref].add(t.id)

    # 3. Track invalidations and paths
    invalidated_evidence_set: set[str] = {root_evidence_id}
    invalidated_task_set: set[str] = set()
    cascade_paths: list[InvalidationPathRecord] = []

    # Mark root evidence record
    if root_record is not None:
        root_record.valid = False
        root_record.invalidated_by = root_evidence_id

    cascade_paths.append(
        InvalidationPathRecord(
            target_type=InvalidationTargetType.EVIDENCE,
            target_id=root_evidence_id,
            root_evidence_id=root_evidence_id,
            path=[root_evidence_id],
            reason=reason,
        )
    )

    # 4. Cascade through downstream tasks via deterministic BFS
    # Queue carries (current_task_id, path_so_far)
    queue: deque[tuple[str, list[str]]] = deque()

    # Determine initial tasks affected
    if root_task_id and root_task_id in dependents:
        for child_id in sorted(dependents[root_task_id]):
            if child_id not in invalidated_task_set:
                invalidated_task_set.add(child_id)
                queue.append((child_id, [root_evidence_id, root_task_id, child_id]))

    while queue:
        curr_task_id, current_path = queue.popleft()
        curr_task = tasks_by_id.get(curr_task_id)

        # Invalidate task status if in tasks list
        if curr_task is not None and curr_task.status != TaskStatus.FAILED:
            curr_task.status = TaskStatus.CANCELLED

        cascade_paths.append(
            InvalidationPathRecord(
                target_type=InvalidationTargetType.TASK,
                target_id=curr_task_id,
                root_evidence_id=root_evidence_id,
                path=list(current_path),
                reason=f"Downstream dependency on invalidated task '{current_path[-2]}'",
            )
        )

        # Invalidate all evidence produced by curr_task_id
        for ev_id, ev_rec in sorted(evidence_store.items()):
            if ev_rec.task_id == curr_task_id and ev_id not in invalidated_evidence_set:
                invalidated_evidence_set.add(ev_id)
                ev_rec.valid = False
                ev_rec.invalidated_by = root_evidence_id
                ev_path = current_path + [ev_id]
                cascade_paths.append(
                    InvalidationPathRecord(
                        target_type=InvalidationTargetType.EVIDENCE,
                        target_id=ev_id,
                        root_evidence_id=root_evidence_id,
                        path=ev_path,
                        reason=f"Produced by invalidated task '{curr_task_id}'",
                    )
                )

        # Enqueue downstream dependents in deterministic sorted order (diamond deduplication)
        for next_task_id in sorted(dependents.get(curr_task_id, set())):
            if next_task_id not in invalidated_task_set:
                invalidated_task_set.add(next_task_id)
                queue.append((next_task_id, current_path + [next_task_id]))

    # 5. Invalidate findings and claims linking to any invalidated evidence
    invalidated_finding_indices: list[int] = []
    invalidated_claims: list[dict[str, Any]] = []

    if findings:
        for f_idx, finding in enumerate(findings):
            finding_invalidated = False
            linked_invalid_evs: list[str] = []

            # Check finding's direct evidence_ids
            for ev_id in finding.evidence_ids:
                if ev_id in invalidated_evidence_set:
                    finding_invalidated = True
                    linked_invalid_evs.append(ev_id)

            # Check finding's numeric claims
            for claim in finding.numeric_claims:
                if claim.evidence_id in invalidated_evidence_set:
                    finding_invalidated = True
                    if claim.evidence_id not in linked_invalid_evs:
                        linked_invalid_evs.append(claim.evidence_id)
                    invalidated_claims.append(
                        {
                            "finding_index": f_idx,
                            "label": claim.label,
                            "value": claim.value,
                            "evidence_id": claim.evidence_id,
                            "reason": f"Linked evidence '{claim.evidence_id}' was invalidated",
                        }
                    )
                    cascade_paths.append(
                        InvalidationPathRecord(
                            target_type=InvalidationTargetType.CLAIM,
                            target_id=f"finding_{f_idx}:{claim.label}",
                            root_evidence_id=root_evidence_id,
                            path=[claim.evidence_id, f"finding_{f_idx}:{claim.label}"],
                            reason=f"Claim links to invalidated evidence '{claim.evidence_id}'",
                        )
                    )

            if finding_invalidated:
                invalidated_finding_indices.append(f_idx)
                cascade_paths.append(
                    InvalidationPathRecord(
                        target_type=InvalidationTargetType.FINDING,
                        target_id=f"finding_{f_idx}",
                        root_evidence_id=root_evidence_id,
                        path=[linked_invalid_evs[0], f"finding_{f_idx}"],
                        reason=f"Finding depends on invalidated evidence: {linked_invalid_evs}",
                    )
                )

    result = InvalidationResult(
        root_evidence_id=root_evidence_id,
        reason=reason,
        invalidated_evidence_ids=sorted(invalidated_evidence_set),
        invalidated_task_ids=sorted(invalidated_task_set),
        invalidated_finding_indices=sorted(invalidated_finding_indices),
        invalidated_claims=invalidated_claims,
        cascade_paths=cascade_paths,
        total_invalidated_evidence=len(invalidated_evidence_set),
        total_invalidated_tasks=len(invalidated_task_set),
        total_invalidated_findings=len(invalidated_finding_indices),
        total_invalidated_claims=len(invalidated_claims),
    )

    if trace_writer is not None:
        trace_writer.log_event("evidence_invalidation", result.model_dump(mode="json"))

    return result
