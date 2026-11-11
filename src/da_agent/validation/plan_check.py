"""Plan validation and topological graph verification.

Layer 4 module: strictly imports contracts and core; NEVER imports da_agent.tools.
Validates execution plans for step bounds, tool presence, argument correctness,
acyclic dependencies, and initial execution readiness.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from da_agent.contracts.models import (
    DatasetProfile,
    Failure,
    FailureClass,
    Task,
    ToolSpec,
)
from da_agent.validation.args import validate_task_args


def _detect_cycles(tasks: list[Task]) -> list[str] | None:
    """Return a cycle as a list of task IDs if one exists, else None."""
    by_id = {task.id: task for task in tasks}
    visited: dict[str, int] = {}  # 0: unvisited, 1: visiting (in stack), 2: visited
    parent_map: dict[str, str] = {}

    for task in tasks:
        visited[task.id] = 0

    cycle_nodes: list[str] = []

    def dfs(node_id: str) -> bool:
        visited[node_id] = 1
        task = by_id.get(node_id)
        if task:
            for dep in task.depends_on:
                if dep not in by_id:
                    continue
                if visited.get(dep) == 1:
                    cycle_nodes.append(dep)
                    cycle_nodes.append(node_id)
                    return True
                if visited.get(dep) == 0:
                    parent_map[dep] = node_id
                    if dfs(dep):
                        return True
        visited[node_id] = 2
        return False

    for task in tasks:
        if visited[task.id] == 0 and dfs(task.id):
            return cycle_nodes

    return None


def validate_plan(
    plan_or_tasks: Any,
    profile: DatasetProfile,
    *,
    tool_specs: list[ToolSpec] | None = None,
    tool_args_models: dict[str, type[BaseModel]] | None = None,
    max_steps: int = 5,
) -> list[Failure]:
    """Validate a plan of tasks against schema, limits, DAG constraints and tool arguments.

    Returns an empty list if the plan is completely valid, or a list of Failure objects.
    """
    failures: list[Failure] = []

    tasks: list[Task] = getattr(plan_or_tasks, "tasks", plan_or_tasks)
    if not isinstance(tasks, list):
        failures.append(
            Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message="Plan must contain a list of tasks",
                context={"provided_type": type(tasks).__name__},
            )
        )
        return failures

    # 1. Non-empty check
    if not tasks:
        failures.append(
            Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message="Plan has no tasks",
                context={"actual_steps": 0},
            )
        )
        return failures

    # 2. Max steps check
    if len(tasks) > max_steps:
        failures.append(
            Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message=f"Plan exceeds maximum step limit of {max_steps} (got {len(tasks)} tasks)",
                context={"max_steps": max_steps, "actual_steps": len(tasks)},
            )
        )

    # 3. Task ID uniqueness
    seen_ids: set[str] = set()
    for task in tasks:
        if not hasattr(task, "id") or not task.id:
            failures.append(
                Failure(
                    failure_class=FailureClass.INVALID_ARGS,
                    recoverable=True,
                    message="Task is missing required 'id'",
                    context={},
                )
            )
            continue
        if task.id in seen_ids:
            failures.append(
                Failure(
                    failure_class=FailureClass.INVALID_ARGS,
                    recoverable=True,
                    message=f"Duplicate task id '{task.id}' found in plan",
                    context={"duplicate_id": task.id},
                    task_id=task.id,
                )
            )
        seen_ids.add(task.id)

    # 4. Dependency references exist
    for task in tasks:
        for dep in task.depends_on:
            if dep not in seen_ids:
                failures.append(
                    Failure(
                        failure_class=FailureClass.INVALID_ARGS,
                        recoverable=True,
                        message=f"Task '{task.id}' depends on nonexistent task '{dep}'",
                        context={"task_id": task.id, "missing_dependency": dep},
                        task_id=task.id,
                    )
                )

    # 5. Cycle and self-dependency detection
    for task in tasks:
        if task.id in task.depends_on:
            failures.append(
                Failure(
                    failure_class=FailureClass.INVALID_ARGS,
                    recoverable=True,
                    message=f"Task '{task.id}' has a circular self-dependency",
                    context={"task_id": task.id, "depends_on": task.depends_on},
                    task_id=task.id,
                )
            )

    cycle = _detect_cycles(tasks)
    if cycle:
        failures.append(
            Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message=f"Dependency cycle detected in plan involving tasks {cycle}",
                context={"cycle": cycle},
            )
        )

    # 6. Readiness check: at least one task must have depends_on == []
    has_ready = any(len(task.depends_on) == 0 for task in tasks)
    if not has_ready:
        failures.append(
            Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=True,
                message="Plan has no ready tasks (every task has dependencies)",
                context={},
            )
        )

    # 7. Task tool and arguments validation via validate_task_args
    available_tools = (
        list(tool_args_models.keys())
        if tool_args_models is not None
        else ([s.name for s in tool_specs] if tool_specs else None)
    )

    for task in tasks:
        args_model = tool_args_models.get(task.tool) if tool_args_models else None
        _, arg_failure = validate_task_args(
            tool_name=task.tool,
            args=task.args,
            profile=profile,
            args_model=args_model,
            available_tools=available_tools,
        )
        if arg_failure:
            arg_failure.task_id = task.id
            failures.append(arg_failure)

    return failures
