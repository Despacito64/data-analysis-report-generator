"""End-to-end: run_agent writes report.json and report.html."""

import json
import tempfile
from pathlib import Path

from da_agent.agent.planner import MockLLMClient
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_agent


def test_run_agent_writes_report_artifacts() -> None:
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
        run_id = "report_e2e"
        writer = RunTraceWriter(run_id=run_id, base_dir=temp_dir)
        run_agent(
            "What is total sales by category?",
            df,
            load_config(),
            client,
            profile=profile,
            run_id=run_id,
            trace_writer=writer,
        )
        json_path = writer.run_dir / "report.json"
        html_path = writer.run_dir / "report.html"
        assert json_path.is_file(), "report.json missing"
        assert html_path.is_file(), "report.html missing"
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        assert payload["run_id"] == run_id
        assert payload["dataset_hash"] == profile.dataset_hash
        html = html_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in html
        assert profile.dataset_hash not in html or "hash" in html.lower()

        event_types = [event.event_type for event in writer.read_events()]
        assert "report_written" in event_types
