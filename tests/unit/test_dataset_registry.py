"""Unit tests verifying dataset registration and SHA-256 hash verification."""

from pathlib import Path

from da_agent.data import (
    BENCHMARK_SUPERSTORE,
    compute_file_sha256,
    verify_dataset_hash,
)


def test_benchmark_superstore_registration() -> None:
    assert BENCHMARK_SUPERSTORE.name == "sample_superstore"
    assert BENCHMARK_SUPERSTORE.row_count == 9994
    assert (
        BENCHMARK_SUPERSTORE.sha256_hash
        == "dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c"
    )
    assert "Sales" in BENCHMARK_SUPERSTORE.column_names
    assert "Profit" in BENCHMARK_SUPERSTORE.column_names


def test_superstore_file_hash_matches_if_present() -> None:
    csv_file = Path("Sample-Superstore.csv")
    if csv_file.exists():
        assert verify_dataset_hash(csv_file, "sample_superstore") is True


def test_compute_file_sha256_on_temp_file(tmp_path: Path) -> None:
    sample_file = tmp_path / "test.txt"
    sample_file.write_bytes(b"hello world\n")
    expected = "a948904f2f0f479b8f8197694b30184b0d2ed1c1cd2a1ec0fb85d299a192a447"
    assert compute_file_sha256(sample_file) == expected
