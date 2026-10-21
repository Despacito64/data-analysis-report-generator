#!/usr/bin/env python3
"""Model spike for M0 step 6 (DECISIONS D-006). Standard library only.

Runs each Ollama model on 10 sample planning prompts and records:
  json_valid, schema_valid, allowlist (only registered tools), columns (only real columns),
  expected_tool (a sensible tool chosen), and latency.

Usage (from the repo root, Ollama running):
    python scripts/model_spike.py qwen2.5:7b llama3.1:8b
Results are printed and saved to scripts/model_spike_results.json
"""
import json
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOST = "http://localhost:11434"
SEED = 42

TOOLS = {
    "filter_rows": "Keep rows matching a condition. args: column, operator, value",
    "group_aggregate": "Group and aggregate a measure. args: group_by (list), metric_column, aggregation",
    "rank": "Rank groups by a measure. args: group_by, metric_column, aggregation, top_n, order",
    "period_compare": "Compare a measure between two periods. args: metric_column, aggregation, period_a, period_b, group_by (optional)",
    "trend": "Measure over time. args: metric_column, aggregation, date_column, frequency",
    "contribution": "Share of total by segment. args: group_by, metric_column, aggregation",
    "correlation": "Correlation between two numeric columns. args: column_a, column_b",
    "anomaly_flags": "IQR outlier flags. args: metric_column, group_by (optional)",
}
COLUMNS = ["Order Date", "Ship Date", "Segment", "Country", "City", "State", "Region",
           "Category", "Sub-Category", "Sales", "Quantity", "Discount", "Profit"]
COLUMN_KEYS = {"column", "group_by", "metric_column", "column_a", "column_b", "date_column"}

# (question, acceptable tools: at least one must appear, min tasks, must_decline)
PROMPTS = [
    ("What were total Sales by Region?", {"group_aggregate"}, 1, False),
    ("Which 5 Sub-Categories have the highest Profit?", {"rank"}, 1, False),
    ("How did total Sales change between 2016 and 2017?", {"period_compare"}, 1, False),
    ("Show the monthly trend of Profit.", {"trend"}, 1, False),
    ("What share of total Sales does each Category contribute?", {"contribution"}, 1, False),
    ("Is Discount correlated with Profit?", {"correlation"}, 1, False),
    ("Flag unusual Sales values within each Sub-Category.", {"anomaly_flags"}, 1, False),
    ("What were total Sales for the Consumer segment only?", {"filter_rows"}, 1, False),
    ("Sales fell in some regions from 2016 to 2017. Find which Category in the worst region drove the drop.",
     {"period_compare", "contribution", "group_aggregate"}, 2, False),
    ("Predict next year's Sales.", set(), 0, True),
]

SYSTEM = (
    "You are an analysis planner. Reply with JSON only, no other text, in exactly this shape:\n"
    '{"tasks":[{"id":"t1","tool":"<tool name>","args":{...},"depends_on":[],"rationale":"<one sentence>"}],'
    '"decline_reason":null}\n'
    "Use only these tools and only these columns.\nTools:\n"
    + "\n".join(f"- {n}: {d}" for n, d in TOOLS.items())
    + "\nColumns: " + ", ".join(COLUMNS)
    + "\nIf the question cannot be answered with these tools, return an empty tasks list and a decline_reason."
)


def ask(model, question):
    body = json.dumps({
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0, "seed": SEED},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
    }).encode()
    req = urllib.request.Request(HOST + "/api/chat", body, {"Content-Type": "application/json"})
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = json.load(resp)
    return data["message"]["content"], time.perf_counter() - start


def acyclic(tasks):
    deps = {t["id"]: list(t["depends_on"]) for t in tasks}
    state = {}

    def visit(n):
        if state.get(n) == 1:
            return False
        if state.get(n) == 2:
            return True
        state[n] = 1
        ok = all(visit(d) for d in deps[n])
        state[n] = 2
        return ok

    return all(visit(n) for n in deps)


def flat(value):
    return [x for v in (value if isinstance(value, list) else [value]) for x in [v]]


def check(raw, expected, min_tasks, must_decline):
    r = {"json_valid": False, "schema_valid": False, "allowlist": False, "columns": False, "expected_tool": False}
    try:
        obj = json.loads(raw)
        r["json_valid"] = isinstance(obj, dict)
        tasks = obj["tasks"]
    except Exception:
        return r
    try:
        ids = [t["id"] for t in tasks]
        ok = (isinstance(tasks, list) and len(set(ids)) == len(ids)
              and all(isinstance(t["id"], str) and isinstance(t["tool"], str) and isinstance(t["args"], dict)
                      and isinstance(t["depends_on"], list) and t["id"] not in t["depends_on"]
                      and all(d in ids for d in t["depends_on"]) for t in tasks))
        r["schema_valid"] = bool(ok and acyclic(tasks))
    except Exception:
        return r
    r["allowlist"] = all(t["tool"] in TOOLS for t in tasks)
    bad = False
    for t in tasks:
        for k, v in t["args"].items():
            if k in COLUMN_KEYS:
                for x in flat(v):
                    if isinstance(x, str) and x not in COLUMNS:
                        bad = True
    r["columns"] = not bad
    if must_decline:
        r["expected_tool"] = len(tasks) == 0
    else:
        used = {t["tool"] for t in tasks}
        r["expected_tool"] = bool(used & expected) and len(tasks) >= min_tasks
    return r


def main(models):
    results = {}
    for model in models:
        print(f"\n== {model} ==")
        rows, times = [], []
        for q, expected, min_tasks, decline in PROMPTS:
            try:
                raw, secs = ask(model, q)
            except Exception as e:  # server down, model missing, timeout
                print(f"  ERROR: {e}")
                raw, secs = "", float("nan")
            r = check(raw, expected, min_tasks, decline)
            times.append(secs)
            rows.append({"question": q, "latency_s": round(secs, 2), **r, "raw": raw})
            print(f"  {secs:6.1f}s  " + " ".join(f"{k}={'Y' if v else 'N'}" for k, v in r.items()) + f"  | {q[:45]}")
        n = len(rows)
        good = [t for t in times if t == t]
        summary = {k: f"{sum(r[k] for r in rows)}/{n}"
                   for k in ("json_valid", "schema_valid", "allowlist", "columns", "expected_tool")}
        summary["median_latency_s"] = round(statistics.median(good), 2) if good else None
        results[model] = {"summary": summary, "rows": rows}
        print("  SUMMARY", summary)
    out = Path(__file__).with_name("model_spike_results.json")
    out.write_text(json.dumps({"run_at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
                               "temperature": 0, "results": results}, indent=2))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python scripts/model_spike.py MODEL [MODEL ...]")
    main(sys.argv[1:])
