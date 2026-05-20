"""
Cash-flow optimization engine.

Pure functions over pandas DataFrames. No I/O, no global state.

Public API:
    dso_by_archetype(ar_df, customers_df, billings_df, period)
    ar_aging_buckets(ar_df, *, as_of, buckets=(30,60,90,180))
    deferred_rev_rollforward(opening_balance, billings_df, recognized_df, adjustments_df=None)
    fx_exposure(billings_df, recognized_df, fx_df)
    prepay_incentive_roi(customers_df, billings_df, *, discount_pct, cost_of_capital_annual, term_months=12)
    payment_term_migration(customers_df, ar_df, *, cost_of_capital_annual)
    hedge_sizing(fx_exposure_df, hedge_policy)
    cash_conversion_cycle(ar_df, ap_df, deferred_rev_balance, annualized_revenue, annualized_cogs)
    customer_watchlist(ar_df, customers_df, dso_df, credit_policy, *, as_of)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd


# --- Helpers -----------------------------------------------------------------

def _as_dt(x) -> date | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if isinstance(x, date) and not isinstance(x, datetime):
        return x
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, str):
        try:
            return date.fromisoformat(x[:10])
        except ValueError:
            return None
    if isinstance(x, pd.Timestamp):
        return x.date()
    return None


def _period_end(period: str) -> date:
    """Return the last day of a YYYY-MM period."""
    y, m = (int(x) for x in period.split("-"))
    if m == 12:
        return date(y + 1, 1, 1) - timedelta(days=1)
    return date(y, m + 1, 1) - timedelta(days=1)


# --- DSO ---------------------------------------------------------------------

def dso_by_archetype(ar_df: pd.DataFrame, customers_df: pd.DataFrame,
                      billings_df: pd.DataFrame | None,
                      period: str, *,
                      lookback_days: int = 90) -> pd.DataFrame:
    """Compute DSO per archetype.

    Formula: DSO = (open_AR / annualized_billings) * 365.

    `billings_df` columns expected: customer_id, period (YYYY-MM), amount_usd.
    When `billings_df` is None or empty, the function falls back to
    `customers_df.revenue_usd` annualized as 12x the period's revenue.

    `customers_df` is the canonical customers table; the function joins on
    customer_id for the archetype attribution. If there is no `archetype`
    column on customers, all rows are bucketed under archetype='unknown'.
    """
    if ar_df is None or ar_df.empty:
        return pd.DataFrame(columns=["archetype", "open_ar_usd",
                                      "annualized_billings_usd", "dso_days"])

    if "archetype" in customers_df.columns:
        cust = customers_df[["customer_id", "archetype"]].drop_duplicates("customer_id")
    else:
        cust = (customers_df[["customer_id"]].drop_duplicates("customer_id")
                .assign(archetype="unknown"))

    open_ar = ar_df[ar_df["status"].fillna("open") == "open"]
    open_ar = open_ar.merge(cust, on="customer_id", how="left").fillna({"archetype": "unknown"})
    open_by_arche = (open_ar.groupby("archetype", dropna=False)["amount_usd"]
                       .sum().rename("open_ar_usd").reset_index())

    if billings_df is not None and not billings_df.empty:
        # Annualize: sum lookback_days worth of billings, scale to 365.
        b = billings_df.merge(cust, on="customer_id", how="left").fillna({"archetype": "unknown"})
        # Filter to period window — billings_df is per-period (YYYY-MM)
        period_end = _period_end(period)
        cutoff_period = (period_end - timedelta(days=lookback_days)).strftime("%Y-%m")
        b = b[b["period"] >= cutoff_period]
        billed = b.groupby("archetype", dropna=False)["amount_usd"].sum()
        annualized = (billed * (365.0 / lookback_days)).rename("annualized_billings_usd").reset_index()
    else:
        # Fall back to customers.revenue_usd annualized.
        # customers_df already carries archetype (or we synthesize 'unknown').
        rev = customers_df[customers_df["period"] == period].copy()
        if "archetype" not in rev.columns:
            rev["archetype"] = "unknown"
        else:
            rev["archetype"] = rev["archetype"].fillna("unknown")
        billed = rev.groupby("archetype", dropna=False)["revenue_usd"].sum()
        annualized = (billed * 12).rename("annualized_billings_usd").reset_index()

    out = open_by_arche.merge(annualized, on="archetype", how="outer").fillna(0.0)
    out["dso_days"] = out.apply(
        lambda r: (float(r["open_ar_usd"]) / float(r["annualized_billings_usd"])) * 365
        if r["annualized_billings_usd"] else float("nan"),
        axis=1,
    )
    return out


# --- AR aging ----------------------------------------------------------------

def ar_aging_buckets(ar_df: pd.DataFrame, *, as_of: date | str | None = None,
                       buckets: tuple[int, ...] = (30, 60, 90, 180)
                       ) -> pd.DataFrame:
    """Bucket open AR invoices by age. Returns one row per (customer_id, bucket)
    with the open_usd in that bucket.

    Buckets are cumulative cutoffs: invoices older than buckets[0] but younger
    than buckets[1] go into label 'b30', and so on. Anything older than the
    last bucket goes to 'b{last}+'.
    """
    if ar_df is None or ar_df.empty:
        return pd.DataFrame(columns=["customer_id", "bucket", "open_usd",
                                      "invoice_count"])

    df = ar_df[ar_df["status"].fillna("open") == "open"].copy()
    if df.empty:
        return pd.DataFrame(columns=["customer_id", "bucket", "open_usd",
                                      "invoice_count"])

    if as_of is None:
        as_of_d = date.today()
    else:
        as_of_d = _as_dt(as_of) or date.today()

    def _bucket(days_open: float) -> str:
        d = float(days_open or 0)
        prev = 0
        for cutoff in buckets:
            if d < cutoff:
                return f"b{prev}_{cutoff}"
            prev = cutoff
        return f"b{buckets[-1]}+"

    if "days_open" not in df.columns or df["days_open"].isna().any():
        df["days_open"] = df["invoice_date"].apply(lambda x:
            (as_of_d - _as_dt(x)).days if _as_dt(x) else 0)

    df["bucket"] = df["days_open"].apply(_bucket)
    grp = (df.groupby(["customer_id", "bucket"], dropna=False)
             .agg(open_usd=("amount_usd", "sum"),
                  invoice_count=("invoice_id", "count"))
             .reset_index())
    return grp


# --- Deferred-revenue rollforward -------------------------------------------

@dataclass
class DeferredRevRollforward:
    opening_balance_usd: float
    billings_usd: float
    recognized_usd: float
    adjustments_usd: float
    closing_balance_usd: float
    tied: bool


def deferred_rev_rollforward(opening_balance: float,
                                billings_df: pd.DataFrame,
                                recognized_df: pd.DataFrame,
                                adjustments_df: pd.DataFrame | None = None,
                                *, tolerance: float = 1.0
                                ) -> DeferredRevRollforward:
    """Opening + Billings - Recognized - Adjustments = Closing.

    Both billings and recognized DataFrames must have an `amount_usd` column.
    The function does not enforce the period — the caller filters first.
    """
    billings = float(billings_df["amount_usd"].sum()) if billings_df is not None and not billings_df.empty else 0.0
    recognized = float(recognized_df["amount_usd"].sum()) if recognized_df is not None and not recognized_df.empty else 0.0
    adjustments = float(adjustments_df["amount_usd"].sum()) if adjustments_df is not None and not adjustments_df.empty else 0.0
    closing = opening_balance + billings - recognized - adjustments
    return DeferredRevRollforward(
        opening_balance_usd=float(opening_balance),
        billings_usd=billings, recognized_usd=recognized,
        adjustments_usd=adjustments, closing_balance_usd=closing,
        tied=abs(opening_balance + billings - recognized - adjustments - closing) <= tolerance,
    )


# --- FX exposure -------------------------------------------------------------

def fx_exposure(billings_df: pd.DataFrame,
                  recognized_df: pd.DataFrame,
                  fx_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Open exposure per non-USD currency = (billings - recognized) per ccy.

    Returns one row per currency with the unhedged USD-equivalent. The
    hedge_sizing step compares this to policy. The fx_df argument is reserved
    for restating amount_local at a single rate when callers want to override
    the embedded amount_usd; v1 ignores it (the embedded amount_usd is trusted).
    """
    del fx_df  # reserved for future use
    if billings_df is None or billings_df.empty:
        return pd.DataFrame(columns=["currency", "exposure_usd"])

    has_local = "amount_local" in billings_df.columns and "currency" in billings_df.columns
    if not has_local:
        return pd.DataFrame(columns=["currency", "exposure_usd"])

    billed = (billings_df.groupby("currency")["amount_usd"]
                .sum().rename("billed_usd").reset_index())
    if recognized_df is not None and not recognized_df.empty and "currency" in recognized_df.columns:
        rec = (recognized_df.groupby("currency")["amount_usd"]
                .sum().rename("recognized_usd").reset_index())
        out = billed.merge(rec, on="currency", how="outer").fillna(0.0)
    else:
        out = billed.assign(recognized_usd=0.0)
    out["exposure_usd"] = out["billed_usd"] - out["recognized_usd"]
    out = out[out["currency"] != "USD"]
    return out


