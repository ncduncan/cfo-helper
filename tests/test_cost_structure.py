"""Tests for the cost-structure engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts import cost_structure as cs

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def categories():
    with (REPO / "profile" / "memory" / "cost_categories.yaml").open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def cap_policy():
    with (REPO / "profile" / "memory" / "capitalization_policy.yaml").open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def kpis():
    with (REPO / "profile" / "memory" / "operational_kpis.yaml").open() as f:
        return yaml.safe_load(f)


def _gl(rows):
    cols = ["entity", "period", "account", "account_name",
            "debit", "credit", "currency", "amount_local", "amount_usd"]
    return pd.DataFrame(rows, columns=cols)


# --- categorize_gl ----------------------------------------------------------

def test_categorize_maps_known_accounts(categories):
    df = _gl([
        ["UK", "2026-05", "5100", "Hosting Costs",   0, 0, "USD", 100, 100],
        ["UK", "2026-05", "6100", "Salaries",        0, 0, "USD", 200, 200],
        ["UK", "2026-05", "6210", "Software Subs",   0, 0, "USD",  50,  50],
        ["UK", "2026-05", "4100", "Subscription Rev",0, 0, "USD", 999, 999],
    ])
    out = cs.categorize_gl(df, categories)
    by = dict(zip(out["account"].astype(str), out["archetype"]))
    assert by["5100"] == "vendor_cogs"
    assert by["6100"] == "people"
    assert by["6210"] == "vendor_opex"
    assert by["4100"] == "_excluded_"


def test_categorize_fails_closed_on_unmapped():
    # Use a deliberately incomplete categories dict (gap at 9999) — production
    # cost_categories.yaml is exhaustive by design (catch-all excluded ranges).
    sparse = {
        "archetypes": {
            "people": {"account_ranges": [["6000", "6199"]]},
        },
        "excluded": {"account_ranges": [["1000", "1199"], ["4000", "4999"]]},
    }
    df = _gl([
        ["UK", "2026-05", "9999", "Mystery", 0, 0, "USD", 100, 100],
    ])
    with pytest.raises(ValueError, match="Unmapped GL accounts"):
        cs.categorize_gl(df, sparse)


def test_production_categories_have_no_gaps(categories):
    # Probe every 50th account across [1000, 9999] — production policy must
    # categorize all of them (either to an archetype or _excluded_).
    probes = [str(n) for n in range(1000, 10000, 50)]
    df = _gl([["UK", "2026-05", a, "probe", 0, 0, "USD", 1, 1] for a in probes])
    out = cs.categorize_gl(df, categories)  # must not raise
    assert (out["archetype"] != "").all()


# --- trend ------------------------------------------------------------------

def test_trend_with_prior_computes_deltas(categories):
    curr = _gl([
        ["UK", "2026-05", "6100", "Salaries", 0, 0, "USD", 1100, 1100],
        ["UK", "2026-05", "6210", "Subs",     0, 0, "USD",  120,  120],
    ])
    curr = cs.categorize_gl(curr, categories)
    prior = _gl([
        ["UK", "2026-04", "6100", "Salaries", 0, 0, "USD", 1000, 1000],
        ["UK", "2026-04", "6210", "Subs",     0, 0, "USD",  100,  100],
    ])
    prior = cs.categorize_gl(prior, categories)
    out = cs.trend(curr, prior).set_index("archetype")
    assert out.loc["people", "current_usd"] == 1100
    assert out.loc["people", "prior_usd"] == 1000
    assert out.loc["people", "delta_usd"] == 100
    assert out.loc["people", "delta_pct"] == pytest.approx(0.10)


def test_trend_without_prior_marks_nan(categories):
    curr = _gl([["UK", "2026-05", "6100", "S", 0, 0, "USD", 100, 100]])
    curr = cs.categorize_gl(curr, categories)
    out = cs.trend(curr, None)
    assert out.iloc[0]["prior_usd"] == 0.0
    assert pd.isna(out.iloc[0]["delta_pct"])


def test_trend_fx_neutralization(categories):
    # Same local currency amount but different USD rates between periods.
    curr = _gl([["UK", "2026-05", "6100", "S", 0, 0, "GBP", 1000, 1300]])  # rate 1.3
    prior = _gl([["UK", "2026-04", "6100", "S", 0, 0, "GBP", 1000, 1200]])  # rate 1.2
    curr = cs.categorize_gl(curr, categories)
    prior = cs.categorize_gl(prior, categories)
    fx = pd.DataFrame([{"currency": "GBP", "rate_to_usd_avg": 1.3, "rate_to_usd_eop": 1.3}])
    out = cs.trend(curr, prior, fx_table=fx).iloc[0]
    # Both restated at 1.3 → both 1300 → delta zero on a constant-currency basis.
    assert out["current_usd"] == pytest.approx(1300)
    assert out["prior_usd"] == pytest.approx(1300)
    assert out["delta_usd"] == pytest.approx(0)


# --- top_movers --------------------------------------------------------------

def test_top_movers_ranks_by_absolute_delta_with_threshold():
    df = pd.DataFrame([
        {"archetype": "a", "current_usd": 1100, "prior_usd": 1000,
         "delta_usd": 100, "delta_pct": 0.10},   # below 20% threshold
        {"archetype": "b", "current_usd": 500,  "prior_usd": 200,
         "delta_usd": 300, "delta_pct": 1.50},
        {"archetype": "c", "current_usd": 250,  "prior_usd": 1000,
         "delta_usd": -750, "delta_pct": -0.75},
    ])
    out = cs.top_movers(df, n=5, threshold_pct=0.20)
    # b (300) and c (-750) qualify; c ranks above b by abs delta.
    assert list(out["archetype"]) == ["c", "b"]


def test_top_movers_no_prior_returns_top_current():
    df = pd.DataFrame([
        {"archetype": "a", "current_usd": 100, "prior_usd": 0,
         "delta_usd": float("nan"), "delta_pct": float("nan")},
        {"archetype": "b", "current_usd": 500, "prior_usd": 0,
         "delta_usd": float("nan"), "delta_pct": float("nan")},
    ])
    out = cs.top_movers(df, n=1)
    assert list(out["archetype"]) == ["b"]


# --- vendor_concentration ---------------------------------------------------

def test_vendor_concentration_with_data():
    vendors = pd.DataFrame([
        {"vendor_id": f"v{i}", "vendor_name": f"v{i}", "category": "x",
         "country": "US", "currency": "USD", "ytd_spend_usd": float(amount)}
        for i, amount in enumerate([900, 800, 700, 600, 500, 400, 300, 200, 100, 50, 30, 20])
    ])
    res = cs.vendor_concentration(pd.DataFrame(), vendors)
    assert res.total_vendor_spend_usd == pytest.approx(4600)
    # top 10 = sum of top10 = 900+800+...+50 = 4550 → 4550/4600 = 98.9%
    assert res.top10_share == pytest.approx(4550 / 4600, abs=1e-6)
    assert len(res.top10_rows) == 10


def test_vendor_concentration_empty_returns_sentinel():
    res = cs.vendor_concentration(pd.DataFrame(), pd.DataFrame())
    assert pd.isna(res.top10_share)
    assert "no vendor master" in res.notes


# --- headcount_unit_cost ----------------------------------------------------

def test_headcount_uses_fully_loaded_cost_when_present():
    hc = pd.DataFrame([
        {"entity": "UK", "period": "2026-05", "department": "Eng", "function": "engineering",
         "fte": 5, "fully_loaded_cost_usd": 1_000_000},
        {"entity": "UK", "period": "2026-05", "department": "GTM", "function": "sales",
         "fte": 3, "fully_loaded_cost_usd": 900_000},
    ])
    res = cs.headcount_unit_cost(hc)
    assert res["fte_total"] == 8
    assert res["fully_loaded_cost_total_usd"] == 1_900_000
    assert res["fully_loaded_cost_per_fte_usd"] == pytest.approx(237_500)
    assert set(res["by_function"]["function"]) == {"engineering", "sales"}


# --- capitalization_classify ------------------------------------------------

def test_capitalization_classify_groups_capex_accounts(cap_policy):
    df = pd.DataFrame([
        {"account": "1750", "account_name": "Cap'd platform dev",
         "amount_usd": 360_000, "archetype": "capex_software"},
        {"account": "1760", "account_name": "Cap'd commissions",
         "amount_usd": 240_000, "archetype": "capex_commission"},
        {"account": "6100", "account_name": "Salaries",
         "amount_usd": 100_000, "archetype": "people"},
    ])
    out = cs.capitalization_classify(df, cap_policy)
    by_account = {e.account: e for e in out}
    assert "1750" in by_account and "1760" in by_account
    sw = by_account["1750"]
    assert sw.useful_life_months == 36
    assert sw.monthly_amortization_usd == pytest.approx(10_000)
    assert sw.rule == "asc_350_40"


# --- commissions_amortization_schedule --------------------------------------

def test_commissions_amortization_tier1(cap_policy):
    deals = pd.DataFrame([
        {"deal_id": "d1", "customer_id": "c1", "archetype": "tier1",
         "tcv_usd": 1_000_000, "period": "2026-01", "commission_usd": 84_000},
    ])
    out = cs.commissions_amortization_schedule(deals, cap_policy, period="2026-05")
    row = out.iloc[0]
    # tier1 amortization = 84 months
    assert row["amortization_months"] == 84
    assert row["monthly_amortization_usd"] == pytest.approx(1000)  # 84_000 / 84
    # 5 months elapsed (Jan..May inclusive) → 5_000 amortized to date
    assert row["amortization_to_date_usd"] == pytest.approx(5000)
    assert row["balance_at_period_end_usd"] == pytest.approx(79_000)


def test_commissions_amortization_inferred_when_no_column(cap_policy):
    deals = pd.DataFrame([
        {"deal_id": "d1", "customer_id": "c1", "archetype": "tier1",
         "tcv_usd": 1_000_000, "period": "2026-01"},
    ])
    out = cs.commissions_amortization_schedule(deals, cap_policy, period="2026-05",
                                                  default_commission_rate=0.08)
    row = out.iloc[0]
    # Inferred commission = 80_000 over 84 months ≈ 952.38 / month
    assert row["commission_usd"] == pytest.approx(80_000)
    assert row["monthly_amortization_usd"] == pytest.approx(80_000 / 84)


def test_commissions_amortization_caps_at_term(cap_policy):
    # Deal closed in 2025-01, analysis period 2030-01 → 60 months elapsed.
    # bga archetype amortizes over 36 months → fully amortized.
    deals = pd.DataFrame([
        {"deal_id": "d1", "customer_id": "c1", "archetype": "bga",
         "tcv_usd": 100_000, "period": "2025-01", "commission_usd": 8_000},
    ])
    out = cs.commissions_amortization_schedule(deals, cap_policy, period="2030-01")
    row = out.iloc[0]
    assert row["amortization_to_date_usd"] == pytest.approx(8_000)
    assert row["balance_at_period_end_usd"] == pytest.approx(0)


def test_commissions_amortization_empty_input(cap_policy):
    out = cs.commissions_amortization_schedule(pd.DataFrame(), cap_policy, period="2026-05")
    assert out.empty
    assert "deal_id" in out.columns


# --- unit_economics ---------------------------------------------------------

def test_unit_economics_uses_aircraft_on_platform(kpis):
    totals = {"people": 50_000_000, "vendor_cogs": 20_000_000,
              "vendor_opex": 10_000_000, "fx": 1_000_000,
              "allocations": 3_000_000}
    res = cs.unit_economics(totals, kpis)
    # total_opex excludes fx + allocations: 50M + 20M + 10M = 80M
    assert res["total_opex_usd"] == pytest.approx(80_000_000)
    aircraft = kpis["aircraft_on_platform"]
    assert res["cost_per_aircraft_on_platform_usd"] == pytest.approx(80_000_000 / aircraft)
    assert res["people_cost_per_aircraft_usd"] == pytest.approx(50_000_000 / aircraft)


def test_unit_economics_handles_missing_kpis():
    res = cs.unit_economics({"people": 1_000_000}, {})
    assert pd.isna(res["cost_per_aircraft_on_platform_usd"])
