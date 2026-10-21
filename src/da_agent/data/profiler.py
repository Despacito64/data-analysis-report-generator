"""Tabular dataset profiler, semantic type detection, and descriptive statistics."""

import hashlib
import math
from pathlib import Path
from typing import Any

import pandas as pd

from da_agent.contracts import (
    ColumnProfile,
    DatasetProfile,
    DateCoverage,
    SemanticType,
    StatBlock,
)
from da_agent.data.loader import load_data
from da_agent.data.registry import compute_file_sha256

TRANSFORMATION_VERSION = "0.1.0"

_POSTAL_KEYWORDS = ("postal", "zip", "zipcode", "postcode")
_ID_SUFFIXES = (
    "_id",
    " id",
    "_key",
    " key",
    "_code",
    " code",
    "_sku",
    " sku",
    "_number",
    " number",
)
_ID_EXACT = {
    "id",
    "key",
    "code",
    "sku",
    "row_id",
    "row id",
    "order_id",
    "order id",
    "customer_id",
    "customer id",
    "product_id",
    "product id",
    "postal_code",
    "postal code",
    "csvbase_row_id",
}
_DATE_TOKENS = {"date", "time", "timestamp", "datetime", "dt", "ts", "day", "month", "year"}
_EXPLICIT_TEXT_KEYWORDS = (
    "note",
    "notes",
    "comment",
    "comments",
    "description",
    "summary",
    "text",
    "message",
    "body",
)
_NAME_TEXT_KEYWORDS = ("product name", "customer name", "title")


def compute_dataset_hash(file_bytes_or_path: bytes | str | Path) -> str:
    """Compute the SHA-256 hash of a file path or raw bytes."""
    if isinstance(file_bytes_or_path, (str, Path)):
        return compute_file_sha256(file_bytes_or_path)
    if isinstance(file_bytes_or_path, bytes):
        return hashlib.sha256(file_bytes_or_path).hexdigest().lower()
    raise TypeError(f"Expected bytes or path-like object, got {type(file_bytes_or_path).__name__}")


def infer_semantic_type(col_name: str, series: pd.Series) -> SemanticType:
    """Infer the semantic type of a DataFrame column according to contract rules.

    Rules:
    - Postal codes, ZIP codes, and ID columns are always IDENTIFIER (never NUMERIC_MEASURE).
    - True date or datetime columns are DATE.
    - Continuous numerical series that are not identifiers are NUMERIC_MEASURE.
    - Low-cardinality discrete categories are CATEGORY.
    - Long strings, free-form text, or descriptions are TEXT.
    """
    clean_name = col_name.strip().lower()

    # Rule 1: Postal codes & ZIP codes MUST be IDENTIFIER, never NUMERIC_MEASURE
    if any(keyword in clean_name for keyword in _POSTAL_KEYWORDS):
        return SemanticType.IDENTIFIER

    # Rule 2: Explicit ID tokens or suffixes
    if (
        clean_name in _ID_EXACT
        or clean_name.endswith(_ID_SUFFIXES)
        or clean_name.startswith(("id_", "key_"))
    ):
        return SemanticType.IDENTIFIER

    # Rule 3: Date / Datetime
    if pd.api.types.is_datetime64_any_dtype(series):
        return SemanticType.DATE

    name_tokens = set(clean_name.replace("_", " ").split())
    non_null = series.dropna()

    if (name_tokens & _DATE_TOKENS) and len(non_null) > 0:
        sample = non_null.head(50)
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if (parsed.notna().sum() / len(sample)) >= 0.5:
            return SemanticType.DATE

    if len(non_null) >= 10 and (series.dtype == object or isinstance(series.dtype, pd.StringDtype)):
        sample = non_null.head(30)
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if (parsed.notna().sum() / len(sample)) >= 0.8:
            return SemanticType.DATE

    # Rule 4: Numeric measures
    if pd.api.types.is_numeric_dtype(series):
        return SemanticType.NUMERIC_MEASURE

    # Rule 5: Boolean or explicit Categorical
    if pd.api.types.is_bool_dtype(series) or isinstance(series.dtype, pd.CategoricalDtype):
        return SemanticType.CATEGORY

    # Rule 6: Strings - Category vs Text
    if any(keyword in clean_name for keyword in _EXPLICIT_TEXT_KEYWORDS) or any(
        keyword in clean_name for keyword in _NAME_TEXT_KEYWORDS
    ):
        return SemanticType.TEXT

    str_series = non_null.astype(str)
    if len(str_series) == 0:
        return SemanticType.CATEGORY

    nunique = series.nunique(dropna=True)
    avg_len = str_series.str.len().mean()
    ratio = nunique / len(str_series)

    if avg_len > 35:
        return SemanticType.TEXT

    if nunique <= 50 or ratio <= 0.2:
        return SemanticType.CATEGORY

    return SemanticType.TEXT


