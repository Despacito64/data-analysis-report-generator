"""Data loader and input validation for CSV and XLSX datasets."""

from pathlib import Path
from typing import Any

import openpyxl
import pandas as pd

from da_agent.core.config import InputLimitsConfig, load_config


class DataLoadError(Exception):
    """Base exception for all data loading errors."""


class InvalidExtensionError(DataLoadError):
    """Raised when the file extension is not in the allowlist."""


class EmptyDataError(DataLoadError):
    """Raised when the file is empty or contains no readable data rows."""


class CorruptFileError(DataLoadError):
    """Raised when the file is corrupted, malformed, or unparseable."""


class FileLimitExceededError(DataLoadError):
    """Raised when the file exceeds configured file size or row limits."""


class InvalidSheetError(DataLoadError):
    """Raised when the requested sheet is not found in the Excel workbook."""


def load_data(
    file_path: str | Path,
    *,
    sheet_name: str | int | None = None,
    delimiter: str | None = None,
    encoding: str = "utf-8",
    date_format: str | None = None,
    parse_dates: bool | list[str] | None = None,
    dtype: dict[str, Any] | type | None = None,
    na_values: list[str] | dict[str, list[str]] | None = None,
    keep_default_na: bool = True,
    limits: InputLimitsConfig | None = None,
    config_path: str | Path = "config.yaml",
) -> pd.DataFrame:
    """Load and validate a CSV or XLSX dataset with configurable parsing and safety checks.

    Args:
        file_path: Path to the target CSV or XLSX file.
        sheet_name: Sheet name or 0-indexed integer for Excel files.
        delimiter: Custom CSV delimiter (e.g. ',', ';', '\\t').
        encoding: File character encoding (default 'utf-8').
        date_format: Date format string for parsing date columns.
        parse_dates: Column names or boolean indicating whether to parse dates.
        dtype: Explicit column data types mapping.
        na_values: Additional strings to recognize as NA/null.
        keep_default_na: Whether to include default pandas NA values.
        limits: InputLimitsConfig instance. If None, loaded from config_path.
        config_path: Path to YAML configuration file if limits are not provided.

    Returns:
        Loaded pandas DataFrame conforming to input limits.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        InvalidExtensionError: If the file extension is not allowlisted.
        EmptyDataError: If the file is 0 bytes or contains no data rows.
        CorruptFileError: If the file cannot be parsed or is corrupted.
        FileLimitExceededError: If the file size or row count exceeds limits.
        InvalidSheetError: If the requested Excel sheet does not exist.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Data file not found: {path}")

    if limits is None:
        try:
            limits = load_config(config_path).input_limits
        except (FileNotFoundError, OSError, ValueError, TypeError):
            limits = InputLimitsConfig()

    ext = path.suffix.lower()
    if ext not in limits.allowed_extensions:
        raise InvalidExtensionError(
            f"Unsupported file extension '{ext}' for file '{path.name}'. "
            f"Allowed extensions are: {limits.allowed_extensions}"
        )

    file_size_bytes = path.stat().st_size
    if file_size_bytes == 0:
        raise EmptyDataError(f"The file '{path.name}' is empty (0 bytes).")

    file_size_mb = file_size_bytes / (1024 * 1024)
    if file_size_mb > limits.max_file_size_mb:
        raise FileLimitExceededError(
            f"File size {file_size_mb:.2f} MB exceeds maximum allowed limit of {limits.max_file_size_mb:.2f} MB."
        )

    if ext == ".csv":
        read_csv_kwargs: dict[str, Any] = {
            "encoding": encoding,
            "keep_default_na": keep_default_na,
        }
        if delimiter is not None:
            read_csv_kwargs["sep"] = delimiter
        if parse_dates is not None:
            read_csv_kwargs["parse_dates"] = parse_dates
        if date_format is not None:
            read_csv_kwargs["date_format"] = date_format
        if dtype is not None:
            read_csv_kwargs["dtype"] = dtype
        if na_values is not None:
            read_csv_kwargs["na_values"] = na_values

        try:
            df = pd.read_csv(path, **read_csv_kwargs)
        except pd.errors.EmptyDataError as err:
            raise EmptyDataError(
                f"File '{path.name}' contains no readable data or columns."
            ) from err
        except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as err:
            raise CorruptFileError(f"Failed to parse CSV file '{path.name}': {err}") from err
        except Exception as err:
            raise CorruptFileError(f"Error reading CSV file '{path.name}': {err}") from err

    elif ext == ".xlsx":
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            available_sheets = wb.sheetnames
            wb.close()
        except Exception as err:
            raise CorruptFileError(
                f"Failed to inspect Excel workbook '{path.name}': {err}"
            ) from err

        if not available_sheets:
            raise EmptyDataError(f"Workbook '{path.name}' contains no sheets.")

        target_sheet: str | int
        if sheet_name is None:
            target_sheet = available_sheets[0]
        elif isinstance(sheet_name, str):
            if sheet_name not in available_sheets:
                raise InvalidSheetError(
                    f"Sheet '{sheet_name}' not found in workbook '{path.name}'. "
                    f"Available sheets: {available_sheets}"
                )
            target_sheet = sheet_name
        elif isinstance(sheet_name, int):
            if sheet_name < 0 or sheet_name >= len(available_sheets):
                raise InvalidSheetError(
                    f"Sheet index {sheet_name} out of range in workbook '{path.name}'. "
                    f"Available sheets: {available_sheets}"
                )
            target_sheet = available_sheets[sheet_name]
        else:
            raise InvalidSheetError(
                f"Invalid sheet_name parameter type: {type(sheet_name).__name__}"
            )

        read_excel_kwargs: dict[str, Any] = {
            "sheet_name": target_sheet,
            "engine": "openpyxl",
            "engine_kwargs": {"data_only": True},
            "keep_default_na": keep_default_na,
        }
        if parse_dates is not None:
            read_excel_kwargs["parse_dates"] = parse_dates
        if date_format is not None:
            read_excel_kwargs["date_format"] = date_format
        if dtype is not None:
            read_excel_kwargs["dtype"] = dtype
        if na_values is not None:
            read_excel_kwargs["na_values"] = na_values

        try:
            df = pd.read_excel(path, **read_excel_kwargs)
        except Exception as err:
            raise CorruptFileError(
                f"Failed to parse Excel sheet '{target_sheet}' in '{path.name}': {err}"
            ) from err

    else:
        raise InvalidExtensionError(f"Unsupported extension '{ext}'.")

    if df.empty or len(df.columns) == 0:
        raise EmptyDataError(f"Dataset in '{path.name}' contains no data rows or columns.")

    if len(df) > limits.max_rows:
        raise FileLimitExceededError(
            f"Row count {len(df)} exceeds maximum allowed limit of {limits.max_rows} rows."
        )

    return df
