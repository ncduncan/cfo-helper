"""
Color and number-format constants for cfo-helper Excel output.

# Pattern source: anthropics/skills/document-skills/xlsx — convention is
# blue=inputs, black=formulas, green=internal links, red=external links.
# Re-implemented here in openpyxl primitives so we have one place to tune
# the close-pack visual language.
"""

from __future__ import annotations

from openpyxl.styles import Font, NamedStyle, PatternFill

# --- Cell-role colors (text color) ------------------------------------------

BLUE_INPUT = "1F4E79"          # hardcoded input values
BLACK_FORMULA = "000000"       # cells with formulas referring to inputs/intermediates
GREEN_INTERNAL_LINK = "2E7D32"  # cross-sheet references inside the same workbook
RED_EXTERNAL_LINK = "B00020"   # references into another workbook (e.g., consolidation feed)

# --- Header band (legacy, preserved for backward compat) --------------------

HEADER_FILL = PatternFill("solid", fgColor="1F2937")
HEADER_FONT = Font(color="FFFFFF", bold=True)

# --- Number-format strings --------------------------------------------------
# Names follow Excel's number-format mini-language. Use the constants rather
# than re-typing the strings so we can later swap presentation (e.g., switch
# from "$" to "USD ") in one place.

USD = "$#,##0;($#,##0);-"
USD_MILLIONS = '_($* #,##0.0,,"M"_);_($* (#,##0.0,,"M");_($* "-"_);_(@_)'
USD_THOUSANDS = '_($* #,##0,"K"_);_($* (#,##0,"K");_($* "-"_);_(@_)'
PCT = "0.0%;(0.0%);-"
PCT_INT = "0%;(0%);-"
RATIO = "0.00x"
INTEGER = "#,##0;(#,##0);-"
DATE_ISO = "yyyy-mm-dd"
MONTH_YEAR = "mmm-yyyy"


def font_for_role(role: str, *, bold: bool = False, size: int | None = None) -> Font:
    """Return an openpyxl Font with the color for a given cell role."""
    color_map = {
        "input": BLUE_INPUT,
        "formula": BLACK_FORMULA,
        "internal_link": GREEN_INTERNAL_LINK,
        "external_link": RED_EXTERNAL_LINK,
    }
    color = color_map.get(role, BLACK_FORMULA)
    kwargs: dict = {"color": color, "bold": bold}
    if size is not None:
        kwargs["size"] = size
    return Font(**kwargs)


def apply_role(cell, role: str, *, bold: bool = False) -> None:
    """Apply the role-color font to a cell in place."""
    cell.font = font_for_role(role, bold=bold)


def register_named_styles(workbook) -> None:
    """Register reusable named styles on a workbook so cells can reference them by name."""
    for name, font in (
        ("input", font_for_role("input")),
        ("formula", font_for_role("formula")),
        ("internal_link", font_for_role("internal_link")),
        ("external_link", font_for_role("external_link")),
    ):
        if name not in workbook.named_styles:
            ns = NamedStyle(name=name)
            ns.font = font
            workbook.add_named_style(ns)


__all__ = [
    "BLUE_INPUT",
    "BLACK_FORMULA",
    "GREEN_INTERNAL_LINK",
    "RED_EXTERNAL_LINK",
    "HEADER_FILL",
    "HEADER_FONT",
    "USD",
    "USD_MILLIONS",
    "USD_THOUSANDS",
    "PCT",
    "PCT_INT",
    "RATIO",
    "INTEGER",
    "DATE_ISO",
    "MONTH_YEAR",
    "font_for_role",
    "apply_role",
    "register_named_styles",
]
