"""Tests for dynamic-agent benchmark scoring and comparison reporting."""

from pathlib import Path

from da_agent.agent.answer import AgentAnswerStatus
from da_agent.pipeline import AgentResult
from evaluation.run_agent_eval import (
    build_comparison,
    extract_score_answer,
    render_markdown_summary,
)


def _result(tool: str, output: dict) -> AgentResult:
    return AgentResult(
        run_id="eval_test",
        question="Test evidence extraction",
        status=AgentAnswerStatus.ANSWERED,
        answer_text="",
        final_answer={},
        evidence=[
            {
                "task_id": "t1",
                "tool": tool,
                "evidence_id": "ev_t1",
                "tool_output": output,
            }
        ],
    )


def test_score_answer_extracts_grouped_values_from_tool_evidence() -> None:
    result = _result(
        "group_aggregate",
        {
            "rows": [
                {"group_keys": {"Region": "East"}, "value": 20.0},
                {"group_keys": {"Region": "West"}, "value": 30.0},
            ]
        },
    )

    assert extract_score_answer(result) == {"East": 20.0, "West": 30.0}


def test_score_answer_uses_single_scalar_aggregate() -> None:
    result = _result(
        "group_aggregate",
        {"rows": [{"group_keys": {}, "value": 42.0}]},
    )

    assert extract_score_answer(result) == 42.0


def test_comparison_and_markdown_include_baseline_ceiling_note() -> None:
    summary = build_comparison(
        agent_answers={"q1": 1.0},
        baseline_answers={"q1": 1.0},
        oracle={"q1": {"expected_answer": 1.0, "tolerance": 0.0}},
        agent_metrics={"tool_calls": 1, "plan_validity_rate": 1.0},
    )
    markdown = render_markdown_summary(summary, Path("results.json"))

    assert summary["agent"]["correct"] == 1
    assert summary["baseline"]["correct"] == 1
    assert summary["per_question"][0]["outcome"] == "tie"
    assert "template-keyed ceiling" in markdown
