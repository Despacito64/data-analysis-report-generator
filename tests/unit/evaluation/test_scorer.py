"""Tests for the frozen benchmark scorer."""

from evaluation.scorer import answers_match, score_baseline


def test_answers_match_nested_numbers_with_tolerance() -> None:
    actual = {"base_value": 10.0, "nested": {"x": 20.0005}}
    expected = {"base_value": 10.0005, "nested": {"x": 20.0}}
    assert answers_match(actual, expected, tolerance=0.001)


def test_score_baseline_counts_correct_answers() -> None:
    oracle = {
        "q1": {"expected_answer": 1.0, "tolerance": 0.01},
        "q2": {"expected_answer": ["A", "B"], "tolerance": 0.0},
    }
    scored = score_baseline({"q1": 1.001, "q2": ["B", "A"]}, oracle)
    assert scored.correct == 1
    assert scored.total == 2
    assert scored.accuracy == 0.5
