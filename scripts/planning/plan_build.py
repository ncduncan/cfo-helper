"""Plan-build: turn a cube-grain driver workbook into versioned assumption rows.

The driver workbook is the human-authored input. It has one row per
(entity × account × product_line|functional_area × driver_dim × driver_value)
with **12 monthly amount columns** (Jan, Feb, …, Dec) — the natural
spreadsheet shape FP&A teams already use. `build()` explodes that into the
per-period rows the assumption schema expects.

Authoring conventions (driver workbook columns):

    entity              UK | US | …
    fy_year             2026   (the fiscal year the columns belong to)
    account             string; matches account_map
    pnl_line            string; matches account_map
    account_class       revenue|cogs|opex|asset|liability|tax
    product_line        flight_ops|tech_ops|apm|channel|military|null
    functional_area     product_mgmt|sales|marketing|finance|hr|legal|general|null
    driver_dim          azure_sku | tail_count | fte_count | arpc | ...
    driver_value        the value of that dim
    quantity_<mon>      one column per month (Jan..Dec), optional
    unit_cost_<mon>     one column per month (Jan..Dec), optional
    amount_<mon>        per-period USD amount; computed as quantity × unit_cost
                        when quantity/unit_cost are present, else taken directly
    locked_at, source_doc   provenance

Either provide `quantity_<mon>` + `unit_cost_<mon>` (volume × price model) or
`amount_<mon>` directly. The build step computes period_amount_usd =
quantity × unit_cost when both are present, else the explicit amount.
"""

from __future__ import annotations

import calendar
from pathlib import Path

import pandas as pd

from connectors.assumptions import ASSUMPTION_COLUMNS, validate_version

_MONTHS = [calendar.month_abbr[i] for i in range(1, 13)]   # ['Jan', 'Feb', ...]


def _expand_one(row: pd.Series, fy_year: int) -> list[dict]:
    """Explode one driver-workbook row into 12 monthly assumption rows.

    A driver row may apply to fewer than 12 months — when both quantity and
    amount are blank/zero for a month, that month's row is suppressed.
    """
    out: list[dict] = []
    for i, mon in enumerate(_MONTHS, start=1):
        period = f"{fy_year}-{i:02d}"

        qty = row.get(f"quantity_{mon}")
        unit_cost = row.get(f"unit_cost_{mon}")
        amount = row.get(f"amount_{mon}")

        # Coerce blanks → None
        qty = float(qty) if pd.notna(qty) and str(qty).strip() != "" else None
        unit_cost = float(unit_cost) if pd.notna(unit_cost) and str(unit_cost).strip() != "" else None
        amount_explicit = float(amount) if pd.notna(amount) and str(amount).strip() != "" else None

        if qty is not None and unit_cost is not None:
            period_amount = qty * unit_cost
        elif amount_explicit is not None:
            period_amount = amount_explicit
        else:
            continue   # nothing for this month

        if period_amount == 0.0 and qty in (0.0, None) and amount_explicit in (0.0, None):
            continue

        out.append({
            "entity": row.get("entity"),
            "period": period,
            "version": None,                 # filled by build()
            "account": str(row.get("account")).strip(),
            "pnl_line": row.get("pnl_line"),
            "account_class": str(row.get("account_class") or "").lower().strip(),
            "product_line": row.get("product_line") if pd.notna(row.get("product_line")) else None,
            "functional_area": row.get("functional_area") if pd.notna(row.get("functional_area")) else None,
            "driver_dim": row.get("driver_dim"),
            "driver_value": row.get("driver_value"),
            "quantity": qty if qty is not None else 0,
            "unit_cost": unit_cost if unit_cost is not None else 0,
            "period_amount_usd": period_amount,
            "locked_at": row.get("locked_at"),
            "source_doc": row.get("source_doc"),
        })
    return out


def build(
    *,
    driver_workbook: Path,
    version: str,
    sheet: str = "Drivers",
    fy_year: int | None = None,
) -> pd.DataFrame:
    """Read a driver workbook and emit assumption rows ready for ingest lock.

    Returns a DataFrame in `connectors.assumptions.ASSUMPTION_COLUMNS` shape.
    Caller is responsible for writing it to `Assumptions_<Version>_<Entity>.xlsx`
    workbooks (one per entity), updating the manifest, and running ingest to
    hash-lock the version with appropriate `change_source` annotations.
    """
    validate_version(version)
    df = pd.read_excel(driver_workbook, sheet_name=sheet, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    if fy_year is None:
        if "fy_year" not in df.columns:
            raise ValueError(
                "driver workbook missing fy_year column and none passed explicitly."
            )
        # Take the unique fy_year from the workbook
        years = df["fy_year"].dropna().astype(int).unique()
        if len(years) != 1:
            raise ValueError(
                f"driver workbook spans multiple fy_year values {sorted(years)}; "
                "pass `fy_year` explicitly or split the workbook."
            )
        fy_year = int(years[0])

    expanded: list[dict] = []
    for _, row in df.iterrows():
        expanded.extend(_expand_one(row, fy_year))

    out = pd.DataFrame(expanded, columns=ASSUMPTION_COLUMNS)
    out["version"] = version
    return out


def write_per_entity_workbooks(
    rows: pd.DataFrame,
    inputs_dir: Path,
    workbook_stem: str,
    sheet: str = "Detail",
) -> dict[str, Path]:
    """Write one Excel per entity (e.g. `Assumptions_BottomsUp_FY26_UK.xlsx`).

    Returns `{entity: workbook_path}`. Caller updates the manifest separately
    (each call to plan-build should update one version's manifest entries).
    """
    paths: dict[str, Path] = {}
    inputs_dir.mkdir(parents=True, exist_ok=True)
    for entity, grp in rows.groupby("entity"):
        path = inputs_dir / f"{workbook_stem}_{entity}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            grp.to_excel(w, sheet_name=sheet, index=False)
        paths[entity] = path
    return paths
