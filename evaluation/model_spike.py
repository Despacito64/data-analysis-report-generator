#!/usr/bin/env python3
"""Run fixed-sampling Ollama planning spikes against the Superstore benchmark.

M4 / M5 Model Spike:
  Evaluates candidate local models (qwen3:4b, qwen3:8b, llama3.1:8b) against
  the 20 frozen benchmark questions in evaluation/benchmark/questions.json.
  Injects registered column names and semantic types from DatasetProfile.
  Measures planning validity (valid_tool_call rate, correct tool selection rate,
  correct argument rate via validate_task_args, latency, schema failure rate).
  Does not score final answers with the oracle.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, ValidationError

from da_agent.contracts.models import DatasetProfile, Task
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.tools.registry import DEFAULT_REGISTRY
from da_agent.validation.args import validate_task_args

MODELS = ("qwen3:4b", "qwen3:8b", "llama3.1:8b")
TEMPERATURE = 0.0
SEED = 42
OLLAMA_HOST = "http://localhost:11434"
DEFAULT_JSON_OUTPUT = Path("evaluation/results/model_spike_m5.json")
DEFAULT_CSV_OUTPUT = Path("evaluation/results/model_spike_m5.csv")

RESULT_FIELDS = (
    "model",
    "question_id",
    "run_number",
    "schema_valid",
    "json_or_schema_failure",
    "valid_tool_call",
    "correct_tool_selection",
    "correct_argument",
    "tasks_count",
    "valid_tasks_count",
    "latency_s",
    "tokens_per_second",
    "selected_tools",
    "expected_tools",
    "retries_used",
)


class SpikeOutput(BaseModel):
    """Response envelope validated by the spike runner."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[Task]
    final_answer: Any


def normalize_answer(value: Any) -> str:
    if isinstance(value, dict) and set(value) == {"answer"}:
        return normalize_answer(value["answer"])
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=True)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    if value is None:
        return "null"
    return str(value).strip()


def answer_matches_oracle(actual: Any, expected: Any, tolerance: float = 1e-6) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(expected, list) and isinstance(actual, list):
        actual_by_key = [normalize_answer(item).casefold() for item in actual]
        expected_by_key = [normalize_answer(item).casefold() for item in expected]
        from collections import Counter

        return Counter(actual_by_key) == Counter(expected_by_key)
    return normalize_answer(actual).casefold() == normalize_answer(expected).casefold()


def tokens_per_second(response: dict[str, Any]) -> float | None:
    count = response.get("eval_count")
    duration_ns = response.get("eval_duration")
    if not isinstance(count, (int, float)) or not isinstance(duration_ns, (int, float)):
        return None
    if count <= 0 or duration_ns <= 0:
        return None
    return float(count) / (float(duration_ns) / 1_000_000_000)


def consistency_rate(rows: list[dict[str, Any]]) -> float:
    from collections import Counter, defaultdict

    by_question: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_question[str(row["question_id"])].append(normalize_answer(row.get("final_answer", "")))
    if not by_question:
        return 0.0
    agreements = []
    for answers in by_question.values():
        counts = Counter(answers)
        agreements.append(max(counts.values()) / len(answers))
    return sum(agreements) / len(agreements)


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_output(content: str) -> SpikeOutput | None:
    try:
        return SpikeOutput.model_validate_json(_strip_json_fence(content))
    except (ValidationError, json.JSONDecodeError):
        return None


def normalize_tool_arguments(arguments: Any) -> dict[str, Any]:
    """Normalize Ollama's dict or JSON-string tool arguments."""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _build_system_prompt(profile: DatasetProfile) -> str:
    """Build system prompt with actual column names injected from profile."""
    col_lines = "; ".join(f"{c.name} ({c.semantic_type.value})" for c in profile.columns)
    return (
        "You are a deterministic analysis planner. Use only the supplied tools. "
        "Return a JSON object with tasks and final_answer. Each task must use "
        "the existing Task contract; arguments must match its tool schema. "
        "Do not invent dataset values. "
        f"Dataset columns (use these exact names): {col_lines}."
    )


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.args_schema,
            },
        }
        for spec in DEFAULT_REGISTRY.export_tool_specs()
    ]


