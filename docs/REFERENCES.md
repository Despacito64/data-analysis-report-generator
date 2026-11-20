# REFERENCES.md: audits, inspirations, and external sources

This file records **what we relied on outside the repo**, **where it appears in the project**, and **why it was needed**. It supports reproducibility, license review, and security audits. Update it when adding datasets, models, skills, or design patterns with external lineage.

**Audit date:** 2026-11-17 (Cursor; background subagent [References audit](ef69e2e7-78d8-457a-b9df-b4226b43e208) failed on model quota — this file was completed in the main session from repo evidence.)

---

## Datasets

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| Tableau **Sample Superstore** (community retail benchmark CSV) | Dataset | `Sample-Superstore.csv`, `src/da_agent/data/registry.py` (`BENCHMARK_SUPERSTORE`), `evaluation/benchmark/`, oracle, all eval runs | Initial domain (retail sales), frozen hash for fair baseline vs agent comparison (**D-007**) | Redistribution in git needs owner approval per **D-007**; hash locked to CRLF bytes `dc81c957…` |
| Registered SHA-256 fingerprint | Audit anchor | `tests/unit/test_dataset_registry.py`, profiler `dataset_hash`, evidence records | Prevents silent dataset drift across runs and follow-ups (**FR03**, **D-007**) | Wrong line endings break the gate (fixed in **88451fc**) |

---

## Models and inference

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| **Ollama** API (`http://localhost:11434`, OpenAI-compatible `/v1`) | Runtime | `config.yaml`, `OllamaClient` in `agent/planner.py`, `app.py`, `evaluation/run_agent_eval.py` | Local LLM per scope (**D-006**); no cloud API keys in repo | Must be running; GPU/CPU latency affects M6 gate (**D-034**) |
| **qwen3:4b** (Q4_K_M GGUF) | Model | `config.yaml` default (see D-023) | Selected by empirical spike: valid JSON + tool-name accuracy bar (**D-023**, supersedes open **D-006**) | See `docs/EXPERIMENTS_SUMMARY.md` for current results |
| **qwen3:8b**, **llama3.1:8b** (spike only) | Model candidates | **D-023** (the spike output files were removed) | Compared during M0/M5 spike; not primary deploy | Documented in decisions only |
| **llama3.2:3b** | Installed on host | Not in `config.yaml` | Present on machine; **not** chosen for project | *Inferred — verify with owner if used anywhere* |

---

## Libraries and tooling (runtime)

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| **Python 3.11+** / **uv** | Platform | `pyproject.toml`, **D-012** | Reproducible env and lockfile | Version pinned in decisions, not always in lock header |
| **Pydantic v2** | Library | `contracts/`, all cross-module DTOs | Typed contracts (**CONTRACTS.md**, **D-003**) | Contract changes need **DECISIONS** + owner |
| **Pandas** + **openpyxl** | Library | `data/loader.py`, tools | CSV/XLSX ingest (**FR01**, **D-015**) | Memory bounds via `input_limits` |
| **LangGraph** | Library | `agent/graph.py` | Fixed control graph with dynamic task DAG (**D-001**) | Vendor API churn |
| **Plotly** | Library | `tools/charts.py`, `reports/renderer.py` | Grounded charts in HTML reports (**M8**) | CDN in HTML output |
| **Streamlit** | Library | `app.py` (**M9**) | Upload, question, progress, download (**FR12**) | Not for headless eval |
| **DuckDB** | Library | `evaluation/oracle.py` only | Independent expected answers (**D-005**) | Oracle must not import agent/tools |
| **pytest** / **ruff** | Dev | `tests/`, CI-style local gates | Exit gates in **MODULES.md** | |
| **PyYAML** | Library | `config.yaml` loader | Budgets, model, limits without hard-coding | |

---

## External data-science / agent projects (design review, not vendored)

Reviewed in Cursor session 2026-11-17 when shaping the **M8 E2E report pipeline** and **M9 Streamlit** responsibilities. **No code was copied**; patterns informed `AnalysisRun`, `reports/delivery.py`, and `pipeline.run_agent(emit_report=True)`.

