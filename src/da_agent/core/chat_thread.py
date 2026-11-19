"""Conversation thread for the React chat path (D-047). No amounts in messages."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from da_agent.contracts.models import DialogueState, FilterSpec


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    text: str
    group_labels: list[str] = Field(default_factory=list)
    summary: str | None = None
    grouping_column: str | None = None
    metric_column: str | None = None
    aggregation: str | None = None


class ChatThread(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(default_factory=list)


def chat_for_hash(
    thread: ChatThread | None, previous_hash: str | None, new_hash: str
) -> ChatThread:
    if thread is None or previous_hash != new_hash:
        return ChatThread()
    return thread


def append_user_message(thread: ChatThread, text: str) -> ChatThread:
    msg = ChatMessage(role="user", text=text.strip())
    return thread.model_copy(update={"messages": [*thread.messages, msg]})


def append_assistant_message(
    thread: ChatThread,
    *,
    text: str,
    summary: str | None = None,
    group_labels: list[str] | None = None,
    grouping_column: str | None = None,
    metric_column: str | None = None,
    aggregation: str | None = None,
) -> ChatThread:
    msg = ChatMessage(
        role="assistant",
        text=text.strip(),
        summary=summary,
        group_labels=list(group_labels or []),
        grouping_column=grouping_column,
        metric_column=metric_column,
        aggregation=aggregation,
    )
    return thread.model_copy(update={"messages": [*thread.messages, msg]})


def prior_group_labels(thread: ChatThread, *, max_messages: int = 12) -> list[str]:
    labels: list[str] = []
    for msg in reversed(thread.messages[-max_messages:]):
        if msg.role == "assistant":
            for label in msg.group_labels:
                if label not in labels:
                    labels.append(label)
    return labels


def prior_grouping_column(thread: ChatThread) -> str | None:
    for msg in reversed(thread.messages):
        if msg.role == "assistant" and msg.grouping_column:
            return msg.grouping_column
    return None


def effective_planning_thread(
    question: str,
    *,
    chat_thread: ChatThread | None = None,
    dialogue: DialogueState | None = None,
) -> ChatThread:
    """Thread used for LLM planning (chat API, one-shot, or Streamlit dialogue)."""
    if chat_thread is not None:
        return chat_thread
    thread = ChatThread()
    if dialogue is not None:
        for turn in dialogue.turns:
            if not turn.answerable:
                continue
            thread = append_user_message(thread, turn.question_text)
            group_col = turn.grouping[0] if len(turn.grouping) == 1 else None
            summary_parts = []
            if turn.metric:
                summary_parts.append(turn.metric)
            if turn.grouping:
                summary_parts.append(f"by {', '.join(turn.grouping)}")
            thread = append_assistant_message(
                thread,
                text="Prior analytical turn",
                summary=". ".join(summary_parts) if summary_parts else None,
                grouping_column=group_col,
            )
    q = question.strip()
    if not thread.messages or thread.messages[-1].text != q:
        thread = append_user_message(thread, q)
    return thread


def suggest_filters_from_message(
    text: str,
    profile,
    known_labels: list[str],
    *,
    grouping_column: str | None = None,
) -> list[FilterSpec]:
    """Map tokens to column filters using profile examples and prior result labels."""
    import re

    from da_agent.contracts.models import DatasetProfile, SemanticType

    if not isinstance(profile, DatasetProfile):
        return []
    filters: list[FilterSpec] = []
    q = text.strip()
    quoted = re.findall(r"'([^']+)'", q) + re.findall(r'"([^"]+)"', q)
    tokens = set(quoted)
    for word in q.replace("?", " ").split():
        clean = word.strip(".,'\"")
        if len(clean) >= 2:
            tokens.add(clean)

    cat_columns = [
        c.name
        for c in profile.columns
        if c.semantic_type in (SemanticType.CATEGORY, SemanticType.IDENTIFIER)
    ]

    def _match_value(val: str) -> FilterSpec | None:
        val_lower = val.lower()
        for col in profile.columns:
            if col.examples:
                for ex in col.examples:
                    if str(ex).lower() == val_lower:
                        return FilterSpec(column=col.name, operator="eq", value=ex)
        for label in known_labels:
            if label.lower() == val_lower:
                col = grouping_column or (cat_columns[0] if cat_columns else None)
                if col:
                    return FilterSpec(column=col, operator="eq", value=label)
        known_pairs = {
            "furniture": "Category",
            "technology": "Category",
            "office supplies": "Category",
            "west": "Region",
            "east": "Region",
            "central": "Region",
            "south": "Region",
            "consumer": "Segment",
            "corporate": "Segment",
            "home office": "Segment",
        }
        if val_lower in known_pairs and known_pairs[val_lower] in cat_columns:
            title = val_lower.title() if val_lower != "office supplies" else "Office Supplies"
            if val_lower == "home office":
                title = "Home Office"
            return FilterSpec(column=known_pairs[val_lower], operator="eq", value=title)
        return None

    seen: set[tuple[str, str]] = set()
    for token in tokens:
        spec = _match_value(token)
        if spec is None:
            continue
        key = (spec.column, str(spec.value).lower())
        if key in seen:
            continue
        seen.add(key)
        filters.append(spec)
    return filters
