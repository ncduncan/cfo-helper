"""Strategic-plan-build: 3-year plan compiler.

The 3-year strategic plan is **Y1 + Y2 + Y3**, where:

  - Y1 = the locked operational plan_fy{YY}, monthly grain (already exists)
  - Y2 = annual roll-up, this skill builds it
  - Y3 = annual roll-up, this skill builds it

Authoring workbook is tiny — fewer than 100 rows for a complete plan, vs.
thousands for the operational annual plan. One row per:

  (entity × year_offset × bucket-or-account × product_line|functional_area)

with a `growth_method` indicating how to compute the absolute amount:

  - `percent_growth`     — Y_n = Y_{n-1} × (1 + parameter_value)
  - `percent_of_revenue` — Y_n = revenue_anchor[Y_n] × parameter_value
  - `absolute`           — Y_n = parameter_value (USD, used for one-time items)

`year_offset ∈ {2, 3}` — Y1 is always anchored to the operational plan_fy{YY}
and not authored here. Y3 percent_growth chains off Y2 (so 5% Y2 followed by
5% Y3 produces a compounded 10.25% over the two outyears).

Output rows live in the standard ASSUMPTION schema with:

  - `period` = year-end month (e.g., '2027-12' for Y2 of plan_3yr_fy26)
  - `driver_dim` = the growth_method
  - `driver_value` = the parameter_value as text (for prose attribution)
  - `quantity` = parameter_value (numeric)
  - `unit_cost` = the anchor amount used in the calculation
  - `period_amount_usd` = the resulting absolute USD for that year

Strategic versions are tagged `change_source: ["strategic_plan_anchor"]` on
first lock and `locked_against: <entity>/plan_fy{YY}` to record the Y1 anchor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from connectors.assumptions import (
    ASSUMPTION_COLUMNS, validate_version, fy_year_from_version, is_strategic_3yr,
)

GROWTH_METHODS = {"percent_growth", "percent_of_revenue", "absolute"}


@dataclass(frozen=True)
class StrategicBuildResult:
    version: str
    fy_year: int                              # Y1 fiscal year
    rows: pd.DataFrame                        # in ASSUMPTION_COLUMNS shape, Y2+Y3 only
    y1_anchor_totals: dict[tuple[str, str], float]   # {(entity, bucket): Y1 total} used as anchor
    notes: list[str] = field(default_factory=list)


def _bucket_for(account_class: str, pnl_line: str) -> str:
    cls = (account_class or "").lower()
    if cls == "revenue":
        return "revenue"
    if cls == "cogs":
        return "cogs"
    if cls == "opex":
        return "rd" if (pnl_line or "").startswith("Opex / R&D") else "sga"
    return "other"


def _y1_anchor(repo_root: Path, fy_year: int) -> tuple[
    dict[tuple, float], dict[tuple[str, str], float]
]:
    """Pull Y1 totals from plan_fy{YY} for each (entity, account, product_line/functional_area).

    Returns:
      cell_anchors: {(entity, account, product_line, functional_area): Y1 total}
      revenue_anchors: {(entity, year): revenue total for Y_n} — used for percent_of_revenue.
        For Y1 anchor, this is just the plan_fy{YY} revenue total.
    """
    import sys
    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433

    base_version = f"plan_fy{fy_year - 2000:02d}"
    # Pick any workspace period to read the manifest from (assumptions return
    # all rows in the workbook regardless of period filter).
    ws = repo_root / "workspace"
    period = sorted(
        d.name for d in ws.iterdir()
        if d.is_dir() and (d / "inputs" / "manifest.yaml").exists()
        and len(d.name) == 7 and d.name[4] == "-"
    )[-1]
    entities = connectors.list_entities(period)

    cell_anchors: dict[tuple, float] = {}
    revenue_anchors: dict[tuple[str, str], float] = {}
    for entity in entities:
        rows = connectors.get_assumptions(period=period, entity=entity, version=base_version)
        if rows.empty:
            continue
        rows = rows.copy()
        rows["account"] = rows["account"].astype(str).str.strip()  # int→str for key
        rows["account_class"] = rows["account_class"].fillna("").astype(str).str.lower()
        rows["product_line"] = rows["product_line"].fillna("").astype(str)
        rows["functional_area"] = rows["functional_area"].fillna("").astype(str)
        rows["period_amount_usd"] = pd.to_numeric(
            rows["period_amount_usd"], errors="coerce"
        ).fillna(0.0)

        # Cell-level anchors (sum across the 12 months of Y1 for each cube cell)
        grouped = rows.groupby(
            ["entity", "account", "product_line", "functional_area"]
        )["period_amount_usd"].sum()
        for key, amt in grouped.items():
            cell_anchors[key] = float(amt)

        rev_total = float(rows[rows["account_class"] == "revenue"]["period_amount_usd"].sum())
        revenue_anchors[(entity, "Y1")] = rev_total

    return cell_anchors, revenue_anchors


def build(
    *,
    workbook: Path,
    version: str,
    repo_root: Path,
    sheet: str = "Strategic",
) -> StrategicBuildResult:
    """Compile a strategic plan workbook into Y2/Y3 assumption rows."""
    validate_version(version)
    if not is_strategic_3yr(version):
        raise ValueError(
            f"Version {version!r} is not a strategic-3yr version "
            "(must start with 'plan_3yr_fy')."
        )
    fy_year = fy_year_from_version(version)
    assert fy_year is not None

    df = pd.read_excel(workbook, sheet_name=sheet, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    required = {"entity", "year_offset", "account", "account_class",
                "growth_method", "parameter_value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Strategic workbook missing required columns: {missing}")

    cell_anchors, revenue_anchors = _y1_anchor(repo_root, fy_year)

    # Y_n revenue anchor needed for percent_of_revenue: Y2 = Y1 × (1+rev_growth_y2);
    # Y3 = Y2 × (1+rev_growth_y3). We compute these as we go through the workbook.
    rev_growth_by_entity_year: dict[tuple[str, int], float] = {}
    for _, r in df.iterrows():
        if (
            (r.get("account_class") or "").lower() == "revenue"
            and r.get("growth_method") == "percent_growth"
        ):
            entity = str(r["entity"])
            yo = int(r["year_offset"])
            param = float(r["parameter_value"])
            # Aggregate weighted by current (multiple revenue rows per entity allowed)
            rev_growth_by_entity_year.setdefault((entity, yo), param)

    # Compute Y2 and Y3 revenue anchors per entity
    for entity in {key[0] for key in revenue_anchors}:
        y1 = revenue_anchors[(entity, "Y1")]
        y2_g = rev_growth_by_entity_year.get((entity, 2), 0.0)
        y3_g = rev_growth_by_entity_year.get((entity, 3), 0.0)
        revenue_anchors[(entity, "Y2")] = y1 * (1 + y2_g)
        revenue_anchors[(entity, "Y3")] = revenue_anchors[(entity, "Y2")] * (1 + y3_g)

    # Compile each row to one assumption row per outyear (the workbook has one
    # row per (entity × year_offset × cell), so each maps to one output row)
    out_rows: list[dict] = []
    notes: list[str] = []

    for _, r in df.iterrows():
        entity = str(r["entity"])
        yo = int(r["year_offset"])
        if yo not in (2, 3):
            raise ValueError(
                f"year_offset must be 2 or 3 for plan_3yr (Y1 is anchored, not authored). "
                f"Got {yo} on row entity={entity} account={r.get('account')}."
            )
        method = str(r["growth_method"])
        if method not in GROWTH_METHODS:
            raise ValueError(
                f"growth_method must be in {sorted(GROWTH_METHODS)}; got {method!r}."
            )

        period = f"{fy_year - 2000 + 2000 + (yo - 1):04d}-12"
        # Y_n period: fy_year + (yo - 1). Y2 of plan_3yr_fy26 → 2027-12.
        period = f"{fy_year + (yo - 1)}-12"

        account = str(r["account"]).strip()
        account_class = str(r.get("account_class") or "").lower().strip()
        pnl_line = r.get("pnl_line") or ""
        product_line = r.get("product_line") if pd.notna(r.get("product_line")) else None
        functional_area = r.get("functional_area") if pd.notna(r.get("functional_area")) else None
        param = float(r["parameter_value"])

        # Anchor lookup
        cell_key = (
            entity, account,
            (product_line or ""), (functional_area or ""),
        )
        y1_anchor = cell_anchors.get(cell_key, 0.0)

        if method == "percent_growth":
            # Y2 = Y1 × (1+param); Y3 = Y2 × (1+param_y3)
            # For Y3 we need the Y2 amount; pull from previously emitted out_rows
            if yo == 2:
                anchor = y1_anchor
                amount = anchor * (1 + param)
            else:  # yo == 3
                # Find this cell's Y2 row, fallback to Y1 if no Y2 was authored
                y2_amt = next(
                    (o["period_amount_usd"] for o in out_rows
                     if o["entity"] == entity and o["account"] == account
                     and o.get("product_line") == product_line
                     and o.get("functional_area") == functional_area
                     and o["period"] == f"{fy_year + 1}-12"),
                    None,
                )
                anchor = y2_amt if y2_amt is not None else y1_anchor
                amount = anchor * (1 + param)
        elif method == "percent_of_revenue":
            year_label = f"Y{yo}"
            rev_anchor = revenue_anchors.get((entity, year_label), 0.0)
            anchor = rev_anchor
            amount = rev_anchor * param
        elif method == "absolute":
            anchor = 0.0
            amount = param
        else:
            raise ValueError(f"Unhandled growth_method: {method}")

        if y1_anchor == 0.0 and method == "percent_growth":
            notes.append(
                f"{entity} account={account} ({product_line or functional_area or '—'}): "
                f"Y1 anchor was 0 (no plan_fy{fy_year - 2000:02d} rows for this cell). "
                f"Y{yo} percent_growth produces 0; consider growth_method=absolute."
            )

        out_rows.append({
            "entity": entity,
            "period": period,
            "version": version,
            "account": account,
            "pnl_line": pnl_line,
            "account_class": account_class,
            "product_line": product_line,
            "functional_area": functional_area,
            "driver_dim": method,
            "driver_value": f"{param:+.2%}" if method != "absolute" else f"${param:,.0f}",
            "quantity": param,
            "unit_cost": anchor,
            "period_amount_usd": amount,
            "locked_at": r.get("locked_at"),
            "source_doc": r.get("source_doc") or workbook.name,
        })

    rows = pd.DataFrame(out_rows, columns=ASSUMPTION_COLUMNS)
    return StrategicBuildResult(
        version=version, fy_year=fy_year,
        rows=rows,
        y1_anchor_totals={(e, b): rev for (e, b), rev in revenue_anchors.items()},
        notes=notes,
    )
