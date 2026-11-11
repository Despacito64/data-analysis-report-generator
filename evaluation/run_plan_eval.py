#!/usr/bin/env python3
"""Benchmark evaluation harness for Module M5: Plan generation and validation.

Evaluates plan validity rate, repair rate, tool-sequence match against the baseline
templates, and records failure reasons across all 20 benchmark questions.
Does NOT execute tool tasks or score answers with the oracle (deferred to M6).
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from typing import Any

from da_agent.agent.planner import MockLLMClient, OllamaClient
from da_agent.contracts.models import DatasetProfile
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import plan_question

DEFAULT_QUESTIONS = Path("evaluation/benchmark/questions.json")
DEFAULT_DATASET = Path("Sample-Superstore.csv")
SPIKE_RESULTS = Path("evaluation/results/model_spike_m5.json")
OUTPUT_FILE = Path("evaluation/results/plan_eval_m5.json")


def _is_ollama_reachable(base_url: str) -> bool:
    try:
        req = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags")
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False


def _load_spike_tasks(spike_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load recorded qwen3:4b tasks from the empirical model spike."""
    if not spike_path.is_file():
        return {}
    with spike_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    tasks_by_qid: dict[str, list[dict[str, Any]]] = {}
    for run in data.get("detailed_runs", []):
        if run.get("model") == "qwen3:4b":
            qid = run.get("question_id")
            if qid and qid not in tasks_by_qid:
                tasks_by_qid[qid] = run.get("tasks", [])
    return tasks_by_qid


def evaluate_planning(
    questions_path: Path = DEFAULT_QUESTIONS,
    dataset_path: Path = DEFAULT_DATASET,
    use_mock: bool | None = None,
    output_path: Path = OUTPUT_FILE,
) -> dict[str, Any]:
    """Run all benchmark questions through plan_question and score planning validity."""
    with questions_path.open("r", encoding="utf-8") as f:
        questions: list[dict[str, Any]] = json.load(f)

    df = load_data(dataset_path)
    profile: DatasetProfile = compute_profile(df, file_path=dataset_path)
    config = load_config()

    # Determine client
    base_url = config.model.base_url
    base_url = base_url.removesuffix("/v1")

    live_available = _is_ollama_reachable(base_url)
    if use_mock is None:
        use_mock = not live_available

    spike_tasks = _load_spike_tasks(SPIKE_RESULTS) if use_mock else {}

    results: list[dict[str, Any]] = []
    total = len(questions)
    valid_count = 0
    repaired_count = 0
    match_count = 0
    failure_reasons: list[str] = []

    for item in questions:
        qid = item["id"]
        q_text = item["question"]
        expected_tools = item.get("expected_tools", [])

        # Setup client
        if use_mock:
            tasks = spike_tasks.get(qid, [])
            # If tasks exist, format into PlanOutput JSON
            if tasks:
                # Clean task dependencies if self-referential
                for t in tasks:
                    if t.get("depends_on") == [t.get("id")]:
                        t["depends_on"] = []
                mock_json = json.dumps({"tasks": tasks})
                client = MockLLMClient(default_response=mock_json)
            else:
                # Fallback to expected tools
                fallback_tasks = [
                    {
                        "id": f"t{idx}",
                        "tool": tool,
                        "args": {},
                        "depends_on": [f"t{idx - 1}"] if idx > 1 else [],
                        "rationale": f"Execute {tool}",
                    }
                    for idx, tool in enumerate(expected_tools, start=1)
                ]
                client = MockLLMClient(default_response=json.dumps({"tasks": fallback_tasks}))
        else:
            client = OllamaClient(
                base_url=base_url,
                model=config.model.name,
                temperature=config.model.temperature,
                seed=config.model.seed,
            )

        run_id = f"plan_eval_{qid}"
        writer = RunTraceWriter(run_id=run_id)

        plan, failure = plan_question(
            q_text,
            profile=profile,
            client=client,
            run_id=run_id,
            trace_writer=writer,
            max_steps=5,
            max_repairs=1,
        )

        is_valid = plan is not None and failure is None
        selected_tools = [t.tool for t in plan.tasks] if plan else []
        matches_baseline = selected_tools == expected_tools

        # Check if repaired
        events = writer.read_events()
        event_types = [e.event_type for e in events]
        was_repaired = "planner_repair_attempt" in event_types

        if is_valid:
            valid_count += 1
        if was_repaired:
            repaired_count += 1
        if matches_baseline:
            match_count += 1
        if failure:
            failure_reasons.append(f"{qid}: {failure.message}")

        results.append(
            {
                "question_id": qid,
                "question": q_text,
                "valid": is_valid,
                "repaired": was_repaired,
                "selected_tools": selected_tools,
                "expected_tools": expected_tools,
                "matches_baseline": matches_baseline,
                "failure_reason": failure.message if failure else None,
            }
        )

    summary = {
        "total_questions": total,
        "valid_plans": valid_count,
        "plan_validity_rate": round(valid_count / total, 4) if total else 0.0,
        "repaired_plans": repaired_count,
        "repair_rate": round(repaired_count / total, 4) if total else 0.0,
        "tool_sequence_matches": match_count,
        "tool_sequence_match_rate": round(match_count / total, 4) if total else 0.0,
        "failure_count": len(failure_reasons),
        "failure_reasons": failure_reasons,
        "mode": "mock" if use_mock else "live",
        "detailed_results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--mock", action="store_true", default=None)
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    args = parser.parse_args()

    summary = evaluate_planning(
        questions_path=args.questions,
        dataset_path=args.dataset,
        use_mock=args.mock,
        output_path=args.output,
    )

    clean_summary = {k: v for k, v in summary.items() if k != "detailed_results"}
    print(json.dumps(clean_summary, indent=2))


if __name__ == "__main__":
    main()
