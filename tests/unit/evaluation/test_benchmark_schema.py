"""Unit tests for the benchmark questions and oracle schemas."""

import ast
import json
from pathlib import Path


def test_benchmark_questions_schema() -> None:
    """Verify evaluation/benchmark/questions.json has 20 valid questions."""
    path = Path("evaluation/benchmark/questions.json")
    assert path.exists()

    with path.open("r", encoding="utf-8") as f:
        questions = json.load(f)

    assert isinstance(questions, list)
    assert len(questions) == 20

    seen_ids = set()
    for q in questions:
        assert "id" in q
        assert "question" in q
        assert "category" in q
        assert "expected_tool" in q
        assert "expected_tools" in q
        assert q["id"] not in seen_ids
        seen_ids.add(q["id"])
        assert len(q["question"]) > 10
        assert isinstance(q["expected_tools"], list)
        assert len(q["expected_tools"]) >= 1


def test_benchmark_oracle_schema_and_coverage() -> None:
    """Verify evaluation/benchmark/oracle.json matches questions and has required fields."""
    q_path = Path("evaluation/benchmark/questions.json")
    o_path = Path("evaluation/benchmark/oracle.json")
    assert o_path.exists()

    with q_path.open("r", encoding="utf-8") as f:
        questions = json.load(f)
    with o_path.open("r", encoding="utf-8") as f:
        oracle = json.load(f)

    assert isinstance(oracle, dict)
    assert len(oracle) == 20

    for q in questions:
        qid = q["id"]
        assert qid in oracle, f"Missing oracle entry for question {qid}"
        entry = oracle[qid]
        assert entry["question_id"] == qid
        assert "expected_answer" in entry
        assert "tolerance" in entry
        assert isinstance(entry["tolerance"], (int, float))
        assert entry["tolerance"] >= 0.0


def test_build_oracle_independence() -> None:
    """Verify build_oracle.py imports nothing from da_agent."""
    script_path = Path("evaluation/benchmark/build_oracle.py")
    assert script_path.exists()

    with script_path.open("r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(script_path))

    forbidden_prefixes = (
        "da_agent.tools",
        "da_agent.agent",
        "da_agent.validation",
        "da_agent.reports",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in forbidden_prefixes:
                    assert not alias.name.startswith(prefix)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for prefix in forbidden_prefixes:
                assert not node.module.startswith(prefix)
