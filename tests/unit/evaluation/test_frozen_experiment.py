"""M10 reproduction entrypoint (mock-only for speed)."""

from pathlib import Path

from evaluation.freeze_manifest import write_freeze_manifest
from evaluation.run_frozen_experiment import run_frozen_experiment


def test_frozen_experiment_verify_only(tmp_path: Path) -> None:
    manifest = tmp_path / "freeze.json"
    write_freeze_manifest(manifest)
    summary = run_frozen_experiment(
        manifest_path=manifest,
        verify_only=True,
    )
    assert summary["status"] == "verified"


def test_frozen_experiment_mock_single_question(tmp_path: Path, monkeypatch) -> None:
    manifest = tmp_path / "freeze.json"
    write_freeze_manifest(manifest)
    results_dir = tmp_path / "results"
    summary_dir = Path("evaluation/results/frozen_experiment")
    monkeypatch.setattr(
        "evaluation.run_frozen_experiment.DEFAULT_SUMMARY",
        tmp_path / "frozen_latest.json",
    )

    summary = run_frozen_experiment(
        manifest_path=manifest,
        mode="mock",
        repeats=1,
        selected_question_ids=["q03"],
        results_dir=results_dir,
        run_id="pytest_m10",
    )

    assert summary["status"] == "complete"
    assert summary["recovery_suite"]["all_passed"] is True
    assert (results_dir / "pytest_m10" / "agent_eval.json").is_file()
    assert (tmp_path / "frozen_latest.json").is_file()
    # Ensure we did not overwrite the repo-default summary path in tests
    assert summary_dir != tmp_path / "frozen_latest.json"