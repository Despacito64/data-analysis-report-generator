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

Our system demonstrates an alternative paradigm: **Dynamic analytical task planning with deterministic tool execution and hash-linked evidence grounding**. The LLM decides *what* to compute (planning a typed DAG of analytical tasks); pre-tested, deterministic Python/Pandas functions decide *how* numbers are computed; and strict validators ensure that **a number reaches the report only if it matches a recorded evidence record**.

### 1.2 Core Research Question
> *Can an autonomous LLM agent dynamically formulate, execute, and revise multi-step analytical investigations on tabular data with zero code-execution safety risks and zero numerical hallucinations?*

**Answer (as far as one dataset and 20 questions can show):** on the final code the agent passes **12/20 (60%)** of a 20-question frozen benchmark scored by a separately computed (pandas/numpy) oracle, using a small local model (`qwen3:4b` on a GTX 1650). A model-free check (`scripts/ceiling_check.py`) shows only **12 of the 20 can be passed through the scoring path at all**, and the agent passes all 12 in 3 of 3 repeats. The 8 others fail because of how tool outputs map to the expected answers, not because a tool crashed (see 9.4). A clean ablation (`max_replans=0`) gave the same 12/20 with 118 instead of 258 LLM calls (see 10.1). Every number in a report passes through claim validation against a recorded evidence record.

---

## 2. Comparison with Base Paper: Data Interpreter

Our assigned base paper is:
> **"Data Interpreter: An LLM Agent For Data Science"** (Hong et al., 2024, arXiv 2402.18679)

### 2.1 Direct Architectural Comparison

| Dimension | *Data Interpreter* (Hong et al., 2024) | Our System (`da-agent`) | Engineering / Research Rationale |
| :--- | :--- | :--- | :--- |
| **Execution Paradigm** | Free-form Python code generation & execution in REPL | Allowlisted, pre-compiled deterministic analytical tools | Prevents arbitrary code execution, syntax crashes, and runaway scripts (`docs/DECISIONS.md:D-002`). |
| **Numerical Grounding** | Text stdout parsed from Python `print()` statements | `EvidenceRecord` with SHA-256 arguments and dataset hashes | Numbers are first-class data contracts, not scraped strings (`docs/CONTRACTS.md:80`). |
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
│ Ingestion, Cleaning, Schema, │   │ 8 Pandas/Stats Tools, Invariants,   │
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
* `budgets.max_llm_calls`: 15 in `config.yaml`; the evaluation harness uses `max_llm_calls_per_question: 8`, including the narration call.
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
| 5 | `trend` | Computes time-grain metrics (daily, monthly, quarterly) and linear trend. | Slope via least-squares: $m = \frac{\sum (t - \bar{t})(y - \bar{y})}{\sum (t - \bar{t})^2}$; direction label: `increasing`, `decreasing`, `flat` or `volatile`. |
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
* Computes expected answers directly from the raw `Sample-Superstore.csv` with a standalone pandas/numpy script (`evaluation/benchmark/build_oracle.py`). The oracle is plain pandas/numpy; the documents originally said DuckDB and were amended in D-051.
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

### 9.3 Main Evaluation Results (final code: `final-code-frozen-real-20261119`)
* **Hardware / model**: one GTX 1650 (4 GB), `qwen3:4b` through local Ollama, temperature 0, seed 42.
* **Protocol**: 20 questions, 3 repeats each, 60 s per call, 300 s per question, 8 LLM calls per question. A question passes if any repeat matches the oracle; attempts are also reported.

| Metric | Fixed baseline | Dynamic agent (`da-agent`) | Notes |
|---|:---:|:---:|---|
| Questions passed | 20 / 20 | **12 / 20 (60%)** | 36 of 60 attempts. 0 timeouts. |
| Reachable questions passed | n/a | **12 / 12**, each 3 of 3 | 12 questions can be passed through the scoring path (`scripts/ceiling_check.py`). |
| Baseline reality | 20 / 20 | n/a | A **ceiling, not a competitor**: `BASELINE_TASKS` is keyed by question id, never reads the question text, and assembles several answers (q01, q06-q08, q20, trend direction) with hand-written code outside the tools. |
| Recovery suite | n/a | **12 / 12** | Mock-only scenarios; no benchmark questions. |
| LLM calls / time | 0 | 258 calls, 93 min | Earlier revision R0 (`m10-frozen-real-20261117`): 13/20, 168 calls, 48 min. |

