"""Helpers to build tiny synthetic planning fixtures inline.

Keeping these in-test (rather than committing binaries) follows the
existing pattern in this repo — see tests/test_excel_coercion.py and
tests/test_xlsx_write_table.py for similar inline-generated workbooks.
"""

from __future__ import annotations

import calendar
from pathlib import Path

import pandas as pd

from connectors.assumptions import ASSUMPTION_COLUMNS

_MONTHS = [calendar.month_abbr[i] for i in range(1, 13)]


def synthetic_assumption_rows(
    *,
    entity: str = "UK",
    version: str = "plan_fy26",
    fy_year: int = 2026,
    revenue_per_month: float = 100_000.0,
    cogs_per_month: float = 30_000.0,
    rd_per_month: float = 15_000.0,
    sga_per_month: float = 12_000.0,
    deferred_rev_per_month: float = 0.0,
    cap_comm_per_month: float = 0.0,
    cash_tax_per_month: float = 0.0,
) -> pd.DataFrame:
    """Build a tiny assumption dataset (12 months × a handful of accounts)
    in the canonical ASSUMPTION_COLUMNS shape.
    """
    rows: list[dict] = []
    items: list[tuple[str, str, str, str, float]] = [
        ("4100", "Revenue / Subscription", "revenue", "tail_count", revenue_per_month),
        ("5100", "COGS / Hosting", "cogs", "azure_sku", cogs_per_month),
        ("6010", "Opex / R&D", "opex", "fte_count", rd_per_month),
        ("6200", "Opex / SG&A", "opex", "fte_count", sga_per_month),
    ]
    if deferred_rev_per_month:
        items.append(("2100", "BS / Deferred Revenue", "liability",
                      "prepay_amount_usd", deferred_rev_per_month))
    if cap_comm_per_month:
        items.append(("1300", "BS / Capitalized Commissions", "asset",
                      "commission_amount_usd", cap_comm_per_month))
    if cash_tax_per_month:
        items.append(("9100", "Tax / Cash Tax", "tax",
                      "etr_pct", cash_tax_per_month))

    for month_idx in range(1, 13):
        for account, pnl_line, cls, dim, monthly in items:
            rows.append({
                "entity": entity,
                "period": f"{fy_year}-{month_idx:02d}",
                "version": version,
                "account": account,
                "pnl_line": pnl_line,
                "account_class": cls,
                "product_line": "flight_ops" if cls == "revenue" else None,
                "functional_area": "general" if cls == "opex" else None,
                "driver_dim": dim,
                "driver_value": "v1",
                "quantity": 1.0,
                "unit_cost": monthly,
                "period_amount_usd": monthly,
                "locked_at": "2026-04-01",
                "source_doc": "synthetic.xlsx",
            })
    return pd.DataFrame(rows, columns=ASSUMPTION_COLUMNS)


