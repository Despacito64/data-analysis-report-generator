"""Dynamic analytical plan generation using local LLMs with bounded repair.

Layer 6 module: translates resolved questions and dataset profiles into validated execution plans.
Coordinates LLM prompting, plan parsing, DAG and tool validation, and single-turn repair.
Never imports evaluation/oracle.py or da_agent.agent.baseline.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from da_agent.agent.resolver import resolve_question
from da_agent.contracts.models import (
    DatasetProfile,
    Failure,
    FailureClass,
    ResolvedQuestion,
    Task,
    ToolSpec,
)
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.tools.registry import DEFAULT_REGISTRY, export_tool_specs
from da_agent.validation.plan_check import validate_plan


class Plan(BaseModel):
    """Execution plan containing ordered analytical tasks."""

    model_config = ConfigDict(extra="forbid")

    plan_version: int = 1
    tasks: list[Task] = Field(default_factory=list)


class PlanOutput(BaseModel):
    """Schema expected from LLM responses."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[Task]


class LLMClient(Protocol):
    """Protocol for mockable LLM inference clients."""

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> tuple[str, dict[str, Any]]: ...


class OllamaClient:
    """Client for local Ollama chat API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:4b",
        temperature: float = 0.0,
        seed: int = 42,
        timeout_s: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.base_url = self.base_url.removesuffix("/v1")
        self.model = model
        self.temperature = temperature
        self.seed = seed
        self.timeout_s = timeout_s

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        url = f"{self.base_url}/api/chat"
        body: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature if temperature is None else temperature,
                "seed": self.seed if seed is None else seed,
            },
        }
        if schema:
            body["format"] = schema

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                payload = json.load(response)
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Ollama connection error at {url}: {exc}") from exc

        content = payload.get("message", {}).get("content", "")
        return str(content), payload


class MockLLMClient:
    """Mock client returning predetermined responses for testing without live Ollama."""

    def __init__(
        self,
        responses: list[str | dict[str, Any]] | None = None,
        default_response: str | dict[str, Any] | None = None,
    ) -> None:
        self.responses: list[str] = [
            r if isinstance(r, str) else json.dumps(r) for r in (responses or [])
        ]
        self.default_response: str = (
            default_response
            if isinstance(default_response, str)
            else (json.dumps(default_response) if default_response else "{}")
        )
        self.call_history: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        schema: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> tuple[str, dict[str, Any]]:
        self.call_history.append(
            {
                "messages": messages,
                "schema": schema,
                "model": model,
                "temperature": temperature,
                "seed": seed,
            }
        )
        if self.responses:
            content = self.responses.pop(0)
        else:
            content = self.default_response
        return content, {"mock": True, "eval_count": 50, "eval_duration": 1_000_000_000}


def _strip_json_fences(text: str) -> str:
    """Strip markdown backticks (e.g. ```json ... ```) from model response."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def build_system_prompt(
    profile: DatasetProfile,
    tool_specs: list[ToolSpec],
    max_steps: int = 5,
) -> str:
    """Build system prompt with tool specs, dataset columns, and few-shot examples (non-benchmark)."""
    tools_formatted = "\n\n".join(
        f"Tool '{spec.name}':\n"
        f"  Description: {spec.description}\n"
        f"  Arguments Schema: {json.dumps(spec.args_schema, indent=2)}"
        for spec in tool_specs
    )

    columns_formatted = ", ".join(
        f"{col.name} ({col.semantic_type.value})" for col in profile.columns
    )

    return f"""You are a deterministic data analysis planner.
Your goal is to translate a user's analytical question into an execution plan of registered tools.
You must use ONLY the registered tools below.
The plan must contain at most {max_steps} steps.

Registered Tools:
{tools_formatted}

Dataset Columns and Semantic Types (use exact column names):
{columns_formatted}

JSON Output Schema:
Return ONLY a valid JSON object matching this schema:
{{
  "tasks": [
    {{
      "id": "t1",
      "tool": "<registered_tool_name>",
      "args": {{ ... }},
      "depends_on": [],
      "rationale": "<one sentence explanation>"
    }}
  ]
}}

Few-Shot Examples:

Example 1:
Question: "What is the average quantity ordered for each Ship Mode?"
Plan:
{{
  "tasks": [
    {{
      "id": "t1",
      "tool": "group_aggregate",
      "args": {{
        "by": ["Ship Mode"],
        "metric_column": "Quantity",
        "aggregation": "mean"
      }},
      "depends_on": [],
      "rationale": "Compute average order quantity grouped by shipping mode."
    }}
  ]
}}

Example 2:
Question: "For orders in California, which 5 Product Names have the highest total Sales?"
Plan:
{{
  "tasks": [
    {{
      "id": "t1",
      "tool": "filter",
      "args": {{
        "conditions": [{{"column": "State", "operator": "eq", "value": "California"}}]
      }},
      "depends_on": [],
      "rationale": "Filter dataset to orders placed in California."
    }},
    {{
      "id": "t2",
      "tool": "rank",
      "args": {{
        "entity_column": "Product Name",
        "metric_column": "Sales",
        "ascending": false,
        "top_n": 5
      }},
      "depends_on": ["t1"],
      "rationale": "Rank top 5 products by sales in California."
    }}
  ]
}}

Example 3:
Question: "What percentage of total Profit is contributed by each Segment?"
Plan:
{{
  "tasks": [
    {{
      "id": "t1",
      "tool": "segment_contribution",
      "args": {{
        "segment_column": "Segment",
        "metric_column": "Profit"
      }},
      "depends_on": [],
      "rationale": "Calculate relative profit share breakdown across customer segments."
    }}
  ]
}}
"""


