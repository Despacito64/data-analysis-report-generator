#!/usr/bin/env python3
"""Technical review deck. Colors and type follow askMNIT_SmritiStyle.pptx."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

NAVY = RGBColor(0x00, 0x33, 0xCC)
INK = RGBColor(0x22, 0x22, 0x22)
GRAY = RGBColor(0x55, 0x55, 0x55)
ORANGE = RGBColor(0xFF, 0x66, 0x00)
AMBER = RGBColor(0xCC, 0x66, 0x00)
CREAM = RGBColor(0xFD, 0xF0, 0xE2)
BLUE = RGBColor(0xE6, 0xED, 0xFB)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREEN = RGBColor(0x1E, 0x8A, 0x4C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Times New Roman"
LOGO = "/tmp/pptstyle/image1.jpeg"

prs = Presentation()
prs.slide_width = Inches(13.333333)
prs.slide_height = Inches(7.5)
prs.core_properties.title = "Evidence-grounded dynamic planning for tabular analysis"
prs.core_properties.subject = "LLM course project review"
BLANK = prs.slide_layouts[6]


def _run(p, text, size, color, bold=False, italic=False, align=None):
    p.alignment = align if align is not None else p.alignment
    run = p.add_run()
    run.text = text
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    # Force latin typeface so LibreOffice does not substitute.
    rpr = run._r.get_or_add_rPr()
    latin = rpr.find(qn("a:latin"))
    if latin is None:
        latin = rpr.makeelement(qn("a:latin"), {})
        rpr.append(latin)
    latin.set("typeface", FONT)
    return run


def _box(slide, l, t, w, h, anchor=MSO_ANCHOR.TOP):
    sh = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = sh.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    tf.paragraphs[0].alignment = PP_ALIGN.LEFT
    sh.text_frame.paragraphs[0].space_before = Pt(0)
    sh.text_frame.paragraphs[0].space_after = Pt(0)
    tf._txBody.bodyPr.set(
        "anchor", {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor]
    )
    return tf


def text(
    slide,
    l,
    t,
    w,
    h,
    content,
    size,
    color,
    bold=False,
    italic=False,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
):
    tf = _box(slide, l, t, w, h, anchor)
    p = tf.paragraphs[0]
    p.alignment = align
    p.clear()
    _run(p, content, size, color, bold, italic, align)
    return tf


def paragraphs(slide, l, t, w, h, rows, anchor=MSO_ANCHOR.TOP):
    """rows: list of (text, size, color, bold, italic, align, space_after_pt)"""
    tf = _box(slide, l, t, w, h, anchor)
    for i, row in enumerate(rows):
        content, size, color, bold, italic, align, space = row
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space)
        p.space_before = Pt(0)
        _run(p, content, size, color, bold, italic, align)
    return tf


def rect(slide, l, t, w, h, fill):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    return sh


def oval(slide, l, t, w, h, fill):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(l), Inches(t), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    return sh


def page_num(slide, n):
    text(slide, 12.15, 7.08, 0.9, 0.28, str(n), 12, GRAY, align=PP_ALIGN.RIGHT)


def title(slide, label):
    text(
        slide,
        0.45,
        0.22,
        12.4,
        0.62,
        label,
        32,
        NAVY,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )


def subtitle(slide, label):
    text(slide, 0.5, 0.92, 12.33, 0.42, label, 15, GRAY, italic=True, align=PP_ALIGN.LEFT)


def source(slide, label):
    text(slide, 0.5, 6.72, 11.5, 0.32, label, 12, GRAY, italic=True)


def new(n, heading, sub=None):
    s = prs.slides.add_slide(BLANK)
    # White background is the default.
    title(s, heading)
    if sub:
        subtitle(s, sub)
    page_num(s, n)
    return s


def card(slide, l, t, w, h, fill=BLUE):
    return rect(slide, l, t, w, h, fill)


def badge(slide, l, t, n, fill=AMBER):
    oval(slide, l, t, 0.42, 0.42, fill)
    text(
        slide,
        l,
        t,
        0.42,
        0.42,
        str(n),
        14,
        WHITE,
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )


# ---------------------------------------------------------------------------
# 1 Title
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
s.shapes.add_picture(LOGO, Inches(6.17), Inches(0.28), Inches(1.0), Inches(1.0))
line = s.shapes.add_shape(
    MSO_SHAPE.RECTANGLE, Inches(0.78), Inches(1.42), Inches(11.77), Inches(0.045)
)
line.fill.solid()
line.fill.fore_color.rgb = ORANGE
line.line.fill.background()
text(
    s,
    0.7,
    1.65,
    11.9,
    1.15,
    "Evidence-Grounded Dynamic Planning\nfor Tabular Analysis",
    32,
    NAVY,
    align=PP_ALIGN.CENTER,
    anchor=MSO_ANCHOR.MIDDLE,
)
text(s, 0.8, 2.9, 11.7, 0.4, "LLM Course Project: Technical Review", 20, INK, align=PP_ALIGN.CENTER)
text(
    s,
    0.8,
    3.4,
    11.7,
    0.35,
    "Presented by: add name and roll number",
    16,
    GRAY,
    italic=True,
    align=PP_ALIGN.CENTER,
)
text(
    s,
    0.8,
    5.35,
    11.7,
    0.4,
    "Department of Artificial Intelligence and Data Engineering, MNIT Jaipur",
    16,
    INK,
    align=PP_ALIGN.CENTER,
)
text(s, 0.8, 5.85, 11.7, 0.35, "November 2026", 16, GRAY, align=PP_ALIGN.CENTER)

# ---------------------------------------------------------------------------
# 2 Index
# ---------------------------------------------------------------------------
s = new(2, "Index")
items = [
    "1    Problem statement and readiness",
    "2    Project type: application-based",
    "3    Working demo",
    "4    Literature, the base paper, and the gap",
    "5    Methodology, model architecture, and flow",
    "6    Results",
    "7    Future work",
    "8    Module 09: what transferred from class",
]
top = 1.48
for i, item in enumerate(items):
    card(s, 1.3, top, 10.7, 0.58)
    text(s, 1.55, top, 10.2, 0.58, item, 18, INK, anchor=MSO_ANCHOR.MIDDLE)
    top += 0.66

# ---------------------------------------------------------------------------
# 3 Problem
# ---------------------------------------------------------------------------
s = new(
    3,
    "Problem Statement",
    "A natural-language question still needs a checked chain of calculations.",
)
card(s, 0.45, 1.55, 6.1, 4.9)
text(s, 0.7, 1.75, 5.65, 0.4, "Where answers break", 20, NAVY, bold=True)
rows = [
    (
        "Fixed sequence",
        "Routine questions finish. A result that calls for a different breakdown stops the path.",
    ),
    (
        "Fluent model",
        "The model can choose a next step and can also write a number that was never computed.",
    ),
    ("Audit", "A sentence in the report is not evidence that the figure was calculated."),
]
y = 2.3
for head, body in rows:
    text(s, 0.7, y, 5.65, 0.32, head, 16, AMBER, bold=True)
    text(s, 0.7, y + 0.32, 5.65, 0.7, body, 14, INK)
    y += 1.15

card(s, 6.75, 1.55, 6.1, 4.9, CREAM)
text(s, 7.0, 1.75, 5.65, 0.4, "Project objective", 20, NAVY, bold=True)
text(
    s,
    7.0,
    2.3,
    5.65,
    3.7,
    "One agent plans approved operations on a table, revises pending tasks from intermediate results, and writes a report whose numbers trace to recorded evidence.\n\n"
    "Excluded on purpose: multi-agent swarms, arbitrary Python, LLM-written SQL, forecasting, model training, and causal claims.",
    16,
    INK,
)
source(s, "Source: docs/PROJECT_SCOPE.md, Problem, Main objective, and Explicit exclusions.")

# ---------------------------------------------------------------------------
# 4 TRL
# ---------------------------------------------------------------------------
s = new(4, "Readiness", "TRL 4 is an assessment for this review. No project file assigns a TRL.")
levels = [
    (
        BLUE,
        "TRL 3",
        "Observed",
        "A local 4B model emits a typed tool plan. On the model spike, qwen3:4b produced a valid plan on 52 of 60 runs.",
    ),
    (
        CREAM,
        "TRL 4",
        "This assessment",
        "Lab prototype on one registered CSV: load, profile, plan, execute, replan, claim check, HTML report, Streamlit, and one finished frozen run. M0–M9 are marked passed. M10 gate sign-off is still open.",
    ),
    (
        BLUE,
        "TRL 5",
        "Not claimed",
        "Would need more than one dataset and users outside this benchmark. The scope forbids a production-readiness claim from one file and 20 questions.",
    ),
]
for i, (fill, name, tag, body) in enumerate(levels):
    x = 0.45 + i * 4.25
    card(s, x, 1.55, 4.05, 4.85, fill)
    text(s, x + 0.2, 1.75, 3.65, 0.45, name, 26, NAVY, bold=True)
    text(s, x + 0.2, 2.25, 3.65, 0.35, tag, 14, AMBER, bold=True)
    text(s, x + 0.2, 2.75, 3.65, 3.3, body, 15, INK)
source(
    s,
    "Sources: model spike, 52/60 valid plans; docs/PROGRESS.md (module gates); docs/M10_RESULTS.md (frozen run); docs/PROJECT_SCOPE.md (exclusions).",
)

# ---------------------------------------------------------------------------
# 5 Demo
# ---------------------------------------------------------------------------
s = new(5, "Project Type", "Classification for this review: an application-based project.")
card(s, 0.45, 1.55, 12.4, 1.35, CREAM)
text(s, 0.7, 1.7, 12.0, 0.4, "Application-based", 26, NAVY, bold=True)
text(
    s,
    0.7,
    2.2,
    12.0,
    0.5,
    "The deliverable is a system a person can run: upload a CSV or XLSX, ask a question, and download an HTML report.",
    16,
    INK,
)
points = [
    (
        "What the user runs",
        "Streamlit loads the file, shows the trace, and writes the report. Demo mode calls the local model, not a test double.",
    ),
    (
        "What the numbers are for",
        "The frozen 13/20 against the template baseline is acceptance evidence for that system. It is not a new model or a new training method.",
    ),
    (
        "What this is not",
        "Not a research-exploratory project. No hypothesis search, no fine-tuning, no new architecture trained on data.",
    ),
]
for i, (head, body) in enumerate(points):
    x = 0.45 + i * 4.2
    card(s, x, 3.15, 4.0, 3.2)
    text(s, x + 0.2, 3.35, 3.6, 0.7, head, 18, NAVY, bold=True)
    text(s, x + 0.2, 4.15, 3.6, 1.9, body, 15, INK)
source(
    s,
    "Sources: docs/PROJECT_SCOPE.md (the system to build); src/da_agent/ui/demo.py (the runnable demo). The application label is the classification for this review.",
)

s = new(
    6,
    "Working Demo",
    "No recording is in the repository. This is the 60–90 second capture to insert.",
)
steps = [
    (
        "1",
        "Load the registered file",
        "Streamlit demo mode loads Sample Superstore and disables custom upload. The client is real Ollama.",
    ),
    ("2", "Ask the preset question", "“What are total sales by category?”"),
    (
        "3",
        "Watch the trace",
        "Resolve, plan, tool call, evidence record. The mock model is tests-only.",
    ),
    (
        "4",
        "Open the HTML report",
        "Category totals, one chart, and an evidence id on each rendered value. Cell text is escaped.",
    ),
]
for i, (n, head, body) in enumerate(steps):
    y = 1.5 + i * 1.22
    card(s, 0.45, y, 12.4, 1.1)
    badge(s, 0.65, y + 0.34, n)
    text(s, 1.25, y + 0.1, 11.3, 0.36, head, 18, NAVY, bold=True)
    text(s, 1.25, y + 0.5, 11.3, 0.48, body, 15, INK)
source(
    s,
    "Sources: src/da_agent/ui/demo.py; src/da_agent/reports/renderer.py. Tool-time counter is on the Results slide.",
)

# ---------------------------------------------------------------------------
# 6 Literature
# ---------------------------------------------------------------------------
s = new(
    7,
    "Literature Survey",
    "Lines of work cited by the base paper, and the limit each one leaves open.",
)
rows = [
    (
        "Code-writing interpreters",
        "Gao et al. 2023; Chen et al. 2022; later interpreter work in the same section. A generated program is the calculation.",
    ),
    (
        "Tool-using models",
        "Schick et al. 2024; Paranjape et al. 2023. External tools, often along one planned path.",
    ),
    (
        "Graph planning",
        "Chain-of-Thought, Tree-of-Thoughts, Graph-of-Thoughts (Wei 2022; Yao 2022; Yao 2024; Besta 2023). Reasoning structure, not a checked table result.",
    ),
    (
        "Data Interpreter",
        "Hong et al. 2024. A hierarchical task and action graph whose nodes are generated code, including machine-learning jobs.",
    ),
]
for i, (head, body) in enumerate(rows):
    y = 1.48 + i * 1.22
    card(s, 0.45, y, 12.4, 1.12)
    badge(s, 0.65, y + 0.35, str(i + 1), NAVY)
    text(s, 1.25, y + 0.1, 11.3, 0.34, head, 18, NAVY, bold=True)
    text(s, 1.25, y + 0.48, 11.3, 0.52, body, 14, INK)
source(
    s,
    "Source: [1] Hong et al., arXiv:2402.18679v4, Related Work. Names above are the papers that section cites.",
)

# ---------------------------------------------------------------------------
# 7 Base paper
# ---------------------------------------------------------------------------
s = new(
    8,
    "Base Paper",
    "Data Interpreter reframes a data-science job as a graph that can change while it runs.",
)
card(s, 0.45, 1.48, 6.1, 2.35)
text(s, 0.65, 1.6, 5.7, 0.35, "Hierarchical graph modeling", 18, NAVY, bold=True)
text(
    s,
    0.65,
    2.05,
    5.7,
    1.55,
    "A project splits into tasks. Each task splits into actions. Dependencies are edges. Nodes can be added and rewritten as intermediate data changes.",
    15,
    INK,
)
card(s, 6.75, 1.48, 6.1, 2.35, CREAM)
text(s, 6.95, 1.6, 5.7, 0.35, "Programmable node generation", 18, NAVY, bold=True)
text(
    s,
    6.95,
    2.05,
    5.7,
    1.55,
    "Each action node is code. The model writes it, runs it, and refines it. That is the mechanism behind the scores below.",
    15,
    INK,
)

metrics = [
    ("75.9% → 94.9%", "InfiAgent-DABench\naccuracy"),
    ("88% → 95%", "Machine-learning\ntasks"),
    ("60% → 97%", "Open-ended\ntasks"),
    ("26%", "MATH improvement\nvs their baselines"),
]
for i, (num, label) in enumerate(metrics):
    x = 0.45 + i * 3.2
    card(s, x, 4.0, 3.05, 2.15)
    text(s, x + 0.12, 4.15, 2.8, 0.7, num, 26, NAVY, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + 0.12, 4.95, 2.8, 0.95, label, 14, INK, align=PP_ALIGN.CENTER)
source(
    s,
    "Source: [1] abstract. These figures are the paper’s results on its benchmarks and models, not this repository.",
)

# ---------------------------------------------------------------------------
# 8 Gap
# ---------------------------------------------------------------------------
s = new(
    9,
    "Gap",
    "Keep the changing task graph. Remove free-form code from the path that produces a number.",
)
card(s, 0.45, 1.5, 6.1, 4.95)
text(s, 0.7, 1.7, 5.65, 0.4, "What the base paper establishes", 18, NAVY, bold=True)
text(
    s,
    0.7,
    2.25,
    5.65,
    3.8,
    "End-to-end data-science work has task dependencies that a one-shot plan does not cover. Data Interpreter raises benchmark scores by generating and executing code, including machine-learning pipelines.\n\nThe published InfiAgent-DABench move is 75.9% to 94.9% accuracy [1].",
    16,
    INK,
)
card(s, 6.75, 1.5, 6.1, 4.95, CREAM)
text(s, 7.0, 1.7, 5.65, 0.4, "What this repository builds", 18, NAVY, bold=True)
text(
    s,
    7.0,
    2.25,
    5.65,
    3.8,
    "One local model plans a typed task DAG. Eight registered Pandas tools compute. The LangGraph control graph stays fixed.\n\nBaseline and agent share tools, resolver, budgets, and scoring. The baseline does not replan. The oracle does not import the agent or the tools.",
    16,
    INK,
)
source(
    s,
    "Sources: [1]; docs/ARCHITECTURE.md; docs/PROJECT_SCOPE.md; src/da_agent/tools/registry.py; evaluation/oracle.py.",
)

# ---------------------------------------------------------------------------
# 9 Methodology rules
# ---------------------------------------------------------------------------
s = new(10, "Proposed Methodology", "Four rules that sit in front of every run.")
rules = [
    (
        "The model proposes",
        "It chooses tasks and writes wording. It does not calculate the reported figure.",
    ),
    (
        "Evidence before claims",
        "A number enters the report only from a valid evidence record. Unsupported claim text is removed.",
    ),
    (
        "Every run ends visibly",
        "Status is complete, partial, or failed, with a reason. Retries and replans have finite budgets.",
    ),
    (
        "Uploaded cells are data",
        "Cell text is never treated as an instruction. HTML output is escaped.",
    ),
]
for i, (head, body) in enumerate(rules):
    y = 1.5 + i * 1.22
    rect(s, 0.45, y, 0.9, 1.08, AMBER)
    text(
        s,
        0.45,
        y,
        0.9,
        1.08,
        str(i + 1),
        26,
        WHITE,
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    card(s, 1.45, y, 11.4, 1.08)
    text(s, 1.7, y + 0.12, 10.9, 0.36, head, 18, NAVY, bold=True)
    text(s, 1.7, y + 0.52, 10.9, 0.45, body, 15, INK)
source(s, "Sources: docs/PROJECT_SCOPE.md; AGENTS.md hard rules 2, 6, and 8.")

# ---------------------------------------------------------------------------
# 10 Dataset
# ---------------------------------------------------------------------------
s = new(
    11,
    "Dataset",
    "One registered retail file. The frozen question file is the set that was scored.",
)
card(s, 0.45, 1.5, 7.55, 4.95)
text(s, 0.7, 1.7, 7.1, 0.4, "Sample Superstore", 20, NAVY, bold=True)
lines = [
    "9,994 data rows. SHA-256 dc81c95712ec307e8a7f6252cbf344ac70a0a325ddc90e000ebae82e4ac02b8c.",
    "22 registered columns, including Order Date, Region, Category, Sub-Category, Sales, Quantity, Discount, and Profit.",
    "20 frozen questions in evaluation/benchmark/questions.json.",
    "filter q01–q02 · group aggregate q03–q05 · rank q06–q08 · period compare q09–q10 · trend q11–q12 · contribution q13–q14 · correlation q15–q16 · IQR anomalies q17–q18 · multistep q19–q20.",
    "The design note in EVALUATION.md also lists ambiguous and unanswerable items. Those items are not in the frozen file.",
]
paragraphs(
    s,
    0.7,
    2.25,
    7.05,
    3.9,
    [(line, 14, INK, False, False, PP_ALIGN.LEFT, 8) for line in lines],
)
card(s, 8.2, 1.5, 4.65, 4.95, CREAM)
text(s, 8.4, 1.7, 4.25, 0.4, "Frozen settings", 20, NAVY, bold=True)
paragraphs(
    s,
    8.4,
    2.3,
    4.25,
    3.7,
    [
        ("qwen3:4b", 18, NAVY, True, False, PP_ALIGN.LEFT, 4),
        ("temperature 0.0", 16, INK, False, False, PP_ALIGN.LEFT, 2),
        ("seed 42", 16, INK, False, False, PP_ALIGN.LEFT, 2),
        ("3 repeats × 20 questions", 16, INK, False, False, PP_ALIGN.LEFT, 2),
        ("60 s per LLM call", 16, INK, False, False, PP_ALIGN.LEFT, 10),
        (
            "Hardware for this 3× run is not recorded with the result.",
            14,
            GRAY,
            False,
            True,
            PP_ALIGN.LEFT,
            0,
        ),
    ],
)
source(
    s,
    "Sources: evaluation/benchmark/freeze_manifest.json; evaluation/benchmark/questions.json; docs/EVALUATION.md.",
)

# ---------------------------------------------------------------------------
# 11 Flow
# ---------------------------------------------------------------------------
s = new(
    12,
    "Model Architecture",
    "One local model proposes a plan. Registered code computes. The control graph does not change during a run.",
)
blocks = [
    (
        "1",
        "Planner",
        "qwen3:4b through Ollama. Temperature 0.0, seed 42. No gradient update and no fine-tune.",
    ),
    (
        "2",
        "Prompt",
        "Eight tool schemas, column names with semantic types, a JSON schema, and three few-shot plans.",
    ),
    (
        "3",
        "Control graph",
        "resolve → plan → validate_repair → execute → inspect → replan → finalize.",
    ),
    (
        "4",
        "Execution",
        "The selected tool runs in Pandas. An evidence record is stored. Claims are checked before HTML.",
    ),
]
for i, (n, head, body) in enumerate(blocks):
    x = 0.4 + i * 3.22
    card(s, x, 1.52, 3.08, 3.15)
    badge(s, x + 0.18, 1.7, n)
    text(s, x + 0.7, 1.72, 2.2, 0.4, head, 16, NAVY, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.18, 2.35, 2.72, 2.1, body, 14, INK)
card(s, 0.4, 4.85, 12.5, 1.6, CREAM)
text(s, 0.65, 5.0, 12.05, 0.35, "How a run is shaped", 16, NAVY, bold=True)
text(
    s,
    0.65,
    5.4,
    12.05,
    0.85,
    "The system prompt says the plan may contain at most max_steps tasks. build_system_prompt defaults that to 5. The live graph passes budgets.max_tool_calls, which is 25 in the frozen manifest. The planner then chooses a subset of the eight tools. It does not train experts, and it does not attend sparsely over tokens.",
    14,
    INK,
)
source(
    s,
    "Sources: planner.py build_system_prompt (Examples 1–3); graph.py node list; config.yaml and freeze_manifest.json (max_tool_calls 25); registry.py.",
)

s = new(
    13,
    "Flow Diagram",
    "Both variants share this path. The baseline replaces planning and replanning with a question-id template.",
)
flow = [
    ("1", "Load and profile", "Checks, hash, types, missing values, date coverage"),
    ("2", "Resolve", "Metric, period, grouping, or a decline"),
    ("3", "Plan the DAG", "Typed tasks and dependencies from the model"),
    ("4", "Check the plan", "Known tools, real columns, no cycle"),
    ("5", "Run one tool", "Argument check, then the Pandas function"),
    ("6", "Store evidence", "Schema and numerical invariants"),
    ("7", "Inspect", "Continue, revise pending tasks, or stop"),
    ("8", "Report", "Claim check, escaped HTML, run trace"),
]
for i, (n, head, body) in enumerate(flow):
    col = i % 4
    row = i // 4
    x = 0.4 + col * 3.22
    y = 1.55 + row * 2.4
    card(s, x, y, 3.05, 2.15)
    badge(s, x + 0.15, y + 0.18, n)
    text(s, x + 0.68, y + 0.2, 2.2, 0.4, head, 15, NAVY, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + 0.15, y + 0.8, 2.75, 1.15, body, 13, INK)
source(
    s,
    "Sources: docs/ARCHITECTURE.md, End-to-end run; src/da_agent/agent/graph.py; src/da_agent/agent/baseline.py.",
)

# ---------------------------------------------------------------------------
# 12 LLM
# ---------------------------------------------------------------------------
s = new(
    14,
    "LLM Technique",
    "The model returns JSON tasks. Registered code returns the numbers. Spike used the same 20 questions, 3 runs each.",
)
# header bar
rect(s, 0.45, 1.5, 12.4, 0.48, NAVY)
headers = [(0.55, "Model"), (3.3, "Valid plans"), (6.2, "Correct tool set"), (9.3, "Role")]
for x, h in headers:
    text(s, x, 1.5, 2.8, 0.48, h, 14, WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
rows = [
    ("qwen3:4b", "52/60  (86.7%)", "56/60  (93.3%)", "Chosen"),
    ("qwen3:8b", "45/60  (75.0%)", "55/60  (91.7%)", "Fallback"),
    ("llama3.1:8b", "33/60  (55.0%)", "49/60  (81.7%)", "Not selected"),
]
for i, row in enumerate(rows):
    y = 2.02 + i * 0.55
    fill = CREAM if i == 0 else BLUE
    rect(s, 0.45, y, 12.4, 0.52, fill)
    vals = [row[0], row[1], row[2], row[3]]
    xs = [0.55, 3.3, 6.2, 9.3]
    for x, val in zip(xs, vals):
        text(s, x, y, 2.9, 0.52, val, 15, INK, bold=(i == 0), anchor=MSO_ANCHOR.MIDDLE)

card(s, 0.45, 3.8, 6.1, 2.65)
text(s, 0.65, 3.95, 5.7, 0.35, "Control graph, fixed", 16, NAVY, bold=True)
text(
    s,
    0.65,
    4.4,
    5.7,
    1.85,
    "resolve → plan → validate_repair → execute → inspect → replan → finalize.\n\nA revision counts as dynamic planning only when a pending task or argument changes because of an observed result or a classified failure.",
    14,
    INK,
)
card(s, 6.75, 3.8, 6.1, 2.65, CREAM)
text(s, 6.95, 3.95, 5.7, 0.35, "Selection bar", 16, NAVY, bold=True)
text(
    s,
    6.95,
    4.4,
    5.7,
    1.85,
    "Selection bar: at least 85% valid plans and 70% correct tool set. qwen3:4b is the only candidate that cleared both. Sampling for the spike and the frozen run: temperature 0.0, seed 42.",
    14,
    INK,
)
source(
    s,
    "Sources: model-spike results; freeze_manifest.json model block; src/da_agent/agent/graph.py; docs/PROJECT_SCOPE.md, Definition of dynamic planning.",
)

# ---------------------------------------------------------------------------
# 13 Validation
# ---------------------------------------------------------------------------
s = new(15, "Validation", "Five checks. The claim check has a recorded limit.")
layers = [
    ("Input", "Extension, size, row cap, empty file, bad sheet"),
    ("Plan", "Allowlisted tool, columns exist, types match, no cycle"),
    ("Arguments", "Measures are numeric. Periods lie inside observed dates."),
    ("Result", "Schema and invariants: shares, ranks, growth"),
    ("Claim", "Stated numbers must match evidence, or the text is dropped"),
]
for i, (head, body) in enumerate(layers):
    x = 0.4 + i * 2.56
    card(s, x, 1.5, 2.45, 2.7)
    text(s, x + 0.12, 1.65, 2.2, 0.7, head, 18, NAVY, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + 0.12, 2.45, 2.2, 1.5, body, 13, INK, align=PP_ALIGN.CENTER)
card(s, 0.4, 4.4, 12.5, 2.05, CREAM)
text(s, 0.65, 4.55, 12.0, 0.35, "Recorded limit", 16, AMBER, bold=True)
text(
    s,
    0.65,
    5.0,
    12.0,
    1.2,
    "The claim check matches a number’s presence, tolerance, and scale. It does not bind the column. A profit figure and a sales figure of the same magnitude are not distinguished. The HTML renderer does escape question text, values, and evidence ids.",
    15,
    INK,
)
source(s, "Sources: docs/ARCHITECTURE.md, Validation layers; src/da_agent/reports/renderer.py.")

# ---------------------------------------------------------------------------
# 14 Results
# ---------------------------------------------------------------------------
s = new(
    16,
    "Results",
    "Run m10-frozen-real-20261117. 20 questions, 3 repeats. Every pass is 3/3 and every loss is 0/3.",
)
stats = [
    ("13/20", "Dynamic agent", "qwen3:4b. Accuracy 0.65. Zero timeouts.", NAVY),
    (
        "20/20",
        "Fixed baseline",
        "Template selected by question id. A ceiling, not a planner.",
        AMBER,
    ),
    ("39 / 21", "Run outcomes", "39 passed runs and 21 failed runs out of 60.", NAVY),
    ("12/12", "Recovery suite", "Controlled failures. No live model. No frozen questions.", GREEN),
]
for i, (num, head, body, col) in enumerate(stats):
    x = 0.4 + i * 3.22
    card(s, x, 1.5, 3.08, 2.85)
    text(s, x + 0.1, 1.65, 2.88, 0.7, num, 28, col, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + 0.12, 2.4, 2.84, 0.4, head, 15, NAVY, bold=True, align=PP_ALIGN.CENTER)
    text(s, x + 0.12, 2.85, 2.84, 1.25, body, 13, INK, align=PP_ALIGN.CENTER)
card(s, 0.4, 4.55, 12.5, 1.9)
text(s, 0.6, 4.7, 12.1, 0.35, "Cost of the agent evaluation", 16, NAVY, bold=True)
text(
    s,
    0.6,
    5.15,
    12.1,
    1.1,
    "Wall clock 2,858.2 s. LLM calls 168, including 1 warm-up. Head-to-head: 13 ties and 7 losses.\n"
    "Recorded stage counters, not an additive split of the wall clock (the counters sum to about 3,569 s): replanning 1,608.8 s, answer synthesis 793.7 s, plan generation 440.4 s, tool execution 9.5 s.",
    14,
    INK,
)
source(
    s,
    "Source: [2] evaluation/results/m10-frozen-real-20261117/agent_eval.json. Recovery: evaluation/results/recovery_suite/latest.json.",
)

# ---------------------------------------------------------------------------
# 15 Losses
# ---------------------------------------------------------------------------
s = new(
    17,
    "Results: Seven Losses",
    "On every failed repeat the tool status is ok. The scored answer is what fails.",
)
rect(s, 0.45, 1.5, 12.4, 0.48, NAVY)
for x, w, h in (
    (0.6, 1.6, "Question"),
    (2.3, 4.2, "What the question asks"),
    (6.6, 2.6, "Tool status, all 3 runs"),
    (9.4, 3.2, "Score reason"),
):
    text(s, x, 1.5, w, 0.48, h, 14, WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
loss_rows = [
    ("q01", "Total sales for First Class shipping", "filter ok", "no_score_shaped_answer"),
    ("q06", "Top 5 sub-categories by sales", "rank ok", "incorrect_answer"),
    ("q07", "Top 3 states by profit", "rank ok", "incorrect_answer"),
    ("q08", "Bottom 5 sub-categories by profit", "rank ok", "incorrect_answer"),
    ("q11", "Monthly sales trend in 2017", "trend ok", "incorrect_answer"),
    ("q12", "Quarterly profit trend", "trend ok", "incorrect_answer"),
    ("q20", "Top 3 cities by sales, Consumer segment", "filter ok, rank ok", "incorrect_answer"),
]
for i, (qid, ask, tool, reason) in enumerate(loss_rows):
    y = 2.02 + i * 0.58
    rect(s, 0.45, y, 12.4, 0.55, BLUE if i % 2 == 0 else WHITE)
    text(s, 0.6, y, 1.6, 0.55, qid, 14, NAVY, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 2.3, y, 4.2, 0.55, ask, 13, INK, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 6.6, y, 2.7, 0.55, tool, 13, INK, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 9.4, y, 3.2, 0.55, reason, 13, RED, anchor=MSO_ANCHOR.MIDDLE)
source(
    s,
    "Sources: [2] runs[].tool_executions and failure_reason. Row labels are shortened from evaluation/benchmark/questions.json.",
)

# ---------------------------------------------------------------------------
# 16 Future
# ---------------------------------------------------------------------------
s = new(18, "Future Work", "Next steps stay inside the current scope.")
future = [
    (
        "Answer fields for rank and trend",
        "Six of the seven losses are incorrect_answer after a successful rank or trend call. q01 is the extraction miss.",
    ),
    (
        "Same budget, fallback model",
        "Repeat the frozen protocol with qwen3:8b and publish the three repeats separately.",
    ),
    (
        "A second registered dataset",
        "New hash and a new frozen set before any sentence about generalization.",
    ),
    (
        "Specified ablation",
        "Dynamic agent with validation feedback off, as already listed in EVALUATION.md.",
    ),
    ("PDF after HTML", "PDF waits until the HTML report is stable."),
]
for i, (head, body) in enumerate(future):
    y = 1.48 + (i % 5) * 0.98
    card(s, 0.45, y, 12.4, 0.9)
    badge(s, 0.62, y + 0.24, str(i + 1))
    text(s, 1.2, y + 0.08, 11.4, 0.32, head, 16, NAVY, bold=True)
    text(s, 1.2, y + 0.42, 11.4, 0.4, body, 13, INK)
source(
    s,
    "Sources: [2] failure reasons; config.yaml fallback model; docs/EVALUATION.md procedure step 5; docs/PROJECT_SCOPE.md exclusions.",
)

# ---------------------------------------------------------------------------
# 19 Module 09 learning
# ---------------------------------------------------------------------------
s = new(
    19,
    "Module 09 Learning",
    "Course ideas used in this project. Each row is the lecture idea, then the code that implements it.",
)
card(s, 0.4, 1.48, 6.25, 4.95)
text(s, 0.6, 1.62, 5.9, 0.38, "GPT-3 class → the planner", 18, NAVY, bold=True)
gpt_rows = [
    ("In-context learning", "A support set plus a query, with no gradient update."),
    (
        "What the prompt holds",
        "Three non-benchmark examples in build_system_prompt, then the user question.",
    ),
    ("What that buys", "The model continues the JSON pattern. qwen3:4b is not fine-tuned."),
]
yy = 2.15
for head, body in gpt_rows:
    text(s, 0.6, yy, 5.85, 0.28, head, 15, AMBER, bold=True)
    text(s, 0.6, yy + 0.3, 5.85, 0.7, body, 14, INK)
    yy += 1.15
card(s, 6.85, 1.48, 6.05, 4.95, CREAM)
text(s, 7.05, 1.62, 5.65, 0.38, "GLM-5 class → the loop", 18, NAVY, bold=True)
glm_rows = [
    ("Agent, not a chatbot", "Fixed nodes: resolve, plan, execute, inspect, replan, finalize."),
    (
        "Revise after evidence",
        "replan_on_failure and replan_on_result. PlanRevision stores the change.",
    ),
    (
        "Choose among tools",
        "Eight tools. The planner selects a subset. Not a mixture-of-experts, and not reinforcement learning.",
    ),
]
yy = 2.15
for head, body in glm_rows:
    text(s, 7.05, yy, 5.65, 0.28, head, 15, AMBER, bold=True)
    text(s, 7.05, yy + 0.3, 5.65, 0.75, body, 14, INK)
    yy += 1.15
source(
    s,
    "Sources: planner.py Examples 1–3; graph.py; replan_on_failure and replan_on_result. Module 09 is the course module for this review.",
)

# ---------------------------------------------------------------------------
# 20 References
# ---------------------------------------------------------------------------
s = new(20, "References")
refs = [
    "[1]  S. Hong et al., “Data Interpreter: An LLM Agent for Data Science,” arXiv:2402.18679v4, 15 Oct 2024. Code: github.com/geekan/MetaGPT.",
    "[2]  evaluation/results/m10-frozen-real-20261117/agent_eval.json. Summary write-up: docs/M10_RESULTS.md.",
    "[3]  config.yaml for the model, seed, temperature, and call timeout.",
    "[4]  evaluation/benchmark/freeze_manifest.json, questions.json, and evaluation/results/recovery_suite/latest.json.",
    "[5]  docs/PROJECT_SCOPE.md, docs/ARCHITECTURE.md, docs/EVALUATION.md, docs/PROGRESS.md.",
    "[6]  src/da_agent/agent/planner.py, graph.py, baseline.py, tools/registry.py, ui/demo.py, reports/renderer.py.",
]
paragraphs(
    s,
    0.6,
    1.45,
    12.1,
    5.2,
    [(line, 16, INK, False, False, PP_ALIGN.LEFT, 12) for line in refs],
)

# ---------------------------------------------------------------------------
# 19 Thank you
# ---------------------------------------------------------------------------
s = prs.slides.add_slide(BLANK)
s.shapes.add_picture(LOGO, Inches(6.17), Inches(0.85), Inches(1.0), Inches(1.0))
line = s.shapes.add_shape(
    MSO_SHAPE.RECTANGLE, Inches(0.78), Inches(2.1), Inches(11.77), Inches(0.045)
)
line.fill.solid()
line.fill.fore_color.rgb = ORANGE
line.line.fill.background()
text(s, 0.8, 2.5, 11.7, 0.8, "Thank you. Questions?", 36, NAVY, align=PP_ALIGN.CENTER)
text(
    s,
    0.8,
    3.5,
    11.7,
    0.45,
    "Evidence-grounded dynamic planning for tabular analysis",
    18,
    INK,
    align=PP_ALIGN.CENTER,
)
text(
    s,
    0.8,
    4.3,
    11.7,
    0.8,
    "Frozen run: m10-frozen-real-20261117\nAgent 13/20 · baseline 20/20 · source [2]",
    16,
    GRAY,
    align=PP_ALIGN.CENTER,
)

out1 = "/mnt/OS/Users/shiva/Documents/Obsidian Vault/College/7th sem/LLM_Project/Evidence-Grounded-Dynamic-Planning.pptx"
out2 = "/home/shivam/ubuntu-sandbox/gitclones/data-analysis-report-generator/docs/Evidence-Grounded-Dynamic-Planning.pptx"
prs.save(out1)
prs.save(out2)
print("saved", out1)
print("slides", len(prs.slides))
