"""Data layer: dataset registration, loading, profiling, and hash verification."""

from da_agent.data.registry import (
    BENCHMARK_SUPERSTORE,
    REGISTERED_DATASETS,
    DatasetMetadata,
    compute_file_sha256,
    verify_dataset_hash,
)

__all__ = [
    "BENCHMARK_SUPERSTORE",
    "REGISTERED_DATASETS",
    "DatasetMetadata",
    "compute_file_sha256",
    "verify_dataset_hash",
]
