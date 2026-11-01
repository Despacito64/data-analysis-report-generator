from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pydantic import ValidationError

MODULE_PATH = Path(__file__).parents[3] / "evaluation" / "model_spike.py"
spec = importlib.util.spec_from_file_location("model_spike_under_test", MODULE_PATH)
assert spec and spec.loader
model_spike = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model_spike
spec.loader.exec_module(model_spike)
SpikeOutput = model_spike.SpikeOutput
answer_matches_oracle = model_spike.answer_matches_oracle
consistency_rate = model_spike.consistency_rate
normalize_answer = model_spike.normalize_answer
normalize_tool_arguments = model_spike.normalize_tool_arguments
tokens_per_second = model_spike.tokens_per_second


def test_spike_output_uses_existing_task_contract():
    output = SpikeOutput.model_validate(
        {
            "tasks": [
                {
                    "id": "t1",
                    "tool": "rank",
                    "args": {},
                    "depends_on": [],
                    "rationale": "Rank the requested entities.",
                }
            ],
            "final_answer": "Technology",
        }
    )
    assert output.tasks[0].tool == "rank"


def test_spike_output_rejects_extra_fields():
    try:
        SpikeOutput.model_validate({"tasks": [], "final_answer": None, "extra": True})
    except ValidationError:
        return
    raise AssertionError("extra fields must be rejected")


def test_questions_path_is_explicit_until_frozen_benchmark_exists():
    parser = model_spike.build_parser()
    args = parser.parse_args([])
    assert args.questions is None


def test_answer_matching_supports_numbers_and_labels():
    assert answer_matches_oracle(12.345, 12.346, tolerance=0.01)
    assert answer_matches_oracle("  technology ", "Technology")
    assert not answer_matches_oracle("Furniture", "Technology")


def test_normalize_answer_reduces_json_answers():
    assert normalize_answer({"answer": 12.0}) == "12"
    assert normalize_answer(["A", "B", "A"]) == '["A", "B", "A"]'


def test_consistency_rate_uses_modal_run_answer():
    rows = [
        {"question_id": "q1", "final_answer": "A"},
        {"question_id": "q1", "final_answer": "A"},
        {"question_id": "q1", "final_answer": "B"},
        {"question_id": "q2", "final_answer": "X"},
        {"question_id": "q2", "final_answer": "X"},
        {"question_id": "q2", "final_answer": "X"},
    ]
    assert consistency_rate(rows) == 0.8333333333333333


def test_normalize_tool_arguments_accepts_dict_and_json_string():
    assert normalize_tool_arguments({"by": ["Region"]}) == {"by": ["Region"]}
    assert normalize_tool_arguments('{"by": ["Region"]}') == {"by": ["Region"]}
    assert normalize_tool_arguments("not-json") == {}
    assert normalize_tool_arguments(["Region"]) == {}


def test_tokens_per_second_uses_ollama_counts():
    assert tokens_per_second({"eval_count": 20, "eval_duration": 2_000_000_000}) == 10.0
    assert tokens_per_second({"eval_count": 20, "eval_duration": 0}) is None
