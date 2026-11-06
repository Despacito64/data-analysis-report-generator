"""Run evaluation harness: executes baseline and scores against the oracle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from da_agent.core.config import load_config
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile
from da_agent.pipeline import run_baseline

try:
    from evaluation.oracle import load_oracle
    from evaluation.scorer import answers_match, score_baseline
except ModuleNotFoundError:
    from oracle import load_oracle
    from scorer import answers_match, score_baseline


def evaluate_baseline(
    dataset_path: Path = Path("Sample-Superstore.csv"),
    oracle_path: Path = Path("evaluation/benchmark/oracle.json"),
) -> dict[str, Any]:
    """Execute the fixed baseline and score its answers against the oracle."""
    df = load_data(dataset_path)
    profile = compute_profile(df, file_path=dataset_path)
    budgets = load_config().budgets

    run = run_baseline(df=df, profile=profile, budgets=budgets)
    oracle = load_oracle(oracle_path)
    score = score_baseline(run.answers, oracle)

    mismatches = [
        qid
        for qid, entry in oracle.items()
        if qid not in run.answers
        or not answers_match(run.answers[qid], entry["expected_answer"], entry["tolerance"])
    ]

    return {
        "correct": score.correct,
        "total": score.total,
        "accuracy": score.accuracy,
        "mismatches": mismatches,
        "status": run.report.status.status.value
        if hasattr(run.report.status.status, "value")
        else str(run.report.status.status),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("Sample-Superstore.csv"))
    parser.add_argument("--oracle", type=Path, default=Path("evaluation/benchmark/oracle.json"))
    args = parser.parse_args()

    results = evaluate_baseline(args.dataset, args.oracle)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
