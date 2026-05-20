"""
Deal-underwriting engine. Pure functions. No I/O beyond reading parquet/Excel
artifacts when explicitly asked.

Public API used by the dispatch runners:
    normalize_deal(brief_fields, artifact_dir) -> Deal
    score_against_strikezone(deal, strikezone) -> Scorecard
    route_delegations(deal, matrix) -> list[str]
    find_comparables(deal, deals_df, k=10) -> pd.DataFrame
    compute_economics(deal, *, discount_rate=0.10) -> Economics
    allocate_ssp(deal, ssp_table) -> list[PerformanceObligation]
    top_risks(deal, scorecard, comps) -> list[Risk]
    recommendation(scorecard, delegations) -> str

Design notes:
- Strikezone bands and delegation rules come from YAML in profile/memory/. Both are
  loaded by the caller and passed in as plain dicts. This module is unaware
  of the filesystem.
- "Hard breach" uses hard_floor / hard_cap when present; otherwise falls back
  to the soft min/max with a 50% magnitude threshold.
- Comparables: same archetype, Jaccard overlap on product_mix, ranked by
  |log(TCV) - log(deal_tcv)|. No ML.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


# --- Types --------------------------------------------------------------------

@dataclass
class Deal:
    customer_name: str
    archetype: str
    product_mix: list[str]
    tcv_usd: float
    term_months: int
    payment_terms: str
    customer_id: str | None = None
    list_price_usd: float | None = None
    invoice_price_usd: float | None = None
    discount_pct: float | None = None
    escalator_pct: float | None = None
    ramp_months: int | None = None
    concessions: str = ""
    artifact_paths: list[str] = field(default_factory=list)
    # Derived flags (set during normalization or scoring)
    ssp_complexity: str = "low"  # low | medium | high


@dataclass
class DimensionScore:
    dim: str
    value: float | str | None
    band: dict
    status: str  # in_zone | breach | hard_breach | n/a
    magnitude_pct: float  # 0 if in_zone; otherwise distance from band edge as % of edge
    note: str = ""


@dataclass
class Scorecard:
    deal: Deal
    dimensions: list[DimensionScore]
    hard_breach: bool

    def by_dim(self, dim: str) -> DimensionScore | None:
        return next((d for d in self.dimensions if d.dim == dim), None)


@dataclass
class Economics:
    tcv_usd: float
    deal_life_gm_pct: float
    npv_usd: float
    irr_annual: float | None
    payback_months: int | None
    deferred_rev_profile: list[dict]  # [{month_index, recognition_usd, cash_in_usd}]


@dataclass
class PerformanceObligation:
    name: str
    ssp_unit_price_usd: float
    quantity: float
    raw_value_usd: float
    allocated_value_usd: float
    recognition_pattern: str  # ratable | point_in_time | usage


@dataclass
class Risk:
    code: str
    severity: str  # high | medium | low
    title: str
    detail: str


# --- Normalization ------------------------------------------------------------

_PAYMENT_TERMS = {"net30", "net60", "net90", "prepay_annual", "prepay_full_term"}
_ARCHETYPES = {"tier1", "lessor", "cargo", "bga", "military", "channel"}

_FLIGHT_OPS_PRODUCTS = {"product_a", "product_c", "product_b",
                        "product_d", "ems"}
_TECH_OPS_PRODUCTS = {"ats", "records_product", "maintenance_product"}
_APM_PRODUCTS = {"analytics_platform", "legacy_platform"}


def _coerce_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def _coerce_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    return int(float(v))


def normalize_deal(brief_fields: dict, artifact_dir: Path | None = None) -> Deal:
    """Build a Deal from the task's brief_fields. Validates required fields."""
    archetype = str(brief_fields.get("archetype") or "").strip()
    if archetype not in _ARCHETYPES:
        raise ValueError(f"archetype must be one of {sorted(_ARCHETYPES)}, got {archetype!r}")

    product_mix_raw = brief_fields.get("product_mix") or []
    if isinstance(product_mix_raw, str):
        product_mix = [p.strip() for p in product_mix_raw.split(",") if p.strip()]
    else:
        product_mix = [str(p).strip() for p in product_mix_raw]
    if not product_mix:
        raise ValueError("product_mix is required")

    payment_terms = str(brief_fields.get("payment_terms") or "").strip()
    if payment_terms and payment_terms not in _PAYMENT_TERMS:
        raise ValueError(
            f"payment_terms must be one of {sorted(_PAYMENT_TERMS)}, got {payment_terms!r}"
        )

    tcv = _coerce_float(brief_fields.get("tcv_usd"))
    if tcv is None or tcv <= 0:
        raise ValueError("tcv_usd must be a positive number")
    term = _coerce_int(brief_fields.get("term_months"))
    if term is None or term <= 0:
        raise ValueError("term_months must be a positive integer")

    list_price = _coerce_float(brief_fields.get("list_price_usd"))
    invoice_price = _coerce_float(brief_fields.get("invoice_price_usd"))
    discount = _coerce_float(brief_fields.get("discount_pct"))
    if discount is None and list_price and invoice_price and list_price > 0:
        discount = max(0.0, 1.0 - invoice_price / list_price)

    deal = Deal(
        customer_name=str(brief_fields.get("customer_name") or "").strip(),
        customer_id=brief_fields.get("customer_id") or None,
        archetype=archetype,
        product_mix=product_mix,
        tcv_usd=tcv,
        term_months=term,
        list_price_usd=list_price,
        invoice_price_usd=invoice_price,
        discount_pct=discount,
        payment_terms=payment_terms,
        escalator_pct=_coerce_float(brief_fields.get("escalator_pct")),
        ramp_months=_coerce_int(brief_fields.get("ramp_months")),
        concessions=str(brief_fields.get("concessions") or ""),
        artifact_paths=list(brief_fields.get("artifact_paths") or []),
    )

    # SSP complexity heuristic: cross-suite product mix → high. The three
    # suites are flight_ops, tech_ops, and apm. Note `_APM_PRODUCTS` includes
    # both `analytics_platform` and the legacy `legacy_platform` analytics product — a mix of
    # the two registers as a single suite (apm), not two, since they share
    # the same SSP-allocation bucket per CLAUDE.md §4.
    suites = sum([
        bool(set(product_mix) & _FLIGHT_OPS_PRODUCTS),
        bool(set(product_mix) & _TECH_OPS_PRODUCTS),
        bool(set(product_mix) & _APM_PRODUCTS),
    ])
    if suites >= 3:
        deal.ssp_complexity = "high"
    elif suites == 2:
        deal.ssp_complexity = "medium"
    else:
        deal.ssp_complexity = "low"

    return deal


