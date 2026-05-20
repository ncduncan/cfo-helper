"""Tests for the deal-underwriting engine."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from scripts import underwriting as uw

REPO = Path(__file__).resolve().parent.parent
POLICIES = REPO / "tests" / "fixtures" / "policies"


@pytest.fixture(scope="module")
def strikezone():
    with (POLICIES / "strikezone.yaml").open() as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def matrix():
    with (POLICIES / "delegation_matrix.yaml").open() as f:
        return yaml.safe_load(f)


def _tier1_deal(**overrides):
    base = dict(
        customer_name="Test Airline",
        archetype="tier1",
        product_mix=["product_a", "product_b"],
        tcv_usd=3_000_000,
        term_months=60,
        payment_terms="net30",
        list_price_usd=3_400_000,
        invoice_price_usd=3_000_000,
        discount_pct=0.12,
        escalator_pct=0.04,
        ramp_months=3,
    )
    base.update(overrides)
    return uw.normalize_deal(base)


# --- normalize_deal ----------------------------------------------------------

def test_normalize_deal_requires_archetype():
    with pytest.raises(ValueError):
        uw.normalize_deal({"product_mix": ["product_a"], "tcv_usd": 100, "term_months": 12})


def test_normalize_deal_rejects_bad_archetype():
    with pytest.raises(ValueError):
        uw.normalize_deal({
            "archetype": "spaceforce", "product_mix": ["ems"],
            "tcv_usd": 100, "term_months": 12, "payment_terms": "net30",
        })


def test_normalize_deal_computes_discount_from_prices():
    d = uw.normalize_deal({
        "customer_name": "X",
        "archetype": "tier1", "product_mix": ["ems"],
        "tcv_usd": 800_000, "term_months": 36,
        "list_price_usd": 1_000_000, "invoice_price_usd": 800_000,
        "payment_terms": "net30",
    })
    assert d.discount_pct == pytest.approx(0.20, abs=1e-9)


def test_normalize_deal_ssp_complexity():
    d_low = _tier1_deal(product_mix=["product_a"])
    assert d_low.ssp_complexity == "low"
    d_med = _tier1_deal(product_mix=["product_a", "ats"])
    assert d_med.ssp_complexity == "medium"
    d_high = _tier1_deal(product_mix=["product_a", "ats", "analytics_platform"])
    assert d_high.ssp_complexity == "high"


# --- score_against_strikezone ------------------------------------------------

def test_score_in_zone(strikezone):
    deal = _tier1_deal()
    sc = uw.score_against_strikezone(deal, strikezone)
    assert sc.by_dim("term_months").status == "in_zone"
    assert sc.by_dim("discount_pct").status == "in_zone"
    assert sc.by_dim("tcv_usd").status == "in_zone"
    assert sc.by_dim("payment_terms").status == "in_zone"
    assert not sc.hard_breach


def test_score_breach_on_discount(strikezone):
    deal = _tier1_deal(invoice_price_usd=2_750_000, discount_pct=0.19)
    sc = uw.score_against_strikezone(deal, strikezone)
    assert sc.by_dim("discount_pct").status == "breach"


def test_score_hard_breach_on_discount(strikezone):
    deal = _tier1_deal(discount_pct=0.30)
    sc = uw.score_against_strikezone(deal, strikezone)
    assert sc.by_dim("discount_pct").status == "hard_breach"
    assert sc.hard_breach


def test_score_breach_on_short_term(strikezone):
    deal = _tier1_deal(term_months=30)
    sc = uw.score_against_strikezone(deal, strikezone)
    assert sc.by_dim("term_months").status == "breach"


def test_score_hard_breach_on_very_short_term(strikezone):
    deal = _tier1_deal(term_months=12)
    sc = uw.score_against_strikezone(deal, strikezone)
    assert sc.by_dim("term_months").status == "hard_breach"


def test_score_breach_on_disallowed_payment_terms(strikezone):
    deal = _tier1_deal(payment_terms="net90")
    sc = uw.score_against_strikezone(deal, strikezone)
    assert sc.by_dim("payment_terms").status == "breach"


# --- route_delegations -------------------------------------------------------

def test_delegation_small_tcv_no_special(matrix, strikezone):
    deal = _tier1_deal(tcv_usd=300_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert delegs == []  # below the $1M ladder, no rules fire


def test_delegation_high_tcv(matrix, strikezone):
    deal = _tier1_deal(tcv_usd=8_000_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert "commercial_director" in delegs
    assert "cfo" in delegs


def test_delegation_huge_tcv_pulls_full_chain(matrix, strikezone):
    deal = _tier1_deal(tcv_usd=30_000_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert "ceo" in delegs
    assert "ge_aerospace_segment_cfo" in delegs


def test_delegation_dedupes_across_rules(matrix, strikezone):
    # tcv >= 1M and >= 5M both list approvers, cfo appears once.
    deal = _tier1_deal(tcv_usd=8_000_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert delegs.count("cfo") == 1


def test_delegation_hard_breach_pulls_cfo(matrix, strikezone):
    deal = _tier1_deal(tcv_usd=300_000, discount_pct=0.30)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert "cfo" in delegs


def test_delegation_military_pulls_counsel(matrix, strikezone):
    deal = _tier1_deal(archetype="military", tcv_usd=2_000_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert "segment_counsel" in delegs


# --- find_comparables --------------------------------------------------------

def test_find_comparables_filters_archetype():
    deal = _tier1_deal()
    deals_df = pd.DataFrame([
        {"deal_id": "d1", "archetype": "tier1",  "tcv_usd": 2_500_000, "product": "product_a"},
        {"deal_id": "d2", "archetype": "lessor", "tcv_usd": 2_500_000, "product": "ats"},
        {"deal_id": "d3", "archetype": "tier1",  "tcv_usd": 5_000_000, "product": "product_b"},
    ])
    out = uw.find_comparables(deal, deals_df, k=10)
    assert set(out["deal_id"]) == {"d1", "d3"}


def test_find_comparables_ranks_by_tcv_proximity():
    deal = _tier1_deal()  # TCV=3M
    deals_df = pd.DataFrame([
        {"deal_id": "far",  "archetype": "tier1", "tcv_usd": 30_000_000, "product": "product_a"},
        {"deal_id": "near", "archetype": "tier1", "tcv_usd": 3_500_000,  "product": "product_a"},
    ])
    out = uw.find_comparables(deal, deals_df, k=2)
    assert out.iloc[0]["deal_id"] == "near"


def test_find_comparables_handles_missing_archetype_column():
    """Existing demo deals table has no archetype column — graceful fallback."""
    deal = _tier1_deal()
    deals_df = pd.DataFrame([
        {"deal_id": "d1", "tcv_usd": 2_500_000, "product": "product_a"},
    ])
    out = uw.find_comparables(deal, deals_df, k=10)
    assert len(out) == 1


def test_find_comparables_empty_input():
    deal = _tier1_deal()
    assert uw.find_comparables(deal, pd.DataFrame()).empty


# --- compute_economics -------------------------------------------------------

def test_economics_basic_npv_positive_for_normal_deal():
    deal = _tier1_deal()
    eco = uw.compute_economics(deal, discount_rate=0.10, cost_ratio=0.30)
    assert eco.tcv_usd == 3_000_000
    assert eco.deal_life_gm_pct == pytest.approx(0.70, abs=1e-9)
    # Net cash positive over life → NPV positive
    assert eco.npv_usd > 0
    assert eco.payback_months is not None and eco.payback_months > 0


def test_economics_full_prepay_payback_immediate():
    deal = _tier1_deal(payment_terms="prepay_full_term")
    eco = uw.compute_economics(deal, cost_ratio=0.30)
    # Cash hits at month 0; cost trickles in over the term — payback is month 1
    # (cumulative net cash >= 0 from month 0 onward).
    assert eco.payback_months == 1


def test_economics_recognition_after_ramp():
    deal = _tier1_deal(ramp_months=6)
    eco = uw.compute_economics(deal)
    # First 6 months recognize zero
    first_six = sum(p["recognition_usd"] for p in eco.deferred_rev_profile[:6])
    assert first_six == 0.0
    # Total recognition equals TCV within rounding
    total_recog = sum(p["recognition_usd"] for p in eco.deferred_rev_profile)
    assert abs(total_recog - deal.tcv_usd) < 1.0


# --- allocate_ssp -----------------------------------------------------------

def test_allocate_ssp_sums_to_tcv():
    deal = _tier1_deal(product_mix=["product_a", "product_b", "ats"])
    pos = uw.allocate_ssp(deal)
    total = sum(p.allocated_value_usd for p in pos)
    assert abs(total - deal.tcv_usd) < 1.0


def test_allocate_ssp_unknown_product_dropped():
    deal = _tier1_deal(product_mix=["nonexistent_product", "product_a"])
    pos = uw.allocate_ssp(deal)
    assert all(p.name == "product_a" for p in pos)
    assert abs(sum(p.allocated_value_usd for p in pos) - deal.tcv_usd) < 1.0


def test_allocate_ssp_returns_recognition_pattern():
    deal = _tier1_deal(product_mix=["ats", "product_a"])
    pos = uw.allocate_ssp(deal)
    by_name = {p.name: p for p in pos}
    assert by_name["ats"].recognition_pattern == "point_in_time"
    assert by_name["product_a"].recognition_pattern == "ratable"


# --- recommendation ----------------------------------------------------------

def test_recommendation_approve_for_clean_small_deal(strikezone, matrix):
    deal = _tier1_deal(tcv_usd=300_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert uw.recommendation(sc, delegs) == "Approve"


def test_recommendation_negotiate_for_soft_breach(strikezone, matrix):
    deal = _tier1_deal(tcv_usd=300_000, term_months=30)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert uw.recommendation(sc, delegs) == "Negotiate"


def test_recommendation_escalate_for_hard_breach(strikezone, matrix):
    deal = _tier1_deal(discount_pct=0.30)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert uw.recommendation(sc, delegs) == "Escalate"


def test_recommendation_escalate_for_heavy_delegation(strikezone, matrix):
    # In-zone deal but TCV is large enough to require CFO sign-off
    deal = _tier1_deal(tcv_usd=8_000_000)
    sc = uw.score_against_strikezone(deal, strikezone)
    delegs = uw.route_delegations(deal, matrix, sc)
    assert "cfo" in delegs
    assert uw.recommendation(sc, delegs) == "Escalate"


# --- top_risks ---------------------------------------------------------------

def test_top_risks_orders_high_first(strikezone):
    deal = _tier1_deal(discount_pct=0.30, payment_terms="prepay_full_term",
                        product_mix=["product_a", "ats", "analytics_platform"])
    sc = uw.score_against_strikezone(deal, strikezone)
    risks = uw.top_risks(deal, sc)
    severities = [r.severity for r in risks]
    assert severities[0] == "high"
    # SSP complexity high should appear
    assert any(r.code == "revrec.ssp_complexity.high" for r in risks)
