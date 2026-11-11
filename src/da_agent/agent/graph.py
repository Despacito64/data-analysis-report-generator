"""Fixed LangGraph control graph for the dynamic planning agent.

Layer 6 module: wires resolve -> plan -> execute -> inspect -> replan-or-finalize.
The control graph is fixed; only the analytical task graph in AgentState changes.
Never imports evaluation/oracle or da_agent.agent.baseline.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from langgraph.graph import END, StateGraph

from da_agent.agent.executor import PlanExecutionResult, TaskStatus, execute_plan
from da_agent.agent.planner import (
    LLMClient,
    Plan,
    failure_reference_id,
    generate_plan,
    replan_on_failure,
    replan_on_result,
)
from da_agent.agent.resolver import resolve_question
from da_agent.agent.state import AgentState
from da_agent.contracts.models import (
    Budgets,
    DatasetProfile,
    ExecutionStatus,
    Failure,
    FailureClass,
    PlanRevision,
    RevisionChangeType,
    RunStatus,
)
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.tools.registry import export_tool_specs

# ---------------------------------------------------------------------------
# Routing Logic (pure functions of state)
# ---------------------------------------------------------------------------


def route_after_resolve(state: AgentState) -> str:
    resolved = state.get("resolved")
    if resolved is None or not resolved.answerable:
        return "finalize"
    return "plan"


def route_after_plan(state: AgentState) -> str:
    if state.get("plan") is None or state.get("status") == "failed":
        return "finalize"
    return "execute"


def route_after_inspect(state: AgentState) -> str:
    result = state.get("last_exec_result")
    replan_count: int = state.get("replan_count", 0)
    max_replans: int = state.get("max_replans", load_config().budgets.max_replans)

    if result is None:
        return "finalize"

    failed_records = [r for r in result.records if r.status == TaskStatus.FAILED]
    if failed_records:
        if result.failure and result.failure.recoverable:
            return "replan_failure"
        return "finalize"
    if result.status == "complete" and result.evidence_ids and replan_count < max_replans:
        return "replan_result"
    return "finalize"


def route_after_replan(state: AgentState) -> str:
    if state.get("status") in ("complete", "partial", "failed") or state.get("plan") is None:
        return "finalize"
    return "execute"


# ---------------------------------------------------------------------------
# Node factory – captures llm_client and trace_writer via closure
# ---------------------------------------------------------------------------


def build_nodes(
    llm_client: LLMClient | None = None,
    trace_writer: RunTraceWriter | None = None,
) -> dict[str, Any]:
    """Return a dict of node callables capturing shared dependencies in closure."""

    def node_resolve(state: AgentState) -> dict[str, Any]:
        """Resolve the natural-language question against the dataset profile."""
        profile = state["profile"]
        question = state["question"]
        resolved = resolve_question(question, profile)
        if trace_writer:
            trace_writer.log_event(
                "resolved_question",
                {"answerable": resolved.answerable, "intent": resolved.intent},
            )
        if not resolved.answerable:
            failure = Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=False,
                message=resolved.decline_reason or "Question is unanswerable",
                context={},
            )
            if trace_writer:
                trace_writer.log_failure(failure)
            return {"resolved": resolved, "status": "failed", "failures": [failure]}
        return {"resolved": resolved}

    def node_plan(state: AgentState) -> dict[str, Any]:
        """Generate and validate the initial execution plan via the LLM."""
        resolved = state.get("resolved")
        profile = state["profile"]

        if resolved is None or not resolved.answerable:
            decline = resolved.decline_reason if resolved else "No resolved question"
            failure = Failure(
                failure_class=FailureClass.INVALID_ARGS,
                recoverable=False,
                message=decline or "Question is unanswerable",
                context={},
            )
            if trace_writer:
                trace_writer.log_failure(failure)
            return {"plan": None, "status": "failed", "failures": [failure]}

        plan, failure = generate_plan(
            resolved,
            profile,
            client=llm_client,
            trace_writer=trace_writer,
            max_steps=state.get("budgets", load_config().budgets).max_tool_calls,
            max_repairs=1,
        )

        if failure:
            return {"plan": None, "status": "failed", "failures": [failure]}

        return {"plan": plan, "plan_version": plan.plan_version if plan else 1}

    def node_execute(state: AgentState) -> dict[str, Any]:
        """Execute the current plan via the DAG executor."""
        plan: Plan | None = state.get("plan")
        if plan is None:
            return {"status": "failed"}

        df = state["df"]
        profile = state["profile"]
        budgets: Budgets = state.get("budgets", load_config().budgets)
        evidence_store: dict[str, Any] = dict(state.get("evidence_store") or {})
        previous_records = list(state.get("executed_records") or [])
        used_tool_calls = sum(record.status != TaskStatus.SKIPPED for record in previous_records)

        result: PlanExecutionResult = execute_plan(
            plan=plan,
            df=df,
            profile=profile,
            budgets=budgets,
            trace_writer=trace_writer,
            evidence_store=evidence_store,
            max_steps=max(0, budgets.max_tool_calls - used_tool_calls),
            prior_records=previous_records,
        )

        new_evidence_ids = list(
            dict.fromkeys(list(state.get("evidence_ids") or []) + result.evidence_ids)
        )
        existing_records = previous_records
        new_records = existing_records + [
            record
            for record in result.records
            if not any(
                previous.task_id == record.task_id
                and previous.tool == record.tool
                and previous.args == record.args
                and previous.status == record.status
                and previous.evidence_id == record.evidence_id
                for previous in existing_records
            )
        ]
        failures = list(state.get("failures") or [])
        if result.failure:
            failures.append(result.failure)

        return {
            "executed_records": new_records,
            "evidence_store": evidence_store,
            "evidence_ids": new_evidence_ids,
            "failures": failures,
            "last_exec_result": result,
        }

    def node_inspect(state: AgentState) -> dict[str, Any]:
        """Inspect execution result and surface first failed task id for replanning."""
        result = state.get("last_exec_result")
        if result is None:
            return {}
        failed_records = [r for r in result.records if r.status == TaskStatus.FAILED]
        if failed_records:
            return {"failed_task_id": failed_records[0].task_id}
        return {"failed_task_id": None}

    def node_replan_failure(state: AgentState) -> dict[str, Any]:
        """Ask the LLM for a corrected plan after a task failure."""
        resolved = state.get("resolved")
        profile = state["profile"]
        current_plan: Plan | None = state.get("plan")
        failures: list[Failure] = list(state.get("failures") or [])
        failed_task_id: str = state.get("failed_task_id") or ""
        replan_count: int = state.get("replan_count", 0)
        max_replans: int = state.get("max_replans", load_config().budgets.max_replans)

        if replan_count >= max_replans or resolved is None or current_plan is None:
            budget_failure = Failure(
                failure_class=FailureClass.BUDGET_EXHAUSTED,
                recoverable=False,
                message=f"Replan budget exhausted after {replan_count} attempts",
                context={"max_replans": max_replans},
            )
            if trace_writer:
                trace_writer.log_failure(budget_failure)
            return {
                "status": "partial",
                "failures": failures + [budget_failure],
                "replan_count": replan_count + 1,
            }

        execution_result = state.get("last_exec_result")
        trigger_failure = execution_result.failure if execution_result else None
        if trigger_failure is None:
            trigger_failure = (
                failures[-1]
                if failures
                else Failure(
                    failure_class=FailureClass.UNKNOWN_TOOL,
                    recoverable=True,
                    message="Unknown task failure",
                    context={},
                    task_id=failed_task_id,
                )
            )

        tool_specs = export_tool_specs()
        available_columns = [c.name for c in profile.columns]

        new_plan, replan_failure = replan_on_failure(
            resolved=resolved,
            profile=profile,
            current_plan=current_plan,
            failed_task_id=failed_task_id,
            failure=trigger_failure,
            available_columns=available_columns,
            tool_specs=tool_specs,
            client=llm_client,
            trace_writer=trace_writer,
            max_steps=state.get("budgets", load_config().budgets).max_tool_calls,
            max_repairs=1,
        )

        if replan_failure or new_plan is None:
            return {
                "status": "partial",
                "failures": failures + ([replan_failure] if replan_failure else []),
                "replan_count": replan_count + 1,
            }

        old_by_id = {task.id: task for task in current_plan.tasks}
        new_by_id = {task.id: task for task in new_plan.tasks}
        affected_task_ids = [
            task.id
            for task in new_plan.tasks
            if task.id not in old_by_id
            or task.model_dump(mode="json", exclude={"plan_version", "status"})
            != old_by_id[task.id].model_dump(mode="json", exclude={"plan_version", "status"})
        ]
        affected_task_ids.extend(task.id for task in current_plan.tasks if task.id not in new_by_id)
        if any(task_id in old_by_id and task_id in new_by_id for task_id in affected_task_ids):
            change_type = RevisionChangeType.REPLACED
        elif any(task_id not in old_by_id for task_id in affected_task_ids):
            change_type = RevisionChangeType.ADDED
        else:
            change_type = RevisionChangeType.CANCELLED
        return {
            "plan": new_plan,
            "plan_version": new_plan.plan_version,
            "replan_count": replan_count + 1,
            "revisions": list(state.get("revisions") or [])
            + [
                PlanRevision(
                    from_version=current_plan.plan_version,
                    to_version=new_plan.plan_version,
                    trigger_evidence_id=failure_reference_id(trigger_failure),
                    change=change_type,
                    observed_result=trigger_failure.message[:500],
                    affected_tasks=affected_task_ids,
                )
            ],
            "evidence_ids": list(state.get("evidence_ids") or []),
            "failed_task_id": None,
        }

    def node_replan_result(state: AgentState) -> dict[str, Any]:
        """Ask the planner for a bounded follow-up based on successful result summaries."""
        resolved = state.get("resolved")
        profile = state["profile"]
        current_plan = state.get("plan")
        result = state.get("last_exec_result")
        replan_count = state.get("replan_count", 0)
        max_replans = state.get("max_replans", load_config().budgets.max_replans)

        if resolved is None or current_plan is None or result is None:
            return {"status": "partial"}

        if replan_count >= max_replans:
            return {"replan_count": replan_count}

        next_plan, failure = replan_on_result(
            resolved=resolved,
            profile=profile,
            current_plan=current_plan,
            records=result.records,
            available_columns=[column.name for column in profile.columns],
            tool_specs=export_tool_specs(),
            client=llm_client,
            trace_writer=trace_writer,
            max_steps=state.get("budgets", load_config().budgets).max_tool_calls,
            max_repairs=1,
        )
        if failure:
            failures = list(state.get("failures") or []) + [failure]
            return {
                "status": "partial",
                "failures": failures,
                "replan_count": replan_count + 1,
            }
        if next_plan is None:
            return {"status": "complete", "replan_count": replan_count + 1}

        old_tasks = {task.id: task for task in current_plan.tasks}
        affected = [
            task.id
            for task in next_plan.tasks
            if task.id not in old_tasks
            or task.model_dump(mode="json", exclude={"plan_version", "status"})
            != old_tasks[task.id].model_dump(mode="json", exclude={"plan_version", "status"})
        ]
        change = (
            RevisionChangeType.REPLACED
            if any(task_id in old_tasks for task_id in affected)
            else RevisionChangeType.ADDED
        )
        trigger_id = next(
            (record.evidence_id for record in reversed(result.records) if record.evidence_id),
            None,
        )
        observed_result = "; ".join(
            f"{record.task_id}: {record.output_summary}"
            for record in result.records
            if record.status == TaskStatus.OK
        )[:500]
        revision = PlanRevision(
            from_version=current_plan.plan_version,
            to_version=next_plan.plan_version,
            trigger_evidence_id=trigger_id,
            change=change,
            observed_result=observed_result,
            affected_tasks=affected,
        )
        return {
            "plan": next_plan,
            "plan_version": next_plan.plan_version,
            "revisions": list(state.get("revisions") or []) + [revision],
            "replan_count": replan_count + 1,
            "failed_task_id": None,
        }

    def node_finalize(state: AgentState) -> dict[str, Any]:
        """Build structured final answer from evidence and set terminal status."""
        evidence_ids = state.get("evidence_ids") or []
        failures = state.get("failures") or []
        result = state.get("last_exec_result")

        if result and result.status == "complete":
            status = "complete"
        elif state.get("status") == "partial" or evidence_ids:
            status = "partial"
        else:
            status = "failed"

        final_answer: dict[str, Any] = {}
        for rec in state.get("executed_records") or []:
            if rec.status == TaskStatus.OK and rec.output_summary:
                final_answer[rec.task_id] = {
                    "tool": rec.tool,
                    "summary": rec.output_summary,
                    "evidence_id": rec.evidence_id,
                }

        if trace_writer:
            run_status = RunStatus(
                status=ExecutionStatus(status),
                reason_text=(
                    f"Completed with {len(evidence_ids)} evidence record(s)."
                    if status == "complete"
                    else f"{status.title()}: {len(evidence_ids)} evidence record(s), "
                    f"{len(failures)} failure(s)."
                ),
            )
            trace_writer.log_status(run_status)
            trace_writer.log_event(
                "final_answer",
                {
                    "status": status,
                    "answer": final_answer,
                    "evidence_ids": evidence_ids,
                },
            )

        return {"status": status, "final_answer": final_answer}

    return {
        "resolve": node_resolve,
        "plan": node_plan,
        "execute": node_execute,
        "inspect": node_inspect,
        "replan_failure": node_replan_failure,
        "replan_result": node_replan_result,
        "finalize": node_finalize,
    }


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------


def build_agent_graph(
    llm_client: LLMClient | None = None,
    trace_writer: RunTraceWriter | None = None,
) -> Any:
    """Build and compile the fixed LangGraph control graph."""
    nodes = build_nodes(llm_client=llm_client, trace_writer=trace_writer)

    graph = StateGraph(AgentState)
    for name, fn in nodes.items():
        graph.add_node(name, fn)

    graph.set_entry_point("resolve")
    graph.add_conditional_edges(
        "resolve", route_after_resolve, {"plan": "plan", "finalize": "finalize"}
    )
    graph.add_conditional_edges(
        "plan", route_after_plan, {"execute": "execute", "finalize": "finalize"}
    )
    graph.add_edge("execute", "inspect")
    graph.add_conditional_edges(
        "inspect",
        route_after_inspect,
        {
            "replan_failure": "replan_failure",
            "replan_result": "replan_result",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "replan_failure",
        route_after_replan,
        {"execute": "execute", "finalize": "finalize"},
    )
    graph.add_conditional_edges(
        "replan_result",
        route_after_replan,
        {"execute": "execute", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_agent(
    question: str,
    df: pd.DataFrame,
    profile: DatasetProfile,
    *,
    run_id: str = "agent_run",
    llm_client: LLMClient | None = None,
    budgets: Budgets | None = None,
    trace_writer: RunTraceWriter | None = None,
    max_replans: int | None = None,
) -> dict[str, Any]:
    """Run the full dynamic planning agent and return the final state."""
    if budgets is None:
        budgets = load_config().budgets
    if max_replans is None:
        max_replans = budgets.max_replans
    if trace_writer is None:
        config = load_config()
        trace_writer = RunTraceWriter(run_id=run_id, base_dir=config.run_trace.base_dir)

    initial_state: AgentState = {
        "question": question,
        "df": df,
        "profile": profile,
        "resolved": None,
        "plan": None,
        "plan_version": 1,
        "revisions": [],
        "executed_records": [],
        "evidence_store": {},
        "evidence_ids": [],
        "failures": [],
        "budgets": budgets,
        "replan_count": 0,
        "max_replans": max_replans,
        "status": "pending",
        "final_answer": None,
        "run_id": run_id,
        "last_exec_result": None,
        "failed_task_id": None,
    }

    agent = build_agent_graph(llm_client=llm_client, trace_writer=trace_writer)
    final_state = agent.invoke(initial_state)
    return dict(final_state)
