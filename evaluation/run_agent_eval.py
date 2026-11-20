"""Run and score the dynamic agent against the frozen oracle and fixed baseline."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from da_agent.agent.answer import AgentAnswerStatus, AgentResult
from da_agent.agent.planner import LLMClient, MockLLMClient, OllamaClient
from da_agent.contracts.models import Budgets
from da_agent.core.config import AppConfig, load_config
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


class EvaluationLimitExceeded(RuntimeError):
    """A per-question time or call/repair limit ended a run."""

    def __init__(self, reason: str, stage: str, elapsed_s: float) -> None:
        super().__init__(f"{reason} during {stage} after {elapsed_s:.3f}s")
        self.reason = reason
        self.stage = stage
        self.elapsed_s = elapsed_s


_GRAPH_STAGE_NAMES = {
    "resolve": "question_resolution",
    "plan": "plan_generation",
    "validate_repair": "plan_validation",
    "execute": "tool_execution",
    "inspect": "result_inspection",
    "replan": "replanning",
    "finalize": "graph_finalization",
}


class EvaluationTraceWriter(RunTraceWriter):
    """Add evaluation timing and limit checks to existing trace events."""

    def __init__(
        self,
        *,
        run_id: str,
        base_dir: Path | str,
        question_budget_s: float | None = None,
        max_repair_attempts: int | None = None,
        overall_deadline: float | None = None,
    ) -> None:
        super().__init__(run_id=run_id, base_dir=base_dir)
        self.started_at = time.perf_counter()
        self.question_budget_s = question_budget_s
        self.max_repair_attempts = max_repair_attempts
        self.overall_deadline = overall_deadline
        self.stage_started_at: dict[str, float] = {}
        self.stage_timings: dict[str, float] = {}
        self.current_stage = "initialization"
        self.repair_attempts: list[dict[str, Any]] = []
        self.tool_executions: list[dict[str, Any]] = []
        self._pending_repair: int | None = None
        self._answer_synthesis_started_at: float | None = None

    @property
    def elapsed_s(self) -> float:
        return time.perf_counter() - self.started_at

    @property
    def remaining_s(self) -> float | None:
        remaining_values: list[float] = []
        if self.question_budget_s is not None:
            remaining_values.append(self.question_budget_s - self.elapsed_s)
        if self.overall_deadline is not None:
            remaining_values.append(self.overall_deadline - time.perf_counter())
        return max(0.0, min(remaining_values)) if remaining_values else None

    def check_budget(self, stage: str) -> None:
        if self.overall_deadline is not None and time.perf_counter() >= self.overall_deadline:
            self._record_active_stage(stage)
            self.stage_timings.setdefault(stage, 0.0)
            super().log_event(
                "evaluation_overall_timeout",
                {
                    "reason": "overall_timeout",
                    "stage": stage,
                    "question_elapsed_s": self.elapsed_s,
                    "stage_timings": dict(self.stage_timings),
                },
            )
            raise EvaluationLimitExceeded("overall_timeout", stage, self.elapsed_s)
        if self.question_budget_s is None or self.elapsed_s < self.question_budget_s:
            return
        self._record_active_stage(stage)
        self.stage_timings.setdefault(stage, 0.0)
        payload = {
            "reason": "question_timeout",
            "stage": stage,
            "elapsed_s": self.elapsed_s,
            "stage_timings": dict(self.stage_timings),
        }
        super().log_event("question_budget_exceeded", payload)
        raise EvaluationLimitExceeded("question_timeout", stage, self.elapsed_s)

    def _record_active_stage(self, stage: str) -> None:
        now = time.perf_counter()
        for node, started in list(self.stage_started_at.items()):
            if _GRAPH_STAGE_NAMES.get(node, node) == stage:
                duration = max(0.0, now - started)
                self.stage_timings[stage] = self.stage_timings.get(stage, 0.0) + duration
                del self.stage_started_at[node]

    def complete_repair_attempt(self, duration_s: float, call_number: int) -> None:
        if self._pending_repair is None:
            return
        attempt = self._pending_repair
        self._pending_repair = None
        if attempt <= len(self.repair_attempts):
            self.repair_attempts[attempt - 1]["duration_s"] = duration_s
        else:
            self.repair_attempts.append(
                {"attempt": attempt, "duration_s": duration_s, "llm_call": call_number}
            )
        self.stage_timings[f"repair_attempt_{attempt}"] = duration_s
        super().log_event(
            "repair_attempt_timing",
            {
                "attempt": attempt,
                "duration_s": duration_s,
                "llm_call": call_number,
            },
        )

    def record_tool_execution(self, record: Any) -> None:
        entry = {
            "task_id": record.task_id,
            "tool": record.tool,
            "status": record.status.value,
            "duration_s": record.duration_s,
        }
        if entry not in self.tool_executions:
            self.tool_executions.append(entry)

    def log_event(self, event_type: str, payload: dict[str, Any]) -> Any:
        event_payload = dict(payload)
        now = time.perf_counter()

        if event_type == "graph_node":
            node = str(event_payload.get("node", "unknown"))
            phase = event_payload.get("phase")
            stage = _GRAPH_STAGE_NAMES.get(node, node)
            if phase == "start":
                self.check_budget(stage)
                self.current_stage = stage
                self.stage_started_at[node] = now
                event_payload["elapsed_s"] = self.elapsed_s
            elif phase == "end":
                started = self.stage_started_at.pop(node, now)
                duration = max(0.0, now - started)
                self.stage_timings[stage] = self.stage_timings.get(stage, 0.0) + duration
                if node == "plan" and "question_resolution" not in self.stage_timings:
                    # D-049: resolver node removed; keep legacy timing key at zero.
                    self.stage_timings["question_resolution"] = 0.0
                event_payload["duration_s"] = duration
                event_payload["elapsed_s"] = self.elapsed_s
                if node == "finalize":
                    self._answer_synthesis_started_at = now
            event = super().log_event(event_type, event_payload)
            if phase == "end":
                self.check_budget(stage)
            return event

        if event_type == "planner_repair_attempt":
            attempt = len(self.repair_attempts) + 1
            event_payload["attempt"] = attempt
            event_payload["started_elapsed_s"] = self.elapsed_s
            self.repair_attempts.append({"attempt": attempt, "duration_s": None})
            event = super().log_event(event_type, event_payload)
            if self.max_repair_attempts is not None and attempt > self.max_repair_attempts:
                super().log_event(
                    "evaluation_cap_exceeded",
                    {
                        "reason": "repair_cap",
                        "stage": self.current_stage,
                        "limit": self.max_repair_attempts,
                        "elapsed_s": self.elapsed_s,
                    },
                )
                raise EvaluationLimitExceeded("repair_cap", self.current_stage, self.elapsed_s)
            self._pending_repair = attempt
            return event

        if event_type == "tool_execution_timing":
            self.tool_executions.append(event_payload)
            return super().log_event(event_type, event_payload)

        if event_type == "final_answer" and self._answer_synthesis_started_at is not None:
            duration = max(0.0, now - self._answer_synthesis_started_at)
            event_payload["duration_s"] = duration
            self.stage_timings["answer_synthesis"] = duration
            event_payload["stage_timings"] = dict(self.stage_timings)
            self.check_budget("answer_synthesis")
            return super().log_event(event_type, event_payload)

        return super().log_event(event_type, event_payload)


class TimedLLMClient:
    """Measure and cap calls while preserving the planner's LLM client protocol."""

    def __init__(
        self,
        client: LLMClient,
        *,
        trace_writer: EvaluationTraceWriter,
        max_llm_calls: int | None,
        model_name: str,
    ) -> None:
        self.client = client
        self.trace_writer = trace_writer
        self.max_llm_calls = max_llm_calls
        self.model_name = model_name
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        stage = self.trace_writer.current_stage
        self.trace_writer.check_budget(stage)
        if self.max_llm_calls is not None and len(self.calls) >= self.max_llm_calls:
            payload = {
                "reason": "llm_call_cap",
                "stage": stage,
                "limit": self.max_llm_calls,
                "elapsed_s": self.trace_writer.elapsed_s,
            }
            self.trace_writer.log_event("evaluation_cap_exceeded", payload)
            raise EvaluationLimitExceeded("llm_call_cap", stage, self.trace_writer.elapsed_s)

        call_number = len(self.calls) + 1
        call_started = time.perf_counter()
        old_timeout = getattr(self.client, "timeout_s", None)
        remaining = self.trace_writer.remaining_s
        if remaining is not None and old_timeout is not None:
            self.client.timeout_s = min(float(old_timeout), remaining)

        try:
            response = self.client.chat(
                messages,
                schema=schema,
                model=model,
                temperature=temperature,
                seed=seed,
            )
        except Exception as exc:
            duration = max(0.0, time.perf_counter() - call_started)
            call = {
                "call_number": call_number,
                "stage": stage,
                "duration_s": duration,
                "completed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "model": model or self.model_name,
            }
            self.calls.append(call)
            self.trace_writer.log_event("llm_call_timing", call)
            self.trace_writer.complete_repair_attempt(duration, call_number)
            self.trace_writer.check_budget(stage)
            raise
        finally:
            if old_timeout is not None:
                self.client.timeout_s = old_timeout

        duration = max(0.0, time.perf_counter() - call_started)
        call = {
            "call_number": call_number,
            "stage": stage,
            "duration_s": duration,
            "completed": True,
            "model": model or self.model_name,
        }
        self.calls.append(call)
        self.trace_writer.log_event("llm_call_timing", call)
        self.trace_writer.complete_repair_attempt(duration, call_number)
        self.trace_writer.check_budget(stage)
        return response


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
    """Render current resumable reports and preserve the legacy helper's format."""
    if "score_complete" in summary:
        agent = summary["agent"]
        lines = [
            "# Dynamic agent evaluation",
            "",
            f"Detailed results: `{json_path}`",
            f"Score complete: **{summary['score_complete']}**",
            "",
            "| Accuracy measure | Correct | Total | Accuracy |",
            "| --- | ---: | ---: | ---: |",
            (
                f"| All questions (timeouts/not-run incorrect) | {agent['correct']} | "
                f"{agent['total']} | {agent['accuracy_over_all_questions']:.3f} |"
            ),
        ]
        completed_accuracy = agent["accuracy_over_completed_questions"]
        completed_text = "n/a" if completed_accuracy is None else f"{completed_accuracy:.3f}"
        lines.append(
            f"| Completed only | {agent['correct'] if completed_accuracy is not None else 0} | "
            f"{agent['completed_questions']} | {completed_text} |"
        )
        lines.extend(
            [
                "",
                summary["baseline"]["note"],
                "",
                f"Total evaluation time: {summary['evaluation']['total_time_s']:.3f}s",
                (
                    f"Warm-up time (excluded from question budgets): "
                    f"{summary['evaluation']['warmup_time_s']:.3f}s"
                ),
                f"Total LLM calls including warm-up: {summary['aggregate']['total_llm_call_count']}",
                (
                    f"Aggregate stage timings (s): "
                    f"`{json.dumps(summary['aggregate']['stage_timings'], sort_keys=True)}`"
                ),
                (
                    f"Agent-vs-baseline outcomes: "
                    f"`{json.dumps(summary['baseline_comparison'], sort_keys=True)}`"
                ),
                (f"Failure reasons: `{json.dumps(summary['failure_reasons'], sort_keys=True)}`"),
                "",
                "## Per-question results",
                "",
                "| Question | Status | Accuracy | Baseline outcome | Total time (s) | Stage timings (s) | Tool executions | Repair attempts | LLM calls | Failure stage/reason |",
                "| --- | --- | --- | --- | ---: | --- | --- | --- | ---: | --- |",
            ]
        )
        for row in summary["per_question"]:
            accuracy = "n/a" if row["accuracy"] is None else str(row["accuracy"])
            stage_timings = json.dumps(row["stage_timings"], sort_keys=True)
            tool_times = json.dumps(row["tool_executions"], sort_keys=True)
            repair_times = json.dumps(row["repair_attempts"], sort_keys=True)
            failure = f"{row['failure_stage'] or ''} / {row['failure_reason'] or ''}".strip(" /")
            lines.append(
                f"| {row['question_id']} | {row['status']} | {accuracy} | {row['outcome']} | "
                f"{row['total_time_s']:.3f} | `{stage_timings}` | `{tool_times}` | "
                f"`{repair_times}` | {row['llm_call_count']} | {failure} |"
            )
        lines.append("")
        return "\n".join(lines)

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


