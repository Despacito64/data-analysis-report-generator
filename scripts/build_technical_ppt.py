#!/usr/bin/env python3
"""Build the technical review deck on top of the askMNIT style template.

The template's own TITLE and CONTENT layouts supply the logo, orange title rule,
footer and slide number, so the output matches the template by construction.

Run without changing pyproject.toml (python-pptx is not a project dependency):

    uv run --with python-pptx python scripts/build_technical_ppt.py \
        --template "/path/to/askMNIT_SmritiStyle.pptx" \
        --out docs/Technical-Review-Deck.pptx

Every number on a slide comes from a recorded artifact named in the speaker notes.
"""

from __future__ import annotations

import argparse
import copy
import io
import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_LINE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE, PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

# Palette and type taken from the template theme.
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
BORDER = "C9D3EE"
FONT = "Times New Roman"

# Icon images that ship inside the template (ppt/media/imageN.png).
ICON = {
    "warn": 2, "folders": 3, "search": 4, "megaphone": 5, "brain": 6, "verified": 7,
    "cap": 8, "doc": 9, "merge": 10, "shield": 11, "lock": 12, "bolt": 13, "chat": 14,
    "book": 15, "chip": 16, "gauge": 17, "file": 18, "checklist": 19, "globe": 20,
    "flask": 21, "check": 22, "sliders": 23, "sigma": 24, "cloud": 25, "tag": 26,
    "list": 27, "pencil": 28, "sort": 29, "ban": 30, "bulb": 31, "piggy": 32,
    "spark": 33, "trend": 34, "layers": 35,
}  # fmt: skip


class Deck:
    def __init__(self, template: Path) -> None:
        self.prs = Presentation(str(template))
        self.zip = zipfile.ZipFile(template)
        self.title_layout = self.prs.slides[0].slide_layout
        self.content_layout = self.prs.slides[1].slide_layout
        self.logo_blob = next(
            sh.image.blob for sh in self.prs.slides[0].shapes if sh.shape_type == 13
        )
        number = next(
            sh
            for sh in self.prs.slides[1].shapes
            if sh.is_placeholder and sh.placeholder_format.type == PP_PLACEHOLDER.SLIDE_NUMBER
        )
        self.number_xml = copy.deepcopy(number._element)
        self.title_xml = copy.deepcopy(self.prs.slides[1].shapes.title._element)
        self._icon_cache: dict[str, bytes] = {}
        self.count = 0
        ids = self.prs.slides._sldIdLst
        for sld in list(ids):
            self.prs.part.drop_rel(sld.rId)
            ids.remove(sld)

    # ---- low-level helpers -------------------------------------------------
    def icon_blob(self, name: str) -> bytes:
        if name not in self._icon_cache:
            self._icon_cache[name] = self.zip.read(f"ppt/media/image{ICON[name]}.png")
        return self._icon_cache[name]

    def new_slide(self, layout, notes: str = ""):
        slide = self.prs.slides.add_slide(layout)
        for ph in list(slide.placeholders):
            if ph.placeholder_format.type not in (PP_PLACEHOLDER.TITLE,):
                ph._element.getparent().remove(ph._element)
        self.count += 1
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        return slide

    def content(self, title: str, subtitle: str | None = None, notes: str = ""):
        slide = self.new_slide(self.content_layout, notes)
        slide.shapes._spTree.append(copy.deepcopy(self.title_xml))
        runs = slide.shapes.title.text_frame.paragraphs[0].runs
        runs[0].text = title
        for extra in runs[1:]:
            extra._r.getparent().remove(extra._r)
        slide.shapes._spTree.append(copy.deepcopy(self.number_xml))
        if subtitle:
            text(slide, 0.5, 1.5, 12.33, 0.4, subtitle, 15, GRAY, italic=True)
        return slide


# ---- drawing primitives -----------------------------------------------------
def _style_run(run, size, color, bold=False, italic=False):
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color


def text(slide, l, t, w, h, content, size=15, color=INK, bold=False, italic=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, space_after=0):  # fmt: skip
    """Text box. `content` is a string, or a list of paragraphs; a paragraph is a
    string or a list of (text, size, color, bold, italic) runs."""
    box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    tf.margin_top = tf.margin_bottom = Inches(0.03)
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        runs = para if isinstance(para, list) else [(para, size, color, bold, italic)]
        for r in runs:
            run = p.add_run()
            run.text = r[0]
            _style_run(run, r[1], r[2], r[3], r[4])
    return box


def card(slide, l, t, w, h, fill=BLUE, line=None, dash=False, radius=0.1, line_w=1.5):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h)
    )
    shape.adjustments[0] = min(0.5, radius / min(w, h))
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w)
        if dash:
            shape.line.dash_style = MSO_LINE.DASH
    return shape


def tile(slide, l, t, w, h, fill):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    shape.shadow.inherit = False
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    return shape


def icon(deck: Deck, slide, l, t, d, fill, name):
    oval = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(l), Inches(t), Inches(d), Inches(d))
    oval.shadow.inherit = False
    oval.fill.solid()
    oval.fill.fore_color.rgb = fill
    oval.line.fill.background()
    pad = d * 0.27
    slide.shapes.add_picture(
        io.BytesIO(deck.icon_blob(name)),
        Inches(l + pad),
        Inches(t + pad),
        Inches(d - 2 * pad),
        Inches(d - 2 * pad),
    )


def arrow(slide, x1, y1, x2, y2, color=NAVY):
    line = slide.shapes.add_connector(
        MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2)
    )
    line.line.color.rgb = color
    line.line.width = Pt(2)
    ln = line.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)


def head_body(head, body, hsize=15, bsize=14, hcolor=INK, bcolor=GRAY):
    return [[(head, hsize, hcolor, True, False)], [(body, bsize, bcolor, False, False)]]


