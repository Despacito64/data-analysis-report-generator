#!/usr/bin/env python3
"""Standalone script to build the frozen evaluation benchmark oracle.

CRITICAL: Must NOT import any modules from da_agent (tools, agent, validation, reports).
Uses pure pandas/numpy to compute ground truth answers from Sample-Superstore.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def compute_oracle(csv_path: Path) -> dict[str, dict]:
    """Compute ground truth answers for all 20 benchmark questions."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    oracle: dict[str, dict] = {}

    # q01: total sales for orders shipped via 'First Class'
    q01_val = float(df[df["Ship Mode"] == "First Class"]["Sales"].sum())
    oracle["q01"] = {
        "question_id": "q01",
        "expected_answer": q01_val,
        "tolerance": 1e-2,
        "type": "numeric",
        "description": "Total sales for First Class shipping",
    }

    # q02: count of rows for Category == 'Technology' and Region == 'West'
    q02_val = len(df[(df["Category"] == "Technology") & (df["Region"] == "West")])
    oracle["q02"] = {
        "question_id": "q02",
        "expected_answer": q02_val,
        "tolerance": 0.0,
        "type": "integer",
        "description": "Row count for Technology in West region",
    }

    # q03: total sales for each Region
    q03_series = df.groupby("Region")["Sales"].sum()
    oracle["q03"] = {
        "question_id": "q03",
        "expected_answer": {k: float(v) for k, v in q03_series.to_dict().items()},
        "tolerance": 1e-2,
        "type": "dict_numeric",
        "description": "Total sales by Region",
    }

    # q04: total profit for each Segment
    q04_series = df.groupby("Segment")["Profit"].sum()
    oracle["q04"] = {
        "question_id": "q04",
        "expected_answer": {k: float(v) for k, v in q04_series.to_dict().items()},
        "tolerance": 1e-2,
        "type": "dict_numeric",
        "description": "Total profit by Segment",
    }

    # q05: average discount across each Category
    q05_series = df.groupby("Category")["Discount"].mean()
    oracle["q05"] = {
        "question_id": "q05",
        "expected_answer": {k: float(v) for k, v in q05_series.to_dict().items()},
        "tolerance": 1e-4,
        "type": "dict_numeric",
        "description": "Average discount by Category",
    }

    # q06: top 5 Sub-Categories ranked by total Sales
    q06_top = (
        df.groupby("Sub-Category")["Sales"]
        .sum()
        .sort_values(ascending=False)
        .head(5)
        .index.tolist()
    )
    oracle["q06"] = {
        "question_id": "q06",
        "expected_answer": q06_top,
        "tolerance": 0.0,
        "type": "list_string",
        "description": "Top 5 Sub-Categories by Sales",
    }

    # q07: top 3 States ranked by total Profit
    q07_top = (
        df.groupby("State")["Profit"].sum().sort_values(ascending=False).head(3).index.tolist()
    )
    oracle["q07"] = {
        "question_id": "q07",
        "expected_answer": q07_top,
        "tolerance": 0.0,
        "type": "list_string",
        "description": "Top 3 States by Profit",
    }

    # q08: bottom 5 Sub-Categories ranked by total Profit
    q08_bottom = (
        df.groupby("Sub-Category")["Profit"]
        .sum()
        .sort_values(ascending=True)
        .head(5)
        .index.tolist()
    )
    oracle["q08"] = {
        "question_id": "q08",
        "expected_answer": q08_bottom,
        "tolerance": 0.0,
        "type": "list_string",
        "description": "Bottom 5 Sub-Categories by Profit",
    }

    # q09: period_compare Sales 2016 vs 2017
    sales_2016 = float(
        df[(df["Order Date"] >= "2016-01-01") & (df["Order Date"] <= "2016-12-31")]["Sales"].sum()
    )
    sales_2017 = float(
        df[(df["Order Date"] >= "2017-01-01") & (df["Order Date"] <= "2017-12-31")]["Sales"].sum()
    )
    growth_09 = float((sales_2017 - sales_2016) / sales_2016)
    oracle["q09"] = {
        "question_id": "q09",
        "expected_answer": {
            "base_value": sales_2016,
            "compare_value": sales_2017,
            "absolute_change": float(sales_2017 - sales_2016),
            "relative_growth": growth_09,
        },
        "tolerance": 1e-4,
        "type": "period_compare",
        "description": "Period comparison Sales 2016 to 2017",
    }

    # q10: period_compare Profit 2015 vs 2016
    profit_2015 = float(
        df[(df["Order Date"] >= "2015-01-01") & (df["Order Date"] <= "2015-12-31")]["Profit"].sum()
    )
    profit_2016 = float(
        df[(df["Order Date"] >= "2016-01-01") & (df["Order Date"] <= "2016-12-31")]["Profit"].sum()
    )
    growth_10 = float((profit_2016 - profit_2015) / profit_2015)
    oracle["q10"] = {
        "question_id": "q10",
        "expected_answer": {
            "base_value": profit_2015,
            "compare_value": profit_2016,
            "absolute_change": float(profit_2016 - profit_2015),
            "relative_growth": growth_10,
        },
        "tolerance": 1e-4,
        "type": "period_compare",
        "description": "Period comparison Profit 2015 to 2016",
    }

    # q11: monthly trend of Sales in 2017
    df_2017 = df[(df["Order Date"] >= "2017-01-01") & (df["Order Date"] <= "2017-12-31")].copy()
    df_2017["Month"] = pd.to_datetime(df_2017["Order Date"]).dt.strftime("%Y-%m")
    trend_11_points = {k: float(v) for k, v in df_2017.groupby("Month")["Sales"].sum().items()}
    # calculate slope / direction
    y_vals = list(trend_11_points.values())
    x_vals = np.arange(len(y_vals), dtype=float)
    slope_11 = float(np.polyfit(x_vals, y_vals, 1)[0])
    oracle["q11"] = {
        "question_id": "q11",
        "expected_answer": {
            "points": trend_11_points,
            "slope": slope_11,
            "direction": "increasing" if slope_11 > 0 else "decreasing",
        },
        "tolerance": 1e-2,
        "type": "trend",
        "description": "Monthly trend of Sales in 2017",
    }

    # q12: quarterly trend of Profit over entire dataset
    df_q = df.copy()
    dt = pd.to_datetime(df_q["Order Date"])
    df_q["Quarter"] = dt.apply(lambda d: f"{d.year}-Q{d.quarter}")
    trend_12_points = {k: float(v) for k, v in df_q.groupby("Quarter")["Profit"].sum().items()}
    y_q = list(trend_12_points.values())
    x_q = np.arange(len(y_q), dtype=float)
    slope_12 = float(np.polyfit(x_q, y_q, 1)[0])
    oracle["q12"] = {
        "question_id": "q12",
        "expected_answer": {
            "points": trend_12_points,
            "slope": slope_12,
            "direction": "increasing" if slope_12 > 0 else "decreasing",
        },
        "tolerance": 1e-2,
        "type": "trend",
        "description": "Quarterly trend of Profit over dataset",
    }

    # q13: contribution of Sales by Category
    total_sales = float(df["Sales"].sum())
    cat_contrib = {
        k: float(v / total_sales) for k, v in df.groupby("Category")["Sales"].sum().items()
    }
    oracle["q13"] = {
        "question_id": "q13",
        "expected_answer": {
            "total_value": total_sales,
            "shares": cat_contrib,
        },
        "tolerance": 1e-4,
        "type": "contribution",
        "description": "Sales contribution shares by Category",
    }

    # q14: contribution of Sales by Region
    reg_contrib = {
        k: float(v / total_sales) for k, v in df.groupby("Region")["Sales"].sum().items()
    }
    oracle["q14"] = {
        "question_id": "q14",
        "expected_answer": {
            "total_value": total_sales,
            "shares": reg_contrib,
        },
        "tolerance": 1e-4,
        "type": "contribution",
        "description": "Sales contribution shares by Region",
    }

    # q15: correlation between Discount and Profit
    corr_15 = float(df["Discount"].corr(df["Profit"]))
    oracle["q15"] = {
        "question_id": "q15",
        "expected_answer": corr_15,
        "tolerance": 1e-4,
        "type": "numeric",
        "description": "Pearson correlation between Discount and Profit",
    }

    # q16: correlation between Sales and Profit
    corr_16 = float(df["Sales"].corr(df["Profit"]))
    oracle["q16"] = {
        "question_id": "q16",
        "expected_answer": corr_16,
        "tolerance": 1e-4,
        "type": "numeric",
        "description": "Pearson correlation between Sales and Profit",
    }

    # q17: anomalies in Sales using 1.5 x IQR rule (method='linear')
    sales_vals = df["Sales"].dropna().to_numpy(dtype=float)
    s_q1 = float(np.percentile(sales_vals, 25, method="linear"))
    s_q3 = float(np.percentile(sales_vals, 75, method="linear"))
    s_iqr = s_q3 - s_q1
    s_lower = s_q1 - 1.5 * s_iqr
    s_upper = s_q3 + 1.5 * s_iqr
    s_flagged = int(np.sum((sales_vals < s_lower) | (sales_vals > s_upper)))
    oracle["q17"] = {
        "question_id": "q17",
        "expected_answer": {
            "q1": s_q1,
            "q3": s_q3,
            "iqr": s_iqr,
            "lower_fence": s_lower,
            "upper_fence": s_upper,
            "flagged_count": s_flagged,
        },
        "tolerance": 1e-2,
        "type": "anomalies",
        "description": "IQR anomalies in Sales",
    }

    # q18: anomalies in Profit using 1.5 x IQR rule
    profit_vals = df["Profit"].dropna().to_numpy(dtype=float)
    p_q1 = float(np.percentile(profit_vals, 25, method="linear"))
    p_q3 = float(np.percentile(profit_vals, 75, method="linear"))
    p_iqr = p_q3 - p_q1
    p_lower = p_q1 - 1.5 * p_iqr
    p_upper = p_q3 + 1.5 * p_iqr
    p_flagged = int(np.sum((profit_vals < p_lower) | (profit_vals > p_upper)))
    oracle["q18"] = {
        "question_id": "q18",
        "expected_answer": {
            "q1": p_q1,
            "q3": p_q3,
            "iqr": p_iqr,
            "lower_fence": p_lower,
            "upper_fence": p_upper,
            "flagged_count": p_flagged,
        },
        "tolerance": 1e-2,
        "type": "anomalies",
        "description": "IQR anomalies in Profit",
    }

    # q19: In 'East' region, total profit for each Category
    east_profit = df[df["Region"] == "East"].groupby("Category")["Profit"].sum().to_dict()
    oracle["q19"] = {
        "question_id": "q19",
        "expected_answer": {k: float(v) for k, v in east_profit.items()},
        "tolerance": 1e-2,
        "type": "dict_numeric",
        "description": "Profit by Category in East region",
    }

    # q20: In 'Consumer' segment, top 3 Cities by total sales
    top_cities_consumer = (
        df[df["Segment"] == "Consumer"]
        .groupby("City")["Sales"]
        .sum()
        .sort_values(ascending=False)
        .head(3)
        .index.tolist()
    )
    oracle["q20"] = {
        "question_id": "q20",
        "expected_answer": top_cities_consumer,
        "tolerance": 0.0,
        "type": "list_string",
        "description": "Top 3 Cities by Sales in Consumer segment",
    }

    return oracle


def main() -> None:
    csv_file = Path("Sample-Superstore.csv")
    if not csv_file.exists():
        raise FileNotFoundError(f"Missing {csv_file}")
    out_dir = Path("evaluation/benchmark")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "oracle.json"

    oracle_data = compute_oracle(csv_file)
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(oracle_data, f, indent=2)
    print(f"Generated oracle with {len(oracle_data)} entries at {out_file}")


if __name__ == "__main__":
    main()
