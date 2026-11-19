"""Unified planning thread without resolver."""

from da_agent.contracts.models import DialogueState, ResolvedQuestion
from da_agent.core.chat_thread import effective_planning_thread
from da_agent.core.dialogue import append_resolved_turn


def test_one_shot_question_becomes_thread() -> None:
    thread = effective_planning_thread("What are sales by category?")
    assert len(thread.messages) == 1
    assert thread.messages[0].role == "user"


def test_dialogue_becomes_thread_without_amounts() -> None:
    first = ResolvedQuestion(
        question_text="What are total sales by category?",
        intent="descriptive",
        answerable=True,
        grouping=["Category"],
        metric="sum(Sales)",
    )
    dialogue = append_resolved_turn(DialogueState(), first)
    thread = effective_planning_thread("by region", dialogue=dialogue)
    assert thread.messages[-1].text == "by region"
    assert any(m.role == "user" for m in thread.messages)
