"""Dataset registration, metadata, and hash verification for benchmark datasets."""

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DatasetMetadata(BaseModel):
    """Metadata describing a benchmark dataset."""

    model_config = ConfigDict(extra="forbid")

    name: str
    file_name: str
    source: str
    sheet: str | None = None
    version: str
    license_conditions: str
    sha256_hash: str
    row_count: int
    column_names: list[str] = Field(default_factory=list)


# Registered benchmark datasets (D-007)
BENCHMARK_SUPERSTORE = DatasetMetadata(
    name="sample_superstore",
    file_name="Sample-Superstore.csv",
    source="Tableau Sample Superstore / Community retail benchmark",
    sheet=None,
    version="1.0.0",
    license_conditions="Public domain / open demonstration dataset. Safe for evaluation.",
    sha256_hash="dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c",
    row_count=9994,
    column_names=[
        "csvbase_row_id",
        "Row ID",
        "Order ID",
        "Order Date",
        "Ship Date",
        "Ship Mode",
        "Customer ID",
        "Customer Name",
        "Segment",
        "Country",
        "City",
        "State",
        "Postal Code",
        "Region",
        "Product ID",
        "Category",
        "Sub-Category",
        "Product Name",
        "Sales",
        "Quantity",
        "Discount",
        "Profit",
    ],
)

REGISTERED_DATASETS: dict[str, DatasetMetadata] = {
    "sample_superstore": BENCHMARK_SUPERSTORE,
}


def compute_file_sha256(path: str | Path, block_size: int = 65536) -> str:
    """Compute lowercase SHA-256 hash of a file's raw bytes."""
    hasher = hashlib.sha256()
    file_path = Path(path)
    with file_path.open("rb") as f:
        while chunk := f.read(block_size):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def verify_dataset_hash(path: str | Path, dataset_key: str = "sample_superstore") -> bool:
    """Verify that a local dataset file matches the registered SHA-256 hash."""
    if dataset_key not in REGISTERED_DATASETS:
        raise KeyError(f"Dataset '{dataset_key}' is not in the registry.")
    expected_hash = REGISTERED_DATASETS[dataset_key].sha256_hash
    computed = compute_file_sha256(path)
    return computed == expected_hash
