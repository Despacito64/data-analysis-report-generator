"""Symbolic conversation memory. No evidence payloads."""

from __future__ import annotations

from da_agent.contracts.models import DialogueState, DialogueTurn, ResolvedQuestion


def dialogue_for_hash(
    dialogue: DialogueState | None,
    previous_hash: str | None,
    new_hash: str,
) -> DialogueState:
    """Drop dialogue when the dataset identity changes."""
    if dialogue is None or previous_hash != new_hash:
        return DialogueState()
    return dialogue


def append_resolved_turn(dialogue: DialogueState, resolved: ResolvedQuestion) -> DialogueState:
    """Record an answerable interpretation. Unanswerable turns are not stored."""
    if not resolved.answerable:
        return dialogue
    turn = DialogueTurn(
        question_text=resolved.question_text,
        intent=resolved.intent,
        metric=resolved.metric,
        period=resolved.period,
        grouping=list(resolved.grouping),
        filters=list(resolved.filters),
        answerable=True,
    )
    return dialogue.model_copy(update={"turns": [*dialogue.turns, turn]})