def _acyclic(task_list: list[Task]) -> bool:
    by_id = {task.id: task for task in task_list}
    if len(by_id) != len(task_list):
        return False
    state: dict[str, int] = {}

    def visit(task_id: str) -> bool:
        if task_id not in by_id:
            return False
        if state.get(task_id) == 1:
            return False
        if state.get(task_id) == 2:
            return True
        state[task_id] = 1
        if not all(visit(parent) for parent in by_id[task_id].depends_on):
            return False
        state[task_id] = 2
        return True

    return all(visit(task_id) for task_id in by_id)


def evaluate_tasks(
    tasks: list[Task],
    profile: DatasetProfile,
) -> tuple[bool, bool, int, list[str]]:
    """Evaluate task list: (all_valid, all_args_valid, valid_count, failure_reasons)."""
    if not tasks:
        return False, False, 0, ["Empty task list"]
    if not _acyclic(tasks):
        return False, False, 0, ["Cyclic task dependency graph"]

    valid_count = 0
    failure_reasons = []
    all_registered = True
    all_args_valid = True

    for task in tasks:
        entry = DEFAULT_REGISTRY.get(task.tool)
        if entry is None:
            all_registered = False
            all_args_valid = False
            failure_reasons.append(f"Tool '{task.tool}' not in DEFAULT_REGISTRY")
            continue

        _, failure = validate_task_args(
            task.tool,
            task.args,
            profile,
            entry.args_model,
            DEFAULT_REGISTRY.list_tools(),
        )
        if failure:
            all_args_valid = False
            failure_reasons.append(f"Task '{task.id}' ({task.tool}) invalid: {failure.message}")
        else:
            valid_count += 1

    all_valid = all_registered and all_args_valid and (valid_count == len(tasks))
    return all_valid, all_args_valid, valid_count, failure_reasons


def valid_tool_call(output: SpikeOutput, profile: DatasetProfile) -> bool:
    if not output.tasks:
        return False
    all_valid, _, _, _ = evaluate_tasks(output.tasks, profile)
    return all_valid


def ollama_chat(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    *,
    host: str = OLLAMA_HOST,
    timeout_s: float = 600.0,
) -> tuple[str, dict[str, Any]]:
    body = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": SpikeOutput.model_json_schema(),
        "tools": tools,
        "think": False,
        "keep_alive": "10m",
        "options": {"temperature": TEMPERATURE, "seed": SEED},
    }
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = json.load(response)
    message = payload.get("message", {})
    content = message.get("content", "")
    if isinstance(content, str) and content.strip():
        return content, payload

    tool_calls = message.get("tool_calls", [])
    if isinstance(tool_calls, list) and tool_calls:
        # Check if model packed the SpikeOutput dictionary inside the first tool call's arguments
        first_call = tool_calls[0].get("function", {})
        first_args = normalize_tool_arguments(first_call.get("arguments", {}))
        if isinstance(first_args, dict) and "tasks" in first_args:
            return (
                json.dumps(
                    {
                        "tasks": first_args.get("tasks", []),
                        "final_answer": first_args.get("final_answer"),
                    }
                ),
                payload,
            )

        tasks = []
        for index, call in enumerate(tool_calls, start=1):
            function = call.get("function", {})
            tasks.append(
                {
                    "id": f"t{index}",
                    "tool": function.get("name", ""),
                    "args": normalize_tool_arguments(function.get("arguments", {})),
                    "depends_on": [],
                    "rationale": "Use the registered tool to answer the question.",
                }
            )
        return json.dumps({"tasks": tasks, "final_answer": None}), payload
    return content if isinstance(content, str) else json.dumps(content), payload


