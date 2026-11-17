#!/usr/bin/env python3
"""Regenerate demo/ artifacts with a real Ollama run (config.yaml model)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from da_agent.agent.planner import OllamaClient
from da_agent.core.config import load_config
from da_agent.core.trace import RunTraceWriter
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_agent

QUESTION = "What are total sales by category?"
RUN_ID = "demo-visual-real"
DATASET = Path("Sample-Superstore.csv")


def main() -> None:
    cfg = load_config()
    df = load_data(DATASET)
    profile = compute_profile(df, file_path=DATASET)
    writer = RunTraceWriter(run_id=RUN_ID, base_dir=cfg.run_trace.base_dir)
    client = OllamaClient(
        base_url=cfg.model.base_url,
        model=cfg.model.name,
        temperature=cfg.model.temperature,
        seed=cfg.model.seed,
        timeout_s=cfg.budgets.per_call_timeout_s,
        thinking_enabled=cfg.evaluation.thinking_enabled,
        keep_alive=cfg.evaluation.keep_alive,
    )
    result = run_agent(
        QUESTION,
        df,
        cfg,
        client,
        profile=profile,
        run_id=RUN_ID,
        trace_writer=writer,
    )
    out = Path("demo")
    out.mkdir(exist_ok=True)
    meta = {
        "run_id": RUN_ID,
        "model": cfg.model.name,
        "provider": cfg.model.provider,
        "mock": False,
        "question": QUESTION,
        "status": result.status.value,
        "answer": result.answer_text,
        "dataset_hash": profile.dataset_hash,
        "key_numbers": [k.model_dump(mode="json") for k in result.key_numbers],
        "events": [e.event_type for e in writer.read_events()],
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    shutil.copy(writer.run_dir / "report.html", out / "report.html")
    shutil.copy(writer.run_dir / "report.json", out / "report.json")
    print(f"Done: {result.status.value}, trace in {writer.run_dir}")


if __name__ == "__main__":
    main()