def apply_eval_timeout(config: AppConfig, timeout_s: float | None) -> AppConfig:
    """Apply an explicit evaluation-only inference timeout without changing app defaults."""
    if timeout_s is None:
        return config
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("Evaluation timeout must be a positive finite number of seconds")
    budget_values = config.budgets.model_dump()
    budget_values["per_call_timeout_s"] = timeout_s
    budgets = Budgets.model_validate(budget_values)
    return config.model_copy(update={"budgets": budgets})


def evaluate_agent(
    *,
    dataset_path: Path,
    oracle_path: Path,
    questions_path: Path,
    results_dir: Path,
    model: str | None = None,
    repeats: int = 1,
    per_call_timeout_s: float | None = None,
    per_question_budget_s: float | None = None,
    overall_timeout_s: float | None = None,
    max_repair_attempts: int | None = None,
    max_replans: int | None = None,
    max_llm_calls_per_question: int | None = None,
    thinking_enabled: bool | None = None,
    keep_alive: str | int | None = None,
    run_id: str | None = None,
    resume: bool = False,
    selected_question_ids: list[str] | None = None,
    mode: str = "real",
    client: LLMClient | None = None,
    config: AppConfig | None = None,
) -> dict[str, Any]:
    """Run/resume a bounded evaluation, persisting every question attempt immediately."""
    if repeats < 1:
        raise ValueError("repeats must be at least one")
    if max_replans is not None and max_replans < 0:
        raise ValueError("max_replans must be zero or greater")
    if mode not in {"real", "mock"}:
        raise ValueError("mode must be 'real' or 'mock'")
    if resume and not run_id:
        raise ValueError("resume requires a run_id")

    config = config or load_config()
    if model:
        config = config.model_copy(
            update={"model": config.model.model_copy(update={"name": model})}
        )
    config = apply_eval_timeout(config, per_call_timeout_s)
    eval_values = config.evaluation.model_dump()
    overrides = {
        "per_question_budget_s": per_question_budget_s,
        "overall_timeout_s": overall_timeout_s,
        "max_repair_attempts": max_repair_attempts,
        "max_llm_calls_per_question": max_llm_calls_per_question,
        "thinking_enabled": thinking_enabled,
        "keep_alive": keep_alive,
    }
    for key, value in overrides.items():
        if value is not None:
            eval_values[key] = value
    config = config.model_copy(
        update={"evaluation": type(config.evaluation).model_validate(eval_values)}
    )
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid4().hex[:8]
    if not run_id or Path(run_id).name != run_id or run_id in {".", ".."}:
        raise ValueError("run_id must be a single safe directory name")
    run_dir = results_dir / run_id
    if resume and not run_dir.is_dir():
        raise FileNotFoundError(f"Evaluation run directory does not exist: {run_dir}")
    if not resume and run_dir.exists():
        raise FileExistsError(f"Evaluation run already exists; use --resume {run_id}: {run_dir}")
    run_dir.mkdir(parents=True, exist_ok=True)

    df = load_data(dataset_path)
    profile = compute_profile(df, file_path=dataset_path)
    oracle = load_oracle(oracle_path)
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    questions_by_id = {item["id"]: item for item in questions}
    unknown_ids = set(selected_question_ids or []) - questions_by_id.keys()
    if unknown_ids:
        raise ValueError(f"Unknown question IDs: {', '.join(sorted(unknown_ids))}")
    selected_ids = (
        selected_question_ids if selected_question_ids is not None else list(questions_by_id)
    )
    question_files_dir = run_dir / "questions"
    attempts_dir = run_dir / "attempts"
    question_files_dir.mkdir(parents=True, exist_ok=True)
    attempts_dir.mkdir(parents=True, exist_ok=True)

    baseline = run_baseline(df=df, profile=profile, budgets=config.budgets)
    run_trace = RunTraceWriter(
        run_id=f"agent_eval_{run_id}",
        base_dir=config.run_trace.base_dir,
    )
    llm_client: LLMClient
    if mode == "mock":
        llm_client = client or MockLLMClient(default_response={"tasks": []})
    else:
        llm_client = client or OllamaClient(
            base_url=config.model.base_url,
            model=config.model.name,
            temperature=config.model.temperature,
            seed=config.model.seed,
            timeout_s=config.budgets.per_call_timeout_s,
            thinking_enabled=config.evaluation.thinking_enabled,
            keep_alive=config.evaluation.keep_alive,
        )

    diagnostics = {
        "run_id": run_id,
        "mode": mode,
        "model": config.model.name,
        "ollama_base_url": config.model.base_url.removesuffix("/v1"),
        "thinking_enabled": config.evaluation.thinking_enabled,
        "temperature": config.model.temperature,
        "seed": config.model.seed,
        "keep_alive": config.evaluation.keep_alive,
        "per_call_timeout_s": config.budgets.per_call_timeout_s,
        "per_question_budget_s": config.evaluation.per_question_budget_s,
        "overall_timeout_s": config.evaluation.overall_timeout_s,
        "max_repair_attempts": config.evaluation.max_repair_attempts,
        "max_replans": config.budgets.max_replans if max_replans is None else max_replans,
        "max_llm_calls_per_question": config.evaluation.max_llm_calls_per_question,
    }
    run_trace.log_event("evaluation_run_started", diagnostics | {"resume": resume})
    warmup_started = time.perf_counter()
    warmup_error: str | None = None
    warmup_llm_calls: list[dict[str, Any]] = []
    if mode == "real":
        warmup_writer = EvaluationTraceWriter(
            run_id=f"agent_eval_{run_id}_warmup",
            base_dir=config.run_trace.base_dir,
        )
        warmup_client = TimedLLMClient(
            llm_client,
            trace_writer=warmup_writer,
            max_llm_calls=1,
            model_name=config.model.name,
        )
        try:
            warmup_client.chat([{"role": "user", "content": "Reply with OK."}])
            warmup_llm_calls = warmup_client.calls
            run_trace.log_event(
                "evaluation_warmup",
                {
                    "status": "complete",
                    "duration_s": time.perf_counter() - warmup_started,
                },
            )
        except Exception as exc:  # noqa: BLE001 - record warm-up failure and produce not_run rows
            warmup_llm_calls = warmup_client.calls
            warmup_error = f"{type(exc).__name__}: {exc}"
            run_trace.log_event(
                "evaluation_warmup",
                {
                    "status": "failed",
                    "duration_s": time.perf_counter() - warmup_started,
                    "error": warmup_error,
                },
            )
    else:
        run_trace.log_event("evaluation_warmup", {"status": "skipped", "reason": "mock_mode"})
    warmup_time_s = time.perf_counter() - warmup_started
    benchmark_started = time.perf_counter()
    overall_deadline = benchmark_started + config.evaluation.overall_timeout_s

    saved_results: dict[str, dict[str, Any]] = {}
    for question_id in questions_by_id:
        result_file = question_files_dir / f"{question_id}.json"
        stored_attempts = (
            json.loads(result_file.read_text(encoding="utf-8")).get("attempts", [])
            if result_file.is_file()
            else []
        )
        attempt_dir = attempts_dir / question_id
        if attempt_dir.is_dir():
            known_run_ids = {attempt.get("run_id") for attempt in stored_attempts}
            for attempt_file in sorted(attempt_dir.glob("attempt-*.json")):
                attempt = json.loads(attempt_file.read_text(encoding="utf-8"))
                if attempt.get("run_id") not in known_run_ids:
                    stored_attempts.append(attempt)
                    known_run_ids.add(attempt.get("run_id"))
        if stored_attempts:
            merged = _aggregate_question(question_id, stored_attempts)
            saved_results[question_id] = merged
            _write_json(result_file, merged)

    for question_id in selected_ids:
        previous = saved_results.get(question_id)
        if resume and previous and previous.get("status") in {"passed", "failed", "timeout"}:
            run_trace.log_event("evaluation_question_skipped", {"question_id": question_id})
            continue
        if warmup_error:
            break
        if time.perf_counter() >= overall_deadline:
            run_trace.log_event(
                "evaluation_overall_timeout",
                {"elapsed_s": time.perf_counter() - benchmark_started},
            )
            break

        item = questions_by_id[question_id]
        previous_attempts = list(previous.get("attempts", [])) if previous else []
        target_repeats = max(repeats, len(previous_attempts) + 1) if not resume else repeats
        while len(previous_attempts) < target_repeats:
            if time.perf_counter() >= overall_deadline:
                break
            attempt_number = len(previous_attempts) + 1
            attempt_id = f"agent_eval_{run_id}_{question_id}_r{attempt_number}_{uuid4().hex[:8]}"
            writer = EvaluationTraceWriter(
                run_id=attempt_id,
                base_dir=config.run_trace.base_dir,
                question_budget_s=config.evaluation.per_question_budget_s,
                max_repair_attempts=config.evaluation.max_repair_attempts,
                overall_deadline=overall_deadline,
            )
            timed_client = TimedLLMClient(
                llm_client,
                trace_writer=writer,
                max_llm_calls=config.evaluation.max_llm_calls_per_question,
                model_name=config.model.name,
            )
            writer.log_event(
                "question_run_started",
                {
                    "question_id": question_id,
                    "attempt": attempt_number,
                    "question_budget_s": config.evaluation.per_question_budget_s,
                    "max_repair_attempts": config.evaluation.max_repair_attempts,
                    "max_llm_calls": config.evaluation.max_llm_calls_per_question,
                },
            )
            attempt_started = time.perf_counter()
            answer: Any | None = None
            status = "failed"
            correct = False
            failure_reason: str | None = None
            failure_stage: str | None = None
            failure_elapsed_s: float | None = None
            result: AgentResult | None = None
            try:
                result = run_agent(
                    item["question"],
                    df,
                    config,
                    timed_client,
                    run_id=attempt_id,
                    profile=profile,
                    trace_writer=writer,
                    max_repairs=config.evaluation.max_repair_attempts,
                    max_replans=max_replans,
                )
                answer = extract_score_answer(result)
                correct = answer is not None and answers_match(
                    answer,
                    oracle[question_id]["expected_answer"],
                    float(oracle[question_id]["tolerance"]),
                )
                status = "passed" if correct else "failed"
                if answer is None:
                    failure_reason = "no_score_shaped_answer"
                    failure_stage = writer.current_stage
                    failure_elapsed_s = writer.elapsed_s
                elif not correct:
                    failure_reason = "incorrect_answer"
            except EvaluationLimitExceeded as exc:
                status = (
                    "timeout" if exc.reason in {"question_timeout", "overall_timeout"} else "failed"
                )
                failure_reason = exc.reason
                failure_stage = exc.stage
                failure_elapsed_s = exc.elapsed_s
            except Exception as exc:  # noqa: BLE001 - persist question failures and continue
                failure_reason = f"run_error:{type(exc).__name__}:{exc}"
                failure_stage = writer.current_stage
                failure_elapsed_s = writer.elapsed_s
            elapsed = time.perf_counter() - attempt_started
            if result is not None:
                for task_record in result.task_results:
                    writer.record_tool_execution(task_record)
            stage_timings = dict(writer.stage_timings)
            stage_timings["tool_executions"] = sum(
                item["duration_s"] for item in writer.tool_executions
            )
            attempt_record = {
                "question_id": question_id,
                "attempt": attempt_number,
                "run_id": attempt_id,
                "status": status,
                "accuracy": correct if status in {"passed", "failed"} else None,
                "answer": answer,
                "failure_reason": failure_reason,
                "failure_stage": failure_stage,
                "failure_elapsed_s": failure_elapsed_s,
                "total_time_s": elapsed,
                "stage_timings": stage_timings,
                "tool_executions": writer.tool_executions,
                "llm_calls": timed_client.calls,
                "llm_call_count": len(timed_client.calls),
                "repair_attempts": writer.repair_attempts,
            }
            writer.log_event(
                "question_terminal",
                {
                    "question_id": question_id,
                    "status": status,
                    "failure_reason": failure_reason,
                    "total_time_s": elapsed,
                },
            )
            previous_attempts.append(attempt_record)
            attempts_path = attempts_dir / question_id
            attempts_path.mkdir(parents=True, exist_ok=True)
            _write_json(
                attempts_path / f"attempt-{attempt_number:03d}.json",
                attempt_record,
            )
            question_result = _aggregate_question(question_id, previous_attempts)
            saved_results[question_id] = question_result
            _write_json(question_files_dir / f"{question_id}.json", question_result)
            if failure_reason == "overall_timeout":
                break
    comparison = _build_resumable_summary(
        questions_by_id=questions_by_id,
        saved_results=saved_results,
        oracle=oracle,
        baseline_answers=baseline.answers,
        diagnostics=diagnostics,
        total_time_s=time.perf_counter() - benchmark_started,
        warmup_time_s=warmup_time_s,
        warmup_llm_calls=warmup_llm_calls,
    )
    comparison["run_id"] = run_id
    comparison["selected_question_ids"] = selected_ids
    comparison["runs"] = [
        attempt for result in saved_results.values() for attempt in result.get("attempts", [])
    ]
    _write_json(run_dir / "agent_eval.json", comparison)
    (run_dir / "agent_eval.md").write_text(
        render_markdown_summary(comparison, run_dir / "agent_eval.json"),
        encoding="utf-8",
    )
    run_trace.log_event(
        "evaluation_run_finished",
        {
            "score_complete": comparison["score_complete"],
            "question_status_counts": comparison["question_status_counts"],
            "total_time_s": comparison["evaluation"]["total_time_s"],
        },
    )
    return comparison


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    temporary_path.replace(path)


