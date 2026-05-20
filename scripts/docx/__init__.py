"""
Word document tooling for cfo-helper — primary surface for the CEO letter.

# Pattern source: anthropics/skills/document-skills/docx — their skill ships
# a docx-js (JavaScript) creator + Pandoc-based extraction. We re-implement
# using python-docx so the toolchain stays Python-only. We deliberately
# omit DOCX OCR / tracked-changes automation (Anthropic's skill covers
# them; we don't currently need either for our deliverables).

The CEO letter is the primary consumer. The composer reads the
exec-summary Markdown plus a structured table payload (sourced from a
sibling .xlsx) and emits a Word doc with a native, copy-pastable table —
the format the CFO requested ("Word doc w/ Excel table input").

Submodules:
- `scripts.docx.styles`           — heading/body styles, signature block
- `scripts.docx.ceo_letter`       — CEO-letter composer
- `scripts.docx.table_from_xlsx`  — read a sheet/range from xlsx, emit Word table
"""

from __future__ import annotations

from scripts.docx.ceo_letter import build_ceo_letter, CEOLetterPayload
from scripts.docx.styles import apply_letterhead, register_styles
from scripts.docx.table_from_xlsx import insert_table_from_xlsx

__all__ = [
    "CEOLetterPayload",
    "build_ceo_letter",
    "apply_letterhead",
    "register_styles",
    "insert_table_from_xlsx",
]
