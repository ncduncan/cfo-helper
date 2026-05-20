"""
Build a deterministic two-entity (UK, US) synthetic fixture for a given period.

Produces (under tasks/close-<period>/inputs/ by default):
  manifest.yaml
  GL_UK_<period>.xlsx, GL_US_<period>.xlsx
  Budget_UK_FY26.xlsx, Budget_US_FY26.xlsx
  Forecast_UK_v3.xlsx, Forecast_US_v3.xlsx
  HC_UK_<period>.xlsx, HC_US_<period>.xlsx
  Customers_<period>.xlsx, Deals_<period>.xlsx, FX_<period>.xlsx

For the gl-drilldown skill (UK-side worked example: cloud-cost overage on
account 5150):
  AP_UK_<period>.xlsx              — Azure invoices by SKU
  IBS_UK_<period>.xlsx             — intercompany infra allocation from US
  Assumptions_Plan_FY26_UK.xlsx           — locked plan-time assumptions
  Assumptions_Outlook_Q1_2026_UK.xlsx     — Q1 outlook revision (append-only)

Also seeds profile/memory/account_map.json with the canonical chart for the test
accounts so consolidation works out of the box.

CLI:
  python -m scripts.build_fixture [--period YYYY-MM] [--task-dir PATH]

  --period   Period to build (default: 2026-05)
  --task-dir Output directory (default: tasks/close-<period>/)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parent.parent


def _gl(entity: str, currency: str, period: str) -> pd.DataFrame:
    """Balanced trial balance for one entity. Debits == credits in local currency.

    Intercompany is settled in USD by treaty so it nets exactly across entities
    regardless of FX. A Cash plug entry absorbs net P&L to keep the TB in
    balance.
    """
    fx = {"USD": 1.0, "GBP": 1.27}[currency]

    if entity == "UK":
        rev_sub_local, rev_svc_local, marketing_local = 950_000, 200_000, 120_000
    else:
        rev_sub_local, rev_svc_local, marketing_local = 1_350_000, 200_000, 180_000

    rows: list[dict] = []

    def add(acct, name, dr_local, cr_local, *, usd_override=None):
        amount_local = cr_local - dr_local
        amount_usd = usd_override if usd_override is not None else amount_local * fx
        rows.append({
            "entity": entity, "period": period, "account": acct, "account_name": name,
            "debit": dr_local, "credit": cr_local, "currency": currency,
            "amount_local": amount_local, "amount_usd": amount_usd,
        })

    add("4100", "Subscription Revenue", 0, rev_sub_local)
    add("4200", "Services Revenue",     0, rev_svc_local)
    add("5100", "Hosting Costs",        150_000, 0)
    add("5200", "Services Delivery",     80_000, 0)
    add("6100", "Salaries",             600_000, 0)
    add("6210", "Software Subs",         50_000, 0)
    add("6300", "Marketing",            marketing_local, 0)
    add("6400", "Travel",                20_000, 0)

    # Cloud Infrastructure (5150) — UK only — planted variance for the
    # gl-drilldown worked example. UK actuals come in $63.5K over plan.
    if entity == "UK":
        # 200,000 GBP × 1.27 = 254,000 USD; budget locked at 150K GBP × 1.27 = 190.5K USD
        add("5150", "Cloud Infrastructure", 200_000, 0)

    ic_usd = 100_000
    ic_local = ic_usd / fx
    if entity == "UK":
        add("1300", "IC Receivable", ic_local, 0, usd_override=ic_usd)
    else:
        add("1300", "IC Payable", 0, ic_local, usd_override=-ic_usd)

    df = pd.DataFrame(rows)
    plug = df["credit"].sum() - df["debit"].sum()
    if plug > 0:
        add("1100", "Cash (plug)", plug, 0, usd_override=plug * fx)
    elif plug < 0:
        add("3900", "Retained Earnings (plug)", 0, -plug, usd_override=plug * fx)
    return pd.DataFrame(rows)


def _budget(entity: str, period: str) -> pd.DataFrame:
    rows = [
        ("4100", "Subscription Revenue", 1_300_000),
        ("4200", "Services Revenue",       200_000),
        ("5100", "Hosting Costs",         -150_000),
        ("5200", "Services Delivery",      -80_000),
        ("6100", "Salaries",              -600_000),
        ("6210", "Software Subs",          -50_000),
        ("6300", "Marketing",             -120_000),
        ("6400", "Travel",                 -25_000),
    ]
    if entity == "UK":
        # Plan-locked baseline for Cloud Infrastructure — actuals will come
        # in $63.5K over this in the fixture.
        rows.append(("5150", "Cloud Infrastructure", -150_000))
    fx_to_usd = 1.27 if entity == "UK" else 1.0
    return pd.DataFrame([
        {"entity": entity, "period": period, "account": a, "account_name": n,
         "amount_usd": v * fx_to_usd}
        for a, n, v in rows
    ])


def _forecast(entity: str, period: str) -> pd.DataFrame:
    b = _budget(entity, period)
    b["version"] = "v3"
    # Forecast slightly more optimistic on revenue
    b.loc[b["account"] == "4100", "amount_usd"] *= 1.03
    return b[["entity", "period", "version", "account", "account_name", "amount_usd"]]


def _customers(period: str) -> pd.DataFrame:
    rows = [
        ("C001", "Acme Manufacturing", 350_000, 4_200_000, "Industrial Suite", "US"),
        ("C002", "Globex Steel",       280_000, 3_360_000, "Industrial Suite", "US"),
        ("C003", "Initech UK Ltd",     180_000, 2_160_000, "Plant Analytics",  "UK"),
        ("C004", "Umbrella Heavy",     220_000, 2_640_000, "Plant Analytics",  "US"),
        ("C005", "Wayne Industrial",   170_000, 2_040_000, "Industrial Suite", "UK"),
    ]
    return pd.DataFrame(rows, columns=["customer_id", "customer_name", "revenue_usd",
                                        "arr_usd", "product", "region"]).assign(period=period)[
        ["customer_id", "customer_name", "period", "revenue_usd", "arr_usd", "product", "region"]
    ]


def _deals(period: str) -> pd.DataFrame:
    rows = [
        ("D001", "C001", "Acme Manufacturing", "closed_won",   600_000, 200_000, "Industrial Suite", "Smith"),
        ("D002", "C004", "Umbrella Heavy",     "closed_won",   480_000, 160_000, "Plant Analytics",  "Patel"),
        ("D003", "C006", "Stark Components",   "slipped",      900_000, 300_000, "Industrial Suite", "Smith"),
        ("D004", "C003", "Initech UK Ltd",     "closed_won",   240_000,  80_000, "Plant Analytics",  "Khan"),
    ]
    return pd.DataFrame(rows, columns=["deal_id", "customer_id", "customer_name", "stage",
                                        "tcv_usd", "acv_usd", "product", "owner"]).assign(period=period)[
        ["deal_id", "customer_id", "customer_name", "period", "stage", "tcv_usd", "acv_usd", "product", "owner"]
    ]


def _headcount(entity: str, period: str) -> pd.DataFrame:
    if entity == "US":
        rows = [("US", period, "Engineering", "Product",     45, 9_000_000),
                ("US", period, "Sales",       "Commercial",  20, 4_000_000),
                ("US", period, "G&A",         "Finance",     12, 1_800_000)]
    else:
        rows = [("UK", period, "Engineering", "Product",     30, 4_500_000),
                ("UK", period, "Sales",       "Commercial",  10, 1_500_000),
                ("UK", period, "G&A",         "Finance",      6,   720_000)]
    return pd.DataFrame(rows, columns=["entity", "period", "department", "function", "fte",
                                        "fully_loaded_cost_usd"])


def _ap_subledger_uk(period: str) -> pd.DataFrame:
    """UK AP detail for the fixture period.

    Drilldown-shape rows (period-flow, per-entity, per-account, per-vendor).
    Hosting/cloud invoices for account 5150 — three Azure SKUs whose total
    drives most of the planted variance.
    """
    # Azure billing is SKU-tagged in this fixture (driver_dim/driver_value
    # populated). For untagged AP feeds these stay null and the bridge falls
    # back to vendor_id as the driver name.
    rows = [
        # (vendor_id, vendor_name, invoice_id, amount_usd, invoice_date, driver_dim, driver_value)
        ("V_AZ", "Microsoft Azure", "INV-AZ-D8S",  140_000, f"{period}-15", "azure_sku", "Standard_D8s_v3"),
        ("V_AZ", "Microsoft Azure", "INV-AZ-SQLM",  60_000, f"{period}-15", "azure_sku", "SQL_Managed_Instance"),
        ("V_AZ", "Microsoft Azure", "INV-AZ-EGR",   30_000, f"{period}-22", "azure_sku", "Network_Egress_TB"),
    ]
    return pd.DataFrame([
        {"entity": "UK", "period": period,
         "account": "5150", "account_name": "Cloud Infrastructure",
         "vendor_id": vid, "vendor_name": vname,
         "currency": "USD", "amount_local": amt_usd, "amount_usd": amt_usd,
         "invoice_id": inv_id, "invoice_date": inv_date,
         "driver_dim": ddim, "driver_value": dval}
        for vid, vname, inv_id, amt_usd, inv_date, ddim, dval in rows
    ])


def _ibs_uk(period: str) -> pd.DataFrame:
    """UK IBS detail for the fixture period.

    A $20K inbound allocation from the US entity for shared network
    infrastructure, hitting account 5150. Demonstrates the bridge summing
    AP + IBS on a single GL account.
    """
    rows = [
        {
            "entity": "UK", "period": period,
            "account": "5150", "account_name": "Cloud Infrastructure",
            "counterparty_entity": "US", "direction": "inbound",
            "currency": "USD", "amount_local": 20_000, "amount_usd": 20_000,
            "allocation_id": f"IBS-{period}-NET",
            "allocation_basis": "shared_network_infra",
            # Not in the assumption set — drilldown will surface this as an
            # unplanned subledger contribution.
            "driver_dim": None, "driver_value": None,
        }
    ]
    return pd.DataFrame(rows)


def _assumptions_uk(version: str, period: str) -> pd.DataFrame:
    """UK plan / outlook assumptions for account 5150 (Cloud Infrastructure).

    Three Azure SKUs at the tech_ops product line. Plan locks at FY26;
    Q1 outlook revises quantity upward (we anticipated growth before May).
    Both versions remain readable — the outlook does not overwrite the plan.
    """
    locked_at, source_doc, rows = {
        "plan_fy26": (
            "2025-12-15",
            "Plan_FY26_v_final.xlsx",
            [
                # (driver_dim, driver_value, qty, unit_cost)
                ("azure_sku", "Standard_D8s_v3",     10, 10_000),
                ("azure_sku", "SQL_Managed_Instance", 2, 25_000),
                ("azure_sku", "Network_Egress_TB",   40,  1_000),
            ],
        ),
        "outlook_q1_2026": (
            "2026-04-10",
            "Outlook_Q1_2026_v1.xlsx",
            [
                ("azure_sku", "Standard_D8s_v3",     12, 10_000),
                ("azure_sku", "SQL_Managed_Instance", 2, 25_000),
                ("azure_sku", "Network_Egress_TB",   45,  1_000),
            ],
        ),
    }[version]
    return pd.DataFrame([
        {
            "entity": "UK", "period": period, "version": version,
            "account": "5150",
            "pnl_line": "COGS / Cloud Infrastructure",
            "account_class": "cogs",
            "product_line": "tech_ops",
            "functional_area": None,
            "driver_dim": dim, "driver_value": val,
            "quantity": qty, "unit_cost": uc,
            "period_amount_usd": qty * uc,
            "locked_at": locked_at,
            "source_doc": source_doc,
        }
        for dim, val, qty, uc in rows
    ])


def _fx(period: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"currency": "USD", "period": period, "rate_to_usd_avg": 1.00, "rate_to_usd_eop": 1.00},
        {"currency": "GBP", "period": period, "rate_to_usd_avg": 1.27, "rate_to_usd_eop": 1.28},
    ])


def _write_xlsx(path: Path, sheet: str, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=sheet, index=False)


def build(period: str = "2026-05", out: Path | None = None) -> None:
    if out is None:
        out = REPO / "tasks" / f"close-{period}"
    inputs = out / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)

    # GL per entity
    _write_xlsx(inputs / f"GL_UK_{period}.xlsx", "TB", _gl("UK", "GBP", period))
    _write_xlsx(inputs / f"GL_US_{period}.xlsx", "TB", _gl("US", "USD", period))

    # Budget per entity
    _write_xlsx(inputs / "Budget_UK_FY26.xlsx", "May", _budget("UK", period))
    _write_xlsx(inputs / "Budget_US_FY26.xlsx", "May", _budget("US", period))

    # Forecast per entity
    _write_xlsx(inputs / "Forecast_UK_v3.xlsx", "May", _forecast("UK", period))
    _write_xlsx(inputs / "Forecast_US_v3.xlsx", "May", _forecast("US", period))

    # Headcount per entity
    _write_xlsx(inputs / f"HC_UK_{period}.xlsx", "Snap", _headcount("UK", period))
    _write_xlsx(inputs / f"HC_US_{period}.xlsx", "Snap", _headcount("US", period))

    # Shared
    _write_xlsx(inputs / f"Customers_{period}.xlsx", "Detail", _customers(period))
    _write_xlsx(inputs / f"Deals_{period}.xlsx",     "Closed", _deals(period))
    _write_xlsx(inputs / f"FX_{period}.xlsx",        "Rates",  _fx(period))

    # UK-only drilldown fixtures (cloud-cost worked example on account 5150)
    _write_xlsx(inputs / f"AP_UK_{period}.xlsx",  "Detail", _ap_subledger_uk(period))
    _write_xlsx(inputs / f"IBS_UK_{period}.xlsx", "Detail", _ibs_uk(period))
    _write_xlsx(inputs / "Assumptions_Plan_FY26_UK.xlsx",       "Detail",
                _assumptions_uk("plan_fy26", period))
    _write_xlsx(inputs / "Assumptions_Outlook_Q1_2026_UK.xlsx", "Detail",
                _assumptions_uk("outlook_q1_2026", period))

    manifest = {
        "period": period,
        "entities": {
            "UK": {
                "gl":        {"workbook": f"GL_UK_{period}.xlsx",       "sheet": "TB",   "header_row": 1},
                "budget":    {"workbook": "Budget_UK_FY26.xlsx",        "sheet": "May",  "header_row": 1},
                "forecast":  {"workbook": "Forecast_UK_v3.xlsx",        "sheet": "May",  "header_row": 1, "version": "v3"},
                "headcount": {"workbook": f"HC_UK_{period}.xlsx",       "sheet": "Snap", "header_row": 1},
                "ap":        {"workbook": f"AP_UK_{period}.xlsx",       "sheet": "Detail", "header_row": 1},
                "ibs":       {"workbook": f"IBS_UK_{period}.xlsx",      "sheet": "Detail", "header_row": 1},
                # Append-only by version. New outlooks add a list entry; existing entries are never edited.
                "assumptions": [
                    {"workbook": "Assumptions_Plan_FY26_UK.xlsx",       "sheet": "Detail",
                     "header_row": 1, "version": "plan_fy26"},
                    {"workbook": "Assumptions_Outlook_Q1_2026_UK.xlsx", "sheet": "Detail",
                     "header_row": 1, "version": "outlook_q1_2026"},
                ],
            },
            "US": {
                "gl":        {"workbook": f"GL_US_{period}.xlsx",       "sheet": "TB",   "header_row": 1},
                "budget":    {"workbook": "Budget_US_FY26.xlsx",        "sheet": "May",  "header_row": 1},
                "forecast":  {"workbook": "Forecast_US_v3.xlsx",        "sheet": "May",  "header_row": 1, "version": "v3"},
                "headcount": {"workbook": f"HC_US_{period}.xlsx",       "sheet": "Snap", "header_row": 1},
                # No AP/IBS/assumptions for US in v1 — drilldown on US accounts will
                # emit not_applicable self-checks naming the missing feeds.
            },
        },
        "shared": {
            "customers": {"workbook": f"Customers_{period}.xlsx", "sheet": "Detail", "header_row": 1},
            "deals":     {"workbook": f"Deals_{period}.xlsx",     "sheet": "Closed", "header_row": 1},
            "fx":        {"workbook": f"FX_{period}.xlsx",        "sheet": "Rates",  "header_row": 1},
        },
    }
    with (inputs / "manifest.yaml").open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    # Seed account_map.json so consolidation works out of the box for both entities
    map_entries = []
    for ent in ("UK", "US"):
        map_entries += [
            {"entity": ent, "account": "4100", "canonical_account": "4100",
             "canonical_name": "Subscription Revenue", "account_class": "revenue",
             "pnl_line": "Revenue / Subscription"},
            {"entity": ent, "account": "4200", "canonical_account": "4200",
             "canonical_name": "Services Revenue", "account_class": "revenue",
             "pnl_line": "Revenue / Services"},
            {"entity": ent, "account": "5100", "canonical_account": "5100",
             "canonical_name": "Hosting Costs", "account_class": "cogs",
             "pnl_line": "COGS / Hosting"},
            {"entity": ent, "account": "5200", "canonical_account": "5200",
             "canonical_name": "Services Delivery", "account_class": "cogs",
             "pnl_line": "COGS / Services"},
            {"entity": ent, "account": "6100", "canonical_account": "6100",
             "canonical_name": "Salaries", "account_class": "opex", "pnl_line": "Opex / Salaries"},
            {"entity": ent, "account": "6210", "canonical_account": "6210",
             "canonical_name": "Software Subs", "account_class": "opex", "pnl_line": "Opex / Software"},
            {"entity": ent, "account": "6300", "canonical_account": "6300",
             "canonical_name": "Marketing", "account_class": "opex", "pnl_line": "Opex / Marketing"},
            {"entity": ent, "account": "6400", "canonical_account": "6400",
             "canonical_name": "Travel", "account_class": "opex", "pnl_line": "Opex / Travel"},
            {"entity": ent, "account": "1300", "canonical_account": "1300",
             "canonical_name": "IC Receivable", "account_class": "intercompany", "pnl_line": "IC"},
            {"entity": ent, "account": "1100", "canonical_account": "1100",
             "canonical_name": "Cash", "account_class": "asset", "pnl_line": "BS / Cash"},
            {"entity": ent, "account": "3900", "canonical_account": "3900",
             "canonical_name": "Retained Earnings", "account_class": "equity", "pnl_line": "BS / Equity"},
        ]
    # Cloud Infrastructure account exists on UK only (the gl-drilldown worked example)
    map_entries.append({
        "entity": "UK", "account": "5150", "canonical_account": "5150",
        "canonical_name": "Cloud Infrastructure",
        "account_class": "cogs", "pnl_line": "COGS / Cloud Infrastructure",
    })
    am_path = REPO / "profile" / "memory" / "account_map.json"
    try:
        with am_path.open() as f:
            am = json.load(f)
    except FileNotFoundError:
        am = {"version": 1, "entries": []}
        am_path.parent.mkdir(parents=True, exist_ok=True)
    am["entries"] = map_entries
    with am_path.open("w") as f:
        json.dump(am, f, indent=2)

    # Make sure task directory skeleton exists
    for sub in ("working", "outputs/controller", "outputs/fpa", "outputs/commercial",
                "outputs/reporting", "review", "final"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    manifest_path = out / "inputs" / "manifest.yaml"
    input_count = len(list((out / "inputs").glob("*.xlsx")))
    print(f"Built fixture for {period} ({input_count} workbooks). Manifest: {manifest_path}")
    print(f"  Next: python -m scripts.ingest --period {period}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default="2026-05",
                        help="YYYY-MM period for the fixture")
    parser.add_argument("--task-dir", type=Path, default=None,
                        help="Output dir; default tasks/close-<period>/")
    args = parser.parse_args()
    out = args.task_dir or (REPO / "tasks" / f"close-{args.period}")
    build(period=args.period, out=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
