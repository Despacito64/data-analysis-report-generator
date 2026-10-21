"""Unit tests for dataset profiler, semantic type detection, and statistics."""

import json
from pathlib import Path

import pandas as pd
import pytest

from da_agent.contracts import (
    DatasetProfile,
    SemanticType,
)
from da_agent.data.loader import load_data
from da_agent.data.profiler import (
    TRANSFORMATION_VERSION,
    compute_dataset_hash,
    compute_profile,
    infer_semantic_type,
    profile_file,
)
from da_agent.data.registry import compute_file_sha256

FIXTURES_DIR = Path("tests/fixtures")
VALID_CSV = FIXTURES_DIR / "valid_sample.csv"
VALID_XLSX = FIXTURES_DIR / "valid_sample.xlsx"
EXPECTED_JSON = FIXTURES_DIR / "valid_sample_expected.json"


def test_compute_dataset_hash() -> None:
    """Verify compute_dataset_hash operates correctly on file paths and raw bytes."""
    with VALID_CSV.open("rb") as f:
        raw_bytes = f.read()

    expected_hash = compute_file_sha256(VALID_CSV)
    assert compute_dataset_hash(VALID_CSV) == expected_hash
    assert compute_dataset_hash(raw_bytes) == expected_hash

    with pytest.raises(TypeError):
        compute_dataset_hash(12345)  # type: ignore[arg-type]


def test_infer_semantic_type_rules() -> None:
    """Verify semantic type detection rules on synthetic series."""
    # Postal codes / zip codes must be IDENTIFIER, not NUMERIC_MEASURE
    s_postal_int = pd.Series([1002, 7030, 90210, 1002, 7030])
    assert infer_semantic_type("postal_code", s_postal_int) == SemanticType.IDENTIFIER
    assert infer_semantic_type("Postal Code", s_postal_int) == SemanticType.IDENTIFIER
    assert infer_semantic_type("zip_code", s_postal_int) == SemanticType.IDENTIFIER

    # IDs must be IDENTIFIER
    s_id_int = pd.Series([1, 2, 3, 4, 5])
    assert infer_semantic_type("row_id", s_id_int) == SemanticType.IDENTIFIER
    assert infer_semantic_type("Row ID", s_id_int) == SemanticType.IDENTIFIER
    s_id_str = pd.Series(["ORD-001", "ORD-002", "ORD-003"])
    assert infer_semantic_type("order_id", s_id_str) == SemanticType.IDENTIFIER

    # Dates must be DATE
    s_date_str = pd.Series(["2023-01-15", "2023-01-16", "not-a-date", None, "2023-01-18"])
    assert infer_semantic_type("order_date", s_date_str) == SemanticType.DATE
    assert infer_semantic_type("Ship Date", s_date_str) == SemanticType.DATE

    # Continuous numeric measures
    s_sales = pd.Series([250.50, None, 120.00, 45.00, 310.25])
    assert infer_semantic_type("sales", s_sales) == SemanticType.NUMERIC_MEASURE
    assert infer_semantic_type("Sales", s_sales) == SemanticType.NUMERIC_MEASURE
    s_qty = pd.Series([2, 3, 5, 10, 1])
    assert infer_semantic_type("Quantity", s_qty) == SemanticType.NUMERIC_MEASURE

    # Categories with low distinct count
    s_cat = pd.Series(["Furniture", "Technology", "Furniture", "Office Supplies"])
    assert infer_semantic_type("category", s_cat) == SemanticType.CATEGORY

    # Free text
    s_text = pd.Series(
        [
            "Express delivery overnight requested by customer",
            "Standard delivery on Thursday afternoon",
            "Gift wrapped with handwritten message",
        ]
    )
    assert infer_semantic_type("notes", s_text) == SemanticType.TEXT


