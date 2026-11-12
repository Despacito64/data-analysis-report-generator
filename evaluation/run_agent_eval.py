"""Run and score the dynamic agent against the frozen oracle and fixed baseline."""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any
from uuid import uuid4

from da_agent.agent.answer import AgentAnswerStatus, AgentResult
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_agent, run_baseline

try:
    from evaluation.oracle import load_oracle
    from evaluation.scorer import answers_match, score_baseline
except ModuleNotFoundError:
    from oracle import load_oracle
    from scorer import answers_match, score_baseline


def _grouped_values(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows or any("value" not in row for row in rows):
        return None
    result: dict[str, Any] = {}
    for row in rows:
        group_keys = row.get("group_keys", {})
        if not group_keys:
            if len(rows) == 1:
                return row["value"]
            return None
        result[" | ".join(str(value) for value in group_keys.values())] = row["value"]
    return result


def extract_score_answer(result: AgentResult) -> Any | None:
    """Shape recorded tool outputs into the corresponding oracle answer structure."""
    if result.status != AgentAnswerStatus.ANSWERED:
        return None

    evidence_by_task = {item.task_id: item for item in result.evidence}
    candidates = [
        (task.tool, evidence_by_task[task.task_id])
        for task in reversed(result.task_results)
        if task.task_id in evidence_by_task
    ]
    seen_task_ids = {evidence.task_id for _, evidence in candidates}
    candidates.extend(
        (evidence.tool, evidence)
        for evidence in reversed(result.evidence)
        if evidence.task_id not in seen_task_ids
    )
    for tool, evidence in candidates:
        output = evidence.tool_output
        if tool == "group_aggregate":
            answer = _grouped_values(output.get("rows", []))
            if answer is not None:
                return answer
        elif tool == "filter" and "how many" in result.question.casefold():
            return output.get("output_row_count")
        elif tool == "rank":
            rows = output.get("rows", [])
            if rows:
                return [row["entity"] for row in rows]
        elif tool == "period_compare":
            base = output.get("base_period", {})
            comparison = output.get("compare_period", {})
            return {
                "base_value": base.get("value"),
                "compare_value": comparison.get("value"),
                "absolute_change": output.get("absolute_change"),
                "relative_growth": output.get("relative_growth"),
            }
        elif tool == "trend":
            points = {
                row["period"]: row["value"]
                for row in output.get("points", [])
                if row.get("present") and row.get("value") is not None
            }
            return {
                "points": points,
                "slope": output.get("slope"),
                "direction": output.get("direction"),
            }
        elif tool == "segment_contribution":
            return {
                "total_value": output.get("total_value"),
                "shares": {row["segment"]: row["share"] for row in output.get("segments", [])},
            }
        elif tool == "correlation":
            return output.get("correlation")
        elif tool == "detect_anomalies_iqr":
            return {
                key: output.get(key)
                for key in ("q1", "q3", "iqr", "lower_fence", "upper_fence", "flagged_count")
            }
    return None


def _trace_metrics(writer: RunTraceWriter) -> dict[str, int]:
    events = writer.read_events()
    return {
        "repair_attempts": sum(event.event_type == "planner_repair_attempt" for event in events),
        "replans": sum(event.event_type == "replan_attempt" for event in events),
        "tool_calls": sum(event.event_type == "tool_call" for event in events),
    }


def build_comparison(
    *,
    agent_answers: dict[str, Any],
    baseline_answers: dict[str, Any],
    oracle: dict[str, dict[str, Any]],
    agent_metrics: dict[str, Any],
) -> dict[str, Any]:
    """Compare scored results per question and summarize metric inputs."""
    agent_score = score_baseline(agent_answers, oracle)
    baseline_score = score_baseline(baseline_answers, oracle)
    per_question: list[dict[str, Any]] = []
    for question_id, entry in oracle.items():
        expected = entry["expected_answer"]
        agent_correct = question_id in agent_answers and answers_match(
            agent_answers[question_id], expected, float(entry["tolerance"])
        )
        baseline_correct = question_id in baseline_answers and answers_match(
            baseline_answers[question_id], expected, float(entry["tolerance"])
        )
        if question_id not in agent_answers:
            outcome = (
                "unscored"
                if agent_metrics.get("unscored_questions", {}).get(question_id)
                else "loss"
            )
        elif agent_correct == baseline_correct:
            outcome = "tie"
        else:
            outcome = "win" if agent_correct else "loss"
        per_question.append(
            {
                "question_id": question_id,
                "agent_correct": agent_correct if question_id in agent_answers else None,
                "baseline_correct": baseline_correct,
                "outcome": outcome,
            }
        )
    return {
        "agent": {
            "correct": agent_score.correct,
            "total": agent_score.total,
            "accuracy": agent_score.accuracy,
        },
        "baseline": {
            "correct": baseline_score.correct,
            "total": baseline_score.total,
            "accuracy": baseline_score.accuracy,
            "note": "The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.",
        },
        "metrics": agent_metrics,
        "per_question": per_question,
    }


def render_markdown_summary(summary: dict[str, Any], json_path: Path) -> str:
    """Render a concise human-readable score and question comparison."""
    lines = [
        "# Dynamic agent evaluation",
        "",
        f"Detailed results: `{json_path}`",
        "",
        "| Variant | Correct | Total | Accuracy |",
        "| --- | ---: | ---: | ---: |",
    ]
    for variant in ("agent", "baseline"):
        score = summary[variant]
        lines.append(
            f"| {variant} | {score['correct']} | {score['total']} | {score['accuracy']:.3f} |"
        )
    lines.extend(
        [
            "",
            summary["baseline"]["note"],
            "",
            "## Agent run metrics",
            "",
        ]
    )
    for name, value in summary["metrics"].items():
        if name != "unscored_questions":
            lines.append(f"- {name}: {value}")
    lines.extend(
        [
            "",
            "## Per-question outcome",
            "",
            "| Question | Agent | Baseline | Outcome |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in summary["per_question"]:
        if "agent_correct_rate" in row:
            agent = f"{row['agent_correct_rate']:.3f}"
        else:
            agent = "unscored" if row["agent_correct"] is None else str(row["agent_correct"])
        lines.append(
            f"| {row['question_id']} | {agent} | {row['baseline_correct']} | {row['outcome']} |"
        )
    lines.append("")
    return "\n".join(lines)


def evaluate_agent(
    *,
    dataset_path: Path,
    oracle_path: Path,
    questions_path: Path,
    results_dir: Path,
    model: str | None = None,
    repeats: int = 1,
) -> dict[str, Any]:
    """Run all frozen questions through the free-text agent and compare with baseline."""
    if repeats < 1:
        raise ValueError("repeats must be at least one")
    config = load_config()
    if model:
        config = config.model_copy(
            update={"model": config.model.model_copy(update={"name": model})}
        )
    df = load_data(dataset_path)
    profile = compute_profile(df, file_path=dataset_path)
    oracle = load_oracle(oracle_path)
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    baseline = run_baseline(df=df, profile=profile, budgets=config.budgets)

    raw_runs: list[dict[str, Any]] = []
    latencies: list[float] = []
    repair_runs = replan_runs = valid_plans = tool_calls = repair_attempts = 0
    correct_by_question: Counter[str] = Counter()
    failure_categories: Counter[str] = Counter()
    unscored_questions: dict[str, str] = {}

    for item in questions:
        question_id = item["id"]
        for repeat in range(1, repeats + 1):
            run_id = f"agent_eval_{question_id}_r{repeat}_{uuid4().hex[:8]}"
            writer = RunTraceWriter(run_id=run_id, base_dir=config.run_trace.base_dir)
            started = time.perf_counter()
            result = run_agent(
                item["question"],
                df,
                config,
                run_id=run_id,
                profile=profile,
                trace_writer=writer,
            )
            latency = time.perf_counter() - started
            metrics = _trace_metrics(writer)
            latencies.append(latency)
            repair_runs += metrics["repair_attempts"] > 0
            replan_runs += metrics["replans"] > 0
            repair_attempts += metrics["repair_attempts"]
            tool_calls += metrics["tool_calls"]
            valid_plans += result.plan is not None
            for failure in result.failures:
                failure_name = getattr(failure.failure_class, "value", failure.failure_class)
                failure_categories[str(failure_name)] += 1

            answer = extract_score_answer(result)
            is_correct = answer is not None and answers_match(
                answer,
                oracle[question_id]["expected_answer"],
                float(oracle[question_id]["tolerance"]),
            )
            correct_by_question[question_id] += is_correct
            if answer is None:
                unscored_questions[question_id] = (
                    "No score-shaped answer could be assembled from successful tool evidence."
                )
            raw_runs.append(
                {
                    "question_id": question_id,
                    "repeat": repeat,
                    "run_id": run_id,
                    "status": result.status.value,
                    "answer": answer,
                    "correct": is_correct,
                    "plan_valid": result.plan is not None,
                    "repair_attempts": metrics["repair_attempts"],
                    "replans": metrics["replans"],
                    "tool_calls": metrics["tool_calls"],
                    "latency_s": latency,
                    "failure_categories": [
                        str(getattr(failure.failure_class, "value", failure.failure_class))
                        for failure in result.failures
                    ],
                }
            )

    count_runs = len(raw_runs) or 1
    per_question_latency = {
        item["id"]: mean(run["latency_s"] for run in raw_runs if run["question_id"] == item["id"])
        for item in questions
    }
    metrics_summary = {
        "runs": len(raw_runs),
        "repeats_per_question": repeats,
        "plan_validity_rate": valid_plans / count_runs,
        "repair_rate": repair_runs / count_runs,
        "repair_attempts_per_run": repair_attempts / count_runs,
        "replan_rate": replan_runs / count_runs,
        "tool_calls_per_run": tool_calls / count_runs,
        "mean_latency_s": mean(latencies) if latencies else 0.0,
        "mean_latency_by_question_s": per_question_latency,
        "failure_categories": dict(failure_categories),
        "unscored_questions": unscored_questions,
    }
    comparison = build_comparison(
        agent_answers={},
        baseline_answers=baseline.answers,
        oracle=oracle,
        agent_metrics=metrics_summary,
    )
    run_correct = sum(run["correct"] for run in raw_runs)
    comparison["agent"] = {
        "correct": run_correct,
        "total": len(raw_runs),
        "accuracy": run_correct / count_runs,
        "attempted_runs": len(raw_runs),
    }
    comparison["evaluation"] = {
        "mode": "real",
        "model": config.model.name,
        "dataset": str(dataset_path),
        "repeats_per_question": repeats,
    }
    per_question_runs = {
        item["id"]: [run for run in raw_runs if run["question_id"] == item["id"]]
        for item in questions
    }
    for row in comparison["per_question"]:
        runs = per_question_runs[row["question_id"]]
        correct_runs = sum(run["correct"] for run in runs)
        rate = correct_runs / len(runs) if runs else 0.0
        row["agent_correct_rate"] = rate
        row["agent_correct"] = bool(runs) and correct_runs == len(runs)
        if runs and all(run["answer"] is None for run in runs):
            row["outcome"] = "unscored"
        elif rate == float(row["baseline_correct"]):
            row["outcome"] = "tie"
        else:
            row["outcome"] = "win" if rate > float(row["baseline_correct"]) else "loss"
    comparison["runs"] = raw_runs
    results_dir.mkdir(parents=True, exist_ok=True)
    json_path = results_dir / "agent_eval.json"
    markdown_path = results_dir / "agent_eval.md"
    json_path.write_text(json.dumps(comparison, indent=2, default=str) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_markdown_summary(comparison, json_path) + "\n", encoding="utf-8"
    )
    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("Sample-Superstore.csv"))
    parser.add_argument("--oracle", type=Path, default=Path("evaluation/benchmark/oracle.json"))
    parser.add_argument(
        "--questions", type=Path, default=Path("evaluation/benchmark/questions.json")
    )
    parser.add_argument("--results-dir", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--model")
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    summary = evaluate_agent(
        dataset_path=args.dataset,
        oracle_path=args.oracle,
        questions_path=args.questions,
        results_dir=args.results_dir,
        model=args.model,
        repeats=args.repeats,
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "runs"}, indent=2))


if __name__ == "__main__":
    main()
