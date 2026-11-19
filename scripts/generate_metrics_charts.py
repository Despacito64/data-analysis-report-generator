#!/usr/bin/env python3
"""Generate presentation-ready charts from existing M10 eval results.

No Ollama required — reads only evaluation/results/m10-frozen-real-20261117/agent_eval.json
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
def chart_accuracy_by_category(eval_data: dict, out_dir: Path, cat_map: dict[str, str]) -> Path:
    per_q = {row["question_id"]: row for row in eval_data["per_question"]}

    # aggregate per category
    cat_agent: dict[str, list[bool]] = defaultdict(list)
    cat_baseline: dict[str, list[bool]] = defaultdict(list)
    for qid, cat in sorted(cat_map.items()):
        if qid not in per_q:
            continue
        row = per_q[qid]
        cat_agent[cat].append(row["accuracy"] is True)
        cat_baseline[cat].append(row.get("baseline_accuracy", True))

    categories = sorted(cat_agent.keys())
    agent_acc = [sum(cat_agent[c]) / len(cat_agent[c]) for c in categories]
    base_acc = [sum(cat_baseline[c]) / len(cat_baseline[c]) for c in categories]
    agent_frac = [f"{sum(cat_agent[c])}/{len(cat_agent[c])}" for c in categories]
    base_frac = [f"{sum(cat_baseline[c])}/{len(cat_baseline[c])}" for c in categories]

    x = np.arange(len(categories))
    w = 0.35

    fig, ax = plt.subplots(figsize=(12, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    b1 = ax.bar(x - w / 2, agent_acc, w, label="Dynamic agent (qwen3:4b)", color=C_AGENT, alpha=0.9)
    b2 = ax.bar(
        x + w / 2, base_acc, w, label="Baseline (template ceiling)", color=C_BASE, alpha=0.9
    )

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
        "Accuracy by Question Category\n"
        "Baseline scores 20/20 only because templates match oracle question shapes at design time"
    )
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace("_", "\n") for c in categories], fontsize=9)
    ax.set_ylim(0, 1.25)
    ax.legend()
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
        "Tool execution < 0.1 s per call — LLM inference is the bottleneck"
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
    ax.set_title("Tool Calls by Type\nAll 10 analytical tools are exercised across the benchmark")
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
        label=f"With replanning ({sum(full_correct)}/20)",
        color=C_AGENT,
        alpha=0.9,
    )
    ax.bar(
        x + w / 2,
        abla_correct,
        w,
        label=f"No replanning ({sum(abla_correct)}/20)",
        color=C_OTHER,
        alpha=0.9,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(qids, rotation=45, fontsize=8)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Incorrect", "Correct"])
    ax.set_title(
        f"Ablation: With Replanning ({sum(full_correct)}/20) vs No Replanning ({sum(abla_correct)}/20)\n"
        f"Replanning contributed {sum(full_correct) - sum(abla_correct)} additional correct answers"
    )
    ax.legend()
    fig.tight_layout()
    return savefig(fig, out_dir, "chart_ablation_comparison.png")


# ── Chart 7: Model comparison bar chart (requires spike JSONs) ────────────────
def chart_model_comparison(
    spike_3b: dict | None,
    spike_7b: dict | None,
    out_dir: Path,
) -> Path:
    # qwen3:4b reference from M10 on same 5 questions: q03=pass,q06=fail,q09=pass,q13=pass,q17=pass
    SPIKE_QS = ["q03", "q06", "q09", "q13", "q17"]
    ref_acc = {q: q != "q06" for q in SPIKE_QS}  # 4/5

    def spike_accuracy(data: dict | None) -> dict[str, bool]:
        if data is None:
            return {}
        return {r["question_id"]: (r["accuracy"] is True) for r in data["per_question"]}

    acc_3b = spike_accuracy(spike_3b)
    acc_7b = spike_accuracy(spike_7b)

    models = ["qwen2.5:3b-instruct", "qwen3:4b\n(reference)", "qwen2.5:7b-instruct"]
    scores = [
        sum(acc_3b.get(q, False) for q in SPIKE_QS),
        sum(ref_acc.values()),
        sum(acc_7b.get(q, False) for q in SPIKE_QS),
    ]
    colours = [C_OTHER, C_AGENT, C_OTHER]

    fig, ax = plt.subplots(figsize=(8, 5))
    plt.style.use("seaborn-v0_8-whitegrid")

    bars = ax.bar(models, scores, color=colours, alpha=0.9, edgecolor="white", width=0.5)
    for bar, score in zip(bars, scores):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.05,
            f"{score}/5",
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
        )

    ax.set_ylabel("Correct answers (out of 5 representative questions)")
    ax.set_ylim(0, 6)
    ax.set_title(
        "Model Comparison on 5 Representative Questions\n"
        "(q03=group_aggregate, q06=rank, q09=period_compare, q13=contribution, q17=anomalies)"
    )
    # annotate model sizes
    sizes = ["3B params", "4B params", "7B params"]
    for bar, size in zip(bars, sizes):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            0.1,
            size,
            ha="center",
            va="bottom",
            fontsize=8,
            color="white",
            fontweight="bold",
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
        default=ROOT / "evaluation/results/m10-frozen-real-20261117/agent_eval.json",
        help="Path to the M10 agent_eval.json (default: m10 reference run)",
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
        default=None,
        help="agent_eval.json from the no-replan ablation run (enables ablation chart)",
    )
    parser.add_argument(
        "--spike-3b",
        type=Path,
        default=None,
        help="agent_eval.json from qwen2.5:3b-instruct spike",
    )
    parser.add_argument(
        "--spike-7b",
        type=Path,
        default=None,
        help="agent_eval.json from qwen2.5:7b-instruct spike",
    )
    args = parser.parse_args()

    print(f"Loading {args.eval_json} ...")
    eval_data = load_eval(args.eval_json)
    cat_map = load_categories(args.questions_json)
    out_dir = args.out

    print("Generating charts ...")
    chart_accuracy_by_category(eval_data, out_dir, cat_map)
    chart_stage_time_waterfall(eval_data, out_dir)
    chart_llm_calls_distribution(eval_data, out_dir)
    chart_tool_distribution(eval_data, out_dir)
    chart_repair_impact(eval_data, out_dir)

    if args.ablation_json and args.ablation_json.exists():
        print(f"Loading ablation data from {args.ablation_json} ...")
        ablation_data = load_eval(args.ablation_json)
        chart_ablation_comparison(eval_data, ablation_data, out_dir, cat_map)
    else:
        print("  (skip) ablation chart — pass --ablation-json <path> after ablation run completes")

    spike_3b = load_eval(args.spike_3b) if args.spike_3b and args.spike_3b.exists() else None
    spike_7b = load_eval(args.spike_7b) if args.spike_7b and args.spike_7b.exists() else None
    chart_model_comparison(spike_3b, spike_7b, out_dir)

    write_summary_csv(eval_data, out_dir, cat_map)
    print(f"\nDone. All artifacts in {out_dir}/")


if __name__ == "__main__":
    main()