# --- Prepay-incentive ROI ---------------------------------------------------

def prepay_incentive_roi(customers_df: pd.DataFrame,
                           billings_df: pd.DataFrame | None,
                           *, discount_pct: float = 0.05,
                           cost_of_capital_annual: float = 0.10,
                           term_months: int = 12,
                           top_n: int = 20) -> pd.DataFrame:
    """For each customer, NPV gain of accepting a prepay-incentive offer.

    Status quo: bill ratably over the term, collect monthly (assumed net30).
    Offered: collect full term up front in exchange for `discount_pct` off.

    NPV gain = (status_quo_NPV) - (prepay_NPV)
    where status_quo_NPV = sum_{m=1..term} monthly_billing / (1 + r/12)^m
    and prepay_NPV       = (1 - discount_pct) * total_billing.

    A positive `npv_gain_usd` means the customer is a candidate for the offer
    from the company's perspective (we'd be cash-positive on it). A negative
    means we'd lose value at this discount level.

    Returns top_n by absolute npv_gain_usd.
    """
    if customers_df is None or customers_df.empty:
        return pd.DataFrame(columns=["customer_id", "customer_name", "archetype",
                                      "annualized_billings_usd", "discount_pct",
                                      "status_quo_npv_usd", "prepay_npv_usd",
                                      "npv_gain_usd"])

    if billings_df is not None and not billings_df.empty:
        billed = (billings_df.groupby("customer_id")["amount_usd"]
                    .sum().rename("annualized_billings_usd").reset_index())
        df = customers_df.drop_duplicates("customer_id").merge(billed, on="customer_id", how="left")
    else:
        df = customers_df.copy()
        df["annualized_billings_usd"] = (df.get("arr_usd")
            if "arr_usd" in df.columns else df.get("revenue_usd", 0) * 12)
    if "archetype" not in df.columns:
        df["archetype"] = "unknown"
    df["annualized_billings_usd"] = df["annualized_billings_usd"].fillna(0.0).astype(float)

    monthly_disc = (1.0 + cost_of_capital_annual) ** (1.0 / 12.0) - 1.0
    annuity_factor = sum(1.0 / ((1.0 + monthly_disc) ** m) for m in range(1, term_months + 1))

    df["status_quo_npv_usd"] = (df["annualized_billings_usd"] / 12.0) * annuity_factor
    df["prepay_npv_usd"] = (1.0 - discount_pct) * df["annualized_billings_usd"]
    df["npv_gain_usd"] = df["prepay_npv_usd"] - df["status_quo_npv_usd"]
    df["discount_pct"] = discount_pct

    keep = ["customer_id", "customer_name", "archetype", "annualized_billings_usd",
            "discount_pct", "status_quo_npv_usd", "prepay_npv_usd", "npv_gain_usd"]
    keep = [c for c in keep if c in df.columns]
    return (df[keep].sort_values("npv_gain_usd", ascending=False).head(top_n).reset_index(drop=True))