# --- Strikezone scoring -------------------------------------------------------

def _score_min(value: float | None, band: dict) -> tuple[str, float]:
    """Score a 'higher is better' dimension (min floor)."""
    if value is None:
        return "n/a", 0.0
    floor = band.get("hard_floor")
    minimum = band.get("min")
    if floor is not None and value < floor:
        return "hard_breach", (minimum - value) / minimum if minimum else 1.0
    if minimum is not None and value < minimum:
        return "breach", (minimum - value) / minimum
    return "in_zone", 0.0


def _score_max(value: float | None, band: dict) -> tuple[str, float]:
    """Score a 'lower is better' dimension (max cap)."""
    if value is None:
        return "n/a", 0.0
    cap_hard = band.get("hard_cap")
    cap = band.get("max")
    if cap_hard is not None and value > cap_hard:
        return "hard_breach", (value - cap) / cap if cap else 1.0
    if cap is not None and value > cap:
        return "breach", (value - cap) / cap
    return "in_zone", 0.0


def _score_enum(value: str | None, band: dict) -> tuple[str, float]:
    if value is None or value == "":
        return "n/a", 0.0
    allowed = band.get("allowed") or []
    if not allowed:
        return "in_zone", 0.0
    return ("in_zone", 0.0) if value in allowed else ("breach", 1.0)


