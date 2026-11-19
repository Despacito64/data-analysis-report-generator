#!/usr/bin/env python3
"""Model-free check of what the evaluation path can score.

For each frozen question this feeds hand-written candidate plans (the baseline's
own plan, plus a few alternatives for the questions the agent failed) through the
same executor, answer extraction and scorer that the real runs use, with a mock
model that simply returns the plan. No LLM is called, so the result depends only
on the tools, the extractor and the oracle, not on planning ability.

    uv run python scripts/ceiling_check.py
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from da_agent.agent.baseline import BASELINE_TASKS
from da_agent.agent.planner import MockLLMClient
from da_agent.core.config import load_config
from evaluation.run_agent_eval import evaluate_agent

DATE = "Order Date"


def chain(steps: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"t{i + 1}",
            "tool": tool,
            "args": args,
            "depends_on": [f"t{i}"] if i else [],
            "rationale": "candidate step",
        }
        for i, (tool, args) in enumerate(steps)
    ]


def gagg(by: str, metric: str, agg: str = "sum") -> tuple[str, dict[str, Any]]:
    return ("group_aggregate", {"by": [by], "metric_column": metric, "aggregation": agg})


def rank(entity: str, metric: str, asc: bool, n: int) -> tuple[str, dict[str, Any]]:
    return (
        "rank",
        {"entity_column": entity, "metric_column": metric, "ascending": asc, "top_n": n},
    )


def flt(column: str, value: str) -> tuple[str, dict[str, Any]]:
    return ("filter", {"conditions": [{"column": column, "operator": "eq", "value": value}]})


YEAR_2017 = (
    "filter",
    {
        "conditions": [
            {"column": DATE, "operator": "gte", "value": "2017-01-01"},
            {"column": DATE, "operator": "lte", "value": "2017-12-31"},
        ]
    },
)
TREND_M = (
    "trend",
    {"date_column": DATE, "metric_column": "Sales", "grain": "monthly", "aggregation": "sum"},
)
TREND_Q = (
    "trend",
    {"date_column": DATE, "metric_column": "Profit", "grain": "quarterly", "aggregation": "sum"},
)

# Extra candidates for the seven questions the agent failed.
EXTRA: dict[str, dict[str, list[tuple[str, dict[str, Any]]]]] = {
    "q01": {
        "filter then group_aggregate(Ship Mode)": [
            flt("Ship Mode", "First Class"),
            gagg("Ship Mode", "Sales"),
        ],
        "group_aggregate(Ship Mode) only": [gagg("Ship Mode", "Sales")],
    },
    "q06": {
        "group_aggregate only": [gagg("Sub-Category", "Sales")],
        "rank only": [rank("Sub-Category", "Sales", False, 5)],
    },
    "q07": {
        "group_aggregate only": [gagg("State", "Profit")],
        "rank only": [rank("State", "Profit", False, 3)],
    },
    "q08": {
        "group_aggregate only": [gagg("Sub-Category", "Profit")],
        "rank only": [rank("Sub-Category", "Profit", True, 5)],
    },
    "q11": {"filter 2017 then trend": [YEAR_2017, TREND_M], "trend only": [TREND_M]},
    "q12": {"trend (quarterly)": [TREND_Q]},
    "q20": {
        "filter then rank": [flt("Segment", "Consumer"), rank("City", "Sales", False, 3)],
        "filter then group_aggregate": [flt("Segment", "Consumer"), gagg("City", "Sales")],
    },
}


def run_candidate(qid: str, steps, tmp: Path) -> dict[str, Any]:
    config = load_config()
    config = config.model_copy(
        update={"run_trace": config.run_trace.model_copy(update={"base_dir": str(tmp / "traces")})}
    )
    client = MockLLMClient(default_response={"tasks": chain(steps)})
    summary = evaluate_agent(
        dataset_path=Path("Sample-Superstore.csv"),
        oracle_path=Path("evaluation/benchmark/oracle.json"),
        questions_path=Path("evaluation/benchmark/questions.json"),
        results_dir=tmp / "results",
        run_id=f"{qid}_{abs(hash(json.dumps(steps, default=str))) % 10**8}",
        selected_question_ids=[qid],
        mode="mock",
        client=client,
        config=config,
        max_replans=0,
    )
    row = next(r for r in summary["per_question"] if r["question_id"] == qid)
    attempt = summary["runs"][0]
    return {
        "status": row["status"],
        "reason": attempt.get("failure_reason"),
        "answer": json.dumps(attempt.get("answer"), default=str)[:70],
    }


def main() -> None:
    questions = {
        q["id"]: q for q in json.loads(Path("evaluation/benchmark/questions.json").read_text())
    }
    results: list[tuple[str, str, dict[str, Any]]] = []
    print(f"{'q':4s} {'candidate plan':40s} {'status':8s} {'reason':22s} answer", flush=True)
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        for qid in questions:
            steps = list(BASELINE_TASKS[qid])
            if qid == "q11":
                steps = [YEAR_2017, *steps]
            jobs = [("baseline's own plan", steps), *EXTRA.get(qid, {}).items()]
            for label, plan in jobs:
                r = run_candidate(qid, plan, tmp)
                results.append((qid, label, r))
                print(
                    f"{qid:4s} {label:40s} {r['status']:8s} {r['reason'] or ''!s:22s} {r['answer']}",
                    flush=True,
                )
    passable = sorted({qid for qid, _, r in results if r["status"] == "passed"})
    out = Path("docs/report/generated")
    out.mkdir(parents=True, exist_ok=True)
    (out / "ceiling_check.json").write_text(
        json.dumps(
            {
                "reachable": passable,
                "candidates": [{"question": q, "plan": label, **r} for q, label, r in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nquestions with at least one passing candidate: {len(passable)}/20")
    print("none passed:", sorted(set(questions) - set(passable)))


if __name__ == "__main__":
    main()
