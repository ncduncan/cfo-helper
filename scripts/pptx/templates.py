"""
Slide primitives for cfo-helper PowerPoint decks.

# Pattern source: anthropics/skills/document-skills/pptx — slide layout
# conventions adapted to python-pptx. We use 16:9 widescreen by default,
# with a consistent header bar and footer carrying the period +
# claim-id reference. The organization name in the footer is read from
# profile/company_profile.yaml via scripts.profile_loader.

Each primitive returns the `Slide` object so the caller can layer additional
content. Notes-pane provenance (`claim_id` references) is set via
`set_provenance_notes(slide, claim_ids)` — call this for every slide that
quotes a number.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from scripts.profile_loader import org_name

# Palette mirrors xlsx.styles + charts.library for cross-deliverable parity.
COLOR_INPUT = RGBColor(0x1F, 0x4E, 0x79)         # blue
COLOR_FORMULA = RGBColor(0x00, 0x00, 0x00)       # black
COLOR_INTERNAL = RGBColor(0x2E, 0x7D, 0x32)      # green
COLOR_EXTERNAL = RGBColor(0xB0, 0x00, 0x20)      # red
COLOR_NEUTRAL = RGBColor(0x6B, 0x72, 0x80)       # gray
COLOR_HEADER_BG = RGBColor(0x1F, 0x29, 0x37)     # dark slate (matches xlsx HEADER_FILL)
COLOR_HEADER_FG = RGBColor(0xFF, 0xFF, 0xFF)

SLIDE_WIDTH = Inches(13.333)
SLIDE_HEIGHT = Inches(7.5)


def new_deck() -> Presentation:
    """Create a fresh 16:9 widescreen presentation."""
    prs = Presentation()
    prs.slide_width = SLIDE_WIDTH
    prs.slide_height = SLIDE_HEIGHT
    return prs


def _blank_slide(prs: Presentation):
    blank = prs.slide_layouts[6]  # 6 = Blank in default template
    return prs.slides.add_slide(blank)


def _add_text(slide, *, left, top, width, height, text,
              font_size=12, bold=False, color=COLOR_FORMULA, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.color.rgb = color
    return box


def _add_footer(slide, *, period: str, slide_no: int = 0, total: int = 0):
    text = f"{org_name()} · {period}"
    if total:
        text += f"  ·  {slide_no} / {total}"
    _add_text(
        slide,
        left=Inches(0.4), top=Inches(7.1),
        width=Inches(12.5), height=Inches(0.3),
        text=text, font_size=9, color=COLOR_NEUTRAL,
    )


def set_provenance_notes(slide, claim_ids: Iterable[str]) -> None:
    """Stamp the speaker-notes pane with `claim_id:` references.

    The pattern matches the XLSX cell-comment convention: every numeric
    assertion on the slide should appear here so a reviewer can audit.
    """
    notes = slide.notes_slide.notes_text_frame
    existing = notes.text or ""
    refs = "\n".join(f"claim_id: {cid}" for cid in claim_ids if cid)
    notes.text = f"{existing}\n{refs}".strip() if existing else refs


def add_title_slide(
    prs: Presentation,
    *,
    title: str,
    subtitle: str = "",
    period: str = "",
    author: str = "",
):
    slide = _blank_slide(prs)
    # Header band
    hdr = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0), Inches(0), SLIDE_WIDTH, Inches(0.5),
    )
    hdr.fill.solid()
    hdr.fill.fore_color.rgb = COLOR_HEADER_BG
    hdr.line.fill.background()

    _add_text(slide,
              left=Inches(0.6), top=Inches(2.4),
              width=Inches(12.0), height=Inches(1.5),
              text=title, font_size=40, bold=True, color=COLOR_INPUT)
    if subtitle:
        _add_text(slide,
                  left=Inches(0.6), top=Inches(3.8),
                  width=Inches(12.0), height=Inches(0.8),
                  text=subtitle, font_size=22, color=COLOR_NEUTRAL)
    meta_text = period
    if author:
        meta_text = f"{period}  ·  {author}" if period else author
    if meta_text:
        _add_text(slide,
                  left=Inches(0.6), top=Inches(6.0),
                  width=Inches(12.0), height=Inches(0.5),
                  text=meta_text, font_size=14, color=COLOR_NEUTRAL)
    return slide


def add_section_divider(prs: Presentation, *, title: str, period: str = ""):
    slide = _blank_slide(prs)
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE,
        Inches(0.6), Inches(3.3), Inches(0.15), Inches(1.0),
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = COLOR_INPUT
    bar.line.fill.background()

    _add_text(slide,
              left=Inches(1.0), top=Inches(3.3),
              width=Inches(11.5), height=Inches(1.0),
              text=title, font_size=36, bold=True, color=COLOR_FORMULA)
    if period:
        _add_footer(slide, period=period)
    return slide


def add_kpi_strip_slide(
    prs: Presentation,
    *,
    title: str,
    kpis: Sequence[Mapping],
    period: str = "",
    claim_ids: Iterable[str] = (),
):
    """KPI strip: 3-6 large numeric tiles across the slide.

    Each kpi: {label, value_text, comparator_text?, role?}. `role` selects
    color: "input" (blue), "internal_link" (green favorable), "external_link"
    (red unfavorable), or "formula" (black).
    """
    slide = _blank_slide(prs)
    _add_text(slide,
              left=Inches(0.6), top=Inches(0.4),
              width=Inches(12.0), height=Inches(0.6),
              text=title, font_size=24, bold=True, color=COLOR_FORMULA)

    role_color = {
        "input": COLOR_INPUT,
        "internal_link": COLOR_INTERNAL,
        "external_link": COLOR_EXTERNAL,
        "formula": COLOR_FORMULA,
    }
    n = len(kpis)
    if n == 0:
        return slide
    margin = Inches(0.6)
    spacing = Inches(0.3)
    total_width = SLIDE_WIDTH - margin * 2 - spacing * (n - 1)
    tile_width = Emu(int(total_width / n))
    tile_top = Inches(2.0)
    tile_height = Inches(3.5)

    for i, k in enumerate(kpis):
        left = margin + Emu(int((tile_width + spacing) * i))
        # Label
        _add_text(slide,
                  left=left, top=tile_top, width=tile_width, height=Inches(0.5),
                  text=k["label"], font_size=12, color=COLOR_NEUTRAL)
        # Value (large)
        color = role_color.get(k.get("role", "input"), COLOR_INPUT)
        _add_text(slide,
                  left=left, top=tile_top + Inches(0.6),
                  width=tile_width, height=Inches(1.6),
                  text=str(k["value_text"]),
                  font_size=44, bold=True, color=color)
        # Comparator (small, with delta)
        if k.get("comparator_text"):
            comp_color = COLOR_INTERNAL if k.get("favorable", True) else COLOR_EXTERNAL
            if k.get("comparator_role") == "neutral":
                comp_color = COLOR_NEUTRAL
            _add_text(slide,
                      left=left, top=tile_top + Inches(2.4),
                      width=tile_width, height=Inches(0.6),
                      text=k["comparator_text"], font_size=12, color=comp_color)

    if period:
        _add_footer(slide, period=period)
    if claim_ids:
        set_provenance_notes(slide, claim_ids)
    return slide


def add_two_column_slide(
    prs: Presentation,
    *,
    title: str,
    left_text: str,
    right_text: str,
    period: str = "",
    claim_ids: Iterable[str] = (),
):
    slide = _blank_slide(prs)
    _add_text(slide,
              left=Inches(0.6), top=Inches(0.4),
              width=Inches(12.0), height=Inches(0.6),
              text=title, font_size=24, bold=True, color=COLOR_FORMULA)
    _add_text(slide,
              left=Inches(0.6), top=Inches(1.3),
              width=Inches(6.0), height=Inches(5.5),
              text=left_text, font_size=14, color=COLOR_FORMULA)
    _add_text(slide,
              left=Inches(7.0), top=Inches(1.3),
              width=Inches(5.7), height=Inches(5.5),
              text=right_text, font_size=14, color=COLOR_FORMULA)
    if period:
        _add_footer(slide, period=period)
    if claim_ids:
        set_provenance_notes(slide, claim_ids)
    return slide


def add_table_slide(
    prs: Presentation,
    *,
    title: str,
    headers: Sequence[str],
    rows: Sequence[Sequence],
    period: str = "",
    claim_ids: Iterable[str] = (),
    highlight_negative_col: int | None = None,
):
    slide = _blank_slide(prs)
    _add_text(slide,
              left=Inches(0.6), top=Inches(0.4),
              width=Inches(12.0), height=Inches(0.6),
              text=title, font_size=24, bold=True, color=COLOR_FORMULA)

    n_rows = len(rows) + 1
    n_cols = len(headers)
    tbl = slide.shapes.add_table(
        n_rows, n_cols,
        Inches(0.6), Inches(1.3),
        Inches(12.1), Inches(5.5),
    ).table

    for c, h in enumerate(headers):
        cell = tbl.cell(0, c)
        cell.text = str(h)
        for run in cell.text_frame.paragraphs[0].runs:
            run.font.bold = True
            run.font.color.rgb = COLOR_HEADER_FG
            run.font.size = Pt(12)
        cell.fill.solid()
        cell.fill.fore_color.rgb = COLOR_HEADER_BG

    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row):
            cell = tbl.cell(r, c)
            cell.text = "" if val is None else str(val)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(11)
                    if highlight_negative_col == c and isinstance(val, (int, float)) and val < 0:
                        run.font.color.rgb = COLOR_EXTERNAL
                    elif highlight_negative_col == c and isinstance(val, (int, float)) and val > 0:
                        run.font.color.rgb = COLOR_INTERNAL

    if period:
        _add_footer(slide, period=period)
    if claim_ids:
        set_provenance_notes(slide, claim_ids)
    return slide


def add_chart_with_callouts_slide(
    prs: Presentation,
    *,
    title: str,
    chart_image_path: Path,
    callouts: Sequence[str],
    period: str = "",
    claim_ids: Iterable[str] = (),
):
    """Chart on left half, bullet callouts on right half."""
    slide = _blank_slide(prs)
    _add_text(slide,
              left=Inches(0.6), top=Inches(0.4),
              width=Inches(12.0), height=Inches(0.6),
              text=title, font_size=24, bold=True, color=COLOR_FORMULA)

    slide.shapes.add_picture(
        str(chart_image_path),
        Inches(0.6), Inches(1.3),
        width=Inches(7.5), height=Inches(5.5),
    )

    # Callouts as a single textbox with bullet-style separators
    callout_text = "\n\n".join(f"•  {c}" for c in callouts)
    _add_text(slide,
              left=Inches(8.4), top=Inches(1.3),
              width=Inches(4.4), height=Inches(5.5),
              text=callout_text, font_size=13, color=COLOR_FORMULA)

    if period:
        _add_footer(slide, period=period)
    if claim_ids:
        set_provenance_notes(slide, claim_ids)
    return slide


def add_variance_commentary_slide(
    prs: Presentation,
    *,
    title: str,
    rows: Sequence[Mapping],
    period: str = "",
    claim_ids: Iterable[str] = (),
):
    """Variance commentary in the archetype × product × mechanism shape.

    Archetypes and product lines come from profile/company_profile.yaml.
    Each row: {archetype, product, mechanism, customer?, variance_usd, narrative}.
    Columns rendered: Archetype | Product | Customer | Variance | Mechanism + narrative.
    """
    headers = ["Archetype", "Product", "Customer", "Variance", "Mechanism / commentary"]
    table_rows = []
    for r in rows:
        table_rows.append([
            r.get("archetype", "—"),
            r.get("product", "—"),
            r.get("customer", "—"),
            f"${r.get('variance_usd', 0):,.0f}",
            f"{r.get('mechanism', '—')}: {r.get('narrative', '')}".strip(": "),
        ])
    return add_table_slide(
        prs,
        title=title,
        headers=headers,
        rows=table_rows,
        period=period,
        claim_ids=claim_ids,
        highlight_negative_col=3,  # Variance column
    )


__all__ = [
    "new_deck",
    "set_provenance_notes",
    "add_title_slide",
    "add_section_divider",
    "add_kpi_strip_slide",
    "add_two_column_slide",
    "add_table_slide",
    "add_chart_with_callouts_slide",
    "add_variance_commentary_slide",
    "SLIDE_WIDTH",
    "SLIDE_HEIGHT",
]
