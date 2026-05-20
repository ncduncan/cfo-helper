"""Tests for the cash-flow engine."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts import cash_flow as cf

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def credit_policy():
    with (REPO / "profile" / "memory" / "credit_policy.yaml").open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def hedge_policy():
    with (REPO / "profile" / "memory" / "fx_hedge_policy.yaml").open() as f:
        return yaml.safe_load(f)


def _ar(rows):
    return pd.DataFrame(rows, columns=cf.__doc__ and [
        "invoice_id", "customer_id", "customer_name", "invoice_date",
        "due_date", "as_of_date", "currency", "amount_local", "amount_usd",
        "days_open", "status",
    ])


# --- DSO ---------------------------------------------------------------------

def test_dso_basic():
    ar = pd.DataFrame([
        {"invoice_id": "i1", "customer_id": "c1", "amount_usd": 50_000,
          "status": "open"},
        {"invoice_id": "i2", "customer_id": "c2", "amount_usd": 30_000,
          "status": "open"},
        {"invoice_id": "i3", "customer_id": "c3", "amount_usd": 999_999,
          "status": "paid"},  # excluded
    ])
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "A", "period": "2026-05",
          "revenue_usd": 100_000, "arr_usd": 1_200_000, "product": "x",
          "region": "US", "archetype": "tier1"},
        {"customer_id": "c2", "customer_name": "B", "period": "2026-05",
          "revenue_usd": 50_000, "arr_usd": 600_000, "product": "y",
          "region": "EU", "archetype": "lessor"},
    ])
    out = cf.dso_by_archetype(ar, customers, billings_df=None, period="2026-05")
    by = {r["archetype"]: r for _, r in out.iterrows()}
    # tier1: open=50k, annualized=100k*12=1.2M → DSO = 50k/1.2M*365 ≈ 15.21
    assert by["tier1"]["dso_days"] == pytest.approx(15.21, abs=0.1)
    # lessor: open=30k, annualized=50k*12=600k → DSO = 30k/600k*365 ≈ 18.25
    assert by["lessor"]["dso_days"] == pytest.approx(30_000 / 600_000 * 365, abs=0.1)


def test_dso_empty_ar_returns_empty():
    out = cf.dso_by_archetype(pd.DataFrame(),
                                pd.DataFrame([{"customer_id": "c1"}]),
                                None, "2026-05")
    assert out.empty


def test_dso_unknown_archetype_falls_back():
    ar = pd.DataFrame([
        {"invoice_id": "i1", "customer_id": "c1", "amount_usd": 10_000, "status": "open"},
    ])
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "A", "period": "2026-05",
          "revenue_usd": 50_000, "arr_usd": 600_000, "product": "x", "region": "US"},
    ])
    out = cf.dso_by_archetype(ar, customers, None, "2026-05")
    assert "unknown" in set(out["archetype"])


# --- AR aging ---------------------------------------------------------------

def test_ar_aging_buckets_assigns_correctly():
    today = date(2026, 5, 31)
    rows = [
        {"invoice_id": "i1", "customer_id": "c1",
          "invoice_date": today - timedelta(days=15),
          "amount_usd": 100, "status": "open", "days_open": 15},
        {"invoice_id": "i2", "customer_id": "c1",
          "invoice_date": today - timedelta(days=45),
          "amount_usd": 200, "status": "open", "days_open": 45},
        {"invoice_id": "i3", "customer_id": "c1",
          "invoice_date": today - timedelta(days=200),
          "amount_usd": 300, "status": "open", "days_open": 200},
    ]
    df = pd.DataFrame(rows)
    out = cf.ar_aging_buckets(df, as_of=today)
    by_bucket = dict(zip(out["bucket"], out["open_usd"]))
    assert by_bucket["b0_30"] == 100
    assert by_bucket["b30_60"] == 200
    assert by_bucket["b180+"] == 300


def test_ar_aging_buckets_skips_paid_and_empty():
    df = pd.DataFrame([
        {"invoice_id": "i1", "customer_id": "c1",
          "invoice_date": date(2026, 1, 1),
          "amount_usd": 999, "status": "paid", "days_open": 100},
    ])
    out = cf.ar_aging_buckets(df, as_of=date(2026, 5, 31))
    assert out.empty


# --- Deferred-rev rollforward -----------------------------------------------

def test_deferred_rev_ties_when_inputs_consistent():
    billings = pd.DataFrame([{"amount_usd": 1_000_000}])
    recognized = pd.DataFrame([{"amount_usd": 800_000}])
    rf = cf.deferred_rev_rollforward(opening_balance=5_000_000,
                                       billings_df=billings,
                                       recognized_df=recognized)
    assert rf.closing_balance_usd == pytest.approx(5_200_000)
    assert rf.tied is True


def test_deferred_rev_handles_empty_inputs():
    rf = cf.deferred_rev_rollforward(opening_balance=2_000_000,
                                       billings_df=pd.DataFrame(),
                                       recognized_df=pd.DataFrame())
    assert rf.closing_balance_usd == 2_000_000
    assert rf.billings_usd == 0.0


def test_deferred_rev_with_adjustments():
    billings = pd.DataFrame([{"amount_usd": 100_000}])
    recognized = pd.DataFrame([{"amount_usd": 80_000}])
    adj = pd.DataFrame([{"amount_usd": 5_000}])
    rf = cf.deferred_rev_rollforward(1_000_000, billings, recognized, adj)
    assert rf.closing_balance_usd == pytest.approx(1_015_000)


# --- FX exposure ------------------------------------------------------------

def test_fx_exposure_excludes_usd():
    billings = pd.DataFrame([
        {"currency": "USD", "amount_local": 100, "amount_usd": 100},
        {"currency": "GBP", "amount_local": 100, "amount_usd": 130},
        {"currency": "EUR", "amount_local": 100, "amount_usd": 110},
    ])
    out = cf.fx_exposure(billings, recognized_df=pd.DataFrame(), fx_df=pd.DataFrame())
    assert "USD" not in set(out["currency"])
    assert set(out["currency"]) == {"GBP", "EUR"}


def test_fx_exposure_subtracts_recognized():
    billings = pd.DataFrame([
        {"currency": "GBP", "amount_local": 1000, "amount_usd": 1300},
    ])
    recognized = pd.DataFrame([
        {"currency": "GBP", "amount_local": 600, "amount_usd": 780},
    ])
    out = cf.fx_exposure(billings, recognized, pd.DataFrame())
    assert out.iloc[0]["exposure_usd"] == pytest.approx(520)


# --- Prepay-incentive ROI ---------------------------------------------------

def test_prepay_roi_positive_when_high_cost_of_capital():
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "BigCo", "archetype": "tier1",
          "arr_usd": 1_200_000, "period": "2026-05", "revenue_usd": 100_000,
          "product": "x", "region": "US"},
    ])
    # 5% discount, 20% cost of capital → discount NPV better than ratable
    out = cf.prepay_incentive_roi(customers, billings_df=None,
                                     discount_pct=0.05,
                                     cost_of_capital_annual=0.20,
                                     term_months=12)
    assert out.iloc[0]["npv_gain_usd"] > 0


def test_prepay_roi_negative_when_low_cost_of_capital_high_discount():
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "BigCo", "archetype": "tier1",
          "arr_usd": 1_200_000, "period": "2026-05", "revenue_usd": 100_000,
          "product": "x", "region": "US"},
    ])
    # 10% discount, 2% cost of capital → discount NPV worse than ratable
    out = cf.prepay_incentive_roi(customers, billings_df=None,
                                     discount_pct=0.10,
                                     cost_of_capital_annual=0.02,
                                     term_months=12)
    assert out.iloc[0]["npv_gain_usd"] < 0


# --- Payment-term migration -------------------------------------------------

def test_payment_term_migration_value():
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "A", "archetype": "tier1",
          "payment_terms": "net90", "arr_usd": 1_000_000,
          "revenue_usd": 100_000, "period": "2026-05",
          "product": "x", "region": "US"},
        {"customer_id": "c2", "customer_name": "B", "archetype": "lessor",
          "payment_terms": "net30", "arr_usd": 500_000,
          "revenue_usd": 50_000, "period": "2026-05",
          "product": "y", "region": "EU"},
    ])
    out = cf.payment_term_migration(customers, ar_df=None,
                                       cost_of_capital_annual=0.10,
                                       target_term="net30")
    # c1 saves 60 days × $1M × 10% / 365 ≈ $16,438
    assert len(out) == 1  # only c1 has > 0 days saved
    assert out.iloc[0]["customer_id"] == "c1"
    assert out.iloc[0]["annual_value_usd"] == pytest.approx(60 / 365 * 1_000_000 * 0.10, abs=1)


def test_payment_term_migration_skipped_when_no_terms_column():
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "A", "archetype": "tier1",
          "arr_usd": 1_000_000, "revenue_usd": 100_000, "period": "2026-05",
          "product": "x", "region": "US"},
    ])
    out = cf.payment_term_migration(customers, ar_df=None)
    assert out.empty


# --- Hedge sizing -----------------------------------------------------------

def test_hedge_sizing_recommends_when_above_threshold(hedge_policy):
    exp = pd.DataFrame([{"currency": "GBP", "exposure_usd": 5_000_000}])
    recs = cf.hedge_sizing(exp, hedge_policy, current_hedges=None)
    r = recs[0]
    assert r.status == "recommend_hedge"
    # 65% of 5M = 3.25M
    assert r.target_notional_usd == pytest.approx(3_250_000)


def test_hedge_sizing_below_threshold_skipped(hedge_policy):
    exp = pd.DataFrame([{"currency": "GBP", "exposure_usd": 100_000}])
    recs = cf.hedge_sizing(exp, hedge_policy)
    assert recs[0].status == "below_threshold"


def test_hedge_sizing_within_band_when_current_matches(hedge_policy):
    exp = pd.DataFrame([{"currency": "GBP", "exposure_usd": 5_000_000}])
    cur = pd.DataFrame([{"currency": "GBP", "notional_usd": 3_300_000}])
    # target 3.25M, ±10% band = 2.925M..3.575M → 3.3M is within band
    recs = cf.hedge_sizing(exp, hedge_policy, current_hedges=cur)
    assert recs[0].status == "within_band"


def test_hedge_sizing_over_hedged(hedge_policy):
    exp = pd.DataFrame([{"currency": "GBP", "exposure_usd": 5_000_000}])
    cur = pd.DataFrame([{"currency": "GBP", "notional_usd": 5_000_000}])
    recs = cf.hedge_sizing(exp, hedge_policy, current_hedges=cur)
    assert recs[0].status == "over_hedged"


def test_hedge_sizing_no_hedge_required_for_pegged(hedge_policy):
    exp = pd.DataFrame([{"currency": "AED", "exposure_usd": 5_000_000}])
    recs = cf.hedge_sizing(exp, hedge_policy)
    assert recs[0].status == "no_hedge_required"


# --- Cash conversion cycle --------------------------------------------------

def test_ccc_with_strong_deferred_revenue():
    """SaaS with multi-year prepays → CCC should be negative (working-capital
    benefit)."""
    ar = pd.DataFrame([
        {"invoice_id": "i1", "customer_id": "c1", "amount_usd": 1_000_000,
          "status": "open"},
    ])
    res = cf.cash_conversion_cycle(ar, None,
                                      deferred_rev_balance=20_000_000,
                                      annualized_revenue=100_000_000)
    assert res["dso_days"] == pytest.approx(3.65, abs=0.1)
    assert res["deferred_rev_days"] == pytest.approx(73, abs=1)
    assert res["ccc_days"] < 0  # cash positive on prepays


# --- Customer watchlist -----------------------------------------------------

def test_watchlist_flags_dso_excess(credit_policy):
    ar = pd.DataFrame([
        {"invoice_id": "i1", "customer_id": "c1", "customer_name": "BigCo",
          "amount_usd": 50_000, "status": "open",
          "invoice_date": date(2026, 1, 1), "days_open": 100},
    ])
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "BigCo", "archetype": "tier1",
          "period": "2026-05", "revenue_usd": 0, "arr_usd": 0,
          "product": "x", "region": "US"},
    ])
    # tier1 target=35, excess=15 → archetype DSO of 60 should trigger
    dso_df = pd.DataFrame([{"archetype": "tier1", "dso_days": 60.0}])
    out = cf.customer_watchlist(ar, customers, dso_df, credit_policy,
                                  as_of=date(2026, 5, 31))
    assert not out.empty
    assert "dso_excess" in out.iloc[0]["flags"]


def test_watchlist_flags_aged_balance(credit_policy):
    # tier1 threshold 250k at 90+ days
    ar = pd.DataFrame([
        {"invoice_id": "i1", "customer_id": "c1", "customer_name": "BigCo",
          "amount_usd": 300_000, "status": "open",
          "invoice_date": date(2025, 11, 1), "days_open": 200},
    ])
    customers = pd.DataFrame([
        {"customer_id": "c1", "customer_name": "BigCo", "archetype": "tier1",
          "period": "2026-05", "revenue_usd": 0, "arr_usd": 0,
          "product": "x", "region": "US"},
    ])
    dso_df = pd.DataFrame([{"archetype": "tier1", "dso_days": 5.0}])  # below excess
    out = cf.customer_watchlist(ar, customers, dso_df, credit_policy,
                                  as_of=date(2026, 5, 31))
    assert not out.empty
    assert "aged_balance" in out.iloc[0]["flags"]
