"""M10: one command to verify the freeze, run baseline vs agent, and the recovery suite."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

try:
    from evaluation.freeze_manifest import (
        DEFAULT_MANIFEST,
        build_freeze_manifest,
        verify_freeze_manifest,
        write_freeze_manifest,
    )
    from evaluation.recovery_suite.runners import run_all_scenarios
    from evaluation.run_agent_eval import evaluate_agent
    from evaluation.run_eval import evaluate_baseline
except ModuleNotFoundError:
    from freeze_manifest import (  # type: ignore[no-redef]
        DEFAULT_MANIFEST,
        build_freeze_manifest,
        verify_freeze_manifest,
        write_freeze_manifest,
    )
    from recovery_suite.runners import run_all_scenarios  # type: ignore[no-redef]
    from run_agent_eval import evaluate_agent  # type: ignore[no-redef]
    from run_eval import evaluate_baseline  # type: ignore[no-redef]

DEFAULT_SCENARIOS = Path("evaluation/recovery_suite/scenarios.json")
DEFAULT_SUMMARY = Path("evaluation/results/frozen_experiment/latest.json")


def run_frozen_experiment(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    write_freeze: bool = False,
    verify_only: bool = False,
    mode: str = "mock",
    repeats: int = 1,
    run_id: str | None = None,
    selected_question_ids: list[str] | None = None,
    results_dir: Path = Path("evaluation/results"),
    require_git_match: bool = False,
) -> dict:
    """Verify frozen assets, optionally run baseline, agent eval, and recovery suite."""
    if write_freeze:
        manifest = build_freeze_manifest()
        write_freeze_manifest(manifest_path, manifest)
    else:
        verify_freeze_manifest(manifest_path, require_git_match=require_git_match)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    started = datetime.now(UTC).isoformat()
    if verify_only:
        payload = {
            "status": "verified",
            "manifest_path": str(manifest_path),
            "started_at": started,
            "finished_at": datetime.now(UTC).isoformat(),
        }
        DEFAULT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_SUMMARY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    dataset = Path(manifest["dataset"]["file"])
    oracle = Path(manifest["benchmark"]["oracle_path"])
    questions = Path(manifest["benchmark"]["questions_path"])

    baseline = evaluate_baseline(dataset_path=dataset, oracle_path=oracle)
    run_id = run_id or f"m10-frozen-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:6]}"
    agent = evaluate_agent(
        dataset_path=dataset,
        oracle_path=oracle,
        questions_path=questions,
        results_dir=results_dir,
        run_id=run_id,
        repeats=repeats,
        mode=mode,
        selected_question_ids=selected_question_ids,
    )
    recovery = run_all_scenarios(DEFAULT_SCENARIOS)

    payload = {
        "status": "complete",
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "manifest_path": str(manifest_path),
        "manifest_git_revision": manifest.get("git_revision"),
        "mode": mode,
        "repeats": repeats,
        "baseline": baseline,
        "agent_run_id": agent["run_id"],
        "agent_summary_path": str(results_dir / agent["run_id"] / "agent_eval.json"),
        "agent": {
            "correct": agent["agent"]["correct"],
            "total": agent["agent"]["total"],
            "accuracy_over_all_questions": agent["agent"]["accuracy_over_all_questions"],
            "score_complete": agent["score_complete"],
        },
        "recovery_suite": {
            "all_passed": recovery["all_passed"],
            "scenario_count": recovery.get("scenario_count"),
        },
        "limitations": (
            "Results apply to Sample Superstore and the frozen 20-question benchmark only."
        ),
    }
    DEFAULT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_SUMMARY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Path to freeze_manifest.json",
    )
    parser.add_argument(
        "--write-freeze",
        action="store_true",
        help="Refresh freeze_manifest.json from the current repo (owner-approved freeze).",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify the manifest matches current benchmark assets.",
    )
    parser.add_argument("--mode", choices=("real", "mock"), default="mock")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--run-id", help="Name the agent evaluation results directory.")
    parser.add_argument(
        "--questions",
        help="Comma-separated question IDs (default: all 20).",
    )
    parser.add_argument(
        "--require-git-match",
        action="store_true",
        help="Fail verification when HEAD differs from manifest git_revision.",
    )
    args = parser.parse_args()
    question_ids = (
        [part.strip() for part in args.questions.split(",") if part.strip()]
        if args.questions
        else None
    )
    summary = run_frozen_experiment(
        manifest_path=args.manifest,
        write_freeze=args.write_freeze,
        verify_only=args.verify_only,
        mode=args.mode,
        repeats=args.repeats,
        run_id=args.run_id,
        selected_question_ids=question_ids,
        require_git_match=args.require_git_match,
    )
    print(json.dumps(summary, indent=2))
    if summary.get("recovery_suite") and not summary["recovery_suite"].get("all_passed", True):
        raise SystemExit(1)


if __name__ == "__main__":
    main()