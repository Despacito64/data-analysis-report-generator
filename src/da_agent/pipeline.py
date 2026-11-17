"""Unified execution pipeline for the fixed baseline and dynamic agent."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pandas as pd

from da_agent.agent.answer import AgentResult, build_agent_result
from da_agent.agent.baseline import BaselineRun
from da_agent.agent.baseline import run_baseline as _run_baseline
from da_agent.agent.graph import run_agent as _run_agent
from da_agent.agent.planner import LLMClient, OllamaClient, Plan, generate_plan
from da_agent.contracts.models import (
    AnalysisRun,
    Budgets,
    DatasetProfile,
    EvidenceRecord,
    ExecutionStatus,
    Failure,
    KeyNumberCitation,
)
from da_agent.core.config import AppConfig, load_config
from da_agent.core.follow_up import ReusedEvidence
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.reports.delivery import finalize_run_report


def _analysis_run_from_result(
    result: AgentResult,
    *,
    dataset_hash: str,
    graph_status: str,
    evidence_records: dict[str, EvidenceRecord],
) -> AnalysisRun:
    try:
        execution_status = ExecutionStatus(graph_status)
    except ValueError:
        execution_status = ExecutionStatus.FAILED
    return AnalysisRun(
        run_id=result.run_id,
        question=result.question,
        dataset_hash=dataset_hash,
        execution_status=execution_status,
        key_numbers=[
            KeyNumberCitation(
                label=item.label,
                value=item.value,
                task_id=item.task_id,
                evidence_id=item.evidence_id,
            )
            for item in result.key_numbers
        ],
        dropped_claims=list(result.dropped_claims),
        assumptions=list(result.assumptions),
        evidence_records=dict(evidence_records),
        answer_text=result.answer_text,
    )


def run_baseline(
    *,
    df: pd.DataFrame | None = None,
    dataset_path: Path | str | None = None,
    profile: DatasetProfile | None = None,
    budgets: Budgets | None = None,
) -> BaselineRun:
    """Run the deterministic fixed-workflow baseline."""
    if df is None:
        if dataset_path is None:
            dataset_path = Path("Sample-Superstore.csv")
        df = load_data(Path(dataset_path))
    if profile is None:
        profile = compute_profile(df, file_path=Path(dataset_path) if dataset_path else None)
    if budgets is None:
        budgets = load_config().budgets

    return _run_baseline(df=df, profile=profile, budgets=budgets)


def plan_question(
    question: str,
    *,
    df: pd.DataFrame | None = None,
    dataset_path: Path | str | None = None,
    profile: DatasetProfile | None = None,
    client: LLMClient | None = None,
    run_id: str | None = None,
    trace_writer: RunTraceWriter | None = None,
    max_steps: int = 5,
    max_repairs: int = 1,
) -> tuple[Plan | None, Failure | None]:
    """Generate and validate an analytical execution plan for a question.

    Returns (validated_plan, None) on success or (None, failure) on validation failure.
    Audit records including raw LLM output, validation failures, repair attempts,
    and final plan are persisted to the run trace.
    """
    if profile is None:
        if df is None:
            if dataset_path is None:
                dataset_path = Path("Sample-Superstore.csv")
            df = load_data(Path(dataset_path))
        profile = compute_profile(df, file_path=Path(dataset_path) if dataset_path else None)

    if trace_writer is None and run_id is not None:
        trace_writer = RunTraceWriter(run_id=run_id)

    return generate_plan(
        question=question,
        profile=profile,
        client=client,
        trace_writer=trace_writer,
        max_steps=max_steps,
        max_repairs=max_repairs,
    )


def run_agent(
    question: str,
    dataset: pd.DataFrame | Path | str | None = None,
    config: AppConfig | None = None,
    client: LLMClient | None = None,
    *,
    df: pd.DataFrame | None = None,
    dataset_path: Path | str | None = None,
    profile: DatasetProfile | None = None,
    run_id: str | None = None,
    budgets: Budgets | None = None,
    trace_writer: RunTraceWriter | None = None,
    max_replans: int | None = None,
    max_repairs: int = 1,
    emit_report: bool = True,
    reused_evidence: list[ReusedEvidence] | None = None,
    prior_run_dir: Path | None = None,
) -> AgentResult:
    """Run a free-text question through the dynamic graph and return typed results."""
    config = config or load_config()
    if dataset is not None and (df is not None or dataset_path is not None):
        raise ValueError("Provide `dataset` or `df`/`dataset_path`, not both")
    if isinstance(dataset, pd.DataFrame):
        df = dataset
    elif dataset is not None:
        dataset_path = Path(dataset)

    if df is None:
        if dataset_path is None:
            dataset_path = Path("Sample-Superstore.csv")
        df = load_data(Path(dataset_path))
    if profile is None:
        profile = compute_profile(df, file_path=Path(dataset_path) if dataset_path else None)
    if budgets is None:
        budgets = config.budgets
    if run_id is None:
        run_id = uuid4().hex
    if trace_writer is None:
        trace_writer = RunTraceWriter(
            run_id=run_id,
            base_dir=config.run_trace.base_dir,
        )

    if client is None:
        client = OllamaClient(
            base_url=config.model.base_url,
            model=config.model.name,
            temperature=config.model.temperature,
            seed=config.model.seed,
            timeout_s=config.budgets.per_call_timeout_s,
            thinking_enabled=config.evaluation.thinking_enabled,
            keep_alive=config.evaluation.keep_alive,
        )

    state = _run_agent(
        question=question,
        df=df,
        profile=profile,
        run_id=run_id,
        llm_client=client,
        budgets=budgets,
        trace_writer=trace_writer,
        max_replans=max_replans,
        max_repairs=max_repairs,
        reused_evidence=reused_evidence,
        prior_run_dir=prior_run_dir,
    )
    result = build_agent_result(
        run_id=run_id,
        question=question,
        resolved=state.get("resolved"),
        plan=state.get("plan"),
        task_results=state.get("executed_records", []),
        evidence_store=state.get("evidence_store", {}),
        run_status=state["status"],
        failures=state.get("failures", []),
        revisions=state.get("revisions", []),
        trace_writer=trace_writer,
        evidence_records=state.get("evidence_records") or None,
        tasks=state["plan"].tasks if state.get("plan") is not None else None,
        claim_config=config.claim_validation,
    )
    if emit_report:
        evidence_records = state.get("evidence_records") or {}
        analysis_run = _analysis_run_from_result(
            result,
            dataset_hash=profile.dataset_hash,
            graph_status=state["status"],
            evidence_records=evidence_records,
        )
        finalize_run_report(
            analysis_run,
            trace_writer,
            claim_config=config.claim_validation,
        )
    return result