def _aggregate_question(question_id: str, attempts: list[dict[str, Any]]) -> dict[str, Any]:
    correct_attempts = [attempt for attempt in attempts if attempt["status"] == "passed"]
    completed_attempts = [
        attempt for attempt in attempts if attempt["status"] in {"passed", "failed"}
    ]
    if correct_attempts:
        status = "passed"
    elif completed_attempts:
        status = "failed"
    elif attempts:
        status = "timeout"
    else:
        status = "not_run"
    if correct_attempts:
        accuracy = True
    elif completed_attempts:
        accuracy = False
    else:
        accuracy = None
    return {
        "question_id": question_id,
        "status": status,
        "accuracy": accuracy,
        "total_time_s": sum(attempt["total_time_s"] for attempt in attempts),
        "stage_timings": _sum_stage_timings(attempts),
        "llm_call_count": sum(attempt["llm_call_count"] for attempt in attempts),
        "llm_calls": [call for attempt in attempts for call in attempt.get("llm_calls", [])],
        "tool_executions": [
            execution for attempt in attempts for execution in attempt.get("tool_executions", [])
        ],
        "repair_attempts": [
            repair for attempt in attempts for repair in attempt.get("repair_attempts", [])
        ],
        "attempt_count": len(attempts),
        "failure_reason": attempts[-1].get("failure_reason") if attempts else None,
        "failure_stage": attempts[-1].get("failure_stage") if attempts else None,
        "attempts": attempts,
    }


