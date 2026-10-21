"""Data layer: dataset registration, loading, profiling, and hash verification."""

from da_agent.data.loader import (
    CorruptFileError,
    DataLoadError,
    EmptyDataError,
    FileLimitExceededError,
    InvalidExtensionError,
    InvalidSheetError,
    load_data,
)
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
    "CorruptFileError",
    "DataLoadError",
    "DatasetMetadata",
    "EmptyDataError",
    "FileLimitExceededError",
    "InvalidExtensionError",
    "InvalidSheetError",
    "compute_file_sha256",
    "load_data",
    "verify_dataset_hash",
]
