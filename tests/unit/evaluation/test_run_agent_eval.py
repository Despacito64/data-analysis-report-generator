"""Tests for dynamic-agent benchmark scoring and comparison reporting."""

import json
import time
from io import BytesIO
from pathlib import Path

from da_agent.agent.answer import AgentAnswerStatus
from da_agent.agent.planner import MockLLMClient, OllamaClient
from da_agent.core.config import load_config
from da_agent.pipeline import AgentResult
from evaluation.run_agent_eval import (
    EvaluationLimitExceeded,
    EvaluationTraceWriter,
    TimedLLMClient,
    apply_eval_timeout,
    build_comparison,
    evaluate_agent,
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


def test_eval_timeout_override_changes_only_evaluation_config() -> None:
    config = load_config()

    updated = apply_eval_timeout(config, 180.0)

    assert updated.budgets.per_call_timeout_s == 180.0
    assert config.budgets.per_call_timeout_s == 60.0


def test_eval_timeout_override_rejects_non_positive_values() -> None:
    config = load_config()

    try:
        apply_eval_timeout(config, 0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("Expected non-positive evaluation timeout to fail")


def test_ollama_client_sends_thinking_and_keep_alive_options(monkeypatch) -> None:
    captured: dict = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data))
        captured["timeout"] = timeout
        return BytesIO(json.dumps({"message": {"content": "OK"}}).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OllamaClient(
        model="qwen3:4b",
        thinking_enabled=True,
        keep_alive="7m",
        timeout_s=11,
    )

    content, _ = client.chat([{"role": "user", "content": "Reply OK"}])

    assert content == "OK"
    assert captured["think"] is True
    assert captured["keep_alive"] == "7m"
    assert captured["timeout"] == 11


def test_trace_records_stage_timing_and_llm_call_duration(tmp_path: Path) -> None:
    writer = EvaluationTraceWriter(
        run_id="timing_test",
        base_dir=tmp_path,
        question_budget_s=10.0,
        max_repair_attempts=2,
    )
    writer.log_event("graph_node", {"node": "resolve", "phase": "start"})
    time.sleep(0.002)
    writer.log_event("graph_node", {"node": "resolve", "phase": "end"})
    writer.log_event("planner_repair_attempt", {"attempt": 1})
    client = TimedLLMClient(
        MockLLMClient(default_response={"tasks": []}),
        trace_writer=writer,
        max_llm_calls=2,
        model_name="mock",
    )
    client.chat([])

    events = writer.read_events()
    stage_end = next(
        event
        for event in events
        if event.event_type == "graph_node" and event.payload["phase"] == "end"
    )
    llm_event = next(event for event in events if event.event_type == "llm_call_timing")
    repair_event = next(event for event in events if event.event_type == "repair_attempt_timing")

    assert stage_end.payload["duration_s"] > 0
    assert llm_event.payload["call_number"] == 1
    assert llm_event.payload["duration_s"] >= 0
    assert repair_event.payload["duration_s"] >= 0


def test_question_budget_exhaustion_reports_current_stage(tmp_path: Path) -> None:
    writer = EvaluationTraceWriter(
        run_id="timeout_test",
        base_dir=tmp_path,
        question_budget_s=0.001,
        max_repair_attempts=2,
    )
    writer.log_event("graph_node", {"node": "plan", "phase": "start"})
    time.sleep(0.005)

    try:
        writer.check_budget("plan_generation")
    except EvaluationLimitExceeded as exc:
        assert exc.reason == "question_timeout"
        assert exc.stage == "plan_generation"
    else:
        raise AssertionError("Expected question budget exhaustion")

    assert any(event.event_type == "question_budget_exceeded" for event in writer.read_events())
    assert writer.stage_timings["plan_generation"] >= 0.001


def test_repair_and_llm_caps_have_distinct_reasons(tmp_path: Path) -> None:
    writer = EvaluationTraceWriter(
        run_id="caps_test",
        base_dir=tmp_path,
        question_budget_s=10.0,
        max_repair_attempts=0,
    )
    try:
        writer.log_event("planner_repair_attempt", {"attempt": 1})
    except EvaluationLimitExceeded as exc:
        assert exc.reason == "repair_cap"
    else:
        raise AssertionError("Expected repair cap")
    assert any(
        event.event_type == "evaluation_cap_exceeded" and event.payload["reason"] == "repair_cap"
        for event in writer.read_events()
    )

    llm_writer = EvaluationTraceWriter(
        run_id="llm_cap_test",
        base_dir=tmp_path,
        question_budget_s=10.0,
        max_repair_attempts=1,
    )
    client = TimedLLMClient(
        MockLLMClient(default_response={"tasks": []}),
        trace_writer=llm_writer,
        max_llm_calls=0,
        model_name="mock",
    )
    try:
        client.chat([])
    except EvaluationLimitExceeded as exc:
        assert exc.reason == "llm_call_cap"
    else:
        raise AssertionError("Expected LLM call cap")
    assert any(
        event.event_type == "evaluation_cap_exceeded" and event.payload["reason"] == "llm_call_cap"
        for event in llm_writer.read_events()
    )


def test_evaluator_persists_question_timeout_status_and_stage(tmp_path: Path, monkeypatch) -> None:
    from types import SimpleNamespace

    import evaluation.run_agent_eval as evaluator

    config = load_config()
    config = config.model_copy(
        update={
            "evaluation": config.evaluation.model_copy(update={"per_question_budget_s": 0.001}),
            "run_trace": config.run_trace.model_copy(update={"base_dir": str(tmp_path / "traces")}),
        }
    )

    def fake_run_agent(_question: str, *_args, trace_writer, **_kwargs) -> AgentResult:
        trace_writer.log_event("graph_node", {"node": "resolve", "phase": "start"})
        time.sleep(0.005)
        trace_writer.log_event("graph_node", {"node": "resolve", "phase": "end"})
        raise AssertionError("Budget enforcement should have stopped before this")

    monkeypatch.setattr(evaluator, "load_config", lambda: config)
    monkeypatch.setattr(evaluator, "load_data", lambda _path: object())
    monkeypatch.setattr(evaluator, "compute_profile", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(evaluator, "run_baseline", lambda **_kwargs: SimpleNamespace(answers={}))
    monkeypatch.setattr(evaluator, "run_agent", fake_run_agent)

    summary = evaluate_agent(
        dataset_path=Path("unused.csv"),
        oracle_path=Path("evaluation/benchmark/oracle.json"),
        questions_path=Path("evaluation/benchmark/questions.json"),
        results_dir=tmp_path / "results",
        run_id="timeout_case",
        selected_question_ids=["q03"],
        mode="mock",
        client=MockLLMClient(),
    )
    q03 = next(row for row in summary["per_question"] if row["question_id"] == "q03")
    attempt_path = tmp_path / "results" / "timeout_case" / "attempts" / "q03" / "attempt-001.json"

    assert q03["status"] == "timeout"
    assert q03["accuracy"] is None
    assert "question_resolution" in q03["stage_timings"]
    assert summary["score_complete"] is False
    assert summary["agent"]["accuracy_over_all_questions"] == 0.0
    assert summary["agent"]["accuracy_over_completed_questions"] is None
    assert json.loads(attempt_path.read_text(encoding="utf-8"))["failure_reason"] == (
        "question_timeout"
    )


def test_resume_skips_finished_questions_and_incomplete_score_is_not_complete(
    tmp_path: Path, monkeypatch
) -> None:
    from types import SimpleNamespace

    import evaluation.run_agent_eval as evaluator

    config = load_config()
    config = config.model_copy(
        update={
            "run_trace": config.run_trace.model_copy(update={"base_dir": str(tmp_path / "traces")})
        }
    )
    invoked_questions: list[str] = []

    def fake_run_agent(question: str, *_args, **_kwargs) -> AgentResult:
        invoked_questions.append(question)
        return AgentResult(
            run_id=f"run_{len(invoked_questions)}",
            question=question,
            status=AgentAnswerStatus.FAILED,
            answer_text="failed",
        )

    monkeypatch.setattr(evaluator, "load_config", lambda: config)
    monkeypatch.setattr(evaluator, "load_data", lambda _path: object())
    monkeypatch.setattr(evaluator, "compute_profile", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(evaluator, "run_baseline", lambda **_kwargs: SimpleNamespace(answers={}))
    monkeypatch.setattr(evaluator, "run_agent", fake_run_agent)

    first = evaluate_agent(
        dataset_path=Path("unused.csv"),
        oracle_path=Path("evaluation/benchmark/oracle.json"),
        questions_path=Path("evaluation/benchmark/questions.json"),
        results_dir=tmp_path / "results",
        run_id="resume_case",
        selected_question_ids=["q03"],
        mode="mock",
        client=MockLLMClient(),
    )
    orphan_attempt_dir = tmp_path / "results" / "resume_case" / "attempts" / "q03"
    orphan_attempt_dir.mkdir(parents=True, exist_ok=True)
    (orphan_attempt_dir / "attempt-002.json").write_text(
        json.dumps(
            {
                "question_id": "q03",
                "attempt": 2,
                "run_id": "orphan_attempt",
                "status": "failed",
                "accuracy": False,
                "total_time_s": 1.0,
                "stage_timings": {"plan_generation": 1.0},
                "llm_call_count": 1,
                "llm_calls": [],
                "tool_executions": [],
                "repair_attempts": [],
            }
        ),
        encoding="utf-8",
    )
    second = evaluate_agent(
        dataset_path=Path("unused.csv"),
        oracle_path=Path("evaluation/benchmark/oracle.json"),
        questions_path=Path("evaluation/benchmark/questions.json"),
        results_dir=tmp_path / "results",
        run_id="resume_case",
        resume=True,
        selected_question_ids=["q03", "q04"],
        mode="mock",
        client=MockLLMClient(),
    )

    assert first["score_complete"] is False
    assert [row["status"] for row in second["per_question"] if row["question_id"] == "q03"] == [
        "failed"
    ]
    assert (
        next(row for row in second["per_question"] if row["question_id"] == "q03")["attempt_count"]
        == 2
    )
    assert second["per_question"][3]["status"] == "failed"
    assert second["per_question"][9]["status"] == "not_run"
    assert invoked_questions == [
        "What is the total sales for each Region?",
        "What is the total profit for each Segment?",
    ]


def test_mock_evaluation_records_agent_stages_and_tool_times(tmp_path: Path) -> None:
    config = load_config()
    config = config.model_copy(
        update={
            "run_trace": config.run_trace.model_copy(update={"base_dir": str(tmp_path / "traces")}),
            "evaluation": config.evaluation.model_copy(
                update={
                    "per_question_budget_s": 120.0,
                    "max_llm_calls_per_question": 5,
                    "max_repair_attempts": 1,
                }
            ),
        }
    )
    client = MockLLMClient(
        default_response={
            "tasks": [
                {
                    "id": "t1",
                    "tool": "group_aggregate",
                    "args": {
                        "by": ["Region"],
                        "metric_column": "Sales",
                        "aggregation": "sum",
                    },
                    "depends_on": [],
                    "rationale": "Aggregate sales for each region.",
                }
            ]
        }
    )

    summary = evaluate_agent(
        dataset_path=Path("Sample-Superstore.csv"),
        oracle_path=Path("evaluation/benchmark/oracle.json"),
        questions_path=Path("evaluation/benchmark/questions.json"),
        results_dir=tmp_path / "results",
        run_id="mock_diagnostics",
        selected_question_ids=["q03"],
        mode="mock",
        client=client,
        config=config,
    )
    q03 = next(row for row in summary["per_question"] if row["question_id"] == "q03")
    saved = json.loads(
        (tmp_path / "results" / "mock_diagnostics" / "questions" / "q03.json").read_text(
            encoding="utf-8"
        )
    )
    trace_path = tmp_path / "traces" / saved["attempts"][0]["run_id"] / "trace.jsonl"
    trace_events = [
        json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]
    run_events = [
        json.loads(line)
        for line in (tmp_path / "traces" / "agent_eval_mock_diagnostics" / "trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]

    assert q03["status"] == "passed"
    assert q03["outcome"] in {"win", "loss", "tie"}
    assert q03["llm_call_count"] >= 1
    assert q03["stage_timings"]["question_resolution"] >= 0
    assert q03["stage_timings"]["plan_generation"] >= 0
    assert q03["stage_timings"]["answer_synthesis"] >= 0
    assert q03["tool_executions"][0]["duration_s"] >= 0
    assert q03["llm_calls"][0]["duration_s"] >= 0
    assert summary["aggregate"]["llm_call_count"] == q03["llm_call_count"]
    assert sum(summary["baseline_comparison"].values()) == 20
    assert summary["evaluation"]["thinking_enabled"] is False
    assert summary["evaluation"]["keep_alive"] == "10m"
    started_event = next(
        event for event in run_events if event["event_type"] == "evaluation_run_started"
    )
    assert started_event["payload"]["model"] == config.model.name
    assert started_event["payload"]["ollama_base_url"] == config.model.base_url.removesuffix("/v1")
    assert any(
        event["event_type"] == "evaluation_warmup" and event["payload"]["status"] == "skipped"
        for event in run_events
    )
    assert any(event["event_type"] == "tool_execution_timing" for event in trace_events)
    assert any(event["event_type"] == "llm_call_timing" for event in trace_events)
    assert summary["score_complete"] is False


def _mock_plan_client() -> MockLLMClient:
    return MockLLMClient(
        default_response={
            "tasks": [
                {
                    "id": "t1",
                    "tool": "group_aggregate",
                    "args": {"by": ["Region"], "metric_column": "Sales", "aggregation": "sum"},
                    "depends_on": [],
                    "rationale": "Aggregate sales for each region.",
                }
            ]
        }
    )


def _mock_eval(tmp_path: Path, run_id: str, **overrides) -> dict:
    config = load_config()
    config = config.model_copy(
        update={"run_trace": config.run_trace.model_copy(update={"base_dir": str(tmp_path / "t")})}
    )
    return evaluate_agent(
        dataset_path=Path("Sample-Superstore.csv"),
        oracle_path=Path("evaluation/benchmark/oracle.json"),
        questions_path=Path("evaluation/benchmark/questions.json"),
        results_dir=tmp_path / "results",
        run_id=run_id,
        selected_question_ids=["q03"],
        mode="mock",
        client=_mock_plan_client(),
        config=config,
        **overrides,
    )


def test_max_replans_override_is_recorded_and_stops_result_replanning(tmp_path: Path) -> None:
    default = _mock_eval(tmp_path, "default_replans")
    no_replan = _mock_eval(tmp_path, "zero_replans", max_replans=0)

    assert default["evaluation"]["max_replans"] == load_config().budgets.max_replans
    assert no_replan["evaluation"]["max_replans"] == 0
    default_calls = next(r for r in default["per_question"] if r["question_id"] == "q03")
    zero_calls = next(r for r in no_replan["per_question"] if r["question_id"] == "q03")
    assert default_calls["llm_call_count"] > zero_calls["llm_call_count"]


def test_negative_max_replans_is_rejected(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="max_replans"):
        _mock_eval(tmp_path, "bad", max_replans=-1)