def load_questions(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        questions = data.get("questions", [])
    else:
        questions = data
    if not isinstance(questions, list):
        raise TypeError(f"Question file must contain a list: {path}")
    return questions[:limit] if limit is not None else questions


def question_id(question: dict[str, Any], index: int) -> str:
    value = question.get("id", question.get("question_id", f"q{index + 1}"))
    return str(value)


def _profile(dataset: Path) -> tuple[pd.DataFrame, DatasetProfile]:
    frame = load_data(dataset)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Dataset loader did not return a DataFrame")
    return frame, compute_profile(frame, file_path=dataset)


def run_spike(
    questions_path: Path,
    dataset_path: Path,
    output_path: Path = DEFAULT_CSV_OUTPUT,
    *,
    limit: int | None = None,
    max_retries: int = 0,
    host: str = OLLAMA_HOST,
    models: tuple[str, ...] = MODELS,
    json_output_path: Path = DEFAULT_JSON_OUTPUT,
    resume: bool = True,
) -> dict[str, Any]:
    """Execute model spike across questions and models, measuring planning validity."""
    questions = load_questions(questions_path, limit)
    _, profile = _profile(dataset_path)
    tool_specs = _tool_definitions()

    detailed_runs: list[dict[str, Any]] = []
    if resume and json_output_path.exists():
        try:
            with json_output_path.open("r", encoding="utf-8") as handle:
                prev_data = json.load(handle)
                if isinstance(prev_data, dict) and "detailed_runs" in prev_data:
                    detailed_runs = prev_data["detailed_runs"]
                    print(
                        f"Resuming from {json_output_path} with {len(detailed_runs)} existing runs."
                    )
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            print(f"Could not load previous runs from {json_output_path}: {exc}")
            detailed_runs = []

    completed_keys = {(r["model"], r["question_id"], r["run_number"]) for r in detailed_runs}

    def _save_checkpoint() -> None:
        summary: dict[str, Any] = {}
        for m in models:
            m_runs = [r for r in detailed_runs if r["model"] == m]
            if not m_runs:
                continue
            total = len(m_runs)
            latencies = [float(r["latency_s"]) for r in m_runs]
            tps_list = [
                r["tokens_per_second"] for r in m_runs if r["tokens_per_second"] is not None
            ]
            total_tasks = sum(r["tasks_count"] for r in m_runs)
            total_valid_tasks = sum(r["valid_tasks_count"] for r in m_runs)

            valid_tool_call_rate = sum(1 for r in m_runs if r["valid_tool_call"]) / total
            correct_tool_sel_rate = sum(1 for r in m_runs if r["correct_tool_selection"]) / total
            correct_argument_rate = sum(1 for r in m_runs if r["correct_argument"]) / total
            task_arg_accuracy = (total_valid_tasks / total_tasks) if total_tasks > 0 else 0.0
            json_schema_failure_rate = sum(1 for r in m_runs if r["json_or_schema_failure"]) / total

            summary[m] = {
                "total_runs": total,
                "valid_tool_call_rate": round(valid_tool_call_rate, 4),
                "correct_tool_selection_rate": round(correct_tool_sel_rate, 4),
                "correct_argument_rate": round(correct_argument_rate, 4),
                "task_argument_accuracy": round(task_arg_accuracy, 4),
                "total_tasks_proposed": total_tasks,
                "total_valid_tasks": total_valid_tasks,
                "mean_latency_s": round(statistics.fmean(latencies), 2),
                "median_latency_s": round(statistics.median(latencies), 2),
                "json_or_schema_failure_rate": round(json_schema_failure_rate, 4),
                "mean_tokens_per_second": round(statistics.fmean(tps_list), 2)
                if tps_list
                else None,
            }

        result_data = {
            "metadata": {
                "timestamp": datetime.now(UTC).isoformat(),
                "temperature": TEMPERATURE,
                "seed": SEED,
                "questions_file": str(questions_path),
                "dataset_file": str(dataset_path),
                "questions_count": len(questions),
                "runs_per_question": 3,
                "total_runs_per_model": len(questions) * 3,
                "minimum_bar": {
                    "valid_tool_call_rate": 0.85,
                    "correct_tool_selection_rate": 0.70,
                },
            },
            "summary": summary,
            "detailed_runs": detailed_runs,
        }

        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        with json_output_path.open("w", encoding="utf-8") as handle:
            json.dump(result_data, handle, indent=2)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[*RESULT_FIELDS, "final_answer"],
                extrasaction="ignore",
            )
            writer.writeheader()
            for r in detailed_runs:
                writer.writerow(r)

    for model in models:
        print(f"\n>>> Starting evaluation for model: {model} ({len(questions)} questions x 3 runs)")
        for index, question in enumerate(questions):
            qid = question_id(question, index)
            prompt = str(question.get("text", question.get("question", "")))
            expected_tools = question.get("expected_tools", [])
            if not expected_tools and "expected_tool" in question:
                expected_tools = [question["expected_tool"]]

            for run_number in range(1, 4):
                if (model, qid, run_number) in completed_keys:
                    print(f"[{model}] {qid} run {run_number}/3: already completed (skipping)")
                    continue

                messages = [
                    {
                        "role": "system",
                        "content": _build_system_prompt(profile),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question category: {question.get('category', '')}. "
                            f"Expected registered tools: {', '.join(expected_tools)}. "
                            f"Use native tool calls when supported. For filter arguments, use the exact "
                            f"conditions schema and exact column names.\n{prompt}"
                        ),
                    },
                ]

                retries = 0
                total_latency = 0.0
                total_tokens = 0
                total_eval_duration = 0
                output: SpikeOutput | None = None
                raw_content = ""

                while retries <= max_retries:
                    start = time.perf_counter()
                    try:
                        content, payload = ollama_chat(model, messages, tool_specs, host=host)
                        raw_content = content
                    except (
                        urllib.error.URLError,
                        TimeoutError,
                        OSError,
                        json.JSONDecodeError,
                    ):
                        total_latency += time.perf_counter() - start
                        if retries >= max_retries:
                            break
                        retries += 1
                        continue

                    elapsed = time.perf_counter() - start
                    total_latency += elapsed
                    count = payload.get("eval_count")
                    duration = payload.get("eval_duration")
                    if isinstance(count, (int, float)):
                        total_tokens += int(count)
                    if isinstance(duration, (int, float)):
                        total_eval_duration += int(duration)
                    output = parse_output(content)
                    if output is not None:
                        break
                    if retries >= max_retries:
                        break
                    retries += 1

                pydantic_valid = output is not None
                json_or_schema_failure = not pydantic_valid

                if output is not None and output.tasks:
                    tasks_count = len(output.tasks)
                    selected_tools = [t.tool for t in output.tasks]
                    correct_tool_selection = set(selected_tools) == set(expected_tools)
                    call_valid, args_valid, valid_count, failures = evaluate_tasks(
                        output.tasks, profile
                    )
                    tasks_dump = [t.model_dump() for t in output.tasks]
                else:
                    tasks_count = 0
                    selected_tools = []
                    correct_tool_selection = False
                    call_valid = False
                    args_valid = False
                    valid_count = 0
                    failures = ["No parsed tasks"] if pydantic_valid else ["Schema parse failure"]
                    tasks_dump = []

                if total_eval_duration > 0 and total_tokens > 0:
                    effective_tps = total_tokens / (total_eval_duration / 1_000_000_000)
                else:
                    effective_tps = None

                row = {
                    "model": model,
                    "question_id": qid,
                    "run_number": run_number,
                    "schema_valid": pydantic_valid,
                    "json_or_schema_failure": json_or_schema_failure,
                    "valid_tool_call": call_valid,
                    "correct_tool_selection": correct_tool_selection,
                    "correct_argument": args_valid,
                    "tasks_count": tasks_count,
                    "valid_tasks_count": valid_count,
                    "latency_s": round(total_latency, 3),
                    "tokens_per_second": round(effective_tps, 2) if effective_tps else None,
                    "selected_tools": selected_tools,
                    "expected_tools": expected_tools,
                    "retries_used": min(retries, max_retries),
                    "failure_reasons": failures,
                    "tasks": tasks_dump,
                    "final_answer": normalize_answer(output.final_answer) if output else "",
                    "raw_content": raw_content[:200] if raw_content else "",
                }
                detailed_runs.append(row)
                completed_keys.add((model, qid, run_number))
                status_str = "OK" if call_valid else f"FAIL ({', '.join(failures[:1])})"
                print(
                    f"[{model}] {qid} run {run_number}/3: "
                    f"valid_tool={call_valid} tool_sel={correct_tool_selection} "
                    f"args_ok={args_valid} latency={total_latency:.1f}s -> {status_str}"
                )
                _save_checkpoint()

    # Final summary display
    _save_checkpoint()
    with json_output_path.open("r", encoding="utf-8") as handle:
        final_data = json.load(handle)
    summary = final_data.get("summary", {})
    print_markdown_summary(summary)
    print(f"\nSaved JSON results to {json_output_path}")
    print(f"Saved CSV results to {output_path}")
    return final_data


