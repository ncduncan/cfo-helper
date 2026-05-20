"""
Read a sheet (or named range) from an .xlsx and emit a Word table.

# Pattern source: cfo-helper-internal — Anthropic's docx skill assumes you
# author tables natively in docx-js; our deliverables produce the data in
# Excel first (close pack is xlsx-primary) and embed the resulting table
# in Word. This bridge keeps a single source of truth in the xlsx.

Numeric cells preserve their format (USD, %, etc.) by reading the openpyxl
cell's number_format. Cell comments carrying `claim_id` provenance are
copied to the Word table footer so the audit trail isn't lost in
translation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from docx.document import Document as DocumentType
from docx.shared import Pt, RGBColor
from openpyxl import load_workbook

from scripts.docx.styles import COLOR_FORMULA, COLOR_NEUTRAL


def _format_value(cell) -> str:
    """Render an openpyxl cell value using its number_format hint."""
    val = cell.value
    if val is None:
        return ""
    fmt = (cell.number_format or "").lower()
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if "%" in fmt:
            return f"{val * 100:.1f}%" if abs(val) < 10 else f"{val:.1f}%"
        if "$" in fmt or "usd" in fmt or fmt.startswith("#,##0"):
            if "m" in fmt:
                return f"${val/1_000_000:,.1f}M"
            if "k" in fmt:
                return f"${val/1_000:,.0f}K"
            return f"${val:,.0f}"
        if "0.00x" in fmt:
            return f"{val:.2f}x"
        return f"{val:,.0f}" if isinstance(val, int) or val.is_integer() else f"{val:,.2f}"
    return str(val)


def _collect_claim_ids(ws, *, max_row: int, max_col: int) -> list[str]:
    """Pull all `claim_id:` references from cell comments in the active range."""
    ids = []
    for row in ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=max_col):
        for cell in row:
            if cell.comment and "claim_id:" in (cell.comment.text or ""):
                # Comment text is "claim_id: foo.bar" — extract the id
                for line in cell.comment.text.splitlines():
                    line = line.strip()
                    if line.startswith("claim_id:"):
                        cid = line.split(":", 1)[1].strip()
                        if cid and cid not in ids:
                            ids.append(cid)
    return ids


def insert_table_from_xlsx(
    doc: DocumentType,
    xlsx_path: Path,
    *,
    sheet: str,
    range: str | None = None,
    max_rows: int | None = None,
    title: str | None = None,
    style: str = "Light Grid Accent 1",
    include_provenance_footer: bool = True,
) -> tuple[int, list[str]]:
    """Insert a Word table populated from `xlsx_path`'s `sheet`.

    `range` is an optional A1-style range like "A1:E20"; if None, reads the
    whole sheet (up to `max_rows` if specified, else the sheet's used range).

    Returns (row_count, claim_ids) so the caller can tie out / quote in
    the surrounding narrative.
    """
    wb = load_workbook(xlsx_path, data_only=True)
    if sheet not in wb.sheetnames:
        raise ValueError(f"sheet {sheet!r} not in {xlsx_path}: {wb.sheetnames}")
    ws = wb[sheet]

    if range:
        cell_range = ws[range]
    else:
        # iterate full used area
        cell_range = ws[f"A1:{ws.dimensions.split(':')[-1]}"]

    rows = list(cell_range)
    if max_rows is not None:
        rows = rows[: max_rows + 1]  # +1 for header

    if not rows:
        return (0, [])

    n_rows = len(rows)
    n_cols = max(len(r) for r in rows)

    if title:
        h = doc.add_paragraph(style="Heading 2")
        h.add_run(title)

    table = doc.add_table(rows=n_rows, cols=n_cols)
    try:
        table.style = style
    except KeyError:
        # Style may not exist in this template; skip.
        pass

    for r_idx, row in enumerate(rows):
        for c_idx, cell in enumerate(row):
            if c_idx >= n_cols:
                continue
            tcell = table.cell(r_idx, c_idx)
            tcell.text = _format_value(cell)
            for p in tcell.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(10)
                    if r_idx == 0:
                        run.font.bold = True

    claim_ids: list[str] = []
    if include_provenance_footer:
        claim_ids = _collect_claim_ids(ws, max_row=n_rows, max_col=n_cols)
        if claim_ids:
            footer = doc.add_paragraph()
            footer_run = footer.add_run(
                "Sources: " + " · ".join(f"[{cid}]" for cid in claim_ids[:8])
                + ("…" if len(claim_ids) > 8 else "")
            )
            footer_run.font.size = Pt(8)
            footer_run.font.color.rgb = COLOR_NEUTRAL
            footer_run.font.italic = True

    return (n_rows, claim_ids)


__all__ = ["insert_table_from_xlsx"]