def rows_card(deck, slide, left, fill, circle, header, header_icon, items, head_color):
    """Template slide-3 pattern: a header with an icon, then icon rows."""
    card(slide, left, 2.05, 6.0, 4.7, fill)
    icon(deck, slide, left + 0.3, 2.25, 0.55, circle, header_icon)
    text(
        slide,
        left + 1.0,
        2.25,
        4.8,
        0.55,
        header,
        20,
        head_color,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    top = 3.1
    for name, head, body in items:
        icon(deck, slide, left + 0.35, top + 0.06, 0.45, circle, name)
        text(slide, left + 1.0, top, 4.8, 0.85, head_body(head, body))
        top += 0.9


def feature_card(deck, slide, l, t, fill, circle, name, title, sub, body, tcolor):
    card(slide, l, t, 6.0, 2.2, fill)
    icon(deck, slide, l + 0.3, t + 0.3, 0.8, circle, name)
    paras = [[(title, 20, tcolor, True, False)]]
    if sub:
        paras.append([(sub, 13, GRAY, False, True)])
    paras.append([(body, 16, INK, False, False)])
    text(slide, l + 1.3, t + 0.22, 4.55, 1.85, paras, space_after=3)


def number_row(slide, deck, t, h, n, fill, tile_fill, head_color, head, body, icon_name=None):
    tile(slide, 0.5, t, 0.9, h, tile_fill)
    text(
        slide,
        0.5,
        t,
        0.9,
        h,
        str(n),
        24,
        WHITE,
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    card(slide, 1.5, t, 11.33, h, fill, radius=0.08)
    text(
        slide,
        1.7,
        t,
        10.0,
        h,
        head_body(head, body, 17, 13, head_color, INK),
        anchor=MSO_ANCHOR.MIDDLE,
    )
    if icon_name:
        icon(deck, slide, 12.05, t + (h - 0.55) / 2, 0.55, tile_fill, icon_name)


def stat_card(deck, slide, l, t, w, h, fill, circle, name, number, label, sub, ncolor):
    card(slide, l, t, w, h, fill)
    icon(deck, slide, l + w / 2 - 0.25, t + 0.15, 0.5, circle, name)
    text(
        slide,
        l,
        t + 0.7,
        w,
        0.7,
        number,
        38,
        ncolor,
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    text(slide, l + 0.1, t + 1.4, w - 0.2, 0.4, label, 15, INK, bold=True, align=PP_ALIGN.CENTER)
    text(slide, l + 0.15, t + 1.8, w - 0.3, h - 1.85, sub, 12, GRAY, align=PP_ALIGN.CENTER)


def takeaway(deck, slide, t, head, body, h=0.7):
    card(slide, 0.5, t, 12.33, h, BLUE, radius=0.1)
    icon(deck, slide, 0.7, t + (h - 0.45) / 2, 0.45, NAVY, "bulb")
    text(
        slide,
        1.35,
        t,
        11.3,
        h,
        [[(head + "  ", 14, NAVY, True, False), (body, 14, INK, False, False)]],
        anchor=MSO_ANCHOR.MIDDLE,
    )


def _cell_border(cell):
    tcPr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        ln = tcPr.makeelement(qn(tag), {"w": "6350", "cap": "flat", "cmpd": "sng", "algn": "ctr"})
        fill = ln.makeelement(qn("a:solidFill"), {})
        fill.append(fill.makeelement(qn("a:srgbClr"), {"val": BORDER}))
        ln.append(fill)
        tcPr.append(ln)


def table(slide, l, t, widths, header, rows, row_h=0.6, size=13, hsize=14, first_col_navy=True):
    shape = slide.shapes.add_table(
        len(rows) + 1,
        len(widths),
        Inches(l),
        Inches(t),
        Inches(sum(widths)),
        Inches(0.45 + row_h * len(rows)),
    )
    tbl = shape.table
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow"):
        tblPr.set(attr, "0")
    for i, w in enumerate(widths):
        tbl.columns[i].width = Inches(w)
    tbl.rows[0].height = Inches(0.45)
    for r in range(1, len(rows) + 1):
        tbl.rows[r].height = Inches(row_h)

    def fill_cell(cell, value, color, bold, bg, sz, align=PP_ALIGN.LEFT):
        cell.fill.solid()
        cell.fill.fore_color.rgb = bg
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = cell.margin_right = Inches(0.08)
        cell.margin_top = cell.margin_bottom = Inches(0.03)
        tf = cell.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.alignment = align
        run = p.add_run()
        run.text = value
        _style_run(run, sz, color, bold)
        _cell_border(cell)

    for c, value in enumerate(header):
        fill_cell(tbl.cell(0, c), value, WHITE, True, NAVY, hsize, PP_ALIGN.CENTER)
    for r, row in enumerate(rows, start=1):
        bg = BLUE if r % 2 == 1 else WHITE
        for c, value in enumerate(row):
            first = c == 0 and first_col_navy
            fill_cell(tbl.cell(r, c), value, NAVY if first else INK, first, bg, size)
    return shape


def bar_chart(slide, l, t, w, h, categories, series, title=None, horizontal=False, number_format="0", gap=60, legend=False, ymax=None, major_unit=None, axis_format=None):  # fmt: skip
    data = CategoryChartData()
    data.categories = categories
    for name, values, _ in series:
        data.add_series(name, values)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    chart = slide.shapes.add_chart(kind, Inches(l), Inches(t), Inches(w), Inches(h), data).chart
    chart.font.name = FONT
    chart.font.size = Pt(11)
    chart.has_title = bool(title)
    if title:
        chart.chart_title.text_frame.text = title
        run = chart.chart_title.text_frame.paragraphs[0].runs[0]
        _style_run(run, 14, NAVY, False)
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(11)
    plot = chart.plots[0]
    plot.gap_width = gap
    plot.has_data_labels = True
    labels = plot.data_labels
    labels.number_format = number_format
    labels.number_format_is_linked = False
    labels.position = XL_LABEL_POSITION.OUTSIDE_END
    labels.font.bold = True
    labels.font.size = Pt(11)
    for plot_series, (_, _, color) in zip(plot.series, series):
        plot_series.format.fill.solid()
        plot_series.format.fill.fore_color.rgb = color
    value_axis = chart.value_axis
    value_axis.major_gridlines.format.line.color.rgb = RGBColor(0xD9, 0xD9, 0xD9)
    value_axis.format.line.fill.background()
    value_axis.tick_labels.font.size = Pt(10)
    if ymax is not None:
        value_axis.maximum_scale = ymax
    if major_unit is not None:
        value_axis.major_unit = major_unit
    if axis_format is not None:
        value_axis.tick_labels.number_format = axis_format
        value_axis.tick_labels.number_format_is_linked = False
    value_axis.minimum_scale = 0
    chart.category_axis.tick_labels.font.size = Pt(10)
    if horizontal:
        chart.category_axis.reverse_order = True
    return chart


def flow_rows(deck, slide, caption_a, row_a, caption_b, row_b, footer):
    """Two-row card diagram in the template's flow style (captions below the subtitle)."""
    text(slide, 0.5, 1.95, 8.0, 0.4, caption_a, 18, NAVY, bold=True)
    for i, (n, head, body, ic, filled, dashed) in enumerate(row_a):
        l = 0.5 + i * 4.265
        card(slide, l, 2.4, 3.8, 1.35, NAVY if filled else BLUE, line=NAVY, dash=dashed)
        icon(deck, slide, l + 0.2, 2.52, 0.5, AMBER if filled else NAVY, ic)
        text(
            slide,
            l + 0.85,
            2.52,
            2.8,
            0.5,
            f"{n}  {head}",
            17,
            WHITE if filled else NAVY,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(slide, l + 0.2, 3.08, 3.4, 0.62, body, 13, WHITE if filled else INK)
        if i < len(row_a) - 1:
            arrow(slide, l + 3.84, 3.07, l + 4.22, 3.07)
    text(slide, 0.5, 3.9, 8.0, 0.4, caption_b, 18, AMBER, bold=True)
    for i, (n, head, body, ic, filled, dashed) in enumerate(row_b):
        l = 0.5 + i * 3.18
        card(slide, l, 4.35, 2.85, 1.6, ORANGE if filled else CREAM, line=AMBER, dash=dashed)
        icon(deck, slide, l + 0.15, 4.47, 0.48, NAVY if filled else AMBER, ic)
        text(
            slide,
            l + 0.7,
            4.47,
            2.1,
            0.5,
            f"{n}  {head}",
            15,
            WHITE if filled else AMBER,
            bold=True,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(slide, l + 0.15, 5.05, 2.55, 0.85, body, 13, WHITE if filled else INK)
        if i < len(row_b) - 1:
            arrow(slide, l + 2.88, 5.15, l + 3.15, 5.15, AMBER)
    card(slide, 0.5, 6.15, 12.33, 0.6, BLUE)
    text(slide, 0.7, 6.15, 11.9, 0.6, footer, 13, INK, anchor=MSO_ANCHOR.MIDDLE)


# ---- slides -------------------------------------------------------------------
def build(deck: Deck, repo: Path) -> None:
    # 1 Title ------------------------------------------------------------------
    s = deck.new_slide(
        deck.title_layout,
        "Technical review of the data-analysis agent. Names and IDs on this slide need to be confirmed by the presenters.",
    )
    s.shapes.add_picture(
        io.BytesIO(deck.logo_blob), Inches(6.17), Inches(0.40), Inches(1.0), Inches(1.0)
    )
    text(
        s,
        0.8,
        1.6,
        11.73,
        1.3,
        ["Evidence-Grounded Dynamic Planning", "for Tabular Analysis"],
        34,
        NAVY,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    text(
        s,
        0.8,
        3.0,
        11.73,
        0.5,
        "LLM Course Project: Technical Review",
        22,
        INK,
        bold=True,
        align=PP_ALIGN.CENTER,
    )
    text(s, 0.8, 3.6, 11.73, 0.4, "Presented By :", 18, INK, bold=True, align=PP_ALIGN.CENTER)
    shape = s.shapes.add_table(3, 2, Inches(4.17), Inches(4.1), Inches(5.0), Inches(1.26))
    tbl = shape.table
    tbl._tbl.tblPr.set("firstRow", "0")
    tbl._tbl.tblPr.set("bandRow", "0")
    tbl.columns[0].width = Inches(3.0)
    tbl.columns[1].width = Inches(2.0)
    for r, row in enumerate(
        [
            ("Name", "Student ID"),
            ("Shivam Singh", "2023UAI1819"),
            ("Menakshi", "2023UAI2000"),
        ]
    ):
        tbl.rows[r].height = Inches(0.42)
        for c, value in enumerate(row):
            cell = tbl.cell(r, c)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if r == 0 else (BLUE if r == 1 else WHITE)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            run = p.add_run()
            run.text = value
            _style_run(run, 13, WHITE if r == 0 else INK, r == 0)
            _cell_border(cell)
    text(
        s,
        0.8,
        5.55,
        11.73,
        0.4,
        "Department of Artificial Intelligence and Data Engineering, MNIT Jaipur",
        18,
        INK,
        align=PP_ALIGN.CENTER,
    )
    text(s, 0.8, 6.1, 11.73, 0.45, "November 2026", 20, INK, bold=True, align=PP_ALIGN.CENTER)

    # 2 Index ------------------------------------------------------------------
    s = deck.content("Index")
    items = [
        "Problem Statement and Readiness",
        "Project Type",
        "Working Demo",
        "Literature Survey, Base Paper and Gap",
        "Proposed Methodology: Dataset, Architecture, Flow, LLM Technique",
        "Results and Experiments",
        "Future Work",
        "Learning: Module 09",
        "References",
    ]
    text(
        s,
        1.2,
        1.6,
        10.5,
        5.2,
        [[(f"{i}.  {item}", 21, INK, False, False)] for i, item in enumerate(items, 1)],
        space_after=8,
    )

    # 3 Problem ----------------------------------------------------------------
    s = deck.content(
        "Problem Statement",
        "A question in plain language needs a checked chain of calculations, and neither fixed pipelines nor free-form code provide one.",
        "Motivation. The design rule is 'the LLM proposes, code disposes' (AGENTS.md rule 2).",
    )
    rows_card(deck, s, 0.5, BLUE, NAVY, "Why current approaches fall short", "warn", [
        ("list", "Fixed workflows", "Run the same steps whatever the first result shows"),
        ("search", "Generated code", "Model-written Python can fail or run unsafe code"),
        ("megaphone", "Fluent but unchecked", "A sentence can state a number no computation produced"),
        ("chip", "Small local models", "Privacy favours on-device models, which plan less reliably"),
    ], NAVY)  # fmt: skip
    rows_card(deck, s, 6.83, CREAM, AMBER, "What this project builds", "verified", [
        ("merge", "Dynamic planning", "The model plans typed tasks and revises pending ones"),
        ("shield", "Allowlisted tools", "Eight registered functions compute every number"),
        ("check", "Evidence records", "Each reported number links to a recorded computation"),
        ("gauge", "Measured honestly", "Frozen questions scored by an independent oracle"),
    ], AMBER)  # fmt: skip

    # 4 Readiness --------------------------------------------------------------
    s = deck.content(
        "Readiness (TRL)",
        "TRL 4 is our assessment for this review; no project file assigns a TRL.",
        "TRL 4 = component validated in a laboratory setting. Evidence: 328 passing tests, frozen benchmark, recovery suite.",
    )
    rows_card(deck, s, 0.5, BLUE, NAVY, "Why TRL 4", "verified", [
        ("flask", "Validated in the lab", "One dataset, 20 frozen questions, independent oracle"),
        ("checklist", "Tested", "328 unit and integration tests pass"),
        ("shield", "Failure handling", "12 recovery scenarios pass (mock, no benchmark data)"),
        ("layers", "Working application", "FastAPI service with React and Streamlit interfaces"),
    ], NAVY)  # fmt: skip
    rows_card(deck, s, 6.83, CREAM, AMBER, "What stops a higher level", "warn", [
        ("folders", "One dataset", "Sample Superstore only; no claim beyond it"),
        ("chip", "Small model", "qwen3:4b-instruct passes 10 to 18 of 20 questions"),
        ("ban", "No field trial", "No real users, no deployment, no authentication"),
        ("sliders", "Known gaps", "Two questions still fail; replanning lowered the score"),
    ], AMBER)  # fmt: skip

    # 5 Project type -----------------------------------------------------------
    s = deck.content(
        "Project Type",
        "Application-based project, with a small exploratory part that is labelled as such.",
        "Answer to the question from the course instructor: application-based.",
    )
    feature_card(deck, s, 0.5, 2.05, BLUE, NAVY, "layers", "A working application", "FastAPI, React 19, Streamlit",
                 "Upload a CSV or XLSX, ask a question, get an evidence-linked HTML report.", NAVY)  # fmt: skip
    feature_card(deck, s, 6.83, 2.05, CREAM, AMBER, "shield", "Engineering focus", "Tools, validators, contracts",
                 "Eight registered tools, typed contracts, five validation layers and 328 tests.", AMBER)  # fmt: skip
    feature_card(deck, s, 0.5, 4.45, CREAM, AMBER, "gauge", "Measured, not only built", "Frozen benchmark",
                 "20 questions scored against separately computed expected answers, one run each.", AMBER)  # fmt: skip
    feature_card(deck, s, 6.83, 4.45, BLUE, NAVY, "flask", "Exploratory part", "Two small runs after the benchmark",
                 "A replanning ablation and a four-model comparison, each shown with its limits.", NAVY)  # fmt: skip

    # 6 Demo -------------------------------------------------------------------
    s = deck.content(
        "Working Demo",
        "Real output from a recorded run (a local 4B model, 'What are total sales by category?'). A 60-90 s screen recording goes here.",
        "Screenshot of demo/report.html, produced by demo/run_real_demo.py with the real model (meta.json: mock false). Live demo questions: q03, q09, q19.",
    )
    s.shapes.add_picture(
        str(repo / "docs/assets/demo_report.png"), Inches(0.5), Inches(2.0), height=Inches(4.7)
    )
    card(s, 5.3, 2.05, 7.53, 3.0, CREAM)
    steps = [
        ("1", "Load Sample Superstore", "Profile and dataset hash appear"),
        ("2", "Ask in plain language", "For example: total sales for each Region"),
        ("3", "Watch plan, tools, evidence", "Live trace of every task"),
        ("4", "Open the report", "Each number links to its evidence record"),
    ]
    top = 2.2
    for n, head, body in steps:
        circ = s.shapes.add_shape(
            MSO_SHAPE.OVAL, Inches(5.55), Inches(top + 0.05), Inches(0.5), Inches(0.5)
        )
        circ.shadow.inherit = False
        circ.fill.solid()
        circ.fill.fore_color.rgb = AMBER
        circ.line.fill.background()
        text(
            s,
            5.55,
            top + 0.05,
            0.5,
            0.5,
            n,
            16,
            WHITE,
            bold=True,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(s, 6.25, top, 6.4, 0.65, head_body(head, body))
        top += 0.7
    card(s, 5.3, 5.3, 7.53, 1.4, WHITE, line=NAVY, dash=True)
    text(s, 5.5, 5.3, 7.1, 1.4, [
        [("Screen recording slot", 16, NAVY, True, False)],
        [("Planned clip: q03 (one tool), q09 (period compare), q19 (two-step plan).", 13, GRAY, False, True)],
    ], anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)  # fmt: skip

    # 7 Literature -------------------------------------------------------------
    s = deck.content(
        "Literature Survey",
        "Lines of work cited by the base paper, and what each leaves open for trustworthy numbers.",
        "Families and examples are taken from the related-work section of Data Interpreter (pp. 3, 11-14). The 'leaves open' column is our reading, not a claim made by those papers.",
    )
    table(s, 0.5, 2.0, [2.6, 4.3, 5.43], ["Line of work", "Examples", "What it leaves open (our reading)"], [
        ["Code as reasoning", "PAL, Program of Thoughts, ToRA", "Model-written code runs unchecked; errors and unsafe code reach the run"],
        ["Data-science agents", "Data-Copilot, DS-Agent, AutoGen, TaskWeaver, OpenInterpreter", "Mostly free-form code; judged on task success, not on per-number evidence"],
        ["Tool use", "Toolformer, HuggingGPT, TaskMatrix.AI", "Choose tools, but nothing checks that reported numbers match tool output"],
        ["Graph-based planning", "CoT, ReAct, Tree and Graph of Thoughts", "Structure the reasoning; no domain execution or evidence trail"],
        ["Reflection", "Reflexion", "Retries from errors; keeps no record linking answers to computations"],
    ], row_h=0.72)  # fmt: skip
    text(
        s,
        0.5,
        6.4,
        12.33,
        0.35,
        "Source: related-work discussion in Data Interpreter, arXiv 2402.18679.",
        12,
        GRAY,
        italic=True,
    )

    # 8 Base paper -------------------------------------------------------------
    s = deck.content(
        "Base Paper: Data Interpreter",
        "Hong et al., arXiv 2402.18679 (v4, Oct 2024): an LLM agent for data science built on task graphs that change while it runs.",
        "Numbers from the paper: DABench Table 1 (p.8), ML-Benchmark Table 2 (p.9), MATH Fig. 4 (p.9), ablation Table 4 (p.10), limits Appendix A (p.15). Different tasks and models from this project, so the scores are not comparable.",
    )
    number_row(
        s,
        deck,
        1.95,
        1.1,
        1,
        BLUE,
        NAVY,
        NAVY,
        "Hierarchical graph modeling",
        "A project becomes a task graph; each task becomes an action graph of executable code.",
        "layers",
    )
    number_row(
        s,
        deck,
        3.17,
        1.1,
        2,
        CREAM,
        AMBER,
        AMBER,
        "Iterative graph refinement",
        "On failure: reflect and retry, then regenerate the task graph and keep every task before the first change.",
        "merge",
    )
    number_row(
        s,
        deck,
        4.39,
        1.1,
        3,
        BLUE,
        NAVY,
        NAVY,
        "Programmable node generation",
        "Retrieve tools by schema, then write one code snippet that mixes tool calls with pandas and numpy.",
        "chip",
    )
    # narrow the rows to leave room for the stats on the right
    # (rows span the full width; stats sit below)
    for i, (num, label, sub) in enumerate([
        ("94.9%", "InfiAgent-DABench", "gpt-4o; 75.9% without the agent"),
        ("0.95", "ML-Benchmark", "average score over Kaggle tasks"),
        ("0.37 to 0.94", "Ablation", "code only versus full method"),
    ]):  # fmt: skip
        l = 0.5 + i * 4.19
        card(s, l, 5.65, 3.95, 1.1, BLUE if i % 2 == 0 else CREAM)
        text(
            s,
            l,
            5.68,
            3.95,
            0.55,
            num,
            26,
            NAVY if i % 2 == 0 else AMBER,
            bold=True,
            align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        text(
            s,
            l,
            6.2,
            3.95,
            0.5,
            [[(label + ": ", 12, INK, True, False), (sub, 12, GRAY, False, False)]],
            align=PP_ALIGN.CENTER,
        )

    # 9 Gap --------------------------------------------------------------------
    s = deck.content(
        "Gap and Our Position",
        "Keep the task graph that changes while it runs; take free-form code out of the path that produces a number.",
        "Admitted limits in the paper (Appendix A, p.15): entry-level Kaggle data only, and executing generated code is a security risk. The comparison is by design choice, not by score.",
    )
    table(s, 0.5, 2.0, [2.5, 4.9, 4.93], ["Aspect", "Data Interpreter", "This project"], [
        ["Computation path", "LLM-written Python executed in a runtime", "Eight registered, tested tools"],
        ["Task graph", "Task and action graphs, regenerated on failure", "Typed task DAG, revised from results or failures"],
        ["Where numbers come from", "Code output", "EvidenceRecord with argument and dataset hashes"],
        ["Output check", "Run the code, reflect on errors", "Claims matched to evidence (rtol 0.001), unsupported claims dropped"],
        ["Model", "GPT-4 class (gpt-4o, gpt-4-0613)", "qwen3:4b-instruct on a local machine through Ollama"],
        ["Evaluation", "Public benchmarks, task success", "20 questions, independent oracle, one run each"],
    ], row_h=0.58, size=13)  # fmt: skip
    takeaway(
        deck,
        s,
        6.05,
        "Not comparable:",
        "different tasks, models and benchmarks. We claim a different design point, not a higher score.",
        h=0.7,
    )

    # 10 Dataset ---------------------------------------------------------------
    s = deck.content(
        "Dataset and Benchmark",
        "One registered retail file; the frozen question set is what was scored.",
        "Dataset: Sample-Superstore.csv, SHA-256 dc81c957... (D-007). Questions: evaluation/benchmark/questions.json (20, frozen by hash in freeze_manifest.json). Oracle: evaluation/oracle.py.",
    )
    bar_chart(s, 0.5, 1.95, 7.3, 4.8, ["group_aggregate", "rank", "filter", "period_compare", "trend", "segment_contribution", "correlation", "anomalies", "multistep"],
              [("Questions", [3, 3, 2, 2, 2, 2, 2, 2, 2], NAVY)], title="Frozen questions by category", horizontal=True, ymax=4, major_unit=1)  # fmt: skip
    card(s, 8.1, 2.05, 4.73, 2.2, BLUE)
    text(
        s,
        8.1,
        2.15,
        4.73,
        0.8,
        "9,994 \u00d7 22",
        38,
        NAVY,
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    text(
        s,
        8.2,
        2.95,
        4.53,
        0.4,
        "rows \u00d7 columns, Sample Superstore",
        15,
        INK,
        bold=True,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        8.25,
        3.4,
        4.43,
        0.8,
        "File identified by its SHA-256 hash; no row or column count is assumed in code.",
        12,
        GRAY,
        align=PP_ALIGN.CENTER,
    )
    card(s, 8.1, 4.45, 4.73, 2.3, CREAM)
    text(
        s,
        8.1,
        4.55,
        4.73,
        0.8,
        "20",
        38,
        AMBER,
        bold=True,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    text(
        s,
        8.2,
        5.35,
        4.53,
        0.4,
        "frozen evaluation questions",
        15,
        INK,
        bold=True,
        align=PP_ALIGN.CENTER,
    )
    text(
        s,
        8.25,
        5.8,
        4.43,
        0.9,
        "Expected answers come from a separate pandas / numpy script that imports none of the agent code.",
        12,
        GRAY,
        align=PP_ALIGN.CENTER,
    )

    # 11 Architecture ----------------------------------------------------------
    s = deck.content(
        "Model Architecture",
        "One local LLM plans; registered code computes; validators and evidence records sit between them.",
        "Layer rules are tested in tests/test_import_rules.py; the oracle must not import da_agent.tools, agent, validation or reports.",
    )
    flow_rows(
        deck, s,
        "A. Application layers",
        [
            ("1", "Interface", "React 19 + Vite chat UI, FastAPI service, Streamlit app", "layers", False, False),
            ("2", "Data layer", "CSV/XLSX loader, input checks, profiler, SHA-256 hash", "folders", False, False),
            ("3", "Planner", "qwen3:4b-instruct via Ollama, 3-shot JSON-schema prompt, LangGraph", "brain", True, False),
        ],
        "B. Deterministic core",
        [
            ("4", "Tool registry", "Eight allowlisted tools with typed arguments", "chip", False, False),
            ("5", "Validators", "Plan, argument, result and claim checks", "shield", False, False),
            ("6", "Evidence store", "One EvidenceRecord per task, JSONL run trace", "file", False, False),
            ("7", "Report", "Escaped HTML and JSON, grounded narration", "doc", True, False),
        ],
        "Lower layers never import higher ones; the oracle imports none of the agent code (both enforced by tests).",
    )  # fmt: skip

    # 12 Flow ------------------------------------------------------------------
    s = deck.content(
        "Flow Diagram",
        "Both the dynamic agent and the baseline follow this path; only planning and replanning differ.",
        "Nodes and edges: src/da_agent/agent/graph.py (plan, validate_repair, execute, inspect, replan, finalize). The baseline uses a fixed per-question plan and never replans.",
    )
    flow_rows(
        deck, s,
        "A. Understand and plan",
        [
            ("1", "Profile", "Load CSV/XLSX, check limits, hash, profile columns", "folders", False, False),
            ("2", "Plan", "LLM returns typed tasks with dependencies as JSON", "pencil", False, False),
            ("3", "Validate", "Known tools, real columns, acyclic DAG; re-prompt on errors", "checklist", False, False),
        ],
        "B. Execute, inspect, revise, report",
        [
            ("4", "Execute", "Run ready tasks with registered tools; store evidence", "chip", False, False),
            ("5", "Inspect", "Success, retry, replan or stop within budgets", "search", False, False),
            ("6", "Replan", "Add, change or cancel pending tasks", "merge", False, True),
            ("7", "Finalize", "Claim check, report, narration", "doc", True, False),
        ],
        "The control graph is fixed; the task graph inside it changes during a run. Dashed step: used only when a result or failure calls for it.",
    )  # fmt: skip

    # 13 LLM technique ---------------------------------------------------------
    s = deck.content(
        "LLM Technique",
        "In-context learning with a fixed prompt and a JSON schema. No fine-tuning, and the model never computes a number.",
        "Prompt: build_system_prompt in src/da_agent/agent/planner.py (3 few-shot examples, lines ~242-309). The schema is passed to Ollama as the format field. Temperature 0 and seed 42 come from config.yaml.",
    )
    rows_card(deck, s, 0.5, BLUE, NAVY, "Planner prompt", "brain", [
        ("book", "Three few-shot plans", "Example question and plan pairs act as the support set"),
        ("list", "Eight tool specs", "Tool schemas plus each column's name and semantic type"),
        ("sliders", "JSON-schema output", "The reply is constrained to a list of typed tasks"),
        ("gauge", "Fixed decoding", "Temperature 0, seed 42, local qwen3:4b-instruct, no fine-tuning"),
    ], NAVY)  # fmt: skip
    rows_card(deck, s, 6.83, CREAM, AMBER, "Where the model is called", "chat", [
        ("pencil", "Plan", "Writes the first typed task DAG for the question"),
        ("merge", "Replan", "After a failure, or after a complete result, edits pending tasks"),
        ("megaphone", "Narrate", "Writes prose from validated claim lines; discarded if it adds a number"),
        ("ban", "Never computes", "Every number comes from a registered tool"),
    ], AMBER)  # fmt: skip

    # 14 Validation ------------------------------------------------------------
    s = deck.content(
        "Validation Layers",
        "Five checks between the model and the reader. A number that fails the last check is dropped, not shown.",
        "Modules: src/da_agent/validation/{plan_check,args,results,claims}.py plus input checks in the data layer. Tolerances from config.yaml (rtol 0.001, atol 0.01, drop_finding).",
    )
    layers = [
        ("Input", "Extension allowlist, size and row limits, empty and corrupt files", "folders"),
        ("Plan", "Known tools only, steps bounded, dependencies form a DAG", "checklist"),
        (
            "Arguments",
            "Tool arguments and column names checked against schemas and the dataset profile",
            "sliders",
        ),
        ("Result", "Output schema and numerical invariants checked per tool", "sigma"),
        (
            "Claim",
            "Each number matched to an EvidenceRecord (rtol 0.001, atol 0.01); unsupported claims dropped",
            "shield",
        ),
    ]
    for i, (head, body, ic) in enumerate(layers):
        odd = i % 2 == 0
        number_row(
            s,
            deck,
            1.95 + i * 0.86,
            0.76,
            i + 1,
            BLUE if odd else CREAM,
            NAVY if odd else AMBER,
            NAVY if odd else AMBER,
            head,
            body,
            ic,
        )
    takeaway(
        deck,
        s,
        6.3,
        "Recovery suite:",
        "12 mock-only failure scenarios pass; none uses benchmark questions or oracle answers.",
        h=0.55,
    )

    # 15 Results ---------------------------------------------------------------
    s = deck.content(
        "Results: Replanning On and Off",
        "20 questions, one run each, qwen3:4b-instruct through Ollama. R1: replanning on. R2: replanning off.",
        "Source: saved evaluation results (agent_eval.json) for the two runs. The system was fixed after an earlier run on the same questions, so these are not held-out results. Baseline: BASELINE_TASKS keyed by question id (baseline.py).",
    )
    cards = [
        (
            "10/20",
            "R1: replanning on",
            "84 LLM calls, 29 min",
            BLUE,
            NAVY,
            NAVY,
            "brain",
        ),
        (
            "18/20",
            "R2: replanning off",
            "42 LLM calls, 12 min",
            CREAM,
            AMBER,
            AMBER,
            "list",
        ),
        (
            "20/20",
            "Fixed baseline",
            "Keyed by question id: a ceiling, not a competitor",
            BLUE,
            NAVY,
            NAVY,
            "list",
        ),
        (
            "12/12",
            "Recovery suite",
            "Mock-only failure scenarios",
            CREAM,
            AMBER,
            AMBER,
            "gauge",
        ),
    ]
    for i, (num, label, sub, fill, circ, ncolor, ic) in enumerate(cards):
        stat_card(
            deck, s, 0.5 + i * 3.12, 2.05, 2.97, 2.45, fill, circ, ic, num, label, sub, ncolor
        )
    text(s, 0.5, 4.7, 12.33, 0.4, "Per category", 17, NAVY, bold=True)
    icon(deck, s, 0.55, 5.18, 0.38, GREEN, "check")
    text(
        s,
        1.1,
        5.1,
        11.7,
        0.55,
        [
            [
                ("Passed: ", 14, INK, True, False),
                (
                    "R2 passes group_aggregate 3/3, rank 3/3, filter 2/2, period_compare 2/2, segment_contribution 2/2, correlation 2/2, anomalies 2/2",
                    14,
                    INK,
                    False,
                    False,
                ),
            ]
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    icon(deck, s, 0.55, 5.78, 0.38, AMBER, "ban")
    text(
        s,
        1.1,
        5.7,
        11.7,
        0.55,
        [
            [
                ("Failed: ", 14, INK, True, False),
                (
                    "R2 fails trend 1/2 (q11) and multistep 1/2 (q20); R1 also loses 8 more",
                    14,
                    INK,
                    False,
                    False,
                ),
            ]
        ],
        anchor=MSO_ANCHOR.MIDDLE,
    )
    takeaway(
        deck,
        s,
        6.3,
        "Reading it:",
        "Replanning on passes 10 of 20, off passes 18 of 20. The system was fixed after an earlier run on the same questions.",
        h=0.55,
    )

    # 16 Failures --------------------------------------------------------------
    s = deck.content(
        "Results: Why Replanning Lowered the Score",
        "Same first plan in both runs. In R1 the inspection step then added tasks, and the last task's output was scored.",
        "Method: for each question, compared the plan versions and executed tools in the two runs (runs/<id>/trace.jsonl). First plans have the same tool list for all 20 questions.",
    )
    cats = [
        "group_aggregate",
        "period_compare",
        "segment_contribution",
        "correlation",
        "anomalies",
        "filter",
        "multistep",
        "rank",
        "trend",
    ]
    r1 = [1 / 3, 1 / 2, 2 / 2, 2 / 2, 0, 2 / 2, 0, 2 / 3, 0]
    r2 = [3 / 3, 2 / 2, 2 / 2, 2 / 2, 2 / 2, 2 / 2, 1 / 2, 3 / 3, 1 / 2]
    bar_chart(s, 0.5, 1.95, 7.4, 4.8, [c.replace("_", " ") for c in cats],
              [("R1 replanning on", r1, NAVY), ("R2 replanning off", r2, AMBER)], title="Share of questions passed, by category", number_format="0%", ymax=1.15, major_unit=0.25, axis_format="0%", legend=True)  # fmt: skip
    card(s, 8.1, 2.05, 4.73, 4.7, CREAM)
    text(s, 8.3, 2.15, 4.4, 0.5, "Diagnosed causes", 20, AMBER, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    causes = [
        (
            "q03, q04, q06, q09, q12, q17, q18, q19",
            "Pass with replanning off. In R1 the inspection step added tasks (2 to 4 plan versions) after a correct first result.",
        ),
        (
            "Example: q03",
            "One group_aggregate by Region was right. Four replan calls added more analyses; the answer became profit shares by segment.",
        ),
        (
            "q11, q20 (fail in both)",
            "q11: no 2017 restriction in the plan. q20: rank had no aggregation and works on the table, not the grouped output.",
        ),
    ]
    top = 2.75
    for head, body in causes:
        text(s, 8.3, top, 4.4, 0.95, head_body(head, body, 14, 13))
        top += 1.3

    # 17 Experiments -----------------------------------------------------------
    s = deck.content(
        "Results: Replanning Ablation and Model Comparison",
        "Replanning off against on, and four local models, one run per question.",
        "R2 sets the replan limit to zero and changes nothing else. The four-model comparison used replanning on for every model. All runs: one run per question, temperature 0, seed 42.",
    )
    card(s, 0.5, 2.05, 6.0, 4.0, BLUE)
    text(
        s,
        0.7,
        2.15,
        5.6,
        0.5,
        "Ablation: replanning off (R2)",
        19,
        NAVY,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    text(s, 0.7, 2.7, 5.6, 0.9, "18 / 20", 38, NAVY, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.7, 3.5, 5.6, 2.4, [
        [("With replanning (R1): 10 / 20", 16, INK, False, False)],
        [("Eight questions pass only without replanning", 16, INK, False, False)],
        [("LLM calls 84 to 42; time 29 to 12 minutes", 16, INK, False, False)],
        [("The model added analyses; the last task was scored", 16, INK, False, False)],
    ], space_after=9)  # fmt: skip
    card(s, 6.83, 2.05, 6.0, 4.0, CREAM)
    text(
        s,
        7.03,
        2.15,
        5.6,
        0.5,
        "Four models (replanning on)",
        19,
        AMBER,
        bold=True,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    table(s, 7.03, 2.8, [3.3, 2.3], ["Model", "Passed of 20"], [
        ["qwen3:4b-instruct", "10"],
        ["qwen2.5:7b-instruct", "8"],
        ["llama3.2:3b", "2"],
        ["qwen2.5:3b-instruct", "1"],
    ], row_h=0.4, size=14)  # fmt: skip
    text(s, 7.03, 5.1, 5.6, 0.9, [
        [("Other models were not run with replanning off", 14, INK, False, False)],
        [("7B does not fit in 4 GB, so timings are not comparable", 14, INK, False, False)],
    ], space_after=8)  # fmt: skip
    takeaway(
        deck,
        s,
        6.2,
        "Next:",
        "read the answer from the designated task, and add longer questions where replanning can matter.",
        h=0.6,
    )

    # 18 Cost ------------------------------------------------------------------
    s = deck.content(
        "Results: Cost and Latency",
        "Time goes to the local model, not to the tools (summed over the 20 question runs of R1).",
        "Source: R1 stage timings from agent_eval.json (replanning 971 s, plan generation 636 s, repair 187 s, answer synthesis 35 s, tool execution 3 s of 1,736 s). Repair prompts run inside planning and replanning calls, so stage times overlap.",
    )
    bar_chart(s, 0.5, 1.95, 7.4, 4.8, ["Replanning", "Plan generation", "Repair", "Answer synthesis", "Tool execution"],
              [("R1 seconds", [971, 636, 187, 35, 3], NAVY)], title="Aggregate time by stage, R1 (seconds)", horizontal=True, number_format="#,##0", ymax=1200)  # fmt: skip
    stat_card(
        deck,
        s,
        8.1,
        2.05,
        4.73,
        2.2,
        BLUE,
        NAVY,
        "gauge",
        "0.2%",
        "Share spent in tools",
        "3 s of 1,736 s (R1)",
        NAVY,
    )
    card(s, 8.1, 4.45, 4.73, 2.3, CREAM)
    text(s, 8.3, 4.55, 4.35, 0.45, "Replanning is costly", 18, AMBER, bold=True)
    text(
        s,
        8.3,
        5.05,
        4.35,
        1.65,
        "Turning replanning off (R2) cut LLM calls from 84 to 42 and time from 29 to 12 minutes, and raised the score from 10 to 18 of 20.",
        13,
        INK,
    )

    # 19 Future work -----------------------------------------------------------
    s = deck.content(
        "Future Work",
        "Next steps stay inside the current scope (single agent, registered tools, no code execution).",
        "Items 1-2 follow directly from the failure diagnosis; the results are not held-out, so item 3 matters most.",
    )
    future = [
        (
            "Answer from the designated task",
            "Read the answer from the task the plan marks as final, not the last one to run, so added analyses cannot displace a correct result.",
            "merge",
        ),
        (
            "Fix the two remaining failures",
            "Restrict trends to the period asked about (q11); let rank work on grouped output (q20).",
            "sliders",
        ),
        (
            "Test replanning properly",
            "Longer dependent questions where a result should change the next step, plus a stop rule for the inspection step.",
            "flask",
        ),
        (
            "Evaluate on unseen questions",
            "A held-out set, and an external benchmark such as InfiAgent-DABench for the subset our tools cover.",
            "chip",
        ),
        (
            "Widen coverage",
            "A second dataset, more registered tools, and measuring the claim checker and narration directly.",
            "folders",
        ),
    ]
    for i, (head, body, ic) in enumerate(future):
        odd = i % 2 == 0
        number_row(
            s,
            deck,
            1.95 + i * 0.95,
            0.85,
            i + 1,
            BLUE if odd else CREAM,
            NAVY if odd else AMBER,
            NAVY if odd else AMBER,
            head,
            body,
            ic,
        )

    # 20 Module 09 -------------------------------------------------------------
    s = deck.content(
        "Module 09 Learning",
        "Class ideas used as design guides. The GLM-5 links are analogies: this project has no RL training or mixture-of-experts.",
        "GPT-3 side: planner.py build_system_prompt (3 few-shot examples) with the schema passed as Ollama format. GLM-5 side is analogy only: graph.py control graph, PlanRevision in contracts/models.py, the 8-tool registry.",
    )
    rows_card(deck, s, 0.5, BLUE, NAVY, "GPT-3 class: in-context learning", "book", [
        ("book", "Support set plus query", "Three example plans, then the user's question"),
        ("ban", "No gradient updates", "No fine-tuning; the prompt is the only adaptation"),
        ("sliders", "Prompt format matters", "Tool specs, column types and a JSON schema fix the output"),
        ("pencil", "Pattern completion", "The model continues the examples into a new typed plan"),
    ], NAVY)  # fmt: skip
    rows_card(deck, s, 6.83, CREAM, AMBER, "GLM-5 class: agentic engineering", "layers", [
        ("merge", "Plan, act, observe loop", "Fixed control graph: plan, execute, inspect, replan"),
        ("chip", "Generation apart from execution", "The model proposes tasks; registered code runs them"),
        ("list", "Versioned revisions", "PlanRevision records the version change and its trigger"),
        ("spark", "Selective tool routing", "A few of eight tools per plan (analogy to sparse experts)"),
    ], AMBER)  # fmt: skip

    # 22 References ------------------------------------------------------------
    s = deck.content(
        "References",
        None,
        "Families and papers listed are those cited in the related-work section of the base paper; years follow that paper's reference list.",
    )
    refs = [
        "[1] Hong et al., Data Interpreter: An LLM Agent For Data Science, arXiv:2402.18679 (v4, 2024).",
        "[2] Gao et al., PAL: Program-aided Language Models (2023); Chen et al., Program of Thoughts Prompting (2022); Gou et al., ToRA (2024), as cited in [1].",
        "[3] Guo et al., DS-Agent (2024); Data-Copilot; AutoGen; TaskWeaver, as cited in [1].",
        "[4] Toolformer (Schick et al.); HuggingGPT (Shen et al.), as cited in [1].",
        "[5] Shinn et al., Reflexion: Language Agents with Verbal Reinforcement Learning, as cited in [1].",
        "[6] Qwen3 family (qwen3:4b-instruct) served locally with Ollama; LangGraph; pandas and numpy (tools and oracle).",
        "[7] Sample Superstore dataset, registered in docs/DECISIONS.md D-007 (SHA-256 dc81c957...).",
        "[8] Project code and experiments: github.com/Despacito64/data-analysis-report-generator (branch shivam).",
    ]
    text(s, 0.6, 1.7, 12.1, 5.0, [[(r, 14, INK, False, False)] for r in refs], space_after=9)

    # 23 Thank you -------------------------------------------------------------
    s = deck.new_slide(deck.title_layout, "Closing slide.")
    s.shapes.add_picture(
        io.BytesIO(deck.logo_blob), Inches(6.17), Inches(0.85), Inches(1.0), Inches(1.0)
    )
    text(
        s,
        0.8,
        2.6,
        11.73,
        0.9,
        "Thank You! Questions?",
        38,
        NAVY,
        align=PP_ALIGN.CENTER,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    text(s, 0.8, 4.6, 11.73, 0.9, [
        [("Code: ", 16, INK, True, False), ("github.com/Despacito64/data-analysis-report-generator", 16, NAVY, True, False)],
        [("Experiments: docs/EXPERIMENTS_SUMMARY.md   Developer guide: docs/DEVELOPER_GUIDE.md", 14, GRAY, False, False)],
    ], align=PP_ALIGN.CENTER, space_after=6)  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/Technical-Review-Deck.pptx"))
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    deck = Deck(args.template)
    build(deck, repo)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    deck.prs.save(str(args.out))
    print(f"wrote {args.out} ({deck.count} slides)")


if __name__ == "__main__":
    main()