def print_markdown_summary(summary: dict[str, Any]) -> str:
    """Print and return markdown summary table."""
    headers = [
        "Model",
        "Valid Tool Calls",
        "Correct Tool Sel.",
        "Correct Arg. Rate",
        "Task Arg. Accuracy",
        "Schema Failure",
        "Mean Latency (s)",
        "Mean TPS",
    ]
    rows_text = []
    rows_text.append("| " + " | ".join(headers) + " |")
    rows_text.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for model, stats in summary.items():
        vtc = f"{stats['valid_tool_call_rate'] * 100:.1f}%"
        cts = f"{stats['correct_tool_selection_rate'] * 100:.1f}%"
        car = f"{stats['correct_argument_rate'] * 100:.1f}%"
        taa = f"{stats['task_argument_accuracy'] * 100:.1f}%"
        sfr = f"{stats['json_or_schema_failure_rate'] * 100:.1f}%"
        lat = f"{stats['mean_latency_s']:.1f}s"
        tps = (
            f"{stats['mean_tokens_per_second']:.1f}"
            if stats.get("mean_tokens_per_second")
            else "N/A"
        )
        row_str = f"| `{model}` | {vtc} | {cts} | {car} | {taa} | {sfr} | {lat} | {tps} |"
        rows_text.append(row_str)

    md_table = "\n".join(rows_text)
    print("\n### Model Spike Evaluation Summary\n")
    print(md_table)
    return md_table


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        type=Path,
        default=None,
        help="JSON question file containing text and expected_tools",
    )
    parser.add_argument("--dataset", type=Path, default=Path("Sample-Superstore.csv"))
    parser.add_argument("--output", type=Path, default=DEFAULT_CSV_OUTPUT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument(
        "--limit", "-n", type=int, default=None, help="number of benchmark questions"
    )
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--host", default=OLLAMA_HOST)
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    parser.add_argument(
        "--no-resume", action="store_true", help="overwrite existing runs instead of resuming"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.questions is None:
        raise SystemExit("--questions is required until the frozen benchmark file is available")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be positive")
    if args.max_retries < 0:
        raise SystemExit("--max-retries must be non-negative")
    run_spike(
        args.questions,
        args.dataset,
        args.output,
        limit=args.limit,
        max_retries=args.max_retries,
        host=args.host,
        models=tuple(args.models),
        json_output_path=args.json_output,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    main()
