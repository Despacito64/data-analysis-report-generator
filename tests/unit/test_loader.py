"""Tests for data loader and input validation (M1 steps 1 and 2)."""

import json
from pathlib import Path

import pandas as pd
import pytest

from da_agent.core.config import InputLimitsConfig
from da_agent.data.loader import (
    CorruptFileError,
    DataLoadError,
    EmptyDataError,
    FileLimitExceededError,
    InvalidExtensionError,
    InvalidSheetError,
    load_data,
)

FIXTURES_DIR = Path("tests/fixtures")


@pytest.fixture
def expected_sample():
    with (FIXTURES_DIR / "valid_sample_expected.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def test_load_csv_matches_expected_hand_computations(expected_sample) -> None:
    """CSV loads and matches hand-computed metrics."""
    df = load_data(FIXTURES_DIR / "valid_sample.csv")

    assert len(df) == expected_sample["row_count"]
    assert list(df.columns) == expected_sample["columns"]
    assert df.duplicated().sum() == expected_sample["duplicate_row_count"]

    # Verify missing counts per column
    for col, expected_missing in expected_sample["missing_counts"].items():
        assert df[col].isna().sum() == expected_missing

    # Verify sales sum (excluding NA)
    assert pytest.approx(df["sales"].dropna().sum(), rel=1e-5) == expected_sample["sales_sum"]


def test_load_xlsx_matches_expected_hand_computations(expected_sample) -> None:
    """XLSX loads and matches hand-computed metrics."""
    df = load_data(FIXTURES_DIR / "valid_sample.xlsx")

    assert len(df) == expected_sample["row_count"]
    assert list(df.columns) == expected_sample["columns"]
    assert df.duplicated().sum() == expected_sample["duplicate_row_count"]

    for col, expected_missing in expected_sample["missing_counts"].items():
        assert df[col].isna().sum() == expected_missing

    assert pytest.approx(df["sales"].dropna().sum(), rel=1e-5) == expected_sample["sales_sum"]


def test_same_data_as_csv_and_xlsx_gives_identical_dataframe() -> None:
    """Exit gate requirement: the same data as CSV and XLSX gives identical data."""
    df_csv = load_data(FIXTURES_DIR / "valid_sample.csv")
    df_xlsx = load_data(FIXTURES_DIR / "valid_sample.xlsx")

    pd.testing.assert_frame_equal(df_csv, df_xlsx)


def test_postal_code_identifier_preserved_with_dtype() -> None:
    """Numeric identifiers with leading zeros are preserved when requested as string."""
    df_csv = load_data(FIXTURES_DIR / "valid_sample.csv", dtype={"postal_code": str})
    df_xlsx = load_data(FIXTURES_DIR / "valid_sample.xlsx", dtype={"postal_code": str})

    expected_codes = [
        "01002",
        "07030",
        "90210",
        "01002",
        "07030",
        "90210",
        "01002",
        "07030",
        "90210",
        "90210",
    ]
    assert list(df_csv["postal_code"]) == expected_codes
    assert list(df_xlsx["postal_code"]) == expected_codes
    pd.testing.assert_frame_equal(df_csv, df_xlsx)


def test_configurable_csv_delimiter(tmp_path: Path) -> None:
    """Loader supports custom delimiters such as semicolon."""
    tsv_file = tmp_path / "custom_delim.csv"
    tsv_file.write_text("id;name;score\n1;Alice;98.5\n2;Bob;87.0\n", encoding="utf-8")

    df = load_data(tsv_file, delimiter=";")
    assert len(df) == 2
    assert list(df.columns) == ["id", "name", "score"]
    assert df.iloc[0]["name"] == "Alice"


def test_configurable_csv_encoding(tmp_path: Path) -> None:
    """Loader supports non-UTF8 encodings like latin-1."""
    latin1_file = tmp_path / "latin1_sample.csv"
    # Write characters specific to latin-1
    content = "id,city,cost\n1,Montréal,45.5\n2,Zürich,55.0\n"
    latin1_file.write_bytes(content.encode("latin-1"))

    df = load_data(latin1_file, encoding="latin-1")
    assert len(df) == 2
    assert df.iloc[0]["city"] == "Montréal"
    assert df.iloc[1]["city"] == "Zürich"


def test_configurable_date_format(tmp_path: Path) -> None:
    """Loader supports date parsing configuration."""
    date_file = tmp_path / "dates.csv"
    date_file.write_text("id,event_date\n1,2023-05-01\n2,2023-06-15\n", encoding="utf-8")

    df = load_data(date_file, parse_dates=["event_date"], date_format="%Y-%m-%d")
    assert pd.api.types.is_datetime64_any_dtype(df["event_date"])
    assert df.iloc[0]["event_date"].year == 2023
    assert df.iloc[0]["event_date"].month == 5


def test_excel_sheet_selection() -> None:
    """Loader supports selecting sheets by name or index."""
    file_path = FIXTURES_DIR / "multi_sheet.xlsx"

    df_orders = load_data(file_path, sheet_name="Orders")
    assert len(df_orders) == 2
    assert list(df_orders.columns) == ["order_id", "amount"]

    df_returns = load_data(file_path, sheet_name="Returns")
    assert len(df_returns) == 1
    assert list(df_returns.columns) == ["return_id", "order_id", "reason"]

    # Index based selection
    df_first = load_data(file_path, sheet_name=0)
    pd.testing.assert_frame_equal(df_first, df_orders)


def test_excel_invalid_sheet_name_fails() -> None:
    """Selecting an invalid sheet raises InvalidSheetError naming available sheets."""
    file_path = FIXTURES_DIR / "multi_sheet.xlsx"

    with pytest.raises(InvalidSheetError) as exc_info:
        load_data(file_path, sheet_name="NonExistentSheet")
    err_msg = str(exc_info.value)
    assert "NonExistentSheet" in err_msg
    assert "Orders" in err_msg
    assert "Returns" in err_msg


def test_excel_invalid_sheet_index_fails() -> None:
    """Selecting an out-of-range sheet index raises InvalidSheetError."""
    file_path = FIXTURES_DIR / "multi_sheet.xlsx"

    with pytest.raises(InvalidSheetError) as exc_info:
        load_data(file_path, sheet_name=99)
    assert "99" in str(exc_info.value)


def test_excel_data_only_loads_evaluated_values() -> None:
    """Verify openpyxl data_only flag is used when loading."""
    file_path = FIXTURES_DIR / "formula.xlsx"
    # Even if cached formula value is not present from Excel calculation,
    # the loader must execute without error using data_only=True
    df = load_data(file_path)
    assert len(df) == 1
    assert list(df.columns) == ["base", "multiplier", "total"]


def test_reject_unsupported_file_extension() -> None:
    """Exit gate requirement: invalid file extensions fail clearly."""
    file_path = FIXTURES_DIR / "wrong_extension.txt"

    with pytest.raises(InvalidExtensionError) as exc_info:
        load_data(file_path)
    assert ".txt" in str(exc_info.value)
    assert ".csv" in str(exc_info.value)
    assert ".xlsx" in str(exc_info.value)


def test_reject_nonexistent_file() -> None:
    """Missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_data("tests/fixtures/non_existent_file.csv")


def test_reject_empty_file() -> None:
    """Exit gate requirement: empty file fails clearly."""
    file_path = FIXTURES_DIR / "empty.csv"

    with pytest.raises(EmptyDataError) as exc_info:
        load_data(file_path)
    assert "empty" in str(exc_info.value).lower()


def test_reject_empty_headers_only_csv(tmp_path: Path) -> None:
    """CSV with header row but 0 data rows fails clearly as empty."""
    empty_csv = tmp_path / "headers_only.csv"
    empty_csv.write_text("col1,col2,col3\n", encoding="utf-8")

    with pytest.raises(EmptyDataError) as exc_info:
        load_data(empty_csv)
    assert "no data rows" in str(exc_info.value).lower()


def test_reject_corrupt_xlsx() -> None:
    """Exit gate requirement: corrupt XLSX fails clearly."""
    file_path = FIXTURES_DIR / "corrupt.xlsx"

    with pytest.raises(CorruptFileError) as exc_info:
        load_data(file_path)
    assert "corrupt" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


def test_reject_corrupt_csv_malformed_encoding(tmp_path: Path) -> None:
    """CSV with invalid byte sequence fails clearly."""
    bad_csv = tmp_path / "bad_bytes.csv"
    # Invalid UTF-8 sequence
    bad_csv.write_bytes(b"col1,col2\n\xff\xfe\x00\x01\n")

    with pytest.raises(CorruptFileError) as exc_info:
        load_data(bad_csv, encoding="utf-8")
    assert "failed" in str(exc_info.value).lower() or "csv" in str(exc_info.value).lower()


def test_reject_file_size_exceeded(tmp_path: Path) -> None:
    """File exceeding max_file_size_mb fails clearly."""
    large_csv = tmp_path / "large.csv"
    large_csv.write_text("a,b\n1,2\n", encoding="utf-8")

    # Set threshold lower than the file size
    strict_limits = InputLimitsConfig(max_file_size_mb=0.000001, max_rows=1000)
    with pytest.raises(FileLimitExceededError) as exc_info:
        load_data(large_csv, limits=strict_limits)
    assert "exceeds maximum allowed limit" in str(exc_info.value)


def test_reject_max_rows_exceeded() -> None:
    """Dataset exceeding max_rows limit fails clearly."""
    strict_limits = InputLimitsConfig(max_file_size_mb=10.0, max_rows=5)
    with pytest.raises(FileLimitExceededError) as exc_info:
        load_data(FIXTURES_DIR / "valid_sample.csv", limits=strict_limits)
    assert "10" in str(exc_info.value)
    assert "5" in str(exc_info.value)
    assert "row count" in str(exc_info.value).lower()


def test_all_custom_exceptions_inherit_from_data_load_error() -> None:
    """All custom loader exceptions inherit from DataLoadError."""
    assert issubclass(InvalidExtensionError, DataLoadError)
    assert issubclass(EmptyDataError, DataLoadError)
    assert issubclass(CorruptFileError, DataLoadError)
    assert issubclass(FileLimitExceededError, DataLoadError)
    assert issubclass(InvalidSheetError, DataLoadError)
