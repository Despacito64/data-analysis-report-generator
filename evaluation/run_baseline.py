"""Run the fixed-workflow M4 baseline against the frozen benchmark oracle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scorer import answers_match, score_baseline

from da_agent.agent.baseline import run_baseline
from da_agent.core.config import load_config
from da_agent.data.loader import load_data
from da_agent.data.profiler import compute_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="Sample-Superstore.csv")
    parser.add_argument("--oracle", default="evaluation/benchmark/oracle.json")
    args = parser.parse_args()

    dataset = Path(args.dataset)
    df = load_data(dataset)
    profile = compute_profile(df, file_path=dataset)
    run = run_baseline(df=df, profile=profile, budgets=load_config().budgets)
    with Path(args.oracle).open(encoding="utf-8") as handle:
        oracle = json.load(handle)
    score = score_baseline(run.answers, oracle)
    mismatches = [
        question_id
        for question_id, entry in oracle.items()
        if question_id not in run.answers
        or not answers_match(run.answers[question_id], entry["expected_answer"], entry["tolerance"])
    ]
    print(
        json.dumps(
            {
                "correct": score.correct,
                "total": score.total,
                "accuracy": score.accuracy,
                "mismatches": mismatches,
                "actual_mismatches": {qid: run.answers.get(qid) for qid in mismatches},
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
