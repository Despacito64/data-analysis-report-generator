"""Planner user prompts for the chat interpreter path (D-047)."""

from __future__ import annotations

from da_agent.contracts.models import DatasetProfile, FilterSpec
from da_agent.core.chat_thread import (
    ChatThread,
    prior_group_labels,
    prior_grouping_column,
    suggest_filters_from_message,
)


def build_chat_user_prompt(
    question: str,
    profile: DatasetProfile,
    thread: ChatThread,
    filter_hints: list[FilterSpec],
    *,
    max_turns: int = 8,
) -> str:
    """Thread plus current question. No dollar amounts from prior turns."""
    lines = [
        f"Dataset: {profile.source_name} ({profile.row_count} rows)",
        "",
        "Conversation (oldest first):",
    ]
    for msg in thread.messages[-max_turns:]:
        if msg.role == "user":
            lines.append(f"User: {msg.text}")
        else:
            body = msg.summary or msg.text
            lines.append(f"Assistant: {body}")
            if msg.group_labels:
                lines.append(f"  (Group labels mentioned: {', '.join(msg.group_labels)})")
    lines.extend(["", f"Current user message: {question}", ""])
    prior_labels = prior_group_labels(thread)
    if prior_labels:
        lines.append(
            "Follow-up guidance: If the user names one of the group labels above "
            f"({', '.join(prior_labels)}), prefer filtering to that value and keeping "
            "the same metric as the previous analysis unless they ask for a new metric or breakdown."
        )
        lines.append("")
    if filter_hints:
        hint_str = ", ".join(f"{f.column} {f.operator} {f.value!r}" for f in filter_hints)
        lines.append(f"Suggested filters from the current message: {hint_str}")
        lines.append("")
    lines.extend(
        [
            "Chat planning rule: Never finish with filter alone when the user wants amounts or a drill-down.",
            "After filter, add group_aggregate (same metric as the prior turn) or rank on the filtered rows.",
            "",
            "Return a JSON plan for the current user message only.",
        ]
    )
    return "\n".join(lines)


def filter_hints_for_turn(
    question: str, profile: DatasetProfile, thread: ChatThread
) -> list[FilterSpec]:
    return suggest_filters_from_message(
        question,
        profile,
        prior_group_labels(thread),
        grouping_column=prior_grouping_column(thread),
    )
