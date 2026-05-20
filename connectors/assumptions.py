"""
Assumptions subledger — schema and validation.

Plan-time and outlook-time business assumptions, more granular than the GL
chart but coarser than invoice-level. Read by the gl-drilldown skill so
actuals can be bridged back to the assumed mix-and-rate the plan was built
on.

Rows are append-only by version. The annual plan is locked once
(`version=plan_fy{YY}`); each quarterly outlook adds a new version
(`version=outlook_q{N}_{YYYY}`) without overwriting prior rows. This module
defines the column contract and the version regex; the actual workbook
reader lives in `connectors/excel.py:read_assumptions`. Append-only is
enforced at ingest time by `scripts/ingest.py`.
"""

from __future__ import annotations

import re

ASSUMPTION_COLUMNS = [
    "entity", "period", "version", "account",
    "pnl_line", "account_class",
    "product_line",       # flight_ops|tech_ops|apm|channel|military|null
    "functional_area",    # product_mgmt|sales|marketing|finance|hr|legal|general|null
    "driver_dim",         # azure_sku | tail_count | fte_count | arpc | ...
    "driver_value",
    "quantity", "unit_cost", "period_amount_usd",
    "locked_at", "source_doc",
]

PRODUCT_LINES = {"flight_ops", "tech_ops", "apm", "channel", "military"}
FUNCTIONAL_AREAS = {"product_mgmt", "sales", "marketing", "finance", "hr", "legal", "general"}

VERSION_REGEX = re.compile(
    r"^(bottoms_up_fy\d{2}|plan_fy\d{2}|outlook_q[1-4]_\d{4}|plan_3yr_fy\d{2})$"
)


def validate_version(version: str) -> None:
    if not VERSION_REGEX.match(version):
        raise ValueError(
            f"Assumption version {version!r} does not match expected shape. "
            "Expected bottoms_up_fy<YY>, plan_fy<YY>, outlook_q[1-4]_<YYYY>, "
            "or plan_3yr_fy<YY> (3-year strategic plan, Y2+Y3 at annual grain)."
        )


def is_strategic_3yr(version: str) -> bool:
    """True if this version is a 3-year strategic plan. These versions carry
    Y2/Y3 rows at annual grain only; Y1 is anchored to the operational
    plan_fy{YY} of the same fiscal year."""
    return version.startswith("plan_3yr_fy")


def fy_year_from_version(version: str) -> int | None:
    """Extract the fiscal-year suffix from any version string. Returns None
    for outlook versions (which carry the calendar year, not FY)."""
    if version.startswith("plan_3yr_fy") or version.startswith("plan_fy") or version.startswith("bottoms_up_fy"):
        return 2000 + int(version.rsplit("fy", 1)[1])
    return None


# Lineage annotation enum — recorded in memory/assumptions_locked.json per version
# so gap-to-stretch can attribute deltas back to what caused them. Multiple values
# may apply to a single version (most quarterly outlooks carry several).
CHANGE_SOURCES = {
    "bottoms_up_submission",        # FP&A's first cut shipped to corporate
    "corporate_stretch_lock",       # corporate accepted with stretch baked in (locks plan_fy{YY})
    "quarterly_corporate_challenge", # corporate added stretch in a quarterly review
    "quarterly_operational_response", # FP&A baked operational measures into the outlook
    "actuals_revision",             # YTD actuals reshaped the projection
}


def validate_change_sources(sources: list[str]) -> None:
    bad = [s for s in sources if s not in CHANGE_SOURCES]
    if bad:
        raise ValueError(
            f"Unknown change_source value(s): {bad}. "
            f"Allowed: {sorted(CHANGE_SOURCES)}"
        )


def natural_key_columns() -> list[str]:
    """Columns that uniquely identify a row across (and within) versions.
    Ingest enforces uniqueness on this tuple to guarantee append-only."""
    return ["entity", "period", "version", "account",
            "product_line", "functional_area", "driver_dim", "driver_value"]
