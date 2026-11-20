#!/usr/bin/env python3
"""Generate presentation-ready charts from saved evaluation runs.

No Ollama required — reads only the saved agent_eval.json files of the runs named by the options below
and evaluation/benchmark/questions.json.

Usage:
    uv run python scripts/generate_metrics_charts.py
    uv run python scripts/generate_metrics_charts.py --out scripts/charts
    uv run python scripts/generate_metrics_charts.py --ablation-json evaluation/results/ablation-no-replan-XXX/agent_eval.json
    uv run python scripts/generate_metrics_charts.py --spike-3b evaluation/results/model-spike-qwen25-3b-XXX/agent_eval.json --spike-7b evaluation/results/model-spike-qwen25-7b-XXX/agent_eval.json
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ── colour palette ────────────────────────────────────────────────────────────
C_AGENT = "#2563EB"  # blue  – dynamic agent
C_BASE = "#F59E0B"  # amber – baseline (template ceiling)
C_PASS = "#16A34A"  # green – passed
C_FAIL = "#DC2626"  # red   – failed
C_PLAN = "#6366F1"  # indigo – plan_generation
C_REPLAN = "#8B5CF6"  # violet – replanning
C_REPAIR1 = "#EC4899"  # pink  – repair_attempt_1
C_REPAIR2 = "#F43F5E"  # rose  – repair_attempt_2
C_ANSWER = "#0EA5E9"  # sky   – answer_synthesis
C_OTHER = "#94A3B8"  # slate – everything else

STAGE_COLOURS = {
    "plan_generation": C_PLAN,
    "replanning": C_REPLAN,
    "repair_attempt_1": C_REPAIR1,
    "repair_attempt_2": C_REPAIR2,
    "answer_synthesis": C_ANSWER,
}

# question-id → category (from questions.json; hard-coded as fallback)
CATEGORY_MAP = {
    "q01": "filter",
    "q02": "filter",
    "q03": "group_aggregate",
    "q04": "group_aggregate",
    "q05": "group_aggregate",
    "q06": "rank",
    "q07": "rank",
    "q08": "rank",
    "q09": "period_compare",
    "q10": "period_compare",
    "q11": "trend",
    "q12": "trend",
    "q13": "segment_contribution",
    "q14": "segment_contribution",
    "q15": "correlation",
    "q16": "correlation",
    "q17": "anomalies",
    "q18": "anomalies",
    "q19": "multistep",
    "q20": "multistep",
}

DPI = 150


def savefig(fig: plt.Figure, out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / name
    fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  saved {p}")
    return p


def load_eval(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_categories(questions_path: Path) -> dict[str, str]:
    if not questions_path.exists():
        return CATEGORY_MAP
    questions = json.loads(questions_path.read_text(encoding="utf-8"))
    return {q["id"]: q.get("category", "unknown") for q in questions}


# ── Chart 1: Accuracy by question category ───────────────────────────────────
def chart_accuracy_by_category(
    eval_data: dict,
    out_dir: Path,
    cat_map: dict[str, str],
    noreplan_data: dict | None = None,
) -> Path:
    per_q = {row["question_id"]: row for row in eval_data["per_question"]}
    per_q_r2 = (
        {row["question_id"]: row for row in noreplan_data["per_question"]} if noreplan_data else {}
    )
    cat_r2: dict[str, list[bool]] = defaultdict(list)

    # aggregate per category
    cat_agent: dict[str, list[bool]] = defaultdict(list)
    cat_baseline: dict[str, list[bool]] = defaultdict(list)
    for qid, cat in sorted(cat_map.items()):
        if qid not in per_q:
            continue
        row = per_q[qid]
        cat_agent[cat].append(row["accuracy"] is True)
        if per_q_r2:
            cat_r2[cat].append(per_q_r2.get(qid, {}).get("accuracy") is True)
        cat_baseline[cat].append(row.get("baseline_accuracy", True))

    categories = sorted(cat_agent.keys())
    agent_acc = [sum(cat_agent[c]) / len(cat_agent[c]) for c in categories]
    base_acc = [sum(cat_baseline[c]) / len(cat_baseline[c]) for c in categories]
    agent_frac = [f"{sum(cat_agent[c])}/{len(cat_agent[c])}" for c in categories]
    base_frac = [f"{sum(cat_baseline[c])}/{len(cat_baseline[c])}" for c in categories]

    x = np.arange(len(categories))
    w = 0.27 if per_q_r2 else 0.35

    fig, ax = plt.subplots(figsize=(12, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    offs = (-w, 0, w) if per_q_r2 else (-w / 2, None, w / 2)
    b1 = ax.bar(
        x + offs[0],
        agent_acc,
        w,
        label="R1: replanning on (qwen3:4b-instruct)",
        color=C_AGENT,
        alpha=0.9,
    )
    if per_q_r2:
        r2_acc = [sum(cat_r2[c]) / len(cat_r2[c]) for c in categories]
        ax.bar(x + offs[1], r2_acc, w, label="R2: replanning off", color=C_OTHER, alpha=0.9)
        for xi, c, acc in zip(x, categories, r2_acc):
            ax.text(
                xi + offs[1],
                acc + 0.02,
                f"{sum(cat_r2[c])}/{len(cat_r2[c])}",
                ha="center",
                va="bottom",
                fontsize=8,
                color="#475569",
                fontweight="bold",
            )
    b2 = ax.bar(x + offs[2], base_acc, w, label="Baseline (keyed ceiling)", color=C_BASE, alpha=0.9)

    for bar, frac in zip(b1, agent_frac):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            frac,
            ha="center",
            va="bottom",
            fontsize=8,
            color=C_AGENT,
            fontweight="bold",
        )
    for bar, frac in zip(b2, base_frac):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            frac,
            ha="center",
            va="bottom",
            fontsize=8,
            color="#92400E",
            fontweight="bold",
        )

    ax.set_xlabel("Question category")
    ax.set_ylabel("Accuracy (fraction correct)")
    ax.set_title(
        "Questions passed by category, one run per question\n"
        "Baseline is keyed by question id (a ceiling, not a competitor)"
    )
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace("_", "\n") for c in categories], fontsize=9)
    ax.set_ylim(0, 1.4)
    ax.legend(loc="upper center", ncol=3, frameon=False)
    ax.axhline(1.0, color=C_BASE, linestyle="--", linewidth=0.8, alpha=0.5)
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_accuracy_by_category.png")


# ── Chart 2: Stage time waterfall (horizontal stacked bar per question) ───────
def chart_stage_time_waterfall(eval_data: dict, out_dir: Path) -> Path:
    per_q = eval_data["per_question"]
    per_q_sorted = sorted(per_q, key=lambda r: r["question_id"])

    labels = [r["question_id"] for r in per_q_sorted]
    statuses = [r["accuracy"] for r in per_q_sorted]  # True / False / None

    tracked = [
        "plan_generation",
        "replanning",
        "repair_attempt_1",
        "repair_attempt_2",
        "answer_synthesis",
    ]

    fig, ax = plt.subplots(figsize=(12, 8))
    plt.style.use("seaborn-v0_8-whitegrid")

    y = np.arange(len(labels))
    lefts = np.zeros(len(labels))
    patches = []

    for stage in tracked:
        vals = np.array([r["stage_timings"].get(stage, 0.0) for r in per_q_sorted])
        bars = ax.barh(
            y,
            vals,
            left=lefts,
            color=STAGE_COLOURS[stage],
            alpha=0.85,
            label=stage.replace("_", " "),
        )
        patches.append(bars)
        lefts += vals

    # other time
    totals = np.array([r.get("total_time_s", 0.0) for r in per_q_sorted])
    other = np.maximum(totals - lefts, 0.0)
    ax.barh(y, other, left=lefts, color=C_OTHER, alpha=0.6, label="other")

    mean_total = totals.mean()
    ax.axvline(
        mean_total, color="black", linestyle="--", linewidth=1.2, label=f"mean {mean_total:.0f}s"
    )

    # mark failed questions
    for i, acc in enumerate(statuses):
        if acc is False:
            ax.text(2, i, "FAIL", va="center", color=C_FAIL, fontsize=8, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel("Time (seconds)")
    ax.set_title(
        "Time per Question by Pipeline Stage\n"
        "Tool execution is about 0.2% of total time (R1); LLM inference dominates"
    )
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_stage_time_waterfall.png")


# ── Chart 3: LLM calls distribution ──────────────────────────────────────────
def chart_llm_calls_distribution(eval_data: dict, out_dir: Path) -> Path:
    per_q = eval_data["per_question"]
    counts = [r.get("llm_call_count", 0) for r in per_q]
    colours = [C_FAIL if r["accuracy"] is False else C_PASS for r in per_q]
    qids = [r["question_id"] for r in per_q]

    fig, ax = plt.subplots(figsize=(10, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    ax.bar(qids, counts, color=colours, alpha=0.85, edgecolor="white")
    ax.set_xlabel("Question ID")
    ax.set_ylabel("LLM calls (all repeats combined)")
    ax.set_title("LLM Calls per Question\nRed = question answered incorrectly")
    ax.tick_params(axis="x", rotation=45)

    legend_patches = [
        mpatches.Patch(color=C_PASS, label="Correct"),
        mpatches.Patch(color=C_FAIL, label="Incorrect"),
    ]
    ax.legend(handles=legend_patches)
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_llm_calls_distribution.png")


# ── Chart 4: Tool call distribution ──────────────────────────────────────────
def chart_tool_distribution(eval_data: dict, out_dir: Path) -> Path:
    tool_counts: dict[str, int] = defaultdict(int)
    for row in eval_data["per_question"]:
        for ex in row.get("tool_executions", []):
            tool_counts[ex.get("tool", "unknown")] += 1

    if not tool_counts:
        # fall back to aggregate if per_question is empty
        for ex in eval_data.get("aggregate", {}).get("tool_executions", []):
            tool_counts[ex.get("tool", "unknown")] += 1

    tools = sorted(tool_counts, key=tool_counts.get, reverse=True)  # type: ignore[arg-type]
    counts = [tool_counts[t] for t in tools]

    tool_colours = {
        "filter": "#2563EB",
        "group_aggregate": "#7C3AED",
        "rank": "#DB2777",
        "period_compare": "#D97706",
        "trend": "#059669",
        "segment_contribution": "#0891B2",
        "correlation": "#DC2626",
        "detect_anomalies_iqr": "#6D28D9",
    }
    bar_colours = [tool_colours.get(t, C_OTHER) for t in tools]

    fig, ax = plt.subplots(figsize=(10, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    ax.barh(tools, counts, color=bar_colours, alpha=0.9, edgecolor="white")
    for i, (t, c) in enumerate(zip(tools, counts)):
        ax.text(c + 0.3, i, str(c), va="center", fontsize=9)
    ax.set_xlabel("Total calls (across all questions and repeats)")
    ax.set_title("Tool Calls by Type\nTools executed across the benchmark (8 registered tools)")
    ax.invert_yaxis()
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_tool_distribution.png")


# ── Chart 5: Repair attempts vs total time scatter ───────────────────────────
def chart_repair_impact(eval_data: dict, out_dir: Path) -> Path:
    per_q = eval_data["per_question"]
    repairs = [len(r.get("repair_attempts", [])) for r in per_q]
    times = [r.get("total_time_s", 0.0) for r in per_q]
    colours = [C_FAIL if r["accuracy"] is False else C_PASS for r in per_q]
    qids = [r["question_id"] for r in per_q]

    fig, ax = plt.subplots(figsize=(8, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    ax.scatter(repairs, times, c=colours, s=90, alpha=0.85, edgecolors="white", linewidths=0.5)
    for qid, rx, ty in zip(qids, repairs, times):
        ax.annotate(qid, (rx, ty), textcoords="offset points", xytext=(5, 3), fontsize=7)

    ax.set_xlabel("Repair attempts")
    ax.set_ylabel("Total time (seconds)")
    ax.set_title("Repair Attempts vs Total Time per Question\nRed = answered incorrectly")
    legend_patches = [
        mpatches.Patch(color=C_PASS, label="Correct"),
        mpatches.Patch(color=C_FAIL, label="Incorrect"),
    ]
    ax.legend(handles=legend_patches)
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_repair_impact.png")


# ── Chart 6: Ablation comparison (requires --ablation-json) ──────────────────
def chart_ablation_comparison(
    eval_data: dict,
    ablation_data: dict,
    out_dir: Path,
    cat_map: dict[str, str],
) -> Path:
    per_q_full = {r["question_id"]: r for r in eval_data["per_question"]}
    per_q_abla = {r["question_id"]: r for r in ablation_data["per_question"]}

    qids = sorted(per_q_full.keys())
    full_correct = [1 if per_q_full[q]["accuracy"] is True else 0 for q in qids]
    abla_correct = [1 if per_q_abla.get(q, {}).get("accuracy") is True else 0 for q in qids]

    x = np.arange(len(qids))
    w = 0.35

    fig, ax = plt.subplots(figsize=(14, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    ax.bar(
        x - w / 2,
        full_correct,
        w,
        label=f"R1: replanning on ({sum(full_correct)}/20)",
        color=C_AGENT,
        alpha=0.9,
    )
    ax.bar(
        x + w / 2,
        abla_correct,
        w,
        label=f"R2: replanning off ({sum(abla_correct)}/20)",
        color=C_OTHER,
        alpha=0.9,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(qids, rotation=45, fontsize=8)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Incorrect", "Correct"])
    ax.set_title(
        "Replanning on versus off, per question (same code, model and settings)\n"
        "One run per question"
    )
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, frameon=False)
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_ablation_comparison.png")


# ── Chart 7: Model comparison bar chart ──────────────────────────────────────
def chart_model_comparison(runs: list[tuple[str, dict]], out_dir: Path) -> Path:
    """Questions passed out of all questions, one run per question, for each (label, eval) pair."""
    models = [label for label, _ in runs]
    scores = [sum(1 for r in data["per_question"] if r["accuracy"] is True) for _, data in runs]
    totals = [len(data["per_question"]) for _, data in runs]
    colours = [C_AGENT] + [C_OTHER] * (len(runs) - 1)

    fig, ax = plt.subplots(figsize=(8, 5))
    plt.style.use("seaborn-v0_8-whitegrid")
    bars = ax.bar(models, scores, color=colours, alpha=0.9, edgecolor="white", width=0.55)
    for bar, score, total in zip(bars, scores, totals):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.2,
            f"{score}/{total}",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )
    ax.set_ylabel("Questions passed")
    ax.set_ylim(0, max(totals) + 2)
    ax.set_title(
        "Four local models, one run per question, replanning on\n"
        "The 7B model does not fit in 4 GB, so timings are not comparable"
    )
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_model_comparison.png")


# ── Summary CSV ───────────────────────────────────────────────────────────────
def write_summary_csv(eval_data: dict, out_dir: Path, cat_map: dict[str, str]) -> Path:
    import csv

    rows = []
    for r in sorted(eval_data["per_question"], key=lambda x: x["question_id"]):
        rows.append(
            {
                "question_id": r["question_id"],
                "category": cat_map.get(r["question_id"], "unknown"),
                "status": r.get("status", ""),
                "accuracy": r.get("accuracy"),
                "llm_calls": r.get("llm_call_count", 0),
                "total_time_s": round(r.get("total_time_s", 0.0), 2),
                "repair_count": len(r.get("repair_attempts", [])),
                "outcome": r.get("outcome", ""),
            }
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "summary_table.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  saved {p}")
    return p


# ── main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    ROOT = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-json",
        type=Path,
        default=ROOT / "evaluation/results/post-freeze-fixes-frozen-real-20261120/agent_eval.json",
        help="agent_eval.json of the main run (replanning on)",
    )
    parser.add_argument(
        "--questions-json",
        type=Path,
        default=ROOT / "evaluation/benchmark/questions.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "scripts/charts",
        help="Output directory for PNG files",
    )
    parser.add_argument(
        "--ablation-json",
        type=Path,
        default=ROOT / "evaluation/results/post-freeze-fixes-no-replan-20261120/agent_eval.json",
        help="agent_eval.json of the same run with replanning off",
    )
    parser.add_argument(
        "--spike-3b",
        type=Path,
        default=ROOT / "evaluation/results/spike-fixed-qwen25-3b-20261120/agent_eval.json",
        help="agent_eval.json from the qwen2.5:3b-instruct run",
    )
    parser.add_argument(
        "--spike-7b",
        type=Path,
        default=ROOT / "evaluation/results/spike-fixed-qwen25-7b-20261120/agent_eval.json",
        help="agent_eval.json from the qwen2.5:7b-instruct run",
    )
    parser.add_argument(
        "--spike-llama",
        type=Path,
        default=ROOT / "evaluation/results/spike-fixed-llama32-3b-20261120/agent_eval.json",
        help="agent_eval.json from the llama3.2:3b run",
    )
    args = parser.parse_args()

    print(f"Loading {args.eval_json} ...")
    eval_data = load_eval(args.eval_json)
    cat_map = load_categories(args.questions_json)
    out_dir = args.out

    noreplan_data = (
        load_eval(args.ablation_json)
        if args.ablation_json and args.ablation_json.exists()
        else None
    )

    print("Generating charts ...")
    chart_accuracy_by_category(eval_data, out_dir, cat_map, noreplan_data)
    chart_stage_time_waterfall(eval_data, out_dir)
    chart_llm_calls_distribution(eval_data, out_dir)
    chart_tool_distribution(eval_data, out_dir)
    chart_repair_impact(eval_data, out_dir)

    if noreplan_data is not None:
        chart_ablation_comparison(eval_data, noreplan_data, out_dir, cat_map)
    else:
        print("  (skip) ablation chart: the replanning-off run was not found")

    runs = [("qwen3:4b-instruct", eval_data)]
    for label, path in (
        ("qwen2.5:7b-instruct", args.spike_7b),
        ("llama3.2:3b", args.spike_llama),
        ("qwen2.5:3b-instruct", args.spike_3b),
    ):
        if path and path.exists():
            runs.append((label, load_eval(path)))
    chart_model_comparison(runs, out_dir)

    write_summary_csv(eval_data, out_dir, cat_map)
    print(f"\nDone. All artifacts in {out_dir}/")


if __name__ == "__main__":
    main()