def test_hand_computed_profile_metrics_csv() -> None:
    """Verify compute_profile matches hand-computed metrics in valid_sample_expected.json."""
    with EXPECTED_JSON.open("r", encoding="utf-8") as f:
        expected = json.load(f)

    df_csv = load_data(VALID_CSV)
    profile = compute_profile(df_csv, file_path=VALID_CSV)

    assert isinstance(profile, DatasetProfile)
    assert profile.transformation_version == TRANSFORMATION_VERSION
    assert profile.row_count == expected["row_count"]
    assert profile.duplicate_row_count == expected["duplicate_row_count"]
    assert profile.dataset_hash == compute_file_sha256(VALID_CSV)

    # Column count and names
    assert len(profile.columns) == expected["column_count"]
    col_dict = {col.name: col for col in profile.columns}
    assert set(col_dict.keys()) == set(expected["columns"])

    # Missing counts
    for col_name, exp_missing in expected["missing_counts"].items():
        assert col_dict[col_name].missing_count == exp_missing, (
            f"Missing count mismatch on {col_name}"
        )

    # Semantic types
    assert col_dict["postal_code"].semantic_type == SemanticType.IDENTIFIER
    assert col_dict["postal_code"].semantic_type != SemanticType.NUMERIC_MEASURE
    assert col_dict["row_id"].semantic_type == SemanticType.IDENTIFIER
    assert col_dict["order_id"].semantic_type == SemanticType.IDENTIFIER
    assert col_dict["order_date"].semantic_type == SemanticType.DATE
    assert col_dict["category"].semantic_type == SemanticType.CATEGORY
    assert col_dict["sales"].semantic_type == SemanticType.NUMERIC_MEASURE
    assert col_dict["notes"].semantic_type == SemanticType.TEXT

    # Date coverage
    assert len(profile.date_coverage) == 1
    date_cov = profile.date_coverage[0]
    exp_date = expected["date_coverage"]
    assert date_cov.column == exp_date["column"]
    assert date_cov.min == exp_date["min"]
    assert date_cov.max == exp_date["max"]
    assert date_cov.parse_failures == exp_date["parse_failures"]

    # Descriptive stats - computed for numeric measures only, NOT identifiers
    assert "sales" in profile.descriptive_stats
    assert "postal_code" not in profile.descriptive_stats
    assert "row_id" not in profile.descriptive_stats

    sales_stat = profile.descriptive_stats["sales"]
    assert sales_stat.count == 7
    assert sales_stat.min == 15.0
    assert sales_stat.max == 310.25
    assert sales_stat.median == 95.5
    assert sales_stat.mean is not None
    assert round(sales_stat.mean, 2) == round(expected["sales_sum"] / 7, 2)

    # Parsing diagnostics should mention date parse failure
    assert any("parse failure" in diag.lower() for diag in profile.parsing_diagnostics)

    # JSON round-trip serialization
    json_str = profile.model_dump_json()
    reloaded = DatasetProfile.model_validate_json(json_str)
    assert reloaded == profile


def test_identical_profile_csv_and_xlsx() -> None:
    """The same data ingested from CSV and XLSX must yield identical profiles."""
    profile_csv = profile_file(VALID_CSV)
    profile_xlsx = profile_file(VALID_XLSX)

    # Statistical and structural contents must match identically
    assert profile_csv.row_count == profile_xlsx.row_count
    assert profile_csv.duplicate_row_count == profile_xlsx.duplicate_row_count
    assert profile_csv.transformation_version == profile_xlsx.transformation_version
    assert profile_csv.date_coverage == profile_xlsx.date_coverage
    assert profile_csv.descriptive_stats == profile_xlsx.descriptive_stats

    # Compare column profiles ignoring source differences
    assert len(profile_csv.columns) == len(profile_xlsx.columns)
    for col_c, col_x in zip(profile_csv.columns, profile_xlsx.columns, strict=True):
        assert col_c.name == col_x.name
        assert col_c.physical_type == col_x.physical_type
        assert col_c.semantic_type == col_x.semantic_type
        assert col_c.missing_count == col_x.missing_count
        assert col_c.distinct_count == col_x.distinct_count
        assert col_c.examples == col_x.examples

    # With normalized source_name and dataset_hash, the models are 100% equal
    norm_csv = profile_csv.model_copy(
        update={"dataset_hash": "fixed_hash", "source_name": "valid_sample"}
    )
    norm_xlsx = profile_xlsx.model_copy(
        update={"dataset_hash": "fixed_hash", "source_name": "valid_sample"}
    )
    assert norm_csv == norm_xlsx


def test_profile_empty_and_all_null_columns() -> None:
    """Profile handles edge cases like all-null numeric columns and empty dataframes."""
    df_edge = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "empty_measure": pd.Series([None, None, None], dtype="float64"),
            "single_val": [42.0, 42.0, 42.0],
        }
    )
    profile = compute_profile(df_edge, source_name="edge_case")

    assert profile.row_count == 3
    assert profile.duplicate_row_count == 0

    col_dict = {c.name: c for c in profile.columns}
    assert col_dict["id"].semantic_type == SemanticType.IDENTIFIER
    assert col_dict["empty_measure"].semantic_type == SemanticType.NUMERIC_MEASURE
    assert col_dict["empty_measure"].missing_count == 3
    assert col_dict["single_val"].missing_count == 0

    # StatBlock for empty_measure has count 0 and None stats
    assert "empty_measure" in profile.descriptive_stats
    empty_stats = profile.descriptive_stats["empty_measure"]
    assert empty_stats.count == 0
    assert empty_stats.mean is None
    assert empty_stats.min is None
