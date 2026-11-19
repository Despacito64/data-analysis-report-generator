"""M10 freeze manifest build and verify."""

import json
from pathlib import Path

import pytest

from evaluation.freeze_manifest import (
    DEFAULT_MANIFEST,
    FreezeMismatchError,
    build_freeze_manifest,
    verify_freeze_manifest,
    write_freeze_manifest,
)


def test_build_freeze_manifest_matches_registered_dataset() -> None:
    manifest = build_freeze_manifest()
    assert manifest["dataset"]["sha256"] == manifest["dataset"]["registered_sha256"]
    assert manifest["benchmark"]["question_count"] == 20
    assert manifest["contract_version"] == "0.2.0"


def test_verify_detects_stale_manifest_hash(tmp_path: Path) -> None:
    manifest_path = tmp_path / "freeze.json"
    write_freeze_manifest(manifest_path)
    stale = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale["benchmark"]["oracle_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(stale, indent=2), encoding="utf-8")
    with pytest.raises(FreezeMismatchError):
        verify_freeze_manifest(manifest_path)


def test_committed_manifest_verifies() -> None:
    if not DEFAULT_MANIFEST.is_file():
        pytest.skip("freeze_manifest.json not committed yet")
    verify_freeze_manifest(DEFAULT_MANIFEST)