def compute_date_coverage(col_name: str, series: pd.Series) -> tuple[DateCoverage, list[str]]:
    """Compute date coverage metrics (min, max, parse_failures) for a date column."""
    diagnostics: list[str] = []
    non_null = series.dropna()

    if len(non_null) == 0:
        return DateCoverage(column=col_name, min=None, max=None, parse_failures=0), diagnostics

    if pd.api.types.is_datetime64_any_dtype(series):
        min_date = non_null.min().strftime("%Y-%m-%d")
        max_date = non_null.max().strftime("%Y-%m-%d")
        return DateCoverage(
            column=col_name, min=min_date, max=max_date, parse_failures=0
        ), diagnostics

    parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    parse_failures = int((non_null.notna() & parsed.isna()).sum())
    valid_dates = parsed.dropna()

    if not valid_dates.empty:
        min_date = valid_dates.min().strftime("%Y-%m-%d")
        max_date = valid_dates.max().strftime("%Y-%m-%d")
    else:
        min_date = None
        max_date = None

    if parse_failures > 0:
        diagnostics.append(
            f"Column '{col_name}' encountered {parse_failures} date parse failure(s)."
        )

    return (
        DateCoverage(
            column=col_name,
            min=min_date,
            max=max_date,
            parse_failures=parse_failures,
        ),
        diagnostics,
    )


def compute_stat_block(series: pd.Series) -> StatBlock:
    """Compute descriptive statistics for a numeric measure column."""
    non_null = pd.to_numeric(series, errors="coerce").dropna()
    count = len(non_null)

    if count == 0:
        return StatBlock(count=0)

    def _sanitize(val: Any) -> float | None:
        if val is None or pd.isna(val):
            return None
        float_val = float(val)
        if math.isnan(float_val) or math.isinf(float_val):
            return None
        return float_val

    mean_val = _sanitize(non_null.mean())
    std_val = _sanitize(non_null.std(ddof=1)) if count > 1 else None
    min_val = _sanitize(non_null.min())
    q25_val = _sanitize(non_null.quantile(0.25))
    median_val = _sanitize(non_null.median())
    q75_val = _sanitize(non_null.quantile(0.75))
    max_val = _sanitize(non_null.max())

    return StatBlock(
        count=count,
        mean=mean_val,
        std=std_val,
        min=min_val,
        q25=q25_val,
        median=median_val,
        q75=q75_val,
        max=max_val,
    )


def _serialize_example(val: Any) -> Any:
    """Convert pandas/numpy types to JSON-safe primitives."""
    if pd.isna(val):
        return None
    if hasattr(val, "item"):
        return val.item()
    return val


def compute_profile(
    df: pd.DataFrame,
    *,
    file_path: str | Path | None = None,
    source_name: str | None = None,
    dataset_hash: str | None = None,
    transformation_version: str = TRANSFORMATION_VERSION,
) -> DatasetProfile:
    """Compute structural and statistical profile of a pandas DataFrame.

    Args:
        df: Input pandas DataFrame.
        file_path: Optional path to the source file (used for hashing and naming).
        source_name: Optional explicit name for data source.
        dataset_hash: Optional SHA-256 hash. If omitted and file_path is given, computed from file.
        transformation_version: Version of the loading and cleaning pipeline.

    Returns:
        Validated DatasetProfile instance conforming to CONTRACT_VERSION.
    """
    resolved_hash: str
    if dataset_hash is not None:
        resolved_hash = dataset_hash
    elif file_path is not None:
        resolved_hash = compute_file_sha256(file_path)
    else:
        # Deterministic in-memory content hash
        resolved_hash = hashlib.sha256(
            pd.util.hash_pandas_object(df, index=True).to_numpy().tobytes()
        ).hexdigest()

    resolved_source: str
    if source_name is not None:
        resolved_source = source_name
    elif file_path is not None:
        resolved_source = Path(file_path).name
    else:
        resolved_source = "in-memory"

    columns: list[ColumnProfile] = []
    date_coverage: list[DateCoverage] = []
    descriptive_stats: dict[str, StatBlock] = {}
    parsing_diagnostics: list[str] = []

    for col in df.columns:
        col_str = str(col)
        series = df[col]
        missing_count = int(series.isna().sum())
        distinct_count = int(series.nunique(dropna=True))
        semantic_type = infer_semantic_type(col_str, series)

        # Pick up to 3 non-null examples
        non_null_samples = series.dropna().unique()[:3]
        examples = [_serialize_example(x) for x in non_null_samples]

        columns.append(
            ColumnProfile(
                name=col_str,
                physical_type=str(series.dtype),
                semantic_type=semantic_type,
                missing_count=missing_count,
                distinct_count=distinct_count,
                examples=examples,
            )
        )

        if semantic_type == SemanticType.DATE:
            dc, diags = compute_date_coverage(col_str, series)
            date_coverage.append(dc)
            parsing_diagnostics.extend(diags)
        elif semantic_type == SemanticType.NUMERIC_MEASURE:
            descriptive_stats[col_str] = compute_stat_block(series)

    duplicate_row_count = int(df.duplicated().sum())

    return DatasetProfile(
        dataset_hash=resolved_hash,
        transformation_version=transformation_version,
        source_name=resolved_source,
        row_count=len(df),
        columns=columns,
        duplicate_row_count=duplicate_row_count,
        date_coverage=date_coverage,
        descriptive_stats=descriptive_stats,
        parsing_diagnostics=parsing_diagnostics,
    )


def profile_file(
    file_path: str | Path,
    *,
    sheet_name: str | int | None = None,
    transformation_version: str = TRANSFORMATION_VERSION,
    **load_kwargs: Any,
) -> DatasetProfile:
    """Load a dataset file and generate its DatasetProfile."""
    path = Path(file_path)
    df = load_data(path, sheet_name=sheet_name, **load_kwargs)
    source = path.name if sheet_name is None else f"{path.name}#{sheet_name}"
    raw_hash = compute_file_sha256(path)
    return compute_profile(
        df,
        file_path=path,
        source_name=source,
        dataset_hash=raw_hash,
        transformation_version=transformation_version,
    )
