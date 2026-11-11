#!/usr/bin/env python3
"""Benchmark evaluation harness for Module M5/M6: Plan generation, repair, and validation.

Evaluates plan validity rate, repair rate, tool-sequence match against the baseline
templates, and records failure reasons across all 20 benchmark questions.
Supports:
  --mode mock (default for CI): fast, deterministic evaluation with mock LLM and repair simulation.
  --mode real: live execution against local Ollama models (e.g. qwen3:4b, qwen3:8b, llama3.1:8b).
  --report-spike: outputs comparative empirical evidence table from benchmark model spike.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
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


def _load_spike_tasks(
    spike_path: Path, model_name: str = "qwen3:4b"
) -> dict[str, list[dict[str, Any]]]:
    """Load recorded tasks for a model from the empirical model spike."""
    if not spike_path.is_file():
        return {}
    with spike_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    tasks_by_qid: dict[str, list[dict[str, Any]]] = {}
    for run in data.get("detailed_runs", []):
        if run.get("model") == model_name:
            qid = run.get("question_id")
            if qid and qid not in tasks_by_qid:
                tasks_by_qid[qid] = run.get("tasks", [])
    return tasks_by_qid


def evaluate_planning(
    questions_path: Path = DEFAULT_QUESTIONS,
    dataset_path: Path = DEFAULT_DATASET,
    mode: str = "mock",
    model_name: str | None = None,
    output_path: Path = OUTPUT_FILE,
) -> dict[str, Any]:
    """Run all benchmark questions through plan_question and score planning validity."""
    with questions_path.open("r", encoding="utf-8") as f:
        questions: list[dict[str, Any]] = json.load(f)

    df = load_data(dataset_path)
    profile: DatasetProfile = compute_profile(df, file_path=dataset_path)
    config = load_config()

    chosen_model = model_name or config.model.name
    use_mock = mode.lower() == "mock"

    base_url = config.model.base_url.removesuffix("/v1")
    if not use_mock and not _is_ollama_reachable(base_url):
        raise ConnectionError(
            f"Ollama server is not reachable at {base_url}. Ensure Ollama is running or use --mode mock."
        )

    spike_tasks = _load_spike_tasks(SPIKE_RESULTS, chosen_model) if use_mock else {}

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
            if tasks:
                # Clean self-referential task dependencies if any
                for t in tasks:
                    if t.get("depends_on") == [t.get("id")]:
                        t["depends_on"] = []

                initial_json = json.dumps({"tasks": tasks})

                # Simulate bounded single-turn repair for known mock failure cases (q03, q08)
                if qid == "q03":
                    # Initial has missing aggregation -> repair supplies aggregation="sum"
                    repaired_tasks = [
                        {
                            "id": "task1",
                            "tool": "group_aggregate",
                            "args": {
                                "by": ["Region"],
                                "metric_column": "Sales",
                                "aggregation": "sum",
                            },
                            "depends_on": [],
                            "rationale": "Repaired: group by Region and sum Sales.",
                        }
                    ]
                    client = MockLLMClient(
                        responses=[initial_json, json.dumps({"tasks": repaired_tasks})]
                    )
                elif qid == "q08":
                    # Initial has empty args -> repair supplies complete rank args
                    repaired_tasks = [
                        {
                            "id": "task1",
                            "tool": "rank",
                            "args": {
                                "entity_column": "Sub-Category",
                                "metric_column": "Profit",
                                "ascending": True,
                                "top_n": 5,
                            },
                            "depends_on": [],
                            "rationale": "Repaired: rank bottom 5 sub-categories by profit ascending.",
                        }
                    ]
                    client = MockLLMClient(
                        responses=[initial_json, json.dumps({"tasks": repaired_tasks})]
                    )
                else:
                    client = MockLLMClient(default_response=initial_json)
            else:
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
                model=chosen_model,
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
        "model": chosen_model,
        "mode": "mock" if use_mock else "real",
        "total_questions": total,
        "valid_plans": valid_count,
        "plan_validity_rate": round(valid_count / total, 4) if total else 0.0,
        "repaired_plans": repaired_count,
        "repair_rate": round(repaired_count / total, 4) if total else 0.0,
        "tool_sequence_matches": match_count,
        "tool_sequence_match_rate": round(match_count / total, 4) if total else 0.0,
        "failure_count": len(failure_reasons),
        "failure_reasons": failure_reasons,
        "detailed_results": results,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    return summary


def print_spike_report(spike_path: Path = SPIKE_RESULTS) -> None:
    """Print comparative empirical table from recorded benchmark model spike."""
    if not spike_path.is_file():
        print(f"Spike results file not found at {spike_path}")
        return
    with spike_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    summary = data.get("summary", {})
    print("=" * 88)
    print(
        "EMPIRICAL BENCHMARK MODEL SPIKE REPORT (20 Benchmark Questions x 3 Runs = 60 Runs/Model)"
    )
    print("=" * 88)
    header = (
        f"{'Model':<14} | {'Valid Tools':<11} | {'Tool Select':<11} | {'Arg Accuracy':<12} "
        f"| {'Schema Fail':<11} | {'Median Lat (s)':<14} | {'TPS':<6}"
    )
    print(header)
    print("-" * 88)
    for model_name, stats in summary.items():
        vt = f"{stats.get('valid_tool_call_rate', 0.0) * 100:.1f}%"
        ts = f"{stats.get('correct_tool_selection_rate', 0.0) * 100:.1f}%"
        aa = f"{stats.get('task_argument_accuracy', 0.0) * 100:.1f}%"
        sf = f"{stats.get('json_or_schema_failure_rate', 0.0) * 100:.1f}%"
        med = f"{stats.get('median_latency_s', 0.0):.2f}s"
        tps = f"{stats.get('mean_tokens_per_second', 0.0):.2f}"
        print(
            f"{model_name:<14} | {vt:<11} | {ts:<11} | {aa:<12} | {sf:<11} | {med:<14} | {tps:<6}"
        )
    print("=" * 88)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--mode", choices=["mock", "real"], default="mock", help="Execution mode ('mock' or 'real')"
    )
    parser.add_argument(
        "--model", type=str, default=None, help="Model name (e.g. qwen3:4b, qwen3:8b, llama3.1:8b)"
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE)
    parser.add_argument(
        "--report-spike", action="store_true", help="Print comparative empirical spike report"
    )
    args = parser.parse_args()

    if args.report_spike:
        print_spike_report()
        return

    summary = evaluate_planning(
        questions_path=args.questions,
        dataset_path=args.dataset,
        mode=args.mode,
        model_name=args.model,
        output_path=args.output,
    )

    clean_summary = {k: v for k, v in summary.items() if k != "detailed_results"}
    print(json.dumps(clean_summary, indent=2))


if __name__ == "__main__":
    main()