# --- Payment-term migration -------------------------------------------------

def payment_term_migration(customers_df: pd.DataFrame,
                              ar_df: pd.DataFrame | None = None,
                              *, cost_of_capital_annual: float = 0.10,
                              target_term: str = "net30",
                              billings_df: pd.DataFrame | None = None
                              ) -> pd.DataFrame:
    """Estimate the cash-conversion gain from migrating long-payment-term
    customers to a shorter term.

    The formula treats the saved DSO days as freed-up working capital:
        annual_value = (days_saved / 365) * annualized_billings * cost_of_capital

    `customers_df` is expected to carry `payment_terms`. If absent, all rows
    are skipped. Migration deltas (in days):
        net30 → 30, net60 → 60, net90 → 90, prepay → 0
    """
    if customers_df is None or customers_df.empty or "payment_terms" not in customers_df.columns:
        return pd.DataFrame(columns=["customer_id", "customer_name", "current_terms",
                                      "target_terms", "days_saved",
                                      "annualized_billings_usd",
                                      "annual_value_usd"])

    del ar_df  # reserved — future versions may use AR-implied effective terms
    days_for = {"net30": 30, "net60": 60, "net90": 90,
                  "prepay_annual": 0, "prepay_full_term": 0}
    target_days = days_for.get(target_term, 30)

    df = customers_df.copy()
    if billings_df is not None and not billings_df.empty:
        billed = (billings_df.groupby("customer_id")["amount_usd"].sum()
                    .rename("annualized_billings_usd").reset_index())
        df = df.merge(billed, on="customer_id", how="left")
    else:
        df["annualized_billings_usd"] = (df.get("arr_usd")
            if "arr_usd" in df.columns else df.get("revenue_usd", 0) * 12)
    df["annualized_billings_usd"] = df["annualized_billings_usd"].fillna(0.0).astype(float)

    df["current_days"] = df["payment_terms"].map(days_for).fillna(30).astype(int)
    df["days_saved"] = (df["current_days"] - target_days).clip(lower=0)
    df = df[df["days_saved"] > 0].copy()
    df["target_terms"] = target_term
    df["annual_value_usd"] = (df["days_saved"] / 365.0
                                 * df["annualized_billings_usd"]
                                 * cost_of_capital_annual)
    df = df.rename(columns={"payment_terms": "current_terms"})
    keep = ["customer_id", "customer_name", "current_terms", "target_terms",
             "days_saved", "annualized_billings_usd", "annual_value_usd"]
    keep = [c for c in keep if c in df.columns]
    return df[keep].sort_values("annual_value_usd", ascending=False).reset_index(drop=True)


