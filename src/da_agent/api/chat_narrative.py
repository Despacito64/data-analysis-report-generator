"""User-facing prose for chat bubbles (grounded in this turn's summary only)."""

from __future__ import annotations

import re

_GENERIC_SUMMARY = re.compile(r"^\d+ supported finding", re.IGNORECASE)


def chat_user_narrative(
    question: str,
    summary: str | None,
    table_rows: list[dict[str, str | float]] | None,
) -> str | None:
    """Short natural-language answer for the React thread."""
    if not summary or _GENERIC_SUMMARY.search(summary):
        if table_rows and len(table_rows) == 1:
            label = str(table_rows[0]["category"])
            amount = float(table_rows[0]["amount"])
            summary = f"{label}: {amount:,.2f}."
        else:
            return None
    q = question.lower()
    if (
        table_rows
        and len(table_rows) == 1
        and any(p in q for p in ("more about", "tell me about", "what about"))
    ):
        label = str(table_rows[0]["category"])
        amount = float(table_rows[0]["amount"])
        lead = f"For {label}, "
        if label.lower() not in summary.lower():
            return f"{lead}{summary.rstrip('.')}: {amount:,.2f}."
        return f"{lead}{summary}"
    if table_rows and len(table_rows) >= 2 and "highest" not in summary.lower():
        best = max(table_rows, key=lambda r: float(r["amount"]))
        return f"{summary} {best['category']} leads at {float(best['amount']):,.2f}."
    return summary
