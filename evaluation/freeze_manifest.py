"""Build and verify the frozen M10 experiment manifest."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from da_agent.contracts import CONTRACT_VERSION
from da_agent.core.config import load_config
from da_agent.data.registry import BENCHMARK_SUPERSTORE, compute_file_sha256

FREEZE_VERSION = "1.0"
DEFAULT_MANIFEST = Path("evaluation/benchmark/freeze_manifest.json")
DEFAULT_DATASET = Path(BENCHMARK_SUPERSTORE.file_name)
DEFAULT_QUESTIONS = Path("evaluation/benchmark/questions.json")
DEFAULT_ORACLE = Path("evaluation/benchmark/oracle.json")
DEFAULT_CONFIG = Path("config.yaml")


class FreezeMismatchError(RuntimeError):
    """Current repository state does not match the frozen manifest."""


def _git_revision(repo_root: Path | None = None) -> str:
    root = repo_root or Path.cwd()
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _sha256_file(path: Path) -> str:
    return compute_file_sha256(path)


def build_freeze_manifest(
    *,
    dataset_path: Path = DEFAULT_DATASET,
    questions_path: Path = DEFAULT_QUESTIONS,
    oracle_path: Path = DEFAULT_ORACLE,
    config_path: Path = DEFAULT_CONFIG,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Capture hashes and settings required to reproduce M10 experiments."""
    config = load_config(config_path)
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    return {
        "freeze_version": FREEZE_VERSION,
        "frozen_at": datetime.now(UTC).isoformat(),
        "git_revision": _git_revision(repo_root),
        "contract_version": CONTRACT_VERSION,
        "dataset": {
            "file": str(dataset_path),
            "sha256": _sha256_file(dataset_path),
            "registered_sha256": BENCHMARK_SUPERSTORE.sha256_hash,
            "row_count": BENCHMARK_SUPERSTORE.row_count,
        },
        "benchmark": {
            "questions_path": str(questions_path),
            "questions_sha256": _sha256_file(questions_path),
            "oracle_path": str(oracle_path),
            "oracle_sha256": _sha256_file(oracle_path),
            "question_count": len(questions),
        },
        "config_path": str(config_path),
        "config_sha256": _sha256_file(config_path),
        "model": {
            "name": config.model.name,
            "base_url": config.model.base_url,
            "temperature": config.model.temperature,
            "seed": config.model.seed,
        },
        "budgets": config.budgets.model_dump(mode="json"),
        "evaluation": config.evaluation.model_dump(mode="json"),
    }


def write_freeze_manifest(path: Path, manifest: dict[str, Any] | None = None, **build_kwargs: Any) -> Path:
    """Write manifest JSON to disk."""
    payload = manifest or build_freeze_manifest(**build_kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def verify_freeze_manifest(
    path: Path,
    *,
    dataset_path: Path = DEFAULT_DATASET,
    questions_path: Path = DEFAULT_QUESTIONS,
    oracle_path: Path = DEFAULT_ORACLE,
    config_path: Path = DEFAULT_CONFIG,
    require_git_match: bool = False,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Ensure benchmark assets and config still match the frozen manifest."""
    if not path.is_file():
        raise FileNotFoundError(f"Missing freeze manifest: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    current = build_freeze_manifest(
        dataset_path=dataset_path,
        questions_path=questions_path,
        oracle_path=oracle_path,
        config_path=config_path,
        repo_root=repo_root,
    )
    mismatches: list[str] = []

    def _check(section: str, key: str, live: Any, frozen: Any) -> None:
        if live != frozen:
            mismatches.append(f"{section}.{key}: expected {frozen!r}, got {live!r}")

    for key in ("contract_version", "freeze_version"):
        _check("root", key, current.get(key), manifest.get(key))
    for key in ("sha256", "registered_sha256", "row_count"):
        _check("dataset", key, current["dataset"].get(key), manifest["dataset"].get(key))
    for key in ("questions_sha256", "oracle_sha256", "question_count"):
        _check("benchmark", key, current["benchmark"].get(key), manifest["benchmark"].get(key))
    _check("config", "sha256", current["config_sha256"], manifest.get("config_sha256"))
    if require_git_match:
        _check("git", "revision", current["git_revision"], manifest.get("git_revision"))

    if mismatches:
        raise FreezeMismatchError("; ".join(mismatches))
    return manifest