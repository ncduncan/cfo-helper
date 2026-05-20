"""
PowerPoint deck builders for cfo-helper post-close deliverables.

# Pattern source: anthropics/skills/document-skills/pptx — their skill ships a
# pptxgenjs (Node.js) creator + Python QA scripts. We re-implement using
# python-pptx so the toolchain stays Python-only — corporate locked-down
# environments may not have Node available, and our deliverables don't
# need pptxgenjs's templating sugar.

The four primary deck types:

- `scripts.pptx.mor`               — Monthly Management Operating Review (LCD+10)
- `scripts.pptx.parent_reportout`  — Quarter-only parent FP&A report-out (when parent reporting applies)
- `scripts.pptx.bsr`               — Quarter-only Balance Sheet Review

All composers consume `work_product.json` claims and stamp `claim_id`
references in the speaker-notes pane of every slide that quotes a number.
"""

from __future__ import annotations

from scripts.pptx.bsr import build_bsr_deck
from scripts.pptx.mor import build_mor_deck
from scripts.pptx.parent_reportout import build_parent_reportout_deck
from scripts.pptx.templates import (
    add_chart_with_callouts_slide,
    add_kpi_strip_slide,
    add_section_divider,
    add_table_slide,
    add_title_slide,
    add_two_column_slide,
    add_variance_commentary_slide,
    new_deck,
)

__all__ = [
    "new_deck",
    "add_title_slide",
    "add_section_divider",
    "add_kpi_strip_slide",
    "add_two_column_slide",
    "add_table_slide",
    "add_chart_with_callouts_slide",
    "add_variance_commentary_slide",
    "build_mor_deck",
    "build_parent_reportout_deck",
    "build_bsr_deck",
]
