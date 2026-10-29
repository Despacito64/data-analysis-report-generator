"""Domain error classes and handling rules for analytical tools.

Empty handling rule:
- filter, group_aggregate, rank, segment_contribution, trend, correlation,
  detect_anomalies_iqr on zero input rows: raise ToolError(EMPTY_RESULT).
- period_compare with an absent period: return a typed result (per-period
  `present` flag, value None, row count 0), not an error and not a zero.
  Distinguishes:
    1. Period absent: present=False, value=None, row_count=0
    2. Period present but all values missing: present=True, value=None, row_count > 0, missing_count == row_count
    3. Period present, value zero: present=True, value=0.0, row_count > 0
"""

import json
from typing import Any

from da_agent.contracts.models import FailureClass

# Recoverable failure classes according to CONTRACTS.md
RECOVERABLE_FAILURE_CLASSES = frozenset(
    {
        FailureClass.INVALID_ARGS,
        FailureClass.UNKNOWN_TOOL,
        FailureClass.EMPTY_RESULT,
        FailureClass.TRANSIENT,
    }
)


class ToolError(Exception):
    """Classified domain exception raised by analytical tools.

    Tools only raise ToolError for anticipated cases with FailureClass.INVALID_ARGS
    or FailureClass.EMPTY_RESULT. Unexpected exceptions propagate unhandled.
    """

    def __init__(
        self,
        failure_class: FailureClass,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_class = failure_class
        self.message = message
        self.context = context or {}
        self.recoverable = failure_class in RECOVERABLE_FAILURE_CLASSES

        # Verify context is JSON-serializable
        try:
            json.dumps(self.context)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"ToolError context must be JSON-serializable: {exc}") from exc

    def __str__(self) -> str:
        return f"[{self.failure_class.value}] {self.message}"