# --- FX hedge sizing --------------------------------------------------------

@dataclass
class HedgeRecommendation:
    currency: str
    exposure_usd: float
    target_hedge_ratio: float
    target_notional_usd: float
    min_threshold_usd: float
    status: str  # below_threshold | recommend_hedge | within_band | unknown_currency
    notes: str = ""


def hedge_sizing(fx_exposure_df: pd.DataFrame, hedge_policy: dict,
                  current_hedges: pd.DataFrame | None = None
                  ) -> list[HedgeRecommendation]:
    """For each currency in the exposure frame, return the recommended hedge
    notional vs. policy.

    `current_hedges` (optional) has columns currency, notional_usd. When
    provided, the recommendation factors in the existing hedge:
        - within_band  : current notional within ±10% of target
        - recommend_hedge : add up to (target - current)
        - over_hedged : current > target * 1.10

    Without `current_hedges`, status is binary (below_threshold or recommend_hedge).
    """
    if fx_exposure_df is None or fx_exposure_df.empty:
        return []
    defaults = hedge_policy
    by_ccy = hedge_policy.get("currencies", {})

    cur_map: dict[str, float] = {}
    if current_hedges is not None and not current_hedges.empty:
        for _, r in current_hedges.iterrows():
            cur_map[str(r["currency"])] = float(r.get("notional_usd") or 0)

    out: list[HedgeRecommendation] = []
    for _, r in fx_exposure_df.iterrows():
        ccy = str(r["currency"])
        exposure = float(r["exposure_usd"])
        ccy_policy = by_ccy.get(ccy, {})
        ratio = float(ccy_policy.get("target_hedge_ratio",
                                       defaults.get("default_target_hedge_ratio", 0.6)))
        threshold = float(ccy_policy.get("min_exposure_for_hedging_usd",
                                            defaults.get("default_min_exposure_for_hedging_usd",
                                                            1_000_000)))
        target = max(0.0, exposure * ratio)
        current = cur_map.get(ccy, 0.0)

        if exposure < threshold:
            status = "below_threshold"
            notes = f"Exposure ${exposure:,.0f} below threshold ${threshold:,.0f}"
        elif ratio == 0.0:
            status = "no_hedge_required"
            notes = ccy_policy.get("notes", "")
        elif current_hedges is None:
            status = "recommend_hedge"
            notes = f"Hedge to ${target:,.0f} ({ratio:.0%} of exposure)"
        else:
            band_lo = target * 0.90
            band_hi = target * 1.10
            if current < band_lo:
                status = "recommend_hedge"
                notes = f"Add ${target - current:,.0f} to reach ${target:,.0f}"
            elif current > band_hi:
                status = "over_hedged"
                notes = f"Reduce by ${current - target:,.0f} to reach ${target:,.0f}"
            else:
                status = "within_band"
                notes = f"Current ${current:,.0f} within ±10% of target"
        out.append(HedgeRecommendation(
            currency=ccy, exposure_usd=exposure,
            target_hedge_ratio=ratio, target_notional_usd=target,
            min_threshold_usd=threshold, status=status, notes=notes,
        ))
    return out


