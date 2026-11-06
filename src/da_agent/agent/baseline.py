"""Deterministic fixed-workflow baseline for the M4 evaluation questions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from da_agent.contracts.models import (
    Budgets,
    DatasetProfile,
    EvidenceRecord,
    Failure,
    Report,
    RunStatus,
    Task,
)
from da_agent.data.profiler import compute_profile
from da_agent.tools.executor import execute_task

BASELINE_TASKS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "q01": [
        (
            "filter",
            {"conditions": [{"column": "Ship Mode", "operator": "eq", "value": "First Class"}]},
        )
    ],
    "q02": [
        (
            "filter",
            {
                "conditions": [
                    {"column": "Category", "operator": "eq", "value": "Technology"},
                    {"column": "Region", "operator": "eq", "value": "West"},
                ]
            },
        )
    ],
    "q03": [
        ("group_aggregate", {"by": ["Region"], "metric_column": "Sales", "aggregation": "sum"})
    ],
    "q04": [
        ("group_aggregate", {"by": ["Segment"], "metric_column": "Profit", "aggregation": "sum"})
    ],
    "q05": [
        (
            "group_aggregate",
            {"by": ["Category"], "metric_column": "Discount", "aggregation": "mean"},
        )
    ],
    "q06": [
        (
            "group_aggregate",
            {"by": ["Sub-Category"], "metric_column": "Sales", "aggregation": "sum"},
        ),
        (
            "rank",
            {
                "entity_column": "Sub-Category",
                "metric_column": "Sales",
                "ascending": False,
                "top_n": 5,
            },
        ),
    ],
    "q07": [
        ("group_aggregate", {"by": ["State"], "metric_column": "Profit", "aggregation": "sum"}),
        (
            "rank",
            {"entity_column": "State", "metric_column": "Profit", "ascending": False, "top_n": 3},
        ),
    ],
    "q08": [
        (
            "group_aggregate",
            {"by": ["Sub-Category"], "metric_column": "Profit", "aggregation": "sum"},
        ),
        (
            "rank",
            {
                "entity_column": "Sub-Category",
                "metric_column": "Profit",
                "ascending": True,
                "top_n": 5,
            },
        ),
    ],
    "q09": [
        (
            "period_compare",
            {
                "date_column": "Order Date",
                "metric_column": "Sales",
                "aggregation": "sum",
                "base_period": ["2016-01-01", "2016-12-31"],
                "compare_period": ["2017-01-01", "2017-12-31"],
            },
        )
    ],
    "q10": [
        (
            "period_compare",
            {
                "date_column": "Order Date",
                "metric_column": "Profit",
                "aggregation": "sum",
                "base_period": ["2015-01-01", "2015-12-31"],
                "compare_period": ["2016-01-01", "2016-12-31"],
            },
        )
    ],
    "q11": [
        (
            "trend",
            {
                "date_column": "Order Date",
                "metric_column": "Sales",
                "aggregation": "sum",
                "grain": "monthly",
            },
        )
    ],
    "q12": [
        (
            "trend",
            {
                "date_column": "Order Date",
                "metric_column": "Profit",
                "aggregation": "sum",
                "grain": "quarterly",
            },
        )
    ],
    "q13": [("segment_contribution", {"segment_column": "Category", "metric_column": "Sales"})],
    "q14": [("segment_contribution", {"segment_column": "Region", "metric_column": "Sales"})],
    "q15": [("correlation", {"x_column": "Discount", "y_column": "Profit", "method": "pearson"})],
    "q16": [("correlation", {"x_column": "Sales", "y_column": "Profit", "method": "pearson"})],
    "q17": [("detect_anomalies_iqr", {"metric_column": "Sales", "k": 1.5})],
    "q18": [("detect_anomalies_iqr", {"metric_column": "Profit", "k": 1.5})],
    "q19": [
        ("filter", {"conditions": [{"column": "Region", "operator": "eq", "value": "East"}]}),
        ("group_aggregate", {"by": ["Category"], "metric_column": "Profit", "aggregation": "sum"}),
    ],
    "q20": [
        ("filter", {"conditions": [{"column": "Segment", "operator": "eq", "value": "Consumer"}]}),
        ("group_aggregate", {"by": ["City"], "metric_column": "Sales", "aggregation": "sum"}),
        (
            "rank",
            {"entity_column": "City", "metric_column": "Sales", "ascending": False, "top_n": 3},
        ),
    ],
}


@dataclass
class BaselineRun:
    answers: dict[str, Any]
    evidence: dict[str, EvidenceRecord]
    failures: dict[str, Failure]
    report: Report


def _execute(
    question_id: str,
    sequence: int,
    tool: str,
    args: dict[str, Any],
    df: pd.DataFrame,
    profile: DatasetProfile,
    budgets: Budgets,
    evidence_store: dict[str, Any],
) -> tuple[EvidenceRecord | None, Failure | None]:
    task = Task(
        id=f"{question_id}_{sequence}_{tool}",
        tool=tool,
        args=args,
        depends_on=[],
        status="pending",
        plan_version=1,
        rationale="Execute the frozen fixed-workflow template.",
    )
    return execute_task(
        task=task, df=df, profile=profile, budgets=budgets, evidence_store=evidence_store
    )


def _answer(question_id: str, df: pd.DataFrame, evidence_store: dict[str, Any]) -> Any:
    if question_id == "q01":
        matched = evidence_store[
            next(k for k in evidence_store if "_filter_" in k and question_id in k)
        ]["matched_indices"]
        return float(df.loc[matched, "Sales"].sum())
    if question_id == "q02":
        result = next(v for k, v in evidence_store.items() if question_id in k and "filter" in k)
        return int(result["output_row_count"])
    if question_id in {"q06", "q07", "q08", "q20"}:
        result_key = next(k for k in evidence_store if question_id in k and "group_aggregate" in k)
        grouped = evidence_store[result_key]["rows"]
        descending = question_id != "q08"
        ranked = sorted(
            grouped,
            key=lambda row: (
                row["value"] * (-1 if descending else 1),
                str(next(iter(row["group_keys"].values()))),
            ),
        )
        if not descending:
            ranked = sorted(ranked, key=lambda row: row["value"])
        limit = 5 if question_id in {"q06", "q08"} else 3
        return [next(iter(row["group_keys"].values())) for row in ranked[:limit]]

    key = next(k for k in evidence_store if question_id in k)
    result = evidence_store[key]
    parts = key.split("_", 3)
    tool = parts[3].rsplit("_", 1)[0] if len(parts) == 4 else ""
    if tool == "group_aggregate":
        return {
            " | ".join(str(v) for v in row["group_keys"].values()): float(row["value"])
            for row in result["rows"]
        }
    if tool == "rank":
        return [row["entity"] for row in result["rows"]]
    if tool == "period_compare":
        return {
            "base_value": result["base_period"]["value"],
            "compare_value": result["compare_period"]["value"],
            "absolute_change": result["absolute_change"],
            "relative_growth": result["relative_growth"],
        }
    if tool == "trend":
        slope = result["slope"]
        direction = (
            "increasing"
            if slope is not None and slope > 0
            else "decreasing"
            if slope is not None and slope < 0
            else "flat"
        )
        return {
            "points": {row["period"]: row["value"] for row in result["points"] if row["present"]},
            "slope": slope,
            "direction": direction,
        }
    if tool == "segment_contribution":
        return {
            "total_value": result["total_value"],
            "shares": {row["segment"]: row["share"] for row in result["segments"]},
        }
    if tool == "correlation":
        return result["correlation"]
    if tool == "detect_anomalies_iqr":
        return {
            name: result[name]
            for name in ("q1", "q3", "iqr", "lower_fence", "upper_fence", "flagged_count")
        }

    last_key = max((k for k in evidence_store if question_id in k), key=lambda k: k)
    result = evidence_store[last_key]
    if "rows" in result:
        return {
            " | ".join(str(v) for v in row["group_keys"].values()): float(row["value"])
            for row in result["rows"]
        }
    raise ValueError(f"No answer assembly rule for {question_id}")


def run_baseline(*, df: pd.DataFrame, profile: DatasetProfile, budgets: Budgets) -> BaselineRun:
    answers: dict[str, Any] = {}
    evidence_by_question: dict[str, EvidenceRecord] = {}
    failures: dict[str, Failure] = {}
    all_evidence: list[EvidenceRecord] = []

    for question_id, template in BASELINE_TASKS.items():
        working_df = df
        working_profile = profile
        evidence_store: dict[str, Any] = {}
        records: list[EvidenceRecord] = []
        failed = False

        if question_id == "q11":
            working_df = df[pd.to_datetime(df["Order Date"]).dt.year.eq(2017)].copy()
            working_profile = compute_profile(
                working_df, dataset_hash=profile.dataset_hash, source_name=profile.source_name
            )

        for index, (tool, args) in enumerate(template, start=1):
            evidence, failure = _execute(
                question_id, index, tool, args, working_df, working_profile, budgets, evidence_store
            )
            if failure is not None:
                failures[question_id] = failure
                failed = True
                break
            assert evidence is not None
            records.append(evidence)
            if tool == "filter":
                full_result = evidence_store[evidence.evidence_id]
                indices = full_result["matched_indices"]
                working_df = working_df.loc[indices].copy()

        if failed:
            continue
        answers[question_id] = _answer(question_id, df, evidence_store)
        evidence_by_question[question_id] = records[-1]
        all_evidence.extend(records)

    status = RunStatus(
        status="complete" if not failures else "partial",
        reason_code="none" if not failures else "baseline_failure",
        reason_text="All fixed templates completed."
        if not failures
        else "One or more fixed templates failed.",
        dropped_claims=[],
        unvalidated_claims=[],
    )
    report = Report(
        run_id="m4_baseline",
        dataset_hash=profile.dataset_hash,
        question="Frozen benchmark fixed-workflow baseline",
        summary=f"Completed {len(answers)} of 20 benchmark questions.",
        findings=[],
        evidence_appendix=all_evidence,
        status=status,
    )
    return BaselineRun(
        answers=answers, evidence=evidence_by_question, failures=failures, report=report
    )
