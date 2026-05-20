"""
CEO letter composer — Word doc with embedded Excel table input.

# Pattern source: cfo-helper-internal — the CFO's confirmed format for the
# monthly CEO letter (LCD+7) is "Word doc with Excel table input." We render
# the narrative body in Word and embed the supporting table natively
# (copy-pastable, plays nicely with Track Changes). An OLE-embedded Excel
# object path is available behind a flag if the CFO ever wants the live link.

The composer accepts:
- A markdown narrative (typically `final/exec_summary.md` or a CEO-letter-specific
  `final/ceo_letter_body.md`)
- A pointer to a sibling .xlsx (typically the close pack) plus the sheet/range
  that should appear as the table
- A signature block

It produces a `.docx` with letterhead, narrative, table, signature.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.shared import Pt

from scripts.docx.styles import (
    COLOR_NEUTRAL,
    append_signature_block,
    apply_letterhead,
    register_styles,
)
from scripts.docx.table_from_xlsx import insert_table_from_xlsx


@dataclass
class CEOLetterPayload:
    period: str
    title: str = "CEO Letter"
    org: str | None = None                    # default: profile/company_profile.yaml:company.org_name

    # Narrative — Markdown body. Lightweight conversion: # / ## / ### → headings,
    # blank lines = paragraph breaks, "[claim: <id>]" inline references are
    # converted to small italic footnote-style spans.
    narrative_md: str = ""

    # Table input
    table_xlsx_path: Path | None = None
    table_sheet: str = "P&L"
    table_range: str | None = None  # if None, read full sheet
    table_max_rows: int | None = 25
    table_title: str = "Supporting figures"

    # Signature
    signer_name: str = ""
    signer_role: str = "Chief Financial Officer"

    # Provenance — additional claim_ids referenced in the narrative
    extra_claim_ids: Sequence[str] = field(default_factory=list)


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_CLAIM_REF_RE = re.compile(r"\[claim:\s*([^\]]+)\]")


def _render_markdown(doc: Document, md: str) -> list[str]:
    """Render a small subset of Markdown into Word paragraphs.

    Supports: # headings, blank-line paragraph breaks, `[claim: <id>]` inline
    references (rendered in italic gray small text). Returns list of all
    claim_ids referenced.
    """
    claim_ids: list[str] = []
    paragraphs = md.split("\n\n")
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        m = _HEADING_RE.match(para)
        if m:
            level = min(len(m.group(1)), 2)
            style = f"Heading {level}"
            doc.add_paragraph(m.group(2).strip(), style=style)
            continue
        # Plain paragraph — split out [claim: <id>] markers
        body = doc.add_paragraph()
        cursor = 0
        for match in _CLAIM_REF_RE.finditer(para):
            pre = para[cursor:match.start()]
            if pre:
                body.add_run(pre.replace("\n", " "))
            ref_run = body.add_run(f" [{match.group(1).strip()}]")
            ref_run.font.italic = True
            ref_run.font.size = Pt(8)
            ref_run.font.color.rgb = COLOR_NEUTRAL
            claim_ids.append(match.group(1).strip())
            cursor = match.end()
        tail = para[cursor:]
        if tail:
            body.add_run(tail.replace("\n", " "))
    return claim_ids


def build_ceo_letter(payload: CEOLetterPayload, output_path: Path) -> tuple[Path, list[str]]:
    """Build the CEO letter and return (output_path, claim_ids_referenced)."""
    doc = Document()
    register_styles(doc)
    apply_letterhead(
        doc,
        title=payload.title,
        period=payload.period,
        author=payload.signer_name or payload.signer_role,
        org=payload.org,
    )

    narrative_claim_ids = _render_markdown(doc, payload.narrative_md or "")

    table_claim_ids: list[str] = []
    if payload.table_xlsx_path and payload.table_xlsx_path.exists():
        _, table_claim_ids = insert_table_from_xlsx(
            doc,
            payload.table_xlsx_path,
            sheet=payload.table_sheet,
            range=payload.table_range,
            max_rows=payload.table_max_rows,
            title=payload.table_title,
        )

    if payload.signer_name:
        append_signature_block(doc, name=payload.signer_name, role=payload.signer_role)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))

    all_ids = list(dict.fromkeys(
        list(narrative_claim_ids) + list(table_claim_ids) + list(payload.extra_claim_ids)
    ))
    return (output_path, all_ids)


__all__ = ["CEOLetterPayload", "build_ceo_letter"]
