"""Chat thread helpers and filter hints (D-047)."""

from pathlib import Path

from da_agent.agent.chat_context import build_chat_user_prompt, filter_hints_for_turn
from da_agent.agent.graph import build_initial_state
from da_agent.contracts.models import Budgets
from da_agent.core.chat_thread import (
    ChatThread,
    append_assistant_message,
    append_user_message,
    chat_for_hash,
)
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile

DATASET = Path("Sample-Superstore.csv")


def _profile():
    df = load_data(DATASET)
    return compute_profile(df, file_path=DATASET)


def test_furniture_follow_up_gets_category_filter() -> None:
    profile = _profile()
    thread = append_assistant_message(
        ChatThread(),
        text="sales by category",
        summary="Totals by category",
        group_labels=["Technology", "Furniture", "Office Supplies"],
        grouping_column="Category",
    )
    hints = filter_hints_for_turn("tell me more about furniture", profile, thread)
    assert len(hints) == 1
    assert hints[0].column == "Category"
    assert hints[0].value == "Furniture"


def test_chat_prompt_contains_thread_not_amounts() -> None:
    profile = _profile()
    thread = append_user_message(
        append_assistant_message(
            ChatThread(),
            text="done",
            summary="Technology leads",
            group_labels=["Technology", "Furniture"],
            grouping_column="Category",
        ),
        "tell me more about furniture",
    )
    prompt = build_chat_user_prompt("tell me more about furniture", profile, thread, [])
    assert "Furniture" in prompt
    assert "836,154" not in prompt


def test_chat_initial_state_carries_thread() -> None:
    profile = _profile()
    thread = append_user_message(ChatThread(), "tell me more about furniture")
    writer = RunTraceWriter(run_id="chat-skip", base_dir="runs")
    state = build_initial_state(
        question="tell me more about furniture",
        df=load_data(DATASET),
        profile=profile,
        run_id="chat-skip",
        budgets=Budgets(
            max_llm_calls=2,
            max_tool_calls=2,
            max_replans=0,
            max_identical_retries=0,
            per_call_timeout_s=1,
            max_total_tokens=100,
        ),
        trace_writer=writer,
        max_replans=0,
        max_repairs=0,
        chat_thread=thread,
    )
    assert state.get("chat_thread") is thread
    assert state["evidence_records"] == {}


def test_hash_change_clears_chat() -> None:
    thread = append_user_message(ChatThread(), "hello")
    kept = chat_for_hash(thread, "a", "a")
    assert len(kept.messages) == 1
    cleared = chat_for_hash(thread, "a", "b")
    assert cleared.messages == []