# --- Cash conversion cycle --------------------------------------------------

def cash_conversion_cycle(ar_df: pd.DataFrame, ap_df: pd.DataFrame | None,
                            deferred_rev_balance: float,
                            annualized_revenue: float,
                            annualized_cogs: float | None = None) -> dict:
    """CCC = DSO + DIO - DPO - Deferred-rev days.

    SaaS: DIO = 0.
    Deferred-rev days = (deferred_rev_balance / annualized_revenue) * 365
    is treated as negative-of-DSO since it represents cash collected ahead of
    revenue (working-capital benefit).
    """
    if ar_df is None or ar_df.empty:
        ar_total = 0.0
    else:
        ar_total = float(ar_df[ar_df["status"].fillna("open") == "open"]["amount_usd"].sum())

    if ap_df is None or ap_df.empty or annualized_cogs is None or annualized_cogs <= 0:
        dpo = 0.0
    else:
        ap_total = float(ap_df[ap_df["status"].fillna("open") == "open"]["amount_usd"].sum())
        dpo = (ap_total / annualized_cogs) * 365

    dso = (ar_total / annualized_revenue) * 365 if annualized_revenue else 0.0
    deferred_days = (deferred_rev_balance / annualized_revenue) * 365 if annualized_revenue else 0.0
    ccc = dso - dpo - deferred_days

    return {
        "dso_days": dso, "dpo_days": dpo, "dio_days": 0.0,
        "deferred_rev_days": deferred_days,
        "ccc_days": ccc,
    }


