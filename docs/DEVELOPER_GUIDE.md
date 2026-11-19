# 🎓 Developer Guide & Viva Defense Manual
## Evidence-Grounded Dynamic Planning Data Analysis Agent (`da-agent`)

> **Purpose**: This guide provides an exhaustive technical reference for developers, viva examiners, and technical interviewers. It explains every design choice, architectural boundary, mathematical invariant, and empirical result in the repository, with precise code citations.

---

## 📑 Table of Contents
1. [Executive Summary & Core Thesis](#1-executive-summary--core-thesis)
2. [Comparison with Base Paper: Data Interpreter](#2-comparison-with-base-paper-data-interpreter)
3. [End-to-End System Architecture](#3-end-to-end-system-architecture)
4. [LangGraph State Machine & Dynamic Planning Loop](#4-langgraph-state-machine--dynamic-planning-loop)
5. [The Deterministic Tool Registry (8 Tools)](#5-the-deterministic-tool-registry-8-tools)
6. [Five Layers of Verification & Claim Grounding](#6-five-layers-of-verification--claim-grounding)
7. [Contracts, Provenance, & Evidence Records](#7-contracts-provenance--evidence-records)
8. [Conversational Engine & Dialogue Memory](#8-conversational-engine--dialogue-memory)
9. [Evaluation Methodology & Benchmark Analysis](#9-evaluation-methodology--benchmark-analysis)
10. [Ablation Study & Model Comparison Findings](#10-ablation-study--model-comparison-findings)
11. [Top 20 Viva & Technical Interview Questions (With Bulletproof Answers)](#11-top-20-viva--technical-interview-questions)
12. [Live Demo Walkthrough & Command Cheat-Sheet](#12-live-demo-walkthrough--command-cheat-sheet)

---

## 1. Executive Summary & Core Thesis

### 1.1 The 30-Second Elevator Pitch
Most LLM data science agents (e.g., Code Interpreter, Data Interpreter) generate raw Python/SQL and run it in an unconstrained sandbox. While flexible, this introduces **severe security risks (arbitrary code execution)**, **hallucinated calculations**, and **zero provenance**. 

Our system demonstrates an alternative paradigm: **Dynamic analytical task planning with deterministic tool execution and cryptographic evidence grounding**. The LLM decides *what* to compute (planning a typed DAG of analytical tasks); pre-tested, deterministic Python/Pandas functions decide *how* numbers are computed; and strict validators ensure that **not a single number reaches the user without an immutable cryptographic link to runtime evidence**.

### 1.2 Core Research Question
> *Can an autonomous LLM agent dynamically formulate, execute, and revise multi-step analytical investigations on tabular data with zero code-execution safety risks and zero numerical hallucinations?*

**Answer (as far as one dataset and 20 questions can show):** the agent reaches **13/20 (65%)** on a 20-question frozen benchmark scored by a separately computed (pandas/numpy) oracle, using a small local model (`qwen3:4b` on a GTX 1650). Every number in a report passes through claim validation against a recorded evidence record. In all 7 failures the tools ran correctly; the fault was in the plan the model wrote or in a tool-versus-oracle label mismatch (see 9.4). The effect of replanning has not been cleanly measured (see 10.1).

---

## 2. Comparison with Base Paper: Data Interpreter

Our assigned base paper is:
> **"Data Interpreter: An LLM Agent For Data Science"** (Cheng et al., 2024 / MetaGPT team)

### 2.1 Direct Architectural Comparison

| Dimension | *Data Interpreter* (Cheng et al., 2024) | Our System (`da-agent`) | Engineering / Research Rationale |
| :--- | :--- | :--- | :--- |
| **Execution Paradigm** | Free-form Python code generation & execution in REPL | Allowlisted, pre-compiled deterministic analytical tools | Prevents arbitrary code execution, syntax crashes, and runaway scripts (`docs/DECISIONS.md:D-002`). |
| **Numerical Grounding** | Text stdout parsed from Python `print()` statements | Cryptographic `EvidenceRecord` with SHA-256 arguments hash | Numbers are first-class data contracts, not scraped strings (`docs/CONTRACTS.md:80`). |
| **Claim Verification** | None (assumes code output is truthful if it doesn't crash) | 5-Layer claim validation (`rtol: 0.001`, `atol: 0.01`) | Model cannot claim a trend or number that contradicts evidence (`src/da_agent/validation/claims.py`). |
| **Control Flow** | Dynamic DAG generated via hierarchical LLM prompts | **Fixed control graph** (LangGraph) + **dynamic task graph** in state | Predictable lifecycle with bounded execution budgets (`docs/DECISIONS.md:D-001`). |
| **Model Requirements** | Frontier cloud LLMs (GPT-4 / Claude 3.5 Sonnet) | Small local open-weights LLMs (`qwen3:4b` via Ollama) | Runs entirely on consumer GPUs (GTX 1650), offline, privacy-preserving (`docs/DECISIONS.md:D-006`). |
| **Evaluation Oracle** | Self-reported execution success or public benchmarks | Expected answers computed by a standalone pandas/numpy script that imports no agent code | Prevents data leakage and circular verification bugs (`evaluation/oracle.py`). |

### 2.2 How to Defend This Pivot in Viva
* **Question**: *"Why did you not implement Data Interpreter's full Python code generation?"*
* **Defense**: 
  > *"Data Interpreter proved that dynamic task graphs outperform static chains. However, executing unverified code in real-world business pipelines violates enterprise compliance and safety constraints (CWE-94: Code Injection). We deliberately isolated the core scientific contribution of Data Interpreter—**dynamic, result-driven DAG planning**—and applied it to a safety-critical setting where all operations are allowlisted, typed, deterministic, and auditable."*

---

## 3. End-to-End System Architecture

The codebase enforces strict unidirectional dependency layers (`docs/ARCHITECTURE.md:1`). A lower layer **never** imports from a higher layer.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Presentation & UI Layer                         │
│       React 19 + Vite SPA (Port 5173)  /  Streamlit App (app.py)       │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │ HTTP / WebSocket / Typed JSON
┌───────────────────────────────────┴────────────────────────────────────┐
│                        API & Service Layer                             │
│         FastAPI Router (api_main.py, src/da_agent/api/)                │
└───────────────────────────────────▲────────────────────────────────────┘
                                    │
┌───────────────────────────────────┴────────────────────────────────────┐
│                  LangGraph Dynamic Planning Engine                     │
│   Plan (LLM) ──► Validate/Repair ──► Execute ──► Inspect ──► Replan   │
└───────────────────▲───────────────────────────────▲────────────────────┘
                    │                               │
┌───────────────────┴──────────┐   ┌────────────────┴────────────────────┐
│       Data Layer (M1)        │   │     Deterministic Tool Registry     │
│ Ingestion, Cleaning, Schema, │   │ 10 Pandas/Stats Tools, Invariants,  │
│ Profiling, SHA-256 Hashing   │   │ Arguments & Schema Validators       │
└──────────────────────────────┘   └────────────────▲────────────────────┘
                                                    │
┌───────────────────────────────────────────────────┴────────────────────┐
│                     Verification & Reporting Layer                     │
│   Claim Matcher, Tolerance Verifier, Presenters, HTML/JSON Renderer    │
└────────────────────────────────────────────────────────────────────────┘
```

### Layer Rules (import rules are tested in `tests/test_import_rules.py`):
1. Lower layers never import higher layers (see `docs/ARCHITECTURE.md`); `tools/` never imports `agent/` or `reports/`.
2. `evaluation/oracle.py` loads expected answers that `evaluation/benchmark/build_oracle.py` computed with pandas and numpy, and neither must import `da_agent.tools`, `agent`, `validation` or `reports` (`test_oracle_independence`).
3. Modules cross boundaries **only via Pydantic v2 models** (`docs/CONTRACTS.md:1`). Untyped dicts across boundaries are rejected.

---

## 4. LangGraph State Machine & Dynamic Planning Loop

### 4.1 Fixed Control Graph vs. Dynamic Task Graph (Crucial Viva Point!)
* **Fixed Control Graph**: The LangGraph state machine structure is static and deterministic. The nodes and transitions are compiled at startup:
  `plan` ➔ `validate_repair` ➔ `execute` ➔ `inspect` ➔ `replan` (loop) or `finalize` (exit).
* **Dynamic Task Graph**: What changes dynamically is the **`Plan` object stored inside `AgentState`**. The analytical tasks (`Task`), their dependencies (`depends_on`), arguments, and execution sequence are formulated and revised at runtime based on intermediate evidence.

```mermaid
stateDiagram-v2
    [*] --> plan: Receive User Question & Profile
    plan --> validate_repair: Generate Typed Plan DAG
    
    validate_repair --> execute: Plan valid
    validate_repair --> finalize: No valid plan after repair attempts
    
    execute --> inspect: Deterministic tools run and emit evidence
    
    inspect --> execute: Retry a failed task
    inspect --> replan: Failure to repair, or a complete result to follow up
    inspect --> finalize: Analysis complete or budget reached
    
    replan --> execute: Revised pending tasks
    replan --> finalize: Nothing to add or budget reached
    
    finalize --> [*]: Claim Verification & Report Synthesis
```

### 4.2 State Machine Node Responsibilities (`src/da_agent/agent/graph.py`):
1. **`plan`**: Calls `LLMClient` with system prompt, tool definitions (`ToolSpec`), dataset profile, and conversation thread. Emits a structured `Plan` containing typed `Task`s with dependency IDs.
2. **`validate_repair`**: Validates the plan without executing it (`src/da_agent/validation/plan_check.py`):
   - Are tool names in the allowlist?
   - Do referenced columns exist in the dataset profile?
   - Is the dependency graph an acyclic DAG?
   - If invalid, the planner re-prompts the model with the validation errors inside the same call (`for attempt in range(max_repairs + 1)`, `planner.py:397`). This repair cap is separate from `max_replans`, which limits result-driven replanning.
3. **`execute`**: Iterates through tasks whose dependencies are satisfied (`status == "ready"`). Calls the deterministic tool via `DEFAULT_REGISTRY.execute()`. Wraps results in an `EvidenceRecord`.
4. **`inspect`**: Inspects tool results and classifies failures (`assess_recovery` in `graph.py:119`):
   - If all tasks succeed and goal is met: routes to `finalize`.
   - If a recoverable failure occurs (e.g., filter returned 0 rows): routes to `replan`.
   - Checks termination rules: halts on `no_progress`, cycle detection, or budget exhaustion.
5. **`replan`**: Prompts the LLM with the surviving evidence records and the failure context to emit a `PlanRevision` (add/replace/cancel pending tasks).
6. **`finalize`**: Compiles final `AgentResult`, triggers claim validation, runs `narrator.py` for grounded prose, and renders reports.

### 4.3 Guaranteed Bounded Execution (Why it cannot infinite-loop):
* `budgets.max_replans`: Default 3.
* `budgets.max_identical_retries`: Default 2.
* `budgets.max_llm_calls`: Default 15.
* **Stall / Cycle Detection**: `detect_no_progress()` fingerprints `(tool, args, depends_on)` history. If identical arguments or zero new evidence is detected across iterations, the run terminates immediately as `partial` (`src/da_agent/validation/recovery.py`).

---

## 5. The Deterministic Tool Registry (8 Tools)

The registry (`src/da_agent/tools/registry.py`, `DEFAULT_REGISTRY`) exposes **8 tools** to the planner. Computations live in `tools/pandas_tools.py` and `tools/statistics.py`. Plotly chart builders in `tools/charts.py` are not planner tools (`registry.py:5`).

| # | Tool Name | Analytical Function | Mathematical Invariants Enforced |
|---|---|---|---|
| 1 | `filter` | Slices DataFrame based on typed operators (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `contains`). | Output row count $\le$ input row count; output rows strictly meet predicate. |
| 2 | `group_aggregate` | Multi-column grouping with aggregations (`sum`, `mean`, `count`, `min`, `max`). | Sum of group counts equals total non-null input rows. |
| 3 | `rank` | Ranks **individual rows** by a metric column (top-N or bottom-N). It has **no aggregation argument** (`RankArgs`: `entity_column`, `metric_column`, `ascending`, `top_n`, `tie_decimals`), so ranking per-entity totals needs `group_aggregate` first. | Deterministic tie-breaking by entity label; ties flagged. |
| 4 | `period_compare` | Compares aggregate metric across two explicit date ranges. | Absolute change: $\Delta = V_{comp} - V_{base}$; Relative growth: $\frac{\Delta}{V_{base}}$ (undefined if $V_{base} = 0$). |
| 5 | `trend` | Computes time-grain metrics (daily, monthly, quarterly) and linear trend. | Slope via least-squares: $m = \frac{\sum (t - \bar{t})(y - \bar{y})}{\sum (t - \bar{t})^2}$; direction: `increasing`, `decreasing`, `flat`. |
| 6 | `segment_contribution`| Computes percentage contribution of each segment to the whole. | Shares sum to $1.0 \pm 0.001$; individual shares bounded in $[0, 1]$. |
| 7 | `correlation` | Computes Pearson correlation coefficient between two numeric columns. | Coefficient $r \in [-1.0, 1.0]$; NaN if variance is zero. |
| 8 | `detect_anomalies_iqr` | Detects outliers via Tukey's fence ($1.5 \times \text{IQR}$). | $\text{IQR} = Q_3 - Q_1$; Lower fence: $Q_1 - 1.5\text{IQR}$; Upper fence: $Q_3 + 1.5\text{IQR}$. |

### Edge Case Handling (`docs/MODULES.md:M2`):
The required behaviours are listed in `docs/MODULES.md` (M2 table). Implementation facts I have verified:
* **Ties in ranking**: sorted by rounded metric, then entity label; each `RankRow` carries `is_tied`.
* **Undefined results** (for example a zero denominator in growth): results carry an `undefined_reason` field instead of a silent zero (`tools/executor.py`, `tools/charts.py:135`). I have not verified the exact reason strings, so check `tools/models.py` before quoting one.
* **Contribution shares / all-missing sums**: required by the M2 table; numerical invariants are checked in `validation/results.py` (`TOLERANCE = 1e-9`). Read the test files before quoting a specific tolerance.

---

## 6. Five Layers of Verification & Claim Grounding

The system implements defense-in-depth across 5 isolated verification layers (`docs/DECISIONS.md:D-003`):

```
Layer 1: Input Validation ──────► Extension allowlist, size limits, CSV/XLSX corrupt check
Layer 2: Plan Validation ───────► Tool allowlist, schema check, column existence, DAG acyclicity
Layer 3: Argument Validation ───► Column semantic types, date ranges within dataset coverage
Layer 4: Result Invariants ─────► Mathematical reconciliation (shares sum to 1, row counts)
Layer 5: Claim Verification ────► Extraction of claims, tolerance match against EvidenceRecords
```

### 6.1 Claim Verification Algorithm (`src/da_agent/validation/claims.py`)
1. **Extraction**: All numbers appearing in the synthesized text or structured findings are extracted via regular expressions.
2. **Matching**: Each reported number is paired with its declared `evidence_id`.
3. **Tolerance Check**: The claim $V_{claim}$ is verified against the recorded tool output $V_{evidence}$:
   $$|V_{claim} - V_{evidence}| \le \text{atol} + \text{rtol} \times |V_{evidence}|$$
   Defaults: $\text{rtol} = 0.001$ (0.1%), $\text{atol} = 0.01$.
4. **Enforcement Policy (`drop_policy: "drop_finding"`)**:
   - If a number matches: The claim is verified and rendered.
   - If a number fails or has no evidence: **It is stripped from the output**. The ungrounded statement is moved to `dropped_claims` in the audit trace, and the run status notes the discrepancy.

### 6.2 Grounded Narrative Synthesis (`src/da_agent/agent/narrator.py`)
To produce fluent, executive-level summaries without hallucination, a second LLM pass is triggered with a restricted prompt containing:
- Only validated claim strings (e.g., `"total sales in West: 725457.82"`).
- User question and conversation history.
- **Strict instruction**: The model cannot introduce any new numerical entities. The output is run through `validate_narrative_grounding()`. If any rogue number appears, the prose is discarded and the system falls back to the deterministic template.

---

## 7. Contracts, Provenance, & Evidence Records

Data crosses module boundaries **exclusively as Pydantic v2 models** (`docs/CONTRACTS.md`, version `0.2.0`).

### 7.1 Anatomy of an `EvidenceRecord`
Every successful tool execution produces an immutable evidence artifact:
```python
class EvidenceRecord(BaseModel):
    evidence_id: str  # e.g. "ev_f83a1b09"
    task_id: str  # e.g. "t1"
    tool: str  # e.g. "group_aggregate"
    args_hash: str  # SHA-256 of canonical JSON arguments
    dataset_hash: str  # SHA-256 of raw dataset (Sample Superstore)
    input_row_count: int  # e.g. 9994
    result_summary: dict[str, Any]  # Structured output payload
    result_schema_version: str  # "0.2.0"
    invariants_checked: list[str]  # e.g. ["non_negative_counts", "group_reconciliation"]
    valid: bool  # True
    invalidated_by: str | None  # Evidence ID that caused cascade invalidation, if any
    created_at: datetime
```

### 7.2 Evidence Invalidation Cascade
If an upstream task $T_1$ produces evidence $E_1$, and downstream task $T_2$ uses $E_1$ as input, what happens if an invariant check on $T_2$ fails?
* `invalidate_evidence(evidence_id="E1")` cascades through the DAG.
* Any dependent evidence records are marked `valid = False, invalidated_by = "E1"`.
* Downstream claims referencing invalidated evidence are automatically purged from the final report (`src/da_agent/validation/invalidation.py`).

---

## 8. Conversational Engine & Dialogue Memory

### 8.1 Symbolic Dialogue State vs. Stale Evidence Re-seeding (`D-046`, `D-047`)
In conversational analytics (e.g., *"Filter to Furniture"* followed by *"Now show me West region"*), many LLM architectures naively append prior tool outputs into the context window. This causes:
1. **Context explosion** (token exhaustion).
2. **Stale data hallucination** (model cites prior numbers instead of recomputing).

**Our Architecture**:
* Dialogue memory is strictly **symbolic** (`DialogueState`, `DialogueTurn` in `src/da_agent/contracts/models.py:38`).
* Memory records: Question text, resolved intent, metric, period, grouping, and active filter conditions.
* Memory **never** stores: Evidence IDs, raw tool outputs, or numeric results.
* **Every follow-up turn re-executes calculations over the dataset**: The planner generates a new plan incorporating active filters, executing deterministic tools afresh.

---

## 9. Evaluation Methodology & Benchmark Analysis

### 9.1 Independent Oracle Protocol (`docs/DECISIONS.md:D-005`, `evaluation/oracle.py`)
To prevent circular evaluation bugs, the oracle:
* Computes expected answers directly from the raw `Sample-Superstore.csv` with a standalone pandas/numpy script (`evaluation/benchmark/build_oracle.py`). The design documents say DuckDB SQL or plain Python; the implemented oracle is plain pandas/numpy, and no code in the repository imports DuckDB.
* **Is forbidden from importing any agent, tool, validation or report modules**. The automated test `test_oracle_independence` in `tests/test_import_rules.py` enforces it.
* Oracle expected answers are **never** present in agent prompts, system context, or repair instructions.

### 9.2 The Benchmark Question Suite (`evaluation/benchmark/questions.json`)
20 frozen questions covering all analytical categories:
* Single-step filter (2 Qs)
* Group & aggregate (3 Qs)
* Rank (3 Qs)
* Period compare (2 Qs)
* Trend analysis (2 Qs)
* Segment contribution (2 Qs)
* Correlation (2 Qs)
* Outlier/Anomaly detection (2 Qs)
* Multi-step diagnostic (2 Qs)

### 9.3 Main Evaluation Results (M10 Reference Run: `m10-frozen-real-20261117`)
* **Hardware**: Single consumer GPU (NVIDIA GTX 1650, 4GB VRAM).
* **Model**: `qwen3:4b` via local Ollama (zero cloud API calls).
* **Protocol**: 20 evaluation questions, 3 repeats each, 60s per-call timeout.

| Evaluation Metric | Fixed Baseline | Dynamic Agent (`da-agent`) | Analysis / Notes |
|---|:---:|:---:|---|
| **Accuracy** | 20 / 20 (100%) | **13 / 20 (65%)** | 0 timeouts; all completed within budget. |
| **Baseline Reality** | 20 / 20 | — | **Ceiling, not a competitor**: `BASELINE_TASKS` is keyed by question id (`baseline.py:22`), never reads the question text, and assembles several answers (q01, q06-q08, q20) with hand-written per-question code (`baseline.py:186-225`). It cannot answer a question outside the 20. |
| **Tool Execution Success** | 100% | **100%** | In every single failed question, the tools executed with status `ok`. |
| **Recovery suite** | — | **12 / 12** | Mock-only controlled-failure scenarios (no real LLM, no benchmark questions). |
| **Total Wall-Clock Time** | — | 2,858 s (~47.6 min) | Average ~143s per question across 3 repeats. |
| **LLM Call Volume** | 0 | 168 calls | All retries cleanly bounded by budget caps. |

### 9.4 Root-Cause Failure Analysis (The 7 Failures):
Diagnosed from the saved attempt files and `runs/<id>/trace.jsonl` (all tool statuses were `ok`):

* **`q01` (filter)**: the plan was a single `filter` task. `filter` returns matched rows and a row count, not a sum, so the scorer found no answer of the expected shape (`no_score_shaped_answer`). The question needed `filter` then `group_aggregate`.
* **`q06`, `q07`, `q08`, `q20` (rank)**: the planner wrote a plausible single `rank` task (for q06: `entity_column=Sub-Category`, `metric_column=Sales`, `top_n=5`). Because `rank` has no aggregation argument, it ranked individual rows, so the result was top single transactions (for example Machines at 22,638.48, and "Copiers" four times) instead of per-entity totals. The question needs `group_aggregate` first. The baseline avoids this by hard-coding that two-step plan.
* **`q11` (trend)**: the plan had no 2017 restriction (no `filter` and no period argument), so the trend covered 48 months from 2014 to 2017. The expected answer covers 2017 only.
* **`q12` (trend)**: all 16 quarterly points and the slope (1194.744...) match the oracle. Only the direction label differs: the tool reports `volatile`, the oracle `increasing`. This is a disagreement between the tool's direction rule and the oracle's, not an LLM error.
* **Replanning noise** (q06, q07, q11): the result-inspection LLM call returned invalid plans (unknown tool `text`; `trend` without required arguments), which validation rejected.

**What this shows**: the deterministic tools executed correctly in every failure. q01 and q11 are incomplete plans; q06, q07, q08 and q20 combine a single-step plan with a `rank` tool that does not aggregate; q12 is a label mismatch. I had earlier attributed these to LLM answer extraction. That was wrong: `extract_score_answer` (`run_agent_eval.py:322`) reads tool evidence deterministically.

---

## 10. Ablation Study & Model Comparison Findings

Two exploratory runs were made beyond the reference run (`docs/EXPERIMENTS_SUMMARY.md`, `D-050`). Neither is a controlled experiment, and the viva answer should say so.

### 10.1 Reduced-budget run with the plan-repair cap set to 0
* **What it was**: all 20 questions, 1 repeat, with `max_repair_attempts=0`, `max_llm_calls_per_question=4` and `per_question_budget_s=180`. The reference used 2, 8, 300 and 3 repeats.
* **What it was not**: a no-replanning ablation. `max_repair_attempts` only limits re-prompting after an invalid plan (`planner.py:397`). Result-driven replanning is limited by `max_replans` (3), which was unchanged and still ran.
* **Result**: 12/20 against 13/20. The only question that differs is q02. The reference passed it in 3 of 3 repeats. The cause is `augment_chat_plan` (D-048), which appends a `group_aggregate` to filter-only plans, so the scored answer becomes a region-sales mapping instead of the count 599. It is not caused by replanning.
* **How to answer in the viva**: "A clean ablation would set `max_replans=0` and change nothing else, with 3 repeats. We ran a reduced-budget variant that changed four settings, so we don't claim an effect for replanning."

### 10.2 Partial model spike
Five questions (`q03`, `q06`, `q09`, `q13`, `q17`), 1 repeat, 180 s budget. Both new runs stopped after these five. The qwen3:4b figure comes from the 3-repeat reference run, so the columns are not like-for-like.

| Model | Passed (of the 5) | Avg time/q | What was recorded |
|---|:---:|:---:|---|
| `qwen2.5:3b-instruct` | 0 | ~85 s | q03, q17 `no_score_shaped_answer`; q09, q13 `repair_cap`; q06 timeout |
| `qwen3:4b` (reference run) | 4 | ~165 s | only q06 failed |
| `qwen2.5:7b-instruct` | 2 | ~90 s | q03, q13 passed; q09, q17 `no_score_shaped_answer`; q06 timeout |

**Takeaway you can defend**: with five questions and one repeat, no ranking of the models is justified. The failure types are the useful part (plans failing validation for the 3B model, answers the scorer could not shape for the 7B model). Why qwen3:4b did better was not investigated, so don't claim a reason.

---

## 11. Top 20 Viva & Technical Interview Questions

Here are the most critical questions a professor or interviewer will ask, with bulletproof answers.

---

### Category 1: Conceptual & Architectural Choices

#### Q1: "Why not simply let the LLM generate Python code like ChatGPT Code Interpreter or Data Interpreter?"
**Answer**:
> *"Allowing LLMs to write and execute arbitrary Python code has two fatal flaws in production data systems:
> 1. **Security & Sandboxing (CWE-94)**: Running LLM-generated code requires heavy containerized sandboxes, yet remains vulnerable to resource exhaustion, filesystem escapes, and malicious libraries.
> 2. **Silent Hallucinations & Non-Determinism**: LLMs frequently introduce subtle statistical bugs in code (e.g., misusing `.dropna()`, dividing by zero, or fabricating synthetic data). 
> Our approach delegates *intent and planning* to the LLM, but delegates *all computation* to allowlisted, unit-tested, deterministic Pandas tools. Every computation is reproducible and mathematically verifiable."*

#### Q2: "Isn't a fixed set of 8 tools too restrictive compared to arbitrary code?"
**Answer**:
> *"Yes, it is restrictive, on purpose. The 8 registered tools (filter, group_aggregate, rank, period_compare, trend, segment_contribution, correlation, detect_anomalies_iqr) cover the routine relational and statistical questions in our benchmark, and the planner can chain them as a DAG (for example filter, then group_aggregate). The cost shows up in our results: `rank` does not aggregate, so a question like 'top 5 sub-categories by total sales' needs group_aggregate first, and our 4B model did not plan that. A new analysis is added as a registered tool with tests and Pydantic schemas, which keeps every number auditable. We did not measure how much of real-world analysis these 8 tools cover."*

#### Q3: "What exactly makes your planning 'dynamic'? Is LangGraph alone dynamic planning?"
**Answer**:
> *"No. Using LangGraph alone is **not** dynamic planning—LangGraph merely provides the state-machine runtime. 
> As defined in `docs/PROJECT_SCOPE.md:66` and `docs/DECISIONS.md:D-001`, our control graph is fixed, but the **analytical task graph in state is dynamic**. The agent examines intermediate tool results and failure feedback at runtime, and can add, substitute, cancel, or revise pending tasks in the DAG based on observed data. A static workflow executes a predetermined sequence regardless of data; our dynamic agent replans when it observes anomalies or empty results."*

#### Q4: "How do you prevent the agent from getting stuck in an infinite replanning loop?"
**Answer**:
> *"We implement four strict bounding mechanisms in `src/da_agent/validation/recovery.py` and `graph.py`:
> 1. Hard execution budgets (`max_replans: 3`, `max_llm_calls: 15`).
> 2. Identical retry cap (`max_identical_retries: 2`).
> 3. State fingerprinting: `detect_no_progress()` computes a hash of `(tool, args, depends_on)`. If the agent suggests an identical task or produces no new evidence, execution halts immediately.
> 4. Graceful degradation: The run terminates with an explicit `status: "partial"` or `"failed"`, returning all valid evidence accumulated up to that point without crashing."*

#### Q5: "What is an `EvidenceRecord` and why is it cryptographic?"
**Answer**:
> *"An `EvidenceRecord` (`docs/CONTRACTS.md:80`) is an immutable Pydantic object emitted by the executor after every tool run. It contains:
> - The unique `evidence_id` and `task_id`.
> - The SHA-256 hash of the canonical JSON arguments (`args_hash`).
> - The SHA-256 hash of the raw dataset (`dataset_hash`).
> - The raw input row count and structured output summary.
> - The list of mathematical invariants verified.
> It is cryptographic because it binds the computed numbers to the exact dataset state and tool parameters via SHA-256 hashes, ensuring that numbers cannot be tampered with or attributed to stale data."*

---

### Category 2: Evaluation & Benchmark Defense

#### Q6: "Your dynamic agent scored 13/20, while the baseline scored 20/20. Doesn't that mean your baseline is better?"
**Answer**:
> *"No. The baseline's 20/20 is a ceiling, not a fair competitor (`docs/M10_RESULTS.md`). Its plans are stored in `BASELINE_TASKS`, a dictionary keyed by question id (`baseline.py:22`); it never reads the question text, and several of its answers (q01, q06-q08, q20) are assembled by hand-written per-question code. It cannot answer a question outside those 20.
> The dynamic agent reads the natural-language question and plans from scratch with a 4B local model, so 13/20 is a measurement of planning, while the baseline's 20/20 measures only that the hand-written plans are right. We make no claim about how the baseline would score on new questions; it simply has no way to attempt them."*

#### Q7: "What caused the 7 failed questions in the benchmark? Did the analytical tools fail?"
**Answer**:
> *"No tool crashed: in every failed run the tool status was `ok`. We then read the traces to see why the answers were wrong.
> - q06, q07, q08, q20 (rank): the model planned one `rank` task. Our `rank` tool ranks individual rows and has no aggregation argument, so it returned the top single transactions instead of per-entity totals. The question needs `group_aggregate` first. That is a planning gap combined with a limitation in our tool design.
> - q01: the plan was `filter` only, which gives a row count, not a sum.
> - q11: the plan did not restrict the trend to 2017.
> - q12: numbers and slope match the oracle exactly; only the direction label differs (`volatile` from our tool, `increasing` from the oracle), a disagreement between two definitions.
> So the failures come from incomplete plans, one tool-design limitation and one label mismatch, not from the arithmetic. The obvious next step is a `rank` that can aggregate, or planner guidance to chain group_aggregate then rank."*

#### Q8: "What was the purpose and result of your Ablation Study?"
**Answer**:
> *"We tried a reduced-budget run with the plan-repair cap set to 0 and scored 12/20 against the reference 13/20. I want to be precise about what that is: it changed four settings at once (repair cap, LLM-call cap, per-question time budget and repeats), and it did not turn replanning off, because replanning is limited by `max_replans`, which we did not touch. The single difference was q02, where a replan step added an unnecessary `group_aggregate` task, so it does not show replanning helping. A proper ablation sets `max_replans=0` and changes nothing else, with 3 repeats; that is the first thing we would run next."*

#### Q9: "Why did Qwen3-4B score 4/5 on the spike while Qwen2.5-7B scored only 2/5?"
**Answer**:
> *"Honestly, five questions with one repeat can't rank the models, and the qwen3:4b number comes from the 3-repeat reference run, so I don't claim a reason. What the traces record: the 7B model passed q03 and q13, returned answers the scorer could not shape on q09 and q17, and timed out on q06; the 3B model had plans fail validation on two questions (repair cap). To explain the gap we would run all 20 questions with 3 repeats per model under identical settings and compare plan validity separately from answer correctness."*

#### Q10: "How do you guarantee that your evaluation benchmark did not leak into your agent?"
**Answer**:
> *"We enforce strict architectural and procedural isolation:
> 1. `evaluation/oracle.py` loads answers computed from the raw file by a standalone pandas/numpy script, and must not import the agent, tools, validation or report code. The automated test `test_oracle_independence` in `tests/test_import_rules.py` enforces this.
> 2. The 20 evaluation questions were frozen into `freeze_manifest.json` with cryptographic SHA-256 hashes (`D-044`).
> 3. Expected oracle answers are **never** provided in any prompt, few-shot example, or error recovery message provided to the agent."*

---

### Category 3: Verification, Security, & Implementation

#### Q11: "Explain how your 5-Layer Claim Validation works."
**Answer**:
> *"Claim validation (`src/da_agent/validation/claims.py`) sits between tool execution and report rendering. 
> When the agent generates a finding or narrative, the validator extracts all numerical values and compares them against the linked `EvidenceRecord` using relative and absolute tolerances (`rtol: 0.001`, `atol: 0.01`). 
> If an LLM hallucinates an unsupported number (e.g., claiming profits grew by 25% when evidence shows 18%), the claim is immediately stripped from the final report (`drop_finding` policy) and logged as a validation failure."*

#### Q12: "How does the agent protect against prompt injection from untrusted CSV data?"
**Answer**:
> *"Uploaded CSV/XLSX cell values are treated as **untrusted data, never instructions** (`AGENTS.md`, hard rule 8). 
> 1. Raw cell text is never interpolated into LLM system prompts or instruction blocks. The LLM receives only schema metadata (column names, semantic data types, missing counts).
> 2. Tool arguments are strictly typed with Pydantic models (e.g., filter values must match column types).
> 3. All strings rendered into HTML reports or frontend components are strictly HTML-escaped to prevent Cross-Site Scripting (XSS)."*

#### Q13: "What happens if a column contains numeric postal codes? Does the agent compute average postal code?"
**Answer**:
> *"No. Our data profiler (`src/da_agent/data/profiler.py`) classifies columns into semantic types: `identifier`, `numeric_measure`, `category`, `date`, and `text` (`docs/CONTRACTS.md:21`). 
> Numeric identifiers such as postal codes must be classified `identifier`, never `numeric_measure` (`docs/CONTRACTS.md:21`), and the planner prompt is given each column's semantic type. I have not found code in `validation/args.py` that rejects an aggregation on an identifier column, so I would not claim that it is blocked; I would say the profiler labels it and the planner sees the label."*

#### Q14: "How does multi-turn conversational memory work in your React interface?"
**Answer**:
> *"Instead of passing prior tool evidence into subsequent turns, our conversational engine uses **symbolic dialogue state** (`DialogueTurn` and `ChatThread` in `src/da_agent/core/chat_thread.py`). 
> It preserves user intent and active filter constraints across turns (e.g., 'Region = West'), but forces the agent to re-execute tool calculations afresh on the underlying dataset. This prevents stale context hallucinations while enabling natural conversational drill-downs."*

#### Q15: "Is your oracle really independent of your tools?"
**Answer**:
> *"Independent in code, not in libraries. The expected answers come from a standalone script (`evaluation/benchmark/build_oracle.py`) that reads the raw CSV and uses pandas and numpy, and a test (`test_oracle_independence`) checks that the oracle imports nothing from the agent. But the tools also use pandas, so a defect inside pandas itself would affect both and would not be caught. Our design documents describe a DuckDB oracle, which would have removed that shared dependency, but the implemented oracle does not use DuckDB. I would state this as a limitation."*

---

### Category 4: Practical & Future Engineering

#### Q16: "What is the average latency per query, and where is the bottleneck?"
**Answer**:
> *"On a standard GTX 1650 GPU, average latency is ~143 seconds per question across 3 repeats (~45 seconds per run). 
> Our stage-time breakdown (`chart_stage_time_waterfall.png`, `agent_eval.md`) shows tool execution at about 0.3% of total time (10 s of 2858 s; single calls took 0.003 s to about 1 s). The bottleneck is local LLM inference: replanning is 56% of the total, answer synthesis 28% and plan generation 15% (these shares overlap with repair time, so they are not additive). We have not measured other hardware, so we don't claim how latency would scale."*

#### Q17: "What are Tukey's fences and how does your anomaly tool work?"
**Answer**:
> *"Our `detect_anomalies_iqr` tool (`src/da_agent/tools/statistics.py`) implements John Tukey's non-parametric outlier detection method:
> 1. Compute the first quartile ($Q_1$, 25th percentile) and third quartile ($Q_3$, 75th percentile).
> 2. Compute Interquartile Range: $\text{IQR} = Q_3 - Q_1$.
> 3. Compute fences: $[\text{Lower} = Q_1 - 1.5\text{IQR}, \text{Upper} = Q_3 + 1.5\text{IQR}]$.
> 4. Any data point outside these fences is flagged as an outlier with its deviation magnitude recorded in the evidence record."*

#### Q18: "What happens if a tool produces a division by zero?"
**Answer**:
> *"The M2 requirement (`docs/MODULES.md`) is that a zero denominator gives an undefined result with a stated reason, not a silent zero. In the code, results carry an `undefined_reason` field (`tools/executor.py`, `tools/charts.py:135`). Before the viva, open `tools/models.py` and `tests/unit/tools/` to confirm the exact reason names and the period_compare behaviour; I did not verify them."*

#### Q19: "Can your system handle multiple datasets or live databases?"
**Answer**:
> *"By design scope (`docs/PROJECT_SCOPE.md:49`), multi-dataset joins and live database integrations were excluded to focus on the correctness of single-dataset dynamic planning and evidence grounding. 
> However, our architecture is modular: the data layer (`src/da_agent/data/loader.py`) loads any CSV or XLSX file and assigns an immutable SHA-256 hash. Adding multi-table support would require adding a relational schema profiler and join tools to the registry."*

#### Q20: "If you had 3 more months on this project, what would be your top priorities?"
**Answer**:
> *"Three specific technical enhancements:
> 1. **Fix the rank gap**: let `rank` aggregate (or teach the planner to chain `group_aggregate` then `rank`), restrict trends to the requested period, and align the trend direction rule with the oracle. These address 6 of the 7 failures; we have not run them, so we don't promise a score.
> 2. **DuckDB In-Process Analytical Tools**: Allowing the agent to plan SQL queries executed in an in-memory DuckDB sandbox for complex multi-table aggregations, retaining full argument validation.
> 3. **Streaming Token Generation**: Adding server-sent events (SSE) to the FastAPI backend so the React UI visualizes the agent's thought chain in real-time."*

---

## 12. Live Demo Walkthrough & Command Cheat-Sheet

### 12.1 Live Demo Script (Step-by-Step for the Presentation)

1. **Step 1: Start Backend and Modern Frontend**
   ```bash
   # Terminal 1: FastAPI Service
   uv run uvicorn api_main:app --reload --host 127.0.0.1 --port 8000
   
   # Terminal 2: React 19 Frontend
   cd frontend && npm run dev
   ```
2. **Step 2: Open Browser to `http://127.0.0.1:5173`**
   - Click **"Load Sample Superstore"** (instantly profiles the 9,994 rows and displays schema).
3. **Step 3: Execute a Single-Step Query**
   - Prompt: *"What is the total sales for each Region?"*
   - **Point out to examiners**:
     - The agent selects `group_aggregate`.
     - Output is verified with zero ungrounded claims.
     - Evidence record ID is displayed and verifiable.
4. **Step 4: Execute a Multi-Step Conversational Drill-Down**
   - Prompt: *"Compare Furniture sales between 2016 and 2017."*
   - **Point out to examiners**:
     - The agent chains `filter` ➔ `period_compare`.
     - The output displays absolute change, relative percentage growth, and an interactive Plotly chart.

---

### 12.2 Terminal Verification Commands

```bash
# 1. Run the full test suite (320 tests in ~20s)
uv run pytest -q

# 2. Run linter and formatting checks
uv run ruff check .
uv run ruff format . --check

# 3. Verify benchmark freeze manifest integrity
uv run python evaluation/run_frozen_experiment.py --verify-only

# 4. Re-generate all presentation metric charts
uv run python scripts/generate_metrics_charts.py

# 5. Run the 12-scenario controlled failure recovery suite
uv run python evaluation/recovery_suite/run_recovery_suite.py
```

---

*Corrected 2026-11-19 against the code, traces and run data (8 tools, baseline mechanism, failure causes, ablation and spike caveats). Items marked "not verified" should be checked before the viva.*