R0 (earlier revision, resolver node, no narration) scored 13/20. The one difference is q02 (see 9.4).

### 9.4 Why 8 questions fail (diagnosed from traces and the ceiling check)
The tools ran with status `ok` in every failure. The ceiling check feeds hand-written plans (including the baseline's own) through the real executor, answer extractor and scorer with a mock model; none of the 8 below passes under any candidate plan:

* **q06, q07, q08, q20 (rank)**: `rank` ranks individual rows and has no aggregation argument, so it returns top single transactions (q06: "Copiers" four times), not per-entity totals.
* **q01 (filter)**: the extractor returns `{"First Class": 351428.42}`; the number equals the expected total, but the oracle stores a scalar, so the shape mismatch fails it.
* **q02 (row count 599)**: the model plans a filter, but `augment_chat_plan` (D-048) appends `group_aggregate` to filter-only plans, so the scored answer becomes `{"West": 251991.83}`. This is why q02 regressed from R0.
* **q11 (trend 2017)**: the agent's answer covers all 48 months; with a filter step the extractor returns a date-keyed mapping, not the trend object.
* **q12 (quarterly trend)**: slope (1194.74) matches; the tool's direction label is `volatile`, the oracle's is `increasing`.

**What this shows**: the score measures the match between tool output shape and the oracle as much as it measures planning. Say "12 of 20, and 12 of 12 of the questions that can be scored". An earlier version of this guide blamed LLM answer extraction and then incomplete plans; both were wrong.

---

## 10. Ablation Study & Model Comparison Findings

### 10.1 Clean ablation: replanning off
* **Run**: `clean-ablation-max-replans-0-20261119`, identical to the final-code run except `--max-replans 0` (3 repeats, same budgets).
* **Result**: 12/20 and 36/60 attempts, the same questions as with replanning. LLM calls fell from 258 to 118 and time from 93 to 61 minutes.
* **Meaning**: on these easy one- or two-step questions replanning bought no accuracy and cost about 2.2 times the calls. It does not show replanning is useless; the benchmark has no questions where a first result should change the next step.
* **Older run**: the earlier reduced-budget run (repair cap 0, 4 LLM calls, 180 s, 1 repeat) changed four settings and the code, so it is not an ablation. Its q02 difference came from plan augmentation.

### 10.2 Partial model spike
`qwen2.5:3b-instruct` and `qwen2.5:7b-instruct`, 1 repeat, stopped after five questions (q03, q06, q09, q13, q17). On the four reachable ones (q03, q09, q13, q17): 3B passed 0, 7B passed 2; qwen3:4b's 4 of 4 comes from the 3-repeat R0 run, so it is not like for like. No ranking of models is justified, and no reason for the differences was investigated.

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

#### Q5: "What is an `EvidenceRecord` and what do the hashes give you?"
**Answer**:
> *"An `EvidenceRecord` (`docs/CONTRACTS.md:80`) is an immutable Pydantic object emitted by the executor after every tool run. It contains:
> - The unique `evidence_id` and `task_id`.
> - The SHA-256 hash of the canonical JSON arguments (`args_hash`).
> - The SHA-256 hash of the raw dataset (`dataset_hash`).
> - The raw input row count and structured output summary.
> - The list of mathematical invariants verified.
> The hashes tie each number to the exact dataset and arguments that produced it, so a number can be traced to its computation. It is hash-linked, not digitally signed; it does not by itself stop someone with write access from editing the file."*

---

### Category 2: Evaluation & Benchmark Defense

#### Q6: "Your dynamic agent scored 12/20, while the baseline scored 20/20. Doesn't that mean your baseline is better?"
**Answer**:
> *"No. The baseline is a ceiling, not a competitor. Its plans are in `BASELINE_TASKS`, keyed by question id; it never reads the question text, and several of its answers (q01, q06-q08, q20, the trend direction) are assembled by hand-written code outside the tools, which the agent does not get. We also checked, without any model, what the scoring path can accept: only 12 of the 20 questions can be passed through it, and the agent passes all 12 in three of three repeats. So the fair statement is 12 of 20, and 12 of 12 on the questions that can be scored. A fairer baseline would use the same answer extraction and would score the same twelve."*

#### Q7: "What caused the 8 failed questions? Did the tools fail?"
**Answer**:
> *"No tool crashed; every failed run had tool status `ok`. The ceiling check shows none of the eight can be passed under any plan. `rank` has no aggregation argument, so q06, q07, q08 and q20 return top single rows instead of totals. For q01 the number is right but it comes back as a group-to-value mapping where the oracle stores a scalar. For q02 a function added for the chat interface appends a group_aggregate, turning the count into a mapping; that is a regression from our earlier revision. q12's slope matches but the direction label is `volatile` against the oracle's `increasing`, and q11 loses the 2017 restriction or the trend shape. These are interface mismatches between tool outputs and the expected answers, not arithmetic errors."*

#### Q8: "What was the result of your ablation?"
**Answer**:
> *"Clean ablation: we set `max_replans` to 0 and changed nothing else, three repeats. It passed the same 12 questions, 36 of 60 attempts, using 118 LLM calls instead of 258 and 61 minutes instead of 93. So on this benchmark replanning cost about 2.2 times the calls and bought no accuracy. I would not call replanning useless: all 20 questions are one or two steps, and the model made a usable first plan for every question that can be scored. Testing the mechanism needs longer dependent questions. An earlier reduced-budget run changed four settings at once and is not an ablation."*

#### Q9: "Why did Qwen3-4B do better than the other models?"
**Answer**:
> *"We can't say. The spike used one repeat and stopped after five questions. On the four reachable ones, 3B passed none and 7B passed two, but the qwen3:4b figure of four comes from a different, three-repeat run, so it is not like for like. We make no ranking and did not investigate why. A fair test runs all 20 questions with three repeats per model under identical settings."*

---

#### Q10: "How do you guarantee that your evaluation benchmark did not leak into your agent?"
**Answer**:
> *"We enforce strict architectural and procedural isolation:
> 1. `evaluation/oracle.py` loads answers computed from the raw file by a standalone pandas/numpy script, and must not import the agent, tools, validation or report code. The automated test `test_oracle_independence` in `tests/test_import_rules.py` enforces this.
> 2. The 20 evaluation questions were frozen into `freeze_manifest.json` with SHA-256 hashes (`D-044`).
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
> *"Independent in code, not in libraries. The expected answers come from a standalone script (`evaluation/benchmark/build_oracle.py`) that reads the raw CSV and uses pandas and numpy, and a test (`test_oracle_independence`) checks that the oracle imports nothing from the agent. But the tools also use pandas, so a defect inside pandas itself would affect both and would not be caught. The original design said DuckDB, which would have removed that shared dependency; we implemented pandas and numpy and amended the documents (D-051). I would state this as a limitation."*

---

### Category 4: Practical & Future Engineering

#### Q16: "What is the average latency per query, and where is the bottleneck?"
**Answer**:
> *"On a standard GTX 1650 GPU, the final-code run took 93 minutes for 60 question runs, about 93 seconds per run. 
> Our stage-time breakdown (`chart_stage_time_waterfall.png`, `agent_eval.md`) shows tool execution at about 0.1% of total time (7 s of 5,584 s). The bottleneck is local LLM inference: replanning 1,867 s, plan generation 1,670 s, repair prompts 933 s and answer synthesis 648 s. Turning replanning off cut the run to 61 minutes. We have not measured other hardware, so we don't claim how latency would scale."*

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
> 1. **Fix the rank gap**: let `rank` aggregate (or teach the planner to chain `group_aggregate` then `rank`), restrict trends to the requested period, and align the trend direction rule with the oracle. These address the answer-shape failures; we have not run them, so we don't promise a score.
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
     - The plan is shown live; check beforehand which tools it picks (we have not verified that it chains `filter` ➔ `period_compare` for this wording).
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

*Updated 2026-11-20 against the final-code run, the clean ablation and the ceiling check (D-051). Items marked "not verified" should be checked before the viva.*