def score_against_strikezone(deal: Deal, strikezone: dict) -> Scorecard:
    """Score deal against the strikezone for its archetype.

    Computes GM% from list/invoice if available; if discount_pct is the only
    proxy, GM is not scored (no_value).
    """
    arche = strikezone.get("archetypes", {}).get(deal.archetype)
    if not arche:
        raise ValueError(f"No strikezone for archetype {deal.archetype!r}")

    dimensions: list[DimensionScore] = []

    # In v1 the cost/SSP connector isn't wired, so true GM% can't be derived.
    # We score `invoice/list` against the strikezone's gross_margin_pct band as
    # a *discount proxy* and surface it under the dim name `discount_proxy_gm_pct`
    # so downstream readers can't mistake it for an audited gross margin.
    gm_band = arche.get("gross_margin_pct", {})
    gm_value = None
    if deal.list_price_usd and deal.invoice_price_usd and deal.list_price_usd > 0:
        gm_value = max(0.0, deal.invoice_price_usd / deal.list_price_usd - 0.0)
    status, mag = _score_min(gm_value, gm_band)
    dimensions.append(DimensionScore(
        dim="discount_proxy_gm_pct", value=gm_value, band=gm_band,
        status=status, magnitude_pct=mag,
        note=("invoice/list as a margin proxy — true GM is not derivable until "
              "the cost connector is wired. Scored against the GM strikezone band, "
              "but treat the result as a discount-discipline check, not GM."
              if gm_value is not None else "List/invoice missing — cannot score."),
    ))

    # Term
    term_band = arche.get("term_months", {})
    status, mag = _score_min(deal.term_months, term_band)
    dimensions.append(DimensionScore(
        dim="term_months", value=deal.term_months, band=term_band,
        status=status, magnitude_pct=mag,
    ))

    # Discount
    disc_band = arche.get("discount_pct", {})
    status, mag = _score_max(deal.discount_pct, disc_band)
    dimensions.append(DimensionScore(
        dim="discount_pct", value=deal.discount_pct, band=disc_band,
        status=status, magnitude_pct=mag,
    ))

    # Payment terms (enum)
    pt_band = arche.get("payment_terms", {})
    status, mag = _score_enum(deal.payment_terms, pt_band)
    dimensions.append(DimensionScore(
        dim="payment_terms", value=deal.payment_terms, band=pt_band,
        status=status, magnitude_pct=mag,
    ))

    # Escalator
    esc_band = arche.get("escalator_pct", {})
    status, mag = _score_min(deal.escalator_pct, esc_band)
    dimensions.append(DimensionScore(
        dim="escalator_pct", value=deal.escalator_pct, band=esc_band,
        status=status, magnitude_pct=mag,
    ))

    # TCV minimum
    tcv_band = arche.get("tcv_usd", {})
    status, mag = _score_min(deal.tcv_usd, tcv_band)
    dimensions.append(DimensionScore(
        dim="tcv_usd", value=deal.tcv_usd, band=tcv_band,
        status=status, magnitude_pct=mag,
    ))

    # Ramp
    ramp_band = arche.get("ramp_months", {})
    status, mag = _score_max(deal.ramp_months, ramp_band)
    dimensions.append(DimensionScore(
        dim="ramp_months", value=deal.ramp_months, band=ramp_band,
        status=status, magnitude_pct=mag,
    ))

    hard_breach = any(d.status == "hard_breach" for d in dimensions)
    return Scorecard(deal=deal, dimensions=dimensions, hard_breach=hard_breach)


# --- Delegation routing -------------------------------------------------------

_OP_FNS = {
    ">=": lambda a, b: a >= b,
    ">":  lambda a, b: a > b,
    "<=": lambda a, b: a <= b,
    "<":  lambda a, b: a < b,
}


