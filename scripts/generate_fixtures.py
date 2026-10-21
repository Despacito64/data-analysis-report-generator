"""Generate test fixtures for M1 data loader and profiler tests."""

import json
from pathlib import Path

import openpyxl


def generate_fixtures() -> None:
    fixtures_dir = Path("tests/fixtures")
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # 1. valid_sample.csv
    # Exercises:
    # - Numeric identifiers with leading zeros ("01002", "07030")
    # - Mixed date formats ("YYYY-MM-DD", "MM/DD/YYYY", "YYYY/MM/DD")
    # - Exactly 1 missing date (row 5: blank)
    # - Exactly 1 junk/unparseable date (row 8: "not-a-date")
    # - Various missing value representations:
    #   - blank cells ("")
    #   - "NA"
    #   - "N/A"
    #   - "null"
    #   - "-" (not treated as NA by default in Pandas, but treated as NA with na_values=["-"])
    # - Exact duplicate rows (row 9 and row 10 are completely identical)
    csv_content = """row_id,order_id,postal_code,order_date,category,sales,notes
1,ORD-1001,01002,2023-01-15,Furniture,250.5,Express delivery
2,ORD-1002,07030,01/16/2023,Technology,, - 
3,ORD-1003,90210,2023/01/17,N/A,120.0,null
4,ORD-1004,01002,2023-01-18,Furniture,45.0,NA
5,ORD-1005,07030,,Office Supplies,NA,Standard delivery
6,ORD-1006,90210,2023-01-20,Technology,310.25,
7,ORD-1007,01002,2023-01-21,null,null,-
8,ORD-1008,07030,not-a-date,,95.5,Gift wrapped
9,ORD-1009,90210,2023-01-23,Office Supplies,15.0,Regular
9,ORD-1009,90210,2023-01-23,Office Supplies,15.0,Regular
"""
    (fixtures_dir / "valid_sample.csv").write_text(csv_content, encoding="utf-8")

    # 2. valid_sample.xlsx (matching valid_sample.csv)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    rows = [
        ["row_id", "order_id", "postal_code", "order_date", "category", "sales", "notes"],
        [1, "ORD-1001", "01002", "2023-01-15", "Furniture", 250.5, "Express delivery"],
        [2, "ORD-1002", "07030", "01/16/2023", "Technology", None, " - "],
        [3, "ORD-1003", "90210", "2023/01/17", "N/A", 120.0, "null"],
        [4, "ORD-1004", "01002", "2023-01-18", "Furniture", 45.0, "NA"],
        [5, "ORD-1005", "07030", None, "Office Supplies", "NA", "Standard delivery"],
        [6, "ORD-1006", "90210", "2023-01-20", "Technology", 310.25, None],
        [7, "ORD-1007", "01002", "2023-01-21", "null", "null", "-"],
        [8, "ORD-1008", "07030", "not-a-date", None, 95.5, "Gift wrapped"],
        [9, "ORD-1009", "90210", "2023-01-23", "Office Supplies", 15.0, "Regular"],
        [9, "ORD-1009", "90210", "2023-01-23", "Office Supplies", 15.0, "Regular"],
    ]

    for r_idx, row in enumerate(rows, start=1):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            # Ensure text columns remain text formatted
            if c_idx in (3, 4, 7) and val is not None and r_idx > 1:
                cell.number_format = "@"

    wb.save(fixtures_dir / "valid_sample.xlsx")

    # 3. valid_sample_expected.json
    expected_data = {
        "description": "Hand-computed expected values and missing-value rules for valid_sample.csv and valid_sample.xlsx",
        "row_count": 10,
        "column_count": 7,
        "columns": [
            "row_id",
            "order_id",
            "postal_code",
            "order_date",
            "category",
            "sales",
            "notes",
        ],
        "duplicate_row_count": 1,
        "duplicate_rows_indices": [8, 9],
        "missing_value_rule": {
            "default_engine": "pandas_default",
            "default_missing_tokens": [
                "",
                "NA",
                "N/A",
                "null",
                "NULL",
                "NaN",
                "None",
            ],
            "non_default_missing_tokens": ["-", " - "],
            "explanation": "Pandas default read_csv/read_excel treats empty strings, 'NA', 'N/A', and 'null' as NaN/missing. Literal '-' and ' - ' are treated as valid strings unless na_values=['-', ' - '] is explicitly configured.",
        },
        "missing_counts": {
            "row_id": 0,
            "order_id": 0,
            "postal_code": 0,
            "order_date": 1,
            "category": 3,
            "sales": 3,
            "notes": 3,
        },
        "missing_counts_with_custom_na": {
            "custom_na_values": ["-", " - "],
            "notes": 5,
        },
        "date_coverage": {
            "column": "order_date",
            "min": "2023-01-15",
            "max": "2023-01-23",
            "missing_count": 1,
            "parse_failures": 1,
            "valid_count": 8,
            "date_formats_present": ["YYYY-MM-DD", "MM/DD/YYYY", "YYYY/MM/DD"],
            "junk_dates": ["not-a-date"],
        },
        "postal_codes": [
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
        ],
        "sales_sum": 851.25,
    }
    (fixtures_dir / "valid_sample_expected.json").write_text(
        json.dumps(expected_data, indent=2), encoding="utf-8"
    )

    # 4. empty.csv (0 bytes)
    (fixtures_dir / "empty.csv").write_bytes(b"")

    # 5. corrupt.xlsx (invalid zip file, random binary/text)
    (fixtures_dir / "corrupt.xlsx").write_bytes(
        b"This is completely invalid binary/text content not a PK zip file."
    )

    # 6. wrong_extension.txt
    (fixtures_dir / "wrong_extension.txt").write_text("col1,col2\n1,2\n", encoding="utf-8")

    # 7. multi_sheet.xlsx (multiple sheets for sheet selection testing)
    wb_multi = openpyxl.Workbook()
    ws_orders = wb_multi.active
    ws_orders.title = "Orders"
    ws_orders.append(["order_id", "amount"])
    ws_orders.append(["ORD-01", 100])
    ws_orders.append(["ORD-02", 200])

    ws_returns = wb_multi.create_sheet(title="Returns")
    ws_returns.append(["return_id", "order_id", "reason"])
    ws_returns.append(["RET-01", "ORD-01", "Defective"])

    wb_multi.save(fixtures_dir / "multi_sheet.xlsx")

    # 8. multi_sheet_expected.json
    multi_expected = {
        "sheets": {
            "Orders": {"row_count": 2, "columns": ["order_id", "amount"]},
            "Returns": {"row_count": 1, "columns": ["return_id", "order_id", "reason"]},
        }
    }
    (fixtures_dir / "multi_sheet_expected.json").write_text(
        json.dumps(multi_expected, indent=2), encoding="utf-8"
    )

    # 9. formula.xlsx (testing data_only=True loading)
    wb_formula = openpyxl.Workbook()
    ws_f = wb_formula.active
    ws_f.title = "Calculations"
    ws_f.append(["base", "multiplier", "total"])
    ws_f.append([10, 5, "=A2*B2"])
    wb_formula.save(fixtures_dir / "formula.xlsx")

    print("Fixtures generated successfully.")


if __name__ == "__main__":
    generate_fixtures()
