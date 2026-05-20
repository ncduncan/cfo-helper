"""
Word document styling for cfo-helper deliverables.

# Pattern source: anthropics/skills/document-skills/docx — their skill
# enforces explicit page dimensions in DXA units (1440 DXA = 1 inch),
# smart quotes, and table widths as arrays. We follow the same conventions.

Provides reusable style registration and a letterhead applicator. The
visual language matches the XLSX/PPTX palette so deliverables are
visually coherent.
"""

from __future__ import annotations

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

# Mirror scripts.xlsx.styles palette
COLOR_INPUT = RGBColor(0x1F, 0x4E, 0x79)
COLOR_FORMULA = RGBColor(0x00, 0x00, 0x00)
COLOR_NEUTRAL = RGBColor(0x6B, 0x72, 0x80)


def register_styles(doc: Document) -> None:
    """Register / tune named styles on a document.

    python-docx exposes styles via `doc.styles[name]`. We tune Heading 1,
    Heading 2, and Body Text to match cfo-helper's visual language.
    """
    styles = doc.styles

    # Heading 1
    h1 = styles["Heading 1"]
    h1.font.name = "Calibri"
    h1.font.size = Pt(20)
    h1.font.bold = True
    h1.font.color.rgb = COLOR_INPUT

    # Heading 2
    h2 = styles["Heading 2"]
    h2.font.name = "Calibri"
    h2.font.size = Pt(14)
    h2.font.bold = True
    h2.font.color.rgb = COLOR_FORMULA

    # Normal body
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = COLOR_FORMULA


def apply_letterhead(
    doc: Document,
    *,
    title: str,
    period: str,
    author: str = "",
    org: str | None = None,
) -> None:
    """Insert a letterhead block at the top of the document.

    ``org`` defaults to ``profile/company_profile.yaml:company.org_name``.
    """
    if org is None:
        from scripts.profile_loader import org_name
        org = org_name()

    section = doc.sections[0]
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(1.0)
    section.right_margin = Inches(1.0)

    # Org line
    org_para = doc.add_paragraph()
    org_run = org_para.add_run(org)
    org_run.font.size = Pt(10)
    org_run.font.color.rgb = COLOR_NEUTRAL
    org_run.font.italic = True
    org_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    # Title
    title_para = doc.add_paragraph(style="Heading 1")
    title_para.add_run(title)

    # Period + author
    meta_para = doc.add_paragraph()
    meta_run = meta_para.add_run(f"{period}" + (f"  ·  {author}" if author else ""))
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = COLOR_NEUTRAL


def append_signature_block(doc: Document, *, name: str, role: str) -> None:
    """Append a signature block at the end of the document."""
    doc.add_paragraph()
    doc.add_paragraph()
    sig_para = doc.add_paragraph()
    sig_run = sig_para.add_run(name)
    sig_run.font.bold = True
    sig_run.font.size = Pt(11)

    role_para = doc.add_paragraph()
    role_run = role_para.add_run(role)
    role_run.font.size = Pt(10)
    role_run.font.color.rgb = COLOR_NEUTRAL


__all__ = [
    "register_styles",
    "apply_letterhead",
    "append_signature_block",
    "COLOR_INPUT",
    "COLOR_FORMULA",
    "COLOR_NEUTRAL",
]