def _deal_dim(deal: Deal, dim: str, scorecard: Scorecard | None) -> Any:
    """Resolve a dim name to a value on the deal or its derived state."""
    if dim == "hard_breach":
        return scorecard.hard_breach if scorecard else False
    if dim == "ssp_complexity":
        return deal.ssp_complexity
    return getattr(deal, dim, None)


def route_delegations(deal: Deal, matrix: dict,
                       scorecard: Scorecard | None = None) -> list[str]:
    """Return a deduplicated, ordered list of required approvers."""
    seen: list[str] = []
    for rule in matrix.get("rules", []):
        dim = rule.get("dim")
        actual = _deal_dim(deal, dim, scorecard)
        match = False
        if "equals" in rule:
            match = actual == rule["equals"]
        elif "threshold" in rule:
            if actual is None:
                match = False
            else:
                op = rule.get("threshold_op", ">=")
                fn = _OP_FNS.get(op)
                if fn is None:
                    raise ValueError(f"Unknown threshold_op {op!r}")
                match = fn(actual, rule["threshold"])
        if match:
            for a in rule.get("approvers", []):
                if a not in seen:
                    seen.append(a)
    return seen


# --- Comparables --------------------------------------------------------------

def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def find_comparables(deal: Deal, deals_df: pd.DataFrame, *,
                      k: int = 10, archetype_col: str = "archetype",
                      tcv_col: str = "tcv_usd",
                      product_col: str = "product") -> pd.DataFrame:
    """Find up to k comparable deals from the historical deals table.

    Strategy:
      - filter to same archetype if the column exists; otherwise treat all
        deals as candidates (the existing demo deals table doesn't carry
        archetype, so this is a no-op until the connector adds it).
      - product_mix overlap via Jaccard on the deal's product list against the
        historical row's `product` (single-product strings) — Jaccard reduces
        to {0, 1} for single-product rows but generalizes when the column is
        a list.
      - rank by composite distance: 0.6 * (1 - jaccard) + 0.4 * |log(TCV ratio)|
    """
    if deals_df is None or deals_df.empty:
        return pd.DataFrame()

    df = deals_df.copy()
    if archetype_col in df.columns:
        df = df[df[archetype_col] == deal.archetype]
    if df.empty:
        return df

    def _row_products(row) -> list[str]:
        v = row.get(product_col)
        if isinstance(v, list):
            return [str(x) for x in v]
        if pd.isna(v):
            return []
        return [str(v)]

    df = df.assign(
        _jaccard=df.apply(lambda r: _jaccard(deal.product_mix, _row_products(r)), axis=1),
    )
    if tcv_col in df.columns:
        df = df.assign(
            _log_tcv_dist=(df[tcv_col].astype(float).clip(lower=1.0)
                            .apply(math.log)
                            - math.log(max(deal.tcv_usd, 1.0))).abs(),
        )
    else:
        df["_log_tcv_dist"] = 0.0

    df = df.assign(
        _distance=(0.6 * (1.0 - df["_jaccard"]) + 0.4 * df["_log_tcv_dist"]),
    ).sort_values("_distance").head(k)

    return df.drop(columns=["_distance"])


# --- Economics ----------------------------------------------------------------

