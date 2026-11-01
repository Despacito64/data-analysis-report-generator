#!/usr/bin/env python3
"""Run fixed-sampling Ollama planning spikes against the Superstore benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Iterable
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
RESULT_FIELDS = (
    "model",
    "question_id",
    "run_number",
    "valid_tool_call",
    "pydantic_valid",
    "answer_match",
    "retries_used",
    "latency_s",
    "tokens_per_second",
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


def consistency_rate(rows: Iterable[dict[str, Any]]) -> float:
    by_question: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_question[str(row["question_id"])].append(normalize_answer(row["final_answer"]))
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


def valid_tool_call(output: SpikeOutput, profile: DatasetProfile) -> bool:
    if not output.tasks or not _acyclic(output.tasks):
        return False
    for task in output.tasks:
        entry = DEFAULT_REGISTRY.get(task.tool)
        _, failure = validate_task_args(
            task.tool,
            task.args,
            profile,
            entry.args_model if entry else None,
            DEFAULT_REGISTRY.list_tools(),
        )
        if failure:
            return False
    return True


def load_questions(path: Path, limit: int | None) -> list[dict[str, Any]]:
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


def oracle_answer(question: dict[str, Any]) -> Any:
    for key in ("expected_answer", "oracle_answer", "answer"):
        if key in question:
            return question[key]
    fields = question.get("expected_answer_fields")
    if isinstance(fields, dict):
        return fields
    raise ValueError(f"Question {question_id(question, 0)!r} has no expected answer")


def _profile(dataset: Path) -> tuple[pd.DataFrame, DatasetProfile]:
    frame = load_data(dataset)
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("Dataset loader did not return a DataFrame")
    return frame, compute_profile(frame, file_path=dataset)


def run_spike(
    questions_path: Path,
    dataset_path: Path,
    output_path: Path,
    *,
    limit: int | None,
    max_retries: int,
    host: str,
    models: tuple[str, ...] = MODELS,
) -> list[dict[str, Any]]:
    questions = load_questions(questions_path, limit)
    _, profile = _profile(dataset_path)
    tool_specs = _tool_definitions()
    rows: list[dict[str, Any]] = []

    for model in models:
        for index, question in enumerate(questions):
            qid = question_id(question, index)
            expected = oracle_answer(question)
            prompt = str(question.get("text", question.get("question", "")))
            for run_number in range(1, 4):
                messages = [
                    {
                        "role": "system",
                        "content": (
                            "You are a deterministic analysis planner. Use only the supplied tools. "
                            "Return a JSON object with tasks and final_answer. Each task must use "
                            "the existing Task contract; arguments must match its tool schema. "
                            "Do not invent dataset values."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ]
                retries = 0
                total_latency = 0.0
                total_tokens = 0
                total_eval_duration = 0
                output: SpikeOutput | None = None
                while retries <= max_retries:
                    start = time.perf_counter()
                    try:
                        content, payload = ollama_chat(model, messages, tool_specs, host=host)
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

                retries_used = min(retries, max_retries)
                pydantic_valid = output is not None
                call_valid = valid_tool_call(output, profile) if output is not None else False
                if total_eval_duration > 0 and total_tokens > 0:
                    effective_tps = total_tokens / (total_eval_duration / 1_000_000_000)
                else:
                    effective_tps = None
                row = {
                    "model": model,
                    "question_id": qid,
                    "run_number": run_number,
                    "valid_tool_call": call_valid,
                    "pydantic_valid": pydantic_valid,
                    "answer_match": (
                        answer_matches_oracle(output.final_answer, expected)
                        if output is not None
                        else False
                    ),
                    "retries_used": retries_used,
                    "latency_s": total_latency,
                    "tokens_per_second": effective_tps,
                    "final_answer": normalize_answer(output.final_answer) if output else "",
                }
                rows.append(row)
                print(
                    f"{model} {qid} run={run_number} "
                    f"schema={pydantic_valid} tool={call_valid} "
                    f"answer={row['answer_match']} latency={total_latency:.2f}s"
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*RESULT_FIELDS, "final_answer"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in writer.fieldnames})
    print_summary(rows)
    print(f"Saved results to {output_path}")
    return rows


def print_summary(rows: list[dict[str, Any]]) -> None:
    print("\nModel spike summary")
    print("model\taccuracy\tschema_valid\tconsistency\tmedian_latency_s\tmean_tokens_per_second")
    for model in MODELS:
        model_rows = [row for row in rows if row["model"] == model]
        if not model_rows:
            continue
        count = len(model_rows)
        latencies = [float(row["latency_s"]) for row in model_rows]
        token_rates = [
            float(row["tokens_per_second"])
            for row in model_rows
            if row["tokens_per_second"] is not None
        ]
        print(
            f"{model}\t"
            f"{sum(bool(row['answer_match']) for row in model_rows) / count:.3f}\t"
            f"{sum(bool(row['pydantic_valid']) for row in model_rows) / count:.3f}\t"
            f"{consistency_rate(model_rows):.3f}\t"
            f"{statistics.median(latencies):.2f}\t"
            f"{statistics.fmean(token_rates) if token_rates else 0:.2f}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--questions",
        type=Path,
        help="required JSON question file containing text and expected_answer",
    )
    parser.add_argument("--dataset", type=Path, default=Path("Sample-Superstore.csv"))
    parser.add_argument("--output", type=Path, default=Path("evaluation/results/model_spike.csv"))
    parser.add_argument("--limit", "-n", type=int, default=10, help="number of benchmark questions")
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--host", default=OLLAMA_HOST)
    parser.add_argument("--models", nargs="+", default=list(MODELS))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.questions is None:
        raise SystemExit("--questions is required until the frozen benchmark file is available")
    if args.limit < 1:
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
    )


if __name__ == "__main__":
    main()