| Source | Type | Where reflected | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| [ahmedabdeltawab602-collab/dextra](https://github.com/ahmedabdeltawab602-collab/dextra) — `REPORT_PHILOSOPHY.md` | GitHub doc | `reports/assembler.py`, `build_report()` | Compose report from phase/tool outputs; do not recompute in the renderer (**FR09**) | Philosophy only; not a dependency |
| [ahmedabdeltawab602-collab/dextra](https://github.com/ahmedabdeltawab602-collab/dextra) — `DASHBOARD_PHILOSOPHY.md` | GitHub doc | `app.py` downloads `report.html`; no Plotly in Streamlit | UI as thin client over same artifacts as static HTML (**M9**) | Same |
| [veer0608/data-analysis-agent](https://github.com/veer0608/data-analysis-agent) | GitHub repo (review) | `pipeline.py` single entry, `runs/<run_id>/` artifacts | Thin orchestration API and per-run artifact directories (**D-013**) | Different stack; router/service layout not adopted literally |
| [santosh374maker/Agentic_Data_Scientist](https://github.com/santosh374maker/Agentic_Data_Scientist) | GitHub repo (review) | Staged pipeline; dedicated report stage | Last stage emits typed report after analysis phases | Multi-agent; we keep **D-001** single agent |

**Transcript anchor:** industry comparison table in chat before user approved E2E finalize (“okay go ahead”). Add further repos here when new design reviews occur.

| [Muvon/octomind-tap analytical-report skill](https://github.com/Muvon/octomind-tap/blob/master/skills/analytical-report/SKILL.md) | Report craft doc | `reports/renderer.py` headline + single table | Pyramid: headline → one visual → appendix; no duplicate bullets | Inspiration only |
| CMU “Structure of a Data Analysis Report” | Pedagogy PDF | Collapsed audit `<details>` | Body vs appendix audiences | https://stat.cmu.edu/~brian/701/notes/paper-structure.pdf |

---

## Architecture and design references (in-repo authority)

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| **Five validation layers** | Design pattern | `ARCHITECTURE.md`, `PROJECT_SCOPE.md`, **D-003** | Evidence before claims; auditability | |
| **Fixed baseline vs dynamic agent** | Experiment design | `agent/baseline.py`, `evaluation/run_eval.py`, **D-004** | Isolate planning variable | Baseline template ceiling 20/20 |
| **Layered imports** | Design pattern | `ARCHITECTURE.md`, `tests/test_import_rules.py`, **D-010** | Prevents oracle/tool coupling | Must extend test when adding packages |
| **LangGraph fixed nodes** (resolve → plan → execute → inspect → replan/finalize) | Control pattern | `graph.py`, **D-001** | Bounded recovery and trace | Not multi-agent |
| **Allowlisted tools only** | Safety pattern | `tools/registry.py`, **D-002** | No arbitrary code/SQL from LLM | New analytics need new tools |
| **AGENTS.md + docs/ handoff** | Process | All sessions | Multi-tool continuity (**D-011**) | Stale HANDOFF if protocol skipped |

---

## Evaluation and benchmarks

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| **20 frozen eval questions** | Benchmark | `evaluation/benchmark/questions.json` | M4/M6/M10 gates; dev/eval split **D-008** | Agent must not see text in prompts (leakage tests) |
| **`evaluation/oracle.py`** | Independent scorer input | M4, M10 | Ground truth without importing agent stack (**D-005**) | Hand-check ≥5 answers per **EVALUATION.md** |
| **`evaluation/scorer.py`** | Metrics | `run_eval.py`, `run_agent_eval.py` | Tolerance-based correctness | |
| **Recovery suite** (non-benchmark) | Test harness | `evaluation/recovery_suite/`, **D-037** | M7 failure scenarios without oracle leakage | Separate from 20 questions |
| **Category mix** (lookup, period, rank, …) | Test design | **EVALUATION.md** table | Coverage of tool surface | Single dataset domain |

---

## Third-party skills and UI inspiration

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| **Leonxlnx/taste-skill** (`design-taste-frontend` 2.5.1) | Cursor Agent Skill | `.agents/skills/design-taste-frontend/` (untracked), `skills-lock.json`, **HANDOFF** M9 polish | Optional anti-slop UI guidance for Streamlit/marketing pages | **skills.sh** reported elevated third-party risk; not vendored in git until owner approves |
| **skills CLI** (`skills@1.9.0` via npx) | Installer | `npx skills add` | Project-local skill install | No global `skills` binary |
| **Plotly White** template | Visual default | `tools/charts.py` | Readable default charts | Brand-neutral demo only |
| [shadcn AI Elements](https://ui.shadcn.com/docs/ai-elements) | UI pattern | `frontend/` header + activity list | Agent chats keep a **model badge** separate from the prompt, and show plan/tool steps as a trace | Pattern only; no component code copied |
| [fal Agent shell](https://fal.ai/docs/documentation/agent/chats/interface) | UI pattern | Context rail vs main answer | Sidebar holds context; the center holds the task and the result | Layout idea only |
| [Intuidy Agent Office](https://docs.intuidy.com/docs/agents/agent-office) | UI pattern | Activity list | Tool calls are a visible step list, not hidden until the answer | Docs only |
| [Qark model bar](https://qarkai.app/docs/getting-started/interface-tour/) | UI pattern | Top model badge | The model stays visible above the composer in every mode | Docs only |

---

## Demos and reproduction commands

| Command | Purpose |
| --- | --- |
| `docs/REPRODUCTION.md` | M10 frozen experiment (baseline + agent + recovery), **D-044** |

| Source | Type | Where used | Justification | Risk / limitation |
| --- | --- | --- | --- | --- |
| `demo/run_real_demo.py` | Script | Regenerates `demo/report.html` via **real Ollama** | Owner-requested non-mock demo; trace `runs/demo-visual-real/` | Requires local Ollama + `qwen3:4b` pull |
| `demo/walkthrough.html` | Static viewer | `http://127.0.0.1:8765/walkthrough.html` | Visual audit of M8/M9 path | Numbers from last real run in `demo/meta.json` |
| Mock LLM (`MockLLMClient`) | Test double | `tests/` only | Deterministic CI and eval; **never** used in Streamlit demo mode | Product demos use Ollama (**D-041**) |
| `da_agent/ui/demo.py` | Preset | `app.py` demo mode ON | Loads **Sample Superstore**, prefills `DEMO_QUESTION`; still calls **Ollama** | Requires benchmark CSV + running Ollama |

---

## External URLs cited in docs (not dependencies)

| URL | Cited in | Purpose |
| --- | --- | --- |
| `https://github.com/Despacito64/data-analysis-report-generator.git` | **D-014** | Intended remote; push deferred |
| `https://skills.sh/Leonxlnx/taste-skill` | **HANDOFF**, taste-skill install | Skill catalog and security summary |
| `https://github.com/Leonxlnx/taste-skill.git` | `skills-lock.json` | Skill source commit `f6b76575…` |

---

## React demo UI (layout inspiration, not vendored)

Patterns for `frontend/` shell (2026-11-18): full-width **top chrome** above a **two-column body**, bordered **side rail** for context, **segmented control** for data source, **model pill** in the header. Reviewed for agent-product UX only; no copied CSS or components.

| Source | Pattern borrowed |
| --- | --- |
| [fal.ai](https://fal.ai) agent / workflow shells (public marketing & docs UI) | Persistent top bar; task canvas below |
| Intuidy **Agent Office** (product screenshots) | Left context rail + bordered panels |
| [shadcn/ui AI Elements](https://ui.shadcn.com/docs/components) (docs) | Compact model / status chips |
| Qark-style **model bar** (internal review notes in Cursor session) | Labeled model readout separate from content |

**Transcript anchor:** user request to move heading above sidebar and improve rail buttons/borders ([cursor chat](01b82234-284a-44ce-8f51-603e65eb7c17)).

---

## Open questions (verify with owner)

1. **Sample Superstore** — confirm license/redistribution for committed `Sample-Superstore.csv` (**D-007** open note in HANDOFF).
2. **Industry / paper citations** — external agent repos are listed in **External data-science / agent projects** above; M10 manuscript should still add formal bibliography entries.
3. **Plotly CDN** — offline/air-gapped deploy may need vendored plotly.js.
4. **Complete taste-skill audit** — review skill scripts (`gate.mjs`, icon fetches) before production UI.

---

## Maintenance

- Append a row when adding: new dataset, model, npm/pip package used for reasoning (not just transitive), or copied prompt patterns from external repos.
- Cross-link the matching **D-xxx** in `DECISIONS.md`.
- Session end: mention updates in `HANDOFF.md` if this file changed.