def compute_economics(deal: Deal, *, discount_rate: float = 0.10,
                       cost_ratio: float = 0.30) -> Economics:
    """Compute headline economics. Monthly model.

    Conventions:
      - Revenue recognized ratably over term, after `ramp_months` of free ramp.
      - Cash in: monthly for net30/60/90 (assume net30 lag for simplicity);
        annual prepay for prepay_annual; full prepay at month 0 for
        prepay_full_term.
      - Cost: assumed `cost_ratio` * revenue, recognized in lockstep with
        revenue. Replace when the cost connector lands.
      - NPV: monthly cash flows discounted at (1 + discount_rate)^(1/12) - 1.
      - IRR: monthly IRR, annualized.
      - Payback: month at which cumulative cash >= cumulative cost.
    """
    months = max(1, deal.term_months)
    ramp = max(0, min(deal.ramp_months or 0, months))
    revenue_months = months - ramp
    if revenue_months <= 0:
        # All ramp, no recognized revenue. Pathological but well-defined.
        return Economics(
            tcv_usd=deal.tcv_usd, deal_life_gm_pct=0.0, npv_usd=-deal.tcv_usd * cost_ratio,
            irr_annual=None, payback_months=None,
            deferred_rev_profile=[{"month_index": i, "recognition_usd": 0.0,
                                     "cash_in_usd": 0.0} for i in range(months)],
        )
    monthly_rev = deal.tcv_usd / revenue_months
    monthly_cost = monthly_rev * cost_ratio

    # Cash schedule
    cash_in = [0.0] * months
    pt = deal.payment_terms
    if pt == "prepay_full_term":
        cash_in[0] = deal.tcv_usd
    elif pt == "prepay_annual":
        # Annual prepay at month 0, 12, 24, ...; final stub for partial year.
        billed = 0.0
        for m in range(0, months, 12):
            chunk = min(12, months - m) * monthly_rev
            cash_in[m] += chunk
            billed += chunk
        # If ramp pushed any chunk past TCV, normalize.
        if billed > deal.tcv_usd > 0:
            scale = deal.tcv_usd / billed
            cash_in = [c * scale for c in cash_in]
    else:
        # net30/60/90: bill monthly, lag by 1 month for net30 simplicity.
        lag = {"net30": 1, "net60": 2, "net90": 3}.get(pt, 1)
        for m in range(months):
            target = m + lag
            if target < months:
                cash_in[target] += monthly_rev
            else:
                cash_in[-1] += monthly_rev  # collapse trailing into last month

    # Recognition schedule (post-ramp)
    recognition = [0.0] * months
    for m in range(ramp, months):
        recognition[m] = monthly_rev

    # Cost schedule: in lockstep with recognition (when revenue is earned, cost incurs)
    cost = [recognition[m] * cost_ratio for m in range(months)]

    # NPV on (cash_in - cost) cash flow
    monthly_disc = (1.0 + discount_rate) ** (1.0 / 12.0) - 1.0
    npv = 0.0
    for m in range(months):
        net = cash_in[m] - cost[m]
        npv += net / ((1.0 + monthly_disc) ** m)

    # IRR via bisection on the same cash flow series. Bound the monthly rate
    # to (-0.999, 5.0): a value <= -1 makes (1+r)^m undefined for any m>0,
    # and 5.0 monthly already annualizes to ~9000% — anything beyond is not
    # economically meaningful. Returning None on a non-bracket is the right
    # behavior; no realistic SaaS deal hits these bounds.
    def _npv_at(rate_monthly: float) -> float:
        s = 0.0
        for m in range(months):
            net = cash_in[m] - cost[m]
            s += net / ((1.0 + rate_monthly) ** m)
        return s

    irr_annual: float | None = None
    lo, hi = -0.999, 5.0  # monthly rate bounds; lo > -1 keeps (1+r)^m finite
    f_lo, f_hi = _npv_at(lo), _npv_at(hi)
    if f_lo * f_hi < 0:
        for _ in range(80):
            mid = (lo + hi) / 2
            f_mid = _npv_at(mid)
            if abs(f_mid) < 1e-6:
                lo = hi = mid
                break
            if f_lo * f_mid < 0:
                hi, f_hi = mid, f_mid
            else:
                lo, f_lo = mid, f_mid
        monthly_irr = (lo + hi) / 2
        irr_annual = (1.0 + monthly_irr) ** 12 - 1.0

    # Payback: first month where cumulative (cash_in - cost) >= 0
    payback_months: int | None = None
    cum = 0.0
    for m in range(months):
        cum += cash_in[m] - cost[m]
        if cum >= 0:
            payback_months = m + 1
            break

    profile = [
        {"month_index": m, "recognition_usd": round(recognition[m], 2),
         "cash_in_usd": round(cash_in[m], 2)}
        for m in range(months)
    ]

    deal_life_gm_pct = 1.0 - cost_ratio  # constant under v1 assumption
    return Economics(
        tcv_usd=deal.tcv_usd, deal_life_gm_pct=deal_life_gm_pct,
        npv_usd=npv, irr_annual=irr_annual, payback_months=payback_months,
        deferred_rev_profile=profile,
    )


