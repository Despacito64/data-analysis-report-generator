"""Tests for the M7 controlled-failure suite (separate from frozen benchmark)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from evaluation.recovery_suite.runners import HANDLERS, load_scenarios, run_all_scenarios

SCENARIOS_PATH = Path("evaluation/recovery_suite/scenarios.json")
BENCHMARK_PATH = Path("evaluation/benchmark/questions.json")
ORACLE_PATH = Path("evaluation/benchmark/oracle.json")


def test_recovery_handlers_cover_all_scenario_entries() -> None:
    scenarios = load_scenarios(SCENARIOS_PATH)
    for scenario in scenarios:
        assert scenario["handler"] in HANDLERS


def test_recovery_scenarios_do_not_reference_frozen_benchmark_ids() -> None:
    text = SCENARIOS_PATH.read_text(encoding="utf-8")
    assert re.search(r"\bq(0[1-9]|1\d|20)\b", text) is None


def test_recovery_scenarios_do_not_reuse_benchmark_question_text() -> None:
    scenarios_text = SCENARIOS_PATH.read_text(encoding="utf-8").casefold()
    with BENCHMARK_PATH.open("r", encoding="utf-8") as handle:
        benchmark = json.load(handle)
    for item in benchmark:
        question = str(item.get("question", "")).strip().casefold()
        if len(question) >= 24:
            assert question not in scenarios_text


def test_recovery_suite_runners_do_not_import_oracle() -> None:
    source = Path("evaluation/recovery_suite/runners.py").read_text(encoding="utf-8")
    assert "evaluation.oracle" not in source
    assert "oracle.json" not in source
    assert ORACLE_PATH.name not in source


def test_run_all_recovery_scenarios_pass() -> None:
    summary = run_all_scenarios(SCENARIOS_PATH)
    assert summary["all_passed"] is True
    assert summary["passed_count"] == summary["scenario_count"]
