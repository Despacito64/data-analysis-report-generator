"""Excel sheet hints for Streamlit (delegates to data.loader when available)."""

from __future__ import annotations

import importlib
from pathlib import Path


def _list_excel_sheet_names_impl(path: Path) -> list[str]:
    import openpyxl

    from da_agent.data.loader import CorruptFileError, EmptyDataError, InvalidExtensionError

    path = Path(path)
    ext = path.suffix.lower()
    if ext != ".xlsx":
        raise InvalidExtensionError(
            f"Sheet listing applies to .xlsx files only, not '{ext}'."
        )
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        names = list(wb.sheetnames)
        wb.close()
    except Exception as err:
        raise CorruptFileError(f"Failed to inspect Excel workbook '{path.name}': {err}") from err
    if not names:
        raise EmptyDataError(f"Workbook '{path.name}' contains no sheets.")
    return names


def list_excel_sheet_names(path: Path) -> list[str]:
    loader = importlib.import_module("da_agent.data.loader")
    delegate = getattr(loader, "list_excel_sheet_names", None)
    if delegate is not None:
        return delegate(path)
    return _list_excel_sheet_names_impl(path)