def _build_user_prompt(resolved: ResolvedQuestion) -> str:
    """Format resolved question into the user prompt."""
    parts = [f"Question: {resolved.question_text}"]
    if resolved.intent:
        parts.append(f"Intent: {resolved.intent}")
    if resolved.metric:
        parts.append(f"Target Metric: {resolved.metric}")
    if resolved.grouping:
        parts.append(f"Grouping Columns: {', '.join(resolved.grouping)}")
    if resolved.filters:
        filters_str = ", ".join(f"{f.column} {f.operator} {f.value}" for f in resolved.filters)
        parts.append(f"Filters: {filters_str}")
    if resolved.period:
        parts.append(
            f"Period Window: {resolved.period.column} ({resolved.period.start or 'start'} to {resolved.period.end or 'end'}, grain={resolved.period.grain or 'none'})"
        )
    return "\n".join(parts)


def generate_plan(
    question: str | ResolvedQuestion,
    profile: DatasetProfile,
    *,
    tool_specs: list[ToolSpec] | None = None,
    client: LLMClient | None = None,
    trace_writer: RunTraceWriter | None = None,
    max_steps: int = 5,
    max_repairs: int = 1,
) -> tuple[Plan | None, Failure | None]:
    """Generate and validate an analytical execution plan with bounded repair."""
    # 1. Question resolution
    if isinstance(question, str):
        resolved = resolve_question(question, profile)
    else:
        resolved = question

    if not resolved.answerable:
        failure = Failure(
            failure_class=FailureClass.INVALID_ARGS,
            recoverable=False,
            message=resolved.decline_reason or "Question is unanswerable",
            context={"question": resolved.question_text},
        )
        if trace_writer:
            trace_writer.log_failure(failure)
        return None, failure

    # 2. Setup tools and client
    if tool_specs is None:
        tool_specs = export_tool_specs(DEFAULT_REGISTRY)

    tool_args_models = {
        name: DEFAULT_REGISTRY.get(name).args_model
        for name in DEFAULT_REGISTRY.list_tools()
        if DEFAULT_REGISTRY.get(name) is not None
    }

    if client is None:
        config = load_config()
        client = OllamaClient(
            base_url=config.model.base_url,
            model=config.model.name,
            temperature=config.model.temperature,
            seed=config.model.seed,
        )

    system_prompt = build_system_prompt(profile, tool_specs, max_steps=max_steps)
    user_prompt = _build_user_prompt(resolved)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 3. Planning & Repair Loop
    last_failure: Failure | None = None

    for attempt in range(max_repairs + 1):
        try:
            content, raw_payload = client.chat(
                messages,
                schema=PlanOutput.model_json_schema(),
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError, RuntimeError, OSError) as exc:
            last_failure = Failure(
                failure_class=FailureClass.TRANSIENT,
                recoverable=True,
                message=f"LLM inference error: {exc}",
                context={"attempt": attempt},
            )
            if trace_writer:
                trace_writer.log_failure(last_failure)
            return None, last_failure

        if trace_writer:
            trace_writer.log_event(
                "planner_llm_call",
                {"attempt": attempt, "raw_output": content, "payload": raw_payload},
            )

        # 4. Parse JSON
        parsed_plan: Plan | None = None
        try:
            cleaned = _strip_json_fences(content)
            output_obj = PlanOutput.model_validate_json(cleaned)
            parsed_plan = Plan(plan_version=1, tasks=output_obj.tasks)
        except (ValidationError, json.JSONDecodeError) as exc:
            last_failure = Failure(
                failure_class=FailureClass.SCHEMA_VIOLATION,
                recoverable=True,
                message=f"Plan schema or JSON validation failed: {exc}",
                context={"attempt": attempt, "raw_content": content},
            )

        # 5. If parse succeeded, validate DAG and tool arguments
        validation_errors: list[Failure] = []
        if parsed_plan is not None:
            validation_errors = validate_plan(
                parsed_plan,
                profile,
                tool_specs=tool_specs,
                tool_args_models=tool_args_models,
                max_steps=max_steps,
            )
            if not validation_errors:
                # Success!
                if trace_writer:
                    trace_writer.log_plan(plan_version=1, tasks=parsed_plan.tasks)
                return parsed_plan, None
            last_failure = validation_errors[0]

        # 6. Repair attempt if within budget
        if trace_writer:
            trace_writer.log_event(
                "planner_validation_failure",
                {
                    "attempt": attempt,
                    "errors": (
                        [e.model_dump(mode="json") for e in validation_errors]
                        if validation_errors
                        else [last_failure.model_dump(mode="json")]
                        if last_failure
                        else []
                    ),
                },
            )

        if attempt < max_repairs:
            error_bullets = "\n".join(
                f"- {e.message}"
                for e in (validation_errors or ([last_failure] if last_failure else []))
            )
            repair_prompt = (
                f"The previous plan failed validation with the following errors:\n"
                f"{error_bullets}\n\n"
                "Please fix these errors and return a corrected plan following the exact JSON schema."
            )
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": repair_prompt})
            if trace_writer:
                trace_writer.log_event(
                    "planner_repair_attempt",
                    {"attempt": attempt + 1, "prompt": repair_prompt},
                )

    # Exhausted retries
    if trace_writer and last_failure:
        trace_writer.log_failure(last_failure)

    return None, last_failure