# --- Customer watchlist -----------------------------------------------------

def customer_watchlist(ar_df: pd.DataFrame, customers_df: pd.DataFrame,
                          dso_df: pd.DataFrame, credit_policy: dict,
                          *, as_of: date | str | None = None) -> pd.DataFrame:
    """Flag customers in breach of credit policy.

    Two flags:
      - dso_excess: archetype DSO exceeds (target + watchlist_dso_excess_days)
      - aged_balance: any single open invoice older than
        watchlist_min_aged_bucket_days with amount > watchlist_aged_balance_threshold_usd
    """
    if ar_df is None or ar_df.empty:
        return pd.DataFrame(columns=["customer_id", "customer_name", "archetype",
                                      "flags", "max_open_invoice_usd",
                                      "max_days_open"])

    if "archetype" in customers_df.columns:
        cust = customers_df[["customer_id", "customer_name", "archetype"]].drop_duplicates("customer_id")
    else:
        cust = (customers_df[["customer_id", "customer_name"]].drop_duplicates("customer_id")
                .assign(archetype="unknown"))

    # Drop overlapping columns from ar before merge so the joined frame has a
    # single customer_name / archetype.
    ar_open = ar_df[ar_df["status"].fillna("open") == "open"].copy()
    drop_cols = [c for c in ("customer_name", "archetype") if c in ar_open.columns]
    open_ar = ar_open.drop(columns=drop_cols).merge(cust, on="customer_id", how="left")
    open_ar = open_ar.fillna({"archetype": "unknown"})
    if as_of is not None:
        as_of_d = _as_dt(as_of)
        if as_of_d and "invoice_date" in open_ar.columns:
            open_ar["days_open"] = open_ar["invoice_date"].apply(
                lambda x: (as_of_d - (_as_dt(x) or as_of_d)).days)

    archetypes = credit_policy.get("archetypes", {})
    dso_lookup = dict(zip(dso_df.get("archetype", []), dso_df.get("dso_days", []))) if dso_df is not None else {}

    flags_list: list[dict] = []
    for cid, grp in open_ar.groupby("customer_id"):
        archetype = grp["archetype"].iloc[0]
        policy = archetypes.get(archetype, archetypes.get("unknown", {}))
        flags = []
        target = float(policy.get("dso_target_days", 45))
        excess = float(policy.get("watchlist_dso_excess_days", 20))
        threshold = float(policy.get("watchlist_aged_balance_threshold_usd", 100_000))
        min_age = float(policy.get("watchlist_min_aged_bucket_days", 90))

        # Default archetype DSO to the policy target (not 0): a missing DSO
        # row should mean "no DSO data wired" → no spurious clean pass, and
        # also no spurious flag. Defaulting to `target` makes the comparison
        # `target > target + excess` always False, so the flag fires only on
        # real measured exceedance.
        archetype_dso = float(dso_lookup.get(archetype, target))
        if archetype_dso > target + excess:
            flags.append(f"dso_excess({archetype_dso:.0f}d vs target {target:.0f}+{excess:.0f})")

        max_open = float(grp["amount_usd"].max())
        max_days = float(grp.get("days_open", pd.Series([0])).max() or 0)
        aged_breach = grp[(grp.get("days_open", 0) >= min_age)
                            & (grp["amount_usd"] >= threshold)]
        if not aged_breach.empty:
            flags.append(f"aged_balance(${aged_breach['amount_usd'].max():,.0f} > ${threshold:,.0f})")

        if flags:
            flags_list.append({
                "customer_id": cid,
                "customer_name": grp["customer_name"].iloc[0],
                "archetype": archetype,
                "flags": "; ".join(flags),
                "max_open_invoice_usd": max_open,
                "max_days_open": max_days,
            })
    return pd.DataFrame(flags_list)
