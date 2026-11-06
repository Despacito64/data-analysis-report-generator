"""Deterministic scoring against the frozen benchmark oracle."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def answers_match(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            answers_match(actual[key], expected[key], tolerance) for key in actual
        )
    if isinstance(actual, list) and isinstance(expected, list):
        if all(isinstance(item, str) for item in actual + expected):
            return actual == expected
        return len(actual) == len(expected) and all(
            answers_match(a, e, tolerance) for a, e in zip(actual, expected, strict=True)
        )
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    return actual == expected


@dataclass(frozen=True)
class Score:
    correct: int
    total: int
    accuracy: float


def score_baseline(answers: dict[str, Any], oracle: dict[str, dict[str, Any]]) -> Score:
    correct = 0
    for question_id, entry in oracle.items():
        if question_id in answers and answers_match(
            answers[question_id], entry["expected_answer"], float(entry["tolerance"])
        ):
            correct += 1
    total = len(oracle)
    return Score(correct=correct, total=total, accuracy=correct / total if total else 0.0)
