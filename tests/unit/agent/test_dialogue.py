"""Conversational follow-ups stay symbolic and do not seed prior evidence."""

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from da_agent.agent.graph import build_initial_state
from da_agent.agent.planner import _build_user_prompt
from da_agent.agent.resolver import resolve_question
from da_agent.contracts.models import Budgets, DialogueState, DialogueTurn
from da_agent.core.dialogue import append_resolved_turn, dialogue_for_hash
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET = Path("Sample-Superstore.csv")


@pytest.fixture(scope="module")
def profile():
    df = load_data(DATASET)
    return compute_profile(df, file_path=DATASET)


def _budgets() -> Budgets:
    return Budgets(
        max_llm_calls=2,
        max_tool_calls=2,
        max_replans=0,
        max_identical_retries=0,
        per_call_timeout_s=1,
        max_total_tokens=100,
    )


def test_follow_up_inherits_metric_and_replaces_grouping(profile) -> None:
    first = resolve_question("What are total sales by category?", profile)
    dialogue = append_resolved_turn(DialogueState(), first)
    second = resolve_question("by region", profile, dialogue=dialogue)
    assert second.answerable
    assert second.metric == "sum(Sales)"
    assert second.grouping == ["Region"]
    assert "evidence_id" not in dialogue.model_dump()


def test_standalone_question_ignores_dialogue(profile) -> None:
    first = resolve_question("What are total sales by category?", profile)
    dialogue = append_resolved_turn(DialogueState(), first)
    fresh = resolve_question(
        "What is the total profit for each segment?", profile, dialogue=dialogue
    )
    assert fresh.metric == "sum(Profit)"
    assert fresh.grouping == ["Segment"]


def test_planner_prompt_has_no_prior_amounts(profile) -> None:
    first = resolve_question("What are total sales by category?", profile)
    dialogue = append_resolved_turn(DialogueState(), first)
    resolved = resolve_question("by region", profile, dialogue=dialogue)
    prompt = _build_user_prompt(resolved)
    assert "sum(Sales)" in prompt
    assert "Region" in prompt
    assert "99999.67" not in prompt
    assert "result_summary" not in prompt


def test_dialogue_turn_rejects_evidence_payload() -> None:
    with pytest.raises(ValidationError):
        DialogueTurn(
            question_text="sales",
            intent="group_aggregate",
            answerable=True,
            evidence_id="ev-1",
        )


def test_hash_change_clears_dialogue() -> None:
    state = DialogueState(
        turns=[
            DialogueTurn(
                question_text="sales by category",
                intent="group_aggregate",
                metric="sum(Sales)",
                grouping=["Category"],
            )
        ]
    )
    kept = dialogue_for_hash(state, "abc", "abc")
    assert len(kept.turns) == 1
    cleared = dialogue_for_hash(state, "abc", "def")
    assert cleared.turns == []


def test_chat_thread_run_starts_with_empty_evidence(profile, tmp_path: Path) -> None:
    from da_agent.core.chat_thread import ChatThread, append_user_message

    thread = append_user_message(ChatThread(), "by region")
    writer = RunTraceWriter(run_id="chat-empty", base_dir=tmp_path)
    state = build_initial_state(
        question="by region",
        df=pd.DataFrame(),
        profile=profile,
        run_id="chat-empty",
        budgets=_budgets(),
        trace_writer=writer,
        max_replans=0,
        max_repairs=0,
        chat_thread=thread,
    )
    assert state["evidence_records"] == {}
    assert state.get("chat_thread") is thread


def test_dialogue_run_starts_with_empty_evidence(profile, tmp_path: Path) -> None:
    first = resolve_question("What are total sales by category?", profile)
    dialogue = append_resolved_turn(DialogueState(), first)
    writer = RunTraceWriter(run_id="dialogue-empty", base_dir=tmp_path)
    state = build_initial_state(
        question="by region",
        df=pd.DataFrame(),
        profile=profile,
        run_id="dialogue-empty",
        budgets=_budgets(),
        trace_writer=writer,
        max_replans=0,
        max_repairs=0,
        reused_evidence=["must-not-be-read"],  # type: ignore[list-item]
        dialogue=dialogue,
    )
    assert state["evidence_records"] == {}
    assert state["evidence_ids"] == []
    assert state["dialogue"] is dialogue


def test_single_shot_without_dialogue_has_empty_evidence(profile, tmp_path: Path) -> None:
    resolved = resolve_question("What are total sales by category?", profile)
    assert resolved.grouping == ["Category"]
    assert resolved.metric == "sum(Sales)"
    writer = RunTraceWriter(run_id="single-shot", base_dir=tmp_path)
    state = build_initial_state(
        question="What are total sales by category?",
        df=pd.DataFrame(),
        profile=profile,
        run_id="single-shot",
        budgets=_budgets(),
        trace_writer=writer,
        max_replans=0,
        max_repairs=0,
    )
    assert state["evidence_records"] == {}
    assert state.get("dialogue") is None
