#!/usr/bin/env python3
"""Run the M7 controlled-failure suite separately from the frozen benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from evaluation.recovery_suite.runners import run_all_scenarios
except ModuleNotFoundError:
    from runners import run_all_scenarios

DEFAULT_SCENARIOS = Path("evaluation/recovery_suite/scenarios.json")
DEFAULT_OUTPUT = Path("evaluation/results/recovery_suite/latest.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=DEFAULT_SCENARIOS,
        help="Path to recovery scenario definitions.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Write JSON summary here.",
    )
    args = parser.parse_args()
    summary = run_all_scenarios(args.scenarios)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"all_passed": summary["all_passed"], "output": str(args.output)}, indent=2))
    if not summary["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()