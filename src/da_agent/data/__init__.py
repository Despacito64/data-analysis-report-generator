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
from da_agent.data.profiler import (
    TRANSFORMATION_VERSION,
    compute_dataset_hash,
    compute_profile,
    infer_semantic_type,
    profile_file,
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
    "TRANSFORMATION_VERSION",
    "CorruptFileError",
    "DataLoadError",
    "DatasetMetadata",
    "EmptyDataError",
    "FileLimitExceededError",
    "InvalidExtensionError",
    "InvalidSheetError",
    "compute_dataset_hash",
    "compute_file_sha256",
    "compute_profile",
    "infer_semantic_type",
    "load_data",
    "profile_file",
    "verify_dataset_hash",
]
