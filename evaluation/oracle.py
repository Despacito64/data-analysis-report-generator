"""Independent oracle for benchmark question evaluation.

CRITICAL: Must NOT import any modules from da_agent (tools, agent, validation, reports).
Computes expected answers from the raw CSV file or loads frozen answers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from evaluation.benchmark.build_oracle import compute_oracle
except ModuleNotFoundError:
    try:
        from benchmark.build_oracle import compute_oracle  # type: ignore[no-redef]
    except ModuleNotFoundError:
        compute_oracle = None  # type: ignore[assignment]

__all__ = ["compute_oracle", "get_expected_answer", "load_oracle"]

ORACLE_JSON = Path("evaluation/benchmark/oracle.json")
QUESTIONS_JSON = Path("evaluation/benchmark/questions.json")


def load_oracle(path: Path = ORACLE_JSON) -> dict[str, dict[str, Any]]:
    """Load the precomputed frozen oracle answers."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_expected_answer(question_id: str, oracle: dict[str, dict[str, Any]] | None = None) -> Any:
    """Retrieve expected answer for a given question ID."""
    if oracle is None:
        oracle = load_oracle()
    if question_id not in oracle:
        raise KeyError(f"Question {question_id} not found in oracle")
    return oracle[question_id]["expected_answer"]