# --- SSP allocation -----------------------------------------------------------

# v1 default SSP table: assumed unit prices per product. Replace with a real
# table derived from list-price comparables once the cost/price connector lands.
DEFAULT_SSP_TABLE: dict[str, dict] = {
    # Flight Ops (per-tail or per-pilot annual). Values are USD per unit per year.
    "product_a":       {"unit_price_usd": 60.0,    "unit": "per_seat_year",
                            "recognition_pattern": "ratable"},
    "product_c":    {"unit_price_usd": 12000.0, "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    "product_b":      {"unit_price_usd": 15000.0, "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    "product_d":  {"unit_price_usd": 8000.0,  "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    "ems":               {"unit_price_usd": 18000.0, "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    # Tech Ops
    "ats":               {"unit_price_usd": 5000.0,  "unit": "per_record",
                            "recognition_pattern": "point_in_time"},
    "records_product":     {"unit_price_usd": 9000.0,  "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    "maintenance_product":{"unit_price_usd": 14000.0, "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    # Analytics platform
    "analytics_platform":      {"unit_price_usd": 25000.0, "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
    "legacy_platform":             {"unit_price_usd": 10000.0, "unit": "per_unit_year",
                            "recognition_pattern": "ratable"},
}


def allocate_ssp(deal: Deal, ssp_table: dict | None = None,
                  *, units_assumed: float = 1.0) -> list[PerformanceObligation]:
    """ASC 606 relative-SSP allocation across the deal's product mix.

    v1 simplification: each product gets `units_assumed` units (1 by default)
    and SSP is the unit price * (term_months/12). When the connector lands we
    replace `units_assumed` with deal-specific quantities (per-tail counts,
    per-pilot counts, per-record volume).

    Returns a list of PerformanceObligation. The allocated_value sums to
    deal.tcv_usd within $1.
    """
    table = ssp_table or DEFAULT_SSP_TABLE
    raw: list[PerformanceObligation] = []
    for product in deal.product_mix:
        spec = table.get(product)
        if spec is None:
            continue
        unit_price = float(spec["unit_price_usd"])
        # Annualize over the term length
        years = max(deal.term_months / 12.0, 0.0001)
        if spec["unit"] in ("per_unit_year", "per_seat_year"):
            raw_value = unit_price * units_assumed * years
        elif spec["unit"] == "per_record":
            raw_value = unit_price * units_assumed
        else:
            raw_value = unit_price * units_assumed * years
        raw.append(PerformanceObligation(
            name=product, ssp_unit_price_usd=unit_price,
            quantity=units_assumed, raw_value_usd=raw_value,
            allocated_value_usd=0.0,
            recognition_pattern=spec["recognition_pattern"],
        ))

    total_raw = sum(p.raw_value_usd for p in raw)
    if total_raw <= 0 or not raw:
        return raw

    # Relative SSP: scale raw values to sum to TCV.
    scale = deal.tcv_usd / total_raw
    for p in raw:
        p.allocated_value_usd = round(p.raw_value_usd * scale, 2)

    # Fix any rounding drift on the last PO so the sum reconciles to TCV exactly.
    drift = round(deal.tcv_usd - sum(p.allocated_value_usd for p in raw), 2)
    if raw:
        raw[-1].allocated_value_usd = round(raw[-1].allocated_value_usd + drift, 2)

    return raw


# --- Risks --------------------------------------------------------------------

def top_risks(deal: Deal, scorecard: Scorecard,
                comps: pd.DataFrame | None = None) -> list[Risk]:
    risks: list[Risk] = []

    # Strikezone breaches → risks
    for d in scorecard.dimensions:
        if d.status == "hard_breach":
            risks.append(Risk(
                code=f"strikezone.{d.dim}.hard_breach", severity="high",
                title=f"Hard breach on {d.dim}",
                detail=f"value={d.value!r} band={d.band}",
            ))
        elif d.status == "breach":
            risks.append(Risk(
                code=f"strikezone.{d.dim}.breach", severity="medium",
                title=f"Out of strikezone on {d.dim}",
                detail=f"value={d.value!r} band={d.band} magnitude={d.magnitude_pct:.0%}",
            ))

    # Rev-rec complexity
    if deal.ssp_complexity == "high":
        risks.append(Risk(
            code="revrec.ssp_complexity.high", severity="high",
            title="Multi-suite SSP allocation required",
            detail="Deal spans Flight Ops, Tech Ops, and APM suites. ASC 606 "
                   "relative-SSP allocation must be reviewed by Chief Accountant.",
        ))
    elif deal.ssp_complexity == "medium":
        risks.append(Risk(
            code="revrec.ssp_complexity.medium", severity="medium",
            title="Two-suite SSP allocation",
            detail="Cross-suite product mix; relative-SSP allocation should be "
                   "documented in the deal file.",
        ))

    # Payment terms — full-term prepay creates a deferred-revenue spike
    if deal.payment_terms == "prepay_full_term":
        risks.append(Risk(
            code="cash.prepay_full_term", severity="medium",
            title="Full-term prepay creates a deferred-revenue lock-up",
            detail=f"${deal.tcv_usd:,.0f} cash collected up front; deferred "
                   f"revenue rolls off over {deal.term_months} months.",
        ))

    # Concentration risk — flagged when comparable deals at this archetype are
    # rare. The runner can pass comps=None to skip this check.
    if comps is not None and len(comps) < 3:
        risks.append(Risk(
            code="concentration.thin_comps", severity="low",
            title="Few comparable deals in history",
            detail=f"Only {len(comps)} comparable deals found at archetype "
                   f"{deal.archetype}. Pricing benchmark is weak.",
        ))

    # Sort by severity (high > medium > low) and keep stable order otherwise
    sev_order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: sev_order.get(r.severity, 3))
    return risks


# --- Recommendation -----------------------------------------------------------

def recommendation(scorecard: Scorecard, delegations: list[str]) -> str:
    """Reduce a scorecard + delegation set to a one-word recommendation.

    Approve  : no breaches, no extraordinary delegations beyond commercial_director.
    Negotiate: at least one soft breach, no hard breaches.
    Escalate : any hard breach, OR delegation requires CFO/CRO/CEO/segment-counsel.
    Reject   : all dimensions hard-breached (rare, but possible — e.g.
               below TCV minimum and below margin floor and discount over hard cap).
    """
    if scorecard.hard_breach:
        # Reject if "most" dimensions hard-breached (>=3) — purely heuristic.
        hards = sum(1 for d in scorecard.dimensions if d.status == "hard_breach")
        if hards >= 3:
            return "Reject"
        return "Escalate"
    breaches = sum(1 for d in scorecard.dimensions if d.status == "breach")
    if breaches > 0:
        return "Negotiate"
    # In-zone but heavy delegation requirement still flags as Escalate
    heavy = {"cfo", "cro", "ceo", "segment_counsel", "chief_accountant",
              "ge_aerospace_segment_cfo"}
    if any(d in heavy for d in delegations):
        return "Escalate"
    return "Approve"


# --- Helpers for runners ------------------------------------------------------

def scorecard_to_rows(scorecard: Scorecard) -> list[dict]:
    """Render a scorecard into JSON-serializable rows for templates."""
    rows = []
    for d in scorecard.dimensions:
        rows.append({
            "dim": d.dim,
            "value": d.value,
            "band": d.band,
            "status": d.status,
            "magnitude_pct": round(d.magnitude_pct, 4),
            "note": d.note,
        })
    return rows


def deal_to_dict(deal: Deal) -> dict:
    return asdict(deal)