def _sum_stage_timings(attempts: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    for attempt in attempts:
        for stage, duration in attempt.get("stage_timings", {}).items():
            if isinstance(duration, (int, float)):
                totals[stage] = totals.get(stage, 0.0) + float(duration)
    return totals


def _build_resumable_summary(
    *,
    questions_by_id: dict[str, dict[str, Any]],
    saved_results: dict[str, dict[str, Any]],
    oracle: dict[str, dict[str, Any]],
    baseline_answers: dict[str, Any],
    diagnostics: dict[str, Any],
    total_time_s: float,
    warmup_time_s: float,
    warmup_llm_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    per_question: list[dict[str, Any]] = []
    correct_all = 0
    completed_count = 0
    correct_completed = 0
    outcomes: Counter[str] = Counter()
    failure_reasons: Counter[str] = Counter()
    for question_id in questions_by_id:
        result = saved_results.get(question_id, _aggregate_question(question_id, []))
        status = result["status"]
        accuracy = result.get("accuracy")
        agent_correct = status == "passed"
        baseline_correct = question_id in baseline_answers and answers_match(
            baseline_answers[question_id],
            oracle[question_id]["expected_answer"],
            float(oracle[question_id]["tolerance"]),
        )
        outcome = "tie" if agent_correct == baseline_correct else "win" if agent_correct else "loss"
        outcomes[outcome] += 1
        failure_reason = result.get("failure_reason")
        if failure_reason:
            failure_reasons[str(failure_reason)] += 1
        if status in {"passed", "failed"}:
            completed_count += 1
            correct_completed += status == "passed"
        correct_all += status == "passed"
        per_question.append(
            {
                "question_id": question_id,
                "status": status,
                "accuracy": accuracy,
                "baseline_accuracy": baseline_correct,
                "total_time_s": result.get("total_time_s", 0.0),
                "stage_timings": result.get("stage_timings", {}),
                "llm_call_count": result.get("llm_call_count", 0),
                "llm_calls": result.get("llm_calls", []),
                "tool_executions": result.get("tool_executions", []),
                "repair_attempts": result.get("repair_attempts", []),
                "attempt_count": result.get("attempt_count", 0),
                "failure_reason": result.get("failure_reason"),
                "failure_stage": result.get("failure_stage"),
                "outcome": outcome,
            }
        )
    total_questions = len(questions_by_id)
    status_counts = Counter(row["status"] for row in per_question)
    terminal_statuses = {"passed", "failed", "timeout"}
    score_complete = all(row["status"] in terminal_statuses for row in per_question)
    completed_accuracy = correct_completed / completed_count if completed_count else None
    aggregate_total_time = sum(row["total_time_s"] for row in per_question)
    aggregate_stage_timings: dict[str, float] = {}
    for row in per_question:
        for stage, duration in row["stage_timings"].items():
            aggregate_stage_timings[stage] = aggregate_stage_timings.get(stage, 0.0) + float(
                duration
            )
    aggregate_tool_executions = [
        execution for row in per_question for execution in row["tool_executions"]
    ]
    aggregate_repairs = [repair for row in per_question for repair in row["repair_attempts"]]
    aggregate_llm_calls = sum(row["llm_call_count"] for row in per_question)
    return {
        "score_complete": score_complete,
        "agent": {
            "correct": correct_all,
            "total": total_questions,
            "accuracy_over_all_questions": correct_all / total_questions
            if total_questions
            else 0.0,
            "accuracy_over_completed_questions": completed_accuracy,
            "completed_questions": completed_count,
            "timeouts": status_counts["timeout"],
            "not_run": status_counts["not_run"],
        },
        "baseline": {
            "correct": sum(row["baseline_accuracy"] for row in per_question),
            "total": total_questions,
            "accuracy": (
                sum(row["baseline_accuracy"] for row in per_question) / total_questions
                if total_questions
                else 0.0
            ),
            "note": "The baseline's 20/20 is a template-keyed ceiling, not a fair competitor.",
        },
        "question_status_counts": dict(status_counts),
        "baseline_comparison": dict(outcomes),
        "failure_reasons": dict(failure_reasons),
        "aggregate": {
            "status": "complete" if score_complete else "incomplete",
            "accuracy_over_all_questions": (
                correct_all / total_questions if total_questions else 0.0
            ),
            "accuracy_over_completed_questions": completed_accuracy,
            "completed_questions": completed_count,
            "total_time_s": aggregate_total_time,
            "stage_timings": aggregate_stage_timings,
            "llm_call_count": aggregate_llm_calls,
            "warmup_llm_call_count": len(warmup_llm_calls),
            "total_llm_call_count": aggregate_llm_calls + len(warmup_llm_calls),
            "llm_calls": [call for row in per_question for call in row["llm_calls"]],
            "tool_executions": aggregate_tool_executions,
            "repair_attempts": aggregate_repairs,
        },
        "per_question": per_question,
        "evaluation": {
            **diagnostics,
            "total_time_s": total_time_s,
            "warmup_time_s": warmup_time_s,
            "warmup_llm_calls": warmup_llm_calls,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("Sample-Superstore.csv"))
    parser.add_argument("--oracle", type=Path, default=Path("evaluation/benchmark/oracle.json"))
    parser.add_argument(
        "--questions-file", type=Path, default=Path("evaluation/benchmark/questions.json")
    )
    parser.add_argument(
        "--questions",
        help="Comma-separated question IDs to run, for example q10,q11. Defaults to all.",
    )
    parser.add_argument("--results-dir", type=Path, default=Path("evaluation/results"))
    parser.add_argument("--model")
    parser.add_argument("--mode", choices=("real", "mock"), default="real")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--run-id", help="Name a new evaluation directory.")
    parser.add_argument("--resume", metavar="RUN_ID", help="Resume an existing evaluation run.")
    parser.add_argument(
        "--per-call-timeout-s",
        type=float,
        help="Evaluation-only override; defaults to budgets.per_call_timeout_s in config.yaml.",
    )
    parser.add_argument("--per-question-budget-s", type=float)
    parser.add_argument("--overall-timeout-s", type=float)
    parser.add_argument("--max-repair-attempts", type=int)
    parser.add_argument(
        "--max-replans",
        type=int,
        help="Override budgets.max_replans for this run only (0 disables result-driven replanning).",
    )
    parser.add_argument("--max-llm-calls-per-question", type=int)
    parser.add_argument(
        "--thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable Ollama thinking mode; defaults to evaluation config.",
    )
    parser.add_argument(
        "--keep-alive", help="Ollama keep_alive value; defaults to evaluation config."
    )
    args = parser.parse_args()
    resume_id = args.resume
    run_id = resume_id or args.run_id
    if args.resume and args.run_id:
        parser.error("Use --resume RUN_ID or --run-id, not both.")
    question_ids = (
        [part.strip() for part in args.questions.split(",") if part.strip()]
        if args.questions
        else None
    )
    summary = evaluate_agent(
        dataset_path=args.dataset,
        oracle_path=args.oracle,
        questions_path=args.questions_file,
        results_dir=args.results_dir,
        model=args.model,
        repeats=args.repeats,
        per_call_timeout_s=args.per_call_timeout_s,
        per_question_budget_s=args.per_question_budget_s,
        overall_timeout_s=args.overall_timeout_s,
        max_repair_attempts=args.max_repair_attempts,
        max_replans=args.max_replans,
        max_llm_calls_per_question=args.max_llm_calls_per_question,
        thinking_enabled=args.thinking,
        keep_alive=args.keep_alive,
        run_id=run_id,
        resume=bool(resume_id),
        selected_question_ids=question_ids,
        mode=args.mode,
    )
    print(
        json.dumps(
            {
                "run_id": summary["run_id"],
                "score_complete": summary["score_complete"],
                "summary_path": str(args.results_dir / summary["run_id"] / "agent_eval.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
