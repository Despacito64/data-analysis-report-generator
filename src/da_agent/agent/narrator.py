"""Second LLM pass: natural-language answer grounded in validated findings only."""

from __future__ import annotations

from da_agent.agent.answer import AgentAnswerStatus, AgentResult, validate_narrative_grounding
from da_agent.agent.planner import LLMClient
from da_agent.core.chat_thread import ChatThread
from da_agent.core.trace import RunTraceWriter

_MAX_WORDS = 120


def conversation_context_for_narrator(
    thread: ChatThread | None, *, max_turns: int = 6
) -> str | None:
    if not thread or not thread.messages:
        return None
    lines: list[str] = []
    for msg in thread.messages[-max_turns:]:
        if msg.role == "user":
            lines.append(f"User: {msg.text}")
        else:
            lines.append(f"Assistant: {msg.summary or msg.text}")
    return "\n".join(lines) if lines else None


def _build_narrator_messages(
    *,
    question: str,
    headline: str | None,
    allowed_claim_lines: list[str],
    conversation: str | None,
) -> list[dict[str, str]]:
    claims_block = "\n".join(f"- {line}" for line in allowed_claim_lines) or "- (none)"
    user_parts = [
        f"User question: {question}",
        "",
        "Verified numbers for this turn (use only these; do not invent or round differently):",
        claims_block,
    ]
    if headline:
        user_parts.extend(["", f"Technical headline: {headline}"])
    if conversation:
        user_parts.extend(
            ["", "Recent conversation (context only; do not reuse its numbers):", conversation]
        )
    user_parts.extend(
        [
            "",
            "Write 2–4 sentences answering the user in plain English.",
            "Use only the verified numbers above. No bullet lists. No evidence ids.",
        ]
    )
    return [
        {
            "role": "system",
            "content": (
                "You write short, clear data-analysis replies. "
                "You never compute new numbers or change numeric values."
            ),
        },
        {"role": "user", "content": "\n".join(user_parts)},
    ]


def _trim_prose(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("markdown"):
            cleaned = cleaned[8:].strip()
    words = cleaned.split()
    if len(words) > _MAX_WORDS:
        cleaned = " ".join(words[:_MAX_WORDS]).rstrip(".,;") + "."
    return cleaned


def synthesize_answer_narrative(
    client: LLMClient,
    *,
    question: str,
    headline: str | None,
    allowed_claim_lines: list[str],
    conversation: str | None = None,
    trace_writer: RunTraceWriter | None = None,
) -> str | None:
    """Call the model once for user-facing prose. Returns None on empty input or LLM failure."""
    if not allowed_claim_lines:
        return None
    messages = _build_narrator_messages(
        question=question,
        headline=headline,
        allowed_claim_lines=allowed_claim_lines,
        conversation=conversation,
    )
    try:
        content, raw = client.chat(messages)
    except (RuntimeError, OSError, TimeoutError, ConnectionError) as exc:
        if trace_writer:
            trace_writer.log_event(
                "answer_narrative_llm",
                {"status": "error", "reason": str(exc)},
            )
        return None
    prose = _trim_prose(content)
    if trace_writer:
        trace_writer.log_event(
            "answer_narrative_llm",
            {"status": "ok", "chars": len(prose), "raw_keys": list(raw.keys())},
        )
    return prose or None


def apply_llm_answer_narrative(
    result: AgentResult,
    *,
    client: LLMClient,
    headline: str | None,
    allowed_claim_lines: list[str],
    conversation: str | None = None,
    trace_writer: RunTraceWriter | None = None,
) -> AgentResult:
    """Replace templated answer_text with grounded LLM prose when validation passes."""
    if result.status != AgentAnswerStatus.ANSWERED or not allowed_claim_lines:
        return result
    prose = synthesize_answer_narrative(
        client,
        question=result.question,
        headline=headline,
        allowed_claim_lines=allowed_claim_lines,
        conversation=conversation,
        trace_writer=trace_writer,
    )
    if not prose:
        return result
    grounded_outputs = [item.tool_output for item in result.evidence]
    if not validate_narrative_grounding(prose, grounded_outputs):
        if trace_writer:
            trace_writer.log_event(
                "answer_narrative_fallback",
                {"reason": "llm_narrative_ungrounded", "run_id": result.run_id},
            )
        return result
    return result.model_copy(update={"answer_text": prose})
