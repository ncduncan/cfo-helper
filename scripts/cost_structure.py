"""
Cost-structure analysis engine.

Pure functions over pandas DataFrames. No I/O, no global state, no model
calls. The dispatch runners orchestrate the data loads; this module is the
math.

Public API:
    categorize_gl(gl_df, categories)
    trend(curr_df, prior_df, *, fx_table=None, key_cols=("archetype",))
    top_movers(trend_df, *, n=10, threshold_pct=0.20)
    vendor_concentration(gl_df, vendor_df)
    headcount_unit_cost(headcount_df, gl_df)
    capitalization_classify(gl_df, policy)
    commissions_amortization_schedule(deals_df, policy, period)
    unit_economics(category_totals, kpis)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

import pandas as pd


# --- Helpers -----------------------------------------------------------------

def _account_in_range(account: str, ranges: list[list[str]]) -> bool:
    """Inclusive string-comparison range match. Account codes are strings;
    we treat them as zero-padded numeric strings for comparison so '5100'
    sorts between '5099' and '5101' correctly."""
    a = str(account).strip()
    for lo, hi in ranges:
        if str(lo) <= a <= str(hi):
            return True
    return False


# --- Categorization ----------------------------------------------------------

def categorize_gl(gl_df: pd.DataFrame, categories: dict) -> pd.DataFrame:
    """Add an `archetype` column to a GL DataFrame.

    Fail-closed: any account that's not in `excluded` and not in any
    archetype range raises ValueError. The error message lists the missing
    accounts so the operator knows what to add to `cost_categories.yaml`.

    Excluded accounts (revenue, balance sheet, intercompany) get archetype
    "_excluded_" — callers filter on `archetype != "_excluded_"` to get
    the opex-relevant rows.
    """
    df = gl_df.copy()
    archetypes = categories.get("archetypes", {})
    excluded_ranges = (categories.get("excluded") or {}).get("account_ranges", [])

    def _match(acc: str) -> str:
        if _account_in_range(acc, excluded_ranges):
            return "_excluded_"
        for name, spec in archetypes.items():
            if _account_in_range(acc, spec.get("account_ranges", [])):
                return name
        return ""

    df["archetype"] = df["account"].apply(_match)
    unmapped = df[df["archetype"] == ""]["account"].astype(str).unique()
    if len(unmapped) > 0:
        raise ValueError(
            f"Unmapped GL accounts: {sorted(unmapped)[:20]}"
            f"{'...' if len(unmapped) > 20 else ''}. "
            f"Add them to profile/memory/cost_categories.yaml."
        )
    return df


# --- Trend -------------------------------------------------------------------

def _aggregate(df: pd.DataFrame, key_cols: tuple[str, ...]) -> pd.DataFrame:
    """Sum amount_usd grouped by key_cols. Filters out _excluded_ archetypes."""
    work = df[df["archetype"] != "_excluded_"] if "archetype" in df.columns else df
    return (
        work.groupby(list(key_cols), dropna=False)["amount_usd"]
            .sum().reset_index().rename(columns={"amount_usd": "amount"})
    )


def trend(curr_df: pd.DataFrame, prior_df: pd.DataFrame | None, *,
          fx_table: pd.DataFrame | None = None,
          key_cols: tuple[str, ...] = ("archetype",)) -> pd.DataFrame:
    """Compute current vs prior aggregated by key_cols.

    Returns a DataFrame with columns: <key_cols>, current_usd, prior_usd,
    delta_usd, delta_pct. When prior_df is None or empty, prior_usd = 0
    and delta columns are NaN (so the caller can render "n/a" in the UI).

    FX neutralization: if fx_table is provided, both periods are restated
    at the *current* period's average rates per currency before summation.
    fx_table is the canonical FX dataframe with columns currency,
    rate_to_usd_avg. (Period-end rates aren't used here — opex trending is
    period-average territory.) The current and prior frames must carry a
    `currency` and `amount_local` column for FX neutralization to apply;
    otherwise the function falls back to amount_usd.
    """
    def _restate(df: pd.DataFrame) -> pd.DataFrame:
        if (fx_table is None or "amount_local" not in df.columns
                or "currency" not in df.columns):
            return df
        rates = fx_table[["currency", "rate_to_usd_avg"]].drop_duplicates("currency")
        merged = df.merge(rates, on="currency", how="left")
        merged["rate_to_usd_avg"] = merged["rate_to_usd_avg"].fillna(1.0)
        merged = merged.copy()
        merged["amount_usd"] = merged["amount_local"] * merged["rate_to_usd_avg"]
        return merged

    cur = _aggregate(_restate(curr_df), key_cols).rename(columns={"amount": "current_usd"})
    if prior_df is None or prior_df.empty:
        cur["prior_usd"] = 0.0
        cur["delta_usd"] = float("nan")
        cur["delta_pct"] = float("nan")
        return cur

    prior = _aggregate(_restate(prior_df), key_cols).rename(columns={"amount": "prior_usd"})
    out = cur.merge(prior, on=list(key_cols), how="outer").fillna({"current_usd": 0.0, "prior_usd": 0.0})
    out["delta_usd"] = out["current_usd"] - out["prior_usd"]
    out["delta_pct"] = out.apply(
        lambda r: (r["delta_usd"] / r["prior_usd"]) if r["prior_usd"] else float("nan"),
        axis=1,
    )
    return out


def top_movers(trend_df: pd.DataFrame, *, n: int = 10,
                threshold_pct: float = 0.20) -> pd.DataFrame:
    """Top-N movers by absolute delta where |delta_pct| >= threshold_pct.

    When trend doesn't have prior (delta is NaN), we still return the top
    current_usd rows so the operator gets a current-period composition view.
    """
    df = trend_df.copy()
    if df["delta_pct"].isna().all():
        return df.nlargest(n, "current_usd")
    df["abs_pct"] = df["delta_pct"].abs()
    qualified = df[df["abs_pct"].fillna(0) >= threshold_pct]
    if qualified.empty:
        return df.assign(abs_delta=df["delta_usd"].abs()).nlargest(n, "abs_delta").drop(columns=["abs_delta"])
    return qualified.assign(abs_delta=qualified["delta_usd"].abs()).nlargest(n, "abs_delta").drop(columns=["abs_delta", "abs_pct"])


# --- Vendor concentration ----------------------------------------------------

@dataclass
class VendorConcentration:
    top10_share: float
    top10_rows: pd.DataFrame
    total_vendor_spend_usd: float
    notes: str = ""


def vendor_concentration(gl_df: pd.DataFrame,
                          vendor_df: pd.DataFrame | None) -> VendorConcentration:
    """Top-10 vendors by spend; concentration ratio = top10_spend / total.

    Today's GL doesn't carry a vendor_id, so concentration is computed from
    the vendor master's `ytd_spend_usd` column. When vendor_df is empty we
    return a sentinel result with notes='no vendor master configured'."""
    if vendor_df is None or vendor_df.empty:
        return VendorConcentration(top10_share=float("nan"),
                                     top10_rows=pd.DataFrame(),
                                     total_vendor_spend_usd=0.0,
                                     notes="no vendor master configured")
    df = vendor_df.copy()
    df["ytd_spend_usd"] = df["ytd_spend_usd"].astype(float).fillna(0.0)
    total = float(df["ytd_spend_usd"].sum())
    top10 = df.nlargest(10, "ytd_spend_usd")
    share = float(top10["ytd_spend_usd"].sum()) / total if total else float("nan")
    return VendorConcentration(top10_share=share, top10_rows=top10,
                                 total_vendor_spend_usd=total)


# --- Headcount unit cost -----------------------------------------------------

def headcount_unit_cost(headcount_df: pd.DataFrame,
                          gl_df: pd.DataFrame | None = None) -> dict:
    """Compute FTE and fully-loaded cost per function/department.

    Uses the headcount table's `fully_loaded_cost_usd` column when present;
    falls back to GL people-archetype total / FTE when not.
    """
    hc = headcount_df.copy()
    fte_total = float(hc["fte"].sum())
    cost_col = "fully_loaded_cost_usd"
    if cost_col in hc.columns and hc[cost_col].notna().any():
        cost_total = float(hc[cost_col].sum())
        cost_per_fte = cost_total / fte_total if fte_total else float("nan")
    elif gl_df is not None:
        people = gl_df[gl_df.get("archetype", "") == "people"] if "archetype" in gl_df.columns else pd.DataFrame()
        cost_total = float(people["amount_usd"].sum()) if not people.empty else 0.0
        cost_per_fte = cost_total / fte_total if fte_total else float("nan")
    else:
        cost_total = 0.0
        cost_per_fte = float("nan")
    by_function = (hc.groupby("function", dropna=False)
                     .agg(fte=("fte", "sum"),
                          cost_usd=(cost_col, "sum") if cost_col in hc.columns
                                   else ("fte", "sum"))
                     .reset_index())
    return {
        "fte_total": fte_total,
        "fully_loaded_cost_total_usd": cost_total,
        "fully_loaded_cost_per_fte_usd": cost_per_fte,
        "by_function": by_function,
    }


# --- Capitalization classification -------------------------------------------

@dataclass
class CapEntry:
    account: str
    account_name: str
    archetype: str          # capex_software | capex_commission
    amount_usd: float
    useful_life_months: int
    monthly_amortization_usd: float
    rule: str               # short policy reference (asc_350_40, asc_985_20, asc_340_40)


def capitalization_classify(gl_df: pd.DataFrame, policy: dict,
                             *, archetype_col: str = "archetype") -> list[CapEntry]:
    """Return capitalization entries with their amortization schedule shape.

    `gl_df` must have been categorized (have an `archetype` column). Only
    accounts in capex_software and capex_commission archetypes are emitted.
    """
    if archetype_col not in gl_df.columns or gl_df.empty:
        return []

    out: list[CapEntry] = []
    capex_rows = gl_df[gl_df[archetype_col].isin(["capex_software", "capex_commission"])]
    for (account, name, arche), grp in capex_rows.groupby(
            ["account", "account_name", archetype_col]):
        amount = float(grp["amount_usd"].sum())
        if arche == "capex_software":
            life = int(policy["internal_use_software"].get("default_useful_life_months", 36))
            rule = "asc_350_40"
        else:
            # commissions — use tier1 as default; per-deal handled in
            # commissions_amortization_schedule().
            life = int(
                policy["commissions"]["default_amortization_months_by_archetype"].get("tier1", 60)
            )
            rule = "asc_340_40"
        monthly = amount / life if life else 0.0
        out.append(CapEntry(account=str(account), account_name=str(name), archetype=arche,
                              amount_usd=amount, useful_life_months=life,
                              monthly_amortization_usd=monthly, rule=rule))
    return out


# --- Commissions amortization schedule ---------------------------------------

def commissions_amortization_schedule(deals_df: pd.DataFrame, policy: dict,
                                        period: str,
                                        *, default_commission_rate: float = 0.08
                                        ) -> pd.DataFrame:
    """Per-deal commission capitalization and amortization.

    Columns expected on deals_df: deal_id, customer_id, period (deal start),
    tcv_usd, archetype (optional — if missing, defaults to tier1 amortization).

    If a `commission_usd` column exists it is used verbatim. Otherwise the
    function infers commission as `tcv_usd * default_commission_rate` and
    flags the row with `commission_inferred=True`.

    `period` is the analysis period (YYYY-MM). The function adds:
      - amortization_months: per archetype lookup
      - monthly_amortization_usd: commission / amortization_months
      - amortization_to_date_usd: months_elapsed * monthly_amort, capped at commission
      - balance_at_period_end_usd: commission - amortization_to_date_usd

    Months elapsed is computed from deal_start (the deal's `period` column,
    YYYY-MM) to the analysis period inclusive.
    """
    if deals_df is None or deals_df.empty:
        return pd.DataFrame(columns=["deal_id", "customer_id", "archetype",
                                       "tcv_usd", "commission_usd",
                                       "commission_inferred", "amortization_months",
                                       "monthly_amortization_usd",
                                       "amortization_to_date_usd",
                                       "balance_at_period_end_usd"])

    df = deals_df.copy()
    if "archetype" not in df.columns:
        df["archetype"] = "tier1"
    if "commission_usd" not in df.columns:
        df["commission_usd"] = df["tcv_usd"].astype(float) * default_commission_rate
        df["commission_inferred"] = True
    else:
        df["commission_usd"] = df["commission_usd"].fillna(
            df["tcv_usd"].astype(float) * default_commission_rate)
        df["commission_inferred"] = df["commission_usd"].isna()

    months_table = policy["commissions"]["default_amortization_months_by_archetype"]
    df["amortization_months"] = df["archetype"].map(months_table).fillna(60).astype(int)
    df["monthly_amortization_usd"] = (
        df["commission_usd"].astype(float) / df["amortization_months"]
    )

    # Months elapsed: from deal start period to analysis period inclusive.
    def _months_elapsed(deal_start: str) -> int:
        try:
            ds = date.fromisoformat(deal_start + "-01")
            ap = date.fromisoformat(period + "-01")
        except (TypeError, ValueError):
            return 0
        return max(0, (ap.year - ds.year) * 12 + (ap.month - ds.month) + 1)

    df["months_elapsed"] = df["period"].apply(_months_elapsed)
    df["amortization_to_date_usd"] = (
        (df["months_elapsed"].clip(upper=df["amortization_months"])
            * df["monthly_amortization_usd"]).round(2)
    )
    df["balance_at_period_end_usd"] = (
        df["commission_usd"].astype(float) - df["amortization_to_date_usd"]
    ).round(2)

    return df[[
        "deal_id", "customer_id", "archetype", "tcv_usd", "commission_usd",
        "commission_inferred", "amortization_months", "monthly_amortization_usd",
        "amortization_to_date_usd", "balance_at_period_end_usd",
    ]]


# --- Unit economics ----------------------------------------------------------

def unit_economics(category_totals: dict, kpis: dict) -> dict:
    """Cost per unit for the operationally meaningful denominators.

    `category_totals` is {archetype_name: total_usd} — typically pulled from
    the trend output's current_usd column.
    `kpis` is the loaded operational_kpis.yaml.
    """
    aircraft = float(kpis.get("aircraft_on_platform") or 0)
    pilots = float(kpis.get("pilots_on_product_a") or 0)
    total_opex = sum(v for k, v in category_totals.items()
                       if k not in ("_excluded_", "fx", "allocations"))
    return {
        "total_opex_usd": total_opex,
        "cost_per_aircraft_on_platform_usd": (total_opex / aircraft) if aircraft else float("nan"),
        "cost_per_seat_on_product_a_usd": (total_opex / pilots) if pilots else float("nan"),
        "people_cost_per_aircraft_usd": (
            (category_totals.get("people", 0.0) / aircraft) if aircraft else float("nan")
        ),
        "vendor_cogs_per_aircraft_usd": (
            (category_totals.get("vendor_cogs", 0.0) / aircraft) if aircraft else float("nan")
        ),
    }