def write_driver_workbook(
    path: Path,
    *,
    entity: str = "UK",
    fy_year: int = 2026,
    revenue_per_month: float = 100_000.0,
    cogs_per_month: float = 30_000.0,
    rd_per_month: float = 15_000.0,
    sga_per_month: float = 12_000.0,
) -> Path:
    """Write a driver workbook with one row per (entity × account) and 12
    monthly amount columns. Matches the column contract documented in
    scripts/planning/plan_build.py.
    """
    items: list[tuple[str, str, str, str, str, str, str, float]] = [
        # account, pnl_line, account_class, product_line, functional_area, driver_dim, driver_value, monthly
        ("4100", "Revenue / Subscription", "revenue", "flight_ops", "",
         "tail_count", "v1", revenue_per_month),
        ("5100", "COGS / Hosting", "cogs", "flight_ops", "",
         "azure_sku", "v1", cogs_per_month),
        ("6010", "Opex / R&D", "opex", "", "general",
         "fte_count", "v1", rd_per_month),
        ("6200", "Opex / SG&A", "opex", "", "general",
         "fte_count", "v1", sga_per_month),
    ]
    columns = [
        "entity", "fy_year", "account", "pnl_line", "account_class",
        "product_line", "functional_area", "driver_dim", "driver_value",
    ] + [f"amount_{m}" for m in _MONTHS]
    rows: list[dict] = []
    for account, pnl_line, cls, pl, fa, dim, dv, monthly in items:
        row = {
            "entity": entity, "fy_year": fy_year,
            "account": account, "pnl_line": pnl_line, "account_class": cls,
            "product_line": pl or None, "functional_area": fa or None,
            "driver_dim": dim, "driver_value": dv,
        }
        for m in _MONTHS:
            row[f"amount_{m}"] = monthly
        rows.append(row)
    df = pd.DataFrame(rows, columns=columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Drivers", index=False)
    return path


def write_assumption_workbook(
    path: Path,
    rows: pd.DataFrame,
    *,
    sheet: str = "Detail",
) -> Path:
    """Write an assumption workbook (one entity, one version) for ingest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        rows.to_excel(w, sheet_name=sheet, index=False)
    return path


def write_empty_support_workbooks(inputs_dir: Path, entity: str) -> dict:
    """Create empty GL / Budget / Headcount workbooks so ingest doesn't crash
    when downstream planning runners trigger it. Returns a manifest fragment
    suitable for the entity's manifest entry.
    """
    inputs_dir.mkdir(parents=True, exist_ok=True)
    gl_wb = inputs_dir / f"GL_{entity}.xlsx"
    bud_wb = inputs_dir / f"Budget_{entity}.xlsx"
    hc_wb = inputs_dir / f"Headcount_{entity}.xlsx"
    with pd.ExcelWriter(gl_wb, engine="openpyxl") as w:
        pd.DataFrame(columns=[
            "entity", "period", "account", "account_name",
            "debit", "credit", "currency", "amount_local", "amount_usd",
        ]).to_excel(w, sheet_name="GL", index=False)
    with pd.ExcelWriter(bud_wb, engine="openpyxl") as w:
        pd.DataFrame(columns=[
            "entity", "period", "account", "account_name", "amount_usd",
        ]).to_excel(w, sheet_name="Budget", index=False)
    with pd.ExcelWriter(hc_wb, engine="openpyxl") as w:
        pd.DataFrame(columns=[
            "entity", "period", "department", "function",
            "fte", "fully_loaded_cost_usd",
        ]).to_excel(w, sheet_name="Headcount", index=False)
    return {
        "gl": {"workbook": gl_wb.name, "sheet": "GL"},
        "budget": {"workbook": bud_wb.name, "sheet": "Budget"},
        "headcount": {"workbook": hc_wb.name, "sheet": "Headcount"},
    }


def write_empty_shared_workbooks(inputs_dir: Path) -> dict:
    """Create empty Customers / Deals / FX workbooks for the manifest.shared
    section so ingest doesn't crash on planning-only fixtures.
    """
    inputs_dir.mkdir(parents=True, exist_ok=True)
    cust_wb = inputs_dir / "Customers.xlsx"
    deals_wb = inputs_dir / "Deals.xlsx"
    fx_wb = inputs_dir / "FX.xlsx"
    with pd.ExcelWriter(cust_wb, engine="openpyxl") as w:
        pd.DataFrame(columns=[
            "customer_id", "customer_name", "period", "revenue_usd",
            "arr_usd", "product", "region",
        ]).to_excel(w, sheet_name="Customers", index=False)
    with pd.ExcelWriter(deals_wb, engine="openpyxl") as w:
        pd.DataFrame(columns=[
            "deal_id", "customer_id", "customer_name", "period",
            "stage", "tcv_usd", "acv_usd", "product", "owner",
        ]).to_excel(w, sheet_name="Deals", index=False)
    with pd.ExcelWriter(fx_wb, engine="openpyxl") as w:
        pd.DataFrame(columns=[
            "currency", "period", "rate_to_usd_avg", "rate_to_usd_eop",
        ]).to_excel(w, sheet_name="FX", index=False)
    return {
        "customers": {"workbook": cust_wb.name, "sheet": "Customers"},
        "deals": {"workbook": deals_wb.name, "sheet": "Deals"},
        "fx": {"workbook": fx_wb.name, "sheet": "FX"},
    }
