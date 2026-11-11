"""Tests for the public pipeline entry points."""

import tempfile
from pathlib import Path

from da_agent.agent.planner import MockLLMClient
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_agent


def test_pipeline_run_agent_wires_graph_and_trace() -> None:
    dataset_path = Path("Sample-Superstore.csv")
    df = load_data(dataset_path)
    profile = compute_profile(df, file_path=dataset_path)
    client = MockLLMClient(
        default_response={
            "tasks": [
                {
                    "id": "t1",
                    "tool": "group_aggregate",
                    "args": {
                        "by": ["Category"],
                        "metric_column": "Sales",
                        "aggregation": "sum",
                    },
                    "depends_on": [],
                    "rationale": "Sum sales by category",
                }
            ]
        }
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        writer = RunTraceWriter(run_id="pipeline_agent_test", base_dir=temp_dir)
        result = run_agent(
            "What is total sales by category?",
            df=df,
            profile=profile,
            client=client,
            run_id="pipeline_agent_test",
            trace_writer=writer,
        )
        event_types = [event.event_type for event in writer.read_events()]

    assert result["status"] == "complete"
    assert result["evidence_ids"]
    assert "final_answer" in result
    assert "status" in event_types
