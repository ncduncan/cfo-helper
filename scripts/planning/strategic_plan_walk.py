"""Strategic-plan-walk: stitch Y1 (operational plan) + Y2 + Y3 strategic rows
into a year-by-year decomposition.

Output is the structure board materials want: a Y1→Y3 walk per entity (and
consolidated) showing trio + bucket totals each year, with mechanism
attribution (which growth_method drove each delta).

Shape:
  walk_by_year: {Y1, Y2, Y3} → {sales, ebit, fcf, buckets}
  by_mechanism: {percent_growth, percent_of_revenue, absolute} → delta totals
  by_entity:    {entity} → walk_by_year

FCF proxy: at strategic grain, D&A / deferred-revenue / capex / cash-tax
detail typically aren't authored. The walk uses `fcf ≈ ebit × (1 − ETR)`
where ETR is read from `profile/memory/materiality.yaml.strategic_plan.cash_tax_rate_proxy`
(default 0.21, CFO-confirmable per planning cycle). When the materiality
key is missing or null, the walk emits `fcf=None` rather than a guessed
number — the prose layer should either omit FCF or surface the gap.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from connectors.assumptions import (
    fy_year_from_version, is_strategic_3yr, validate_version,
)


@dataclass(frozen=True)
class WalkResult:
    strategic_version: str
    operational_version: str               # plan_fy{YY} — Y1 anchor
    fy_year: int                           # Y1 fiscal year
    cash_tax_rate_used: float | None       # ETR applied to compute FCF, or None if unset
    walk_by_year: dict[str, dict[str, float | None]]   # {'Y1', 'Y2', 'Y3'} → {sales, ebit, fcf, ...}
    by_entity: dict[str, dict[str, dict[str, float | None]]]
    by_mechanism: dict[str, dict[str, float]]
    notes: list[str] = field(default_factory=list)


def _cash_tax_rate(repo_root: Path) -> float | None:
    """Read the CFO-confirmed strategic ETR from materiality.yaml.

    Returns None when the key is absent or null — caller surfaces that as
    "FCF unknown until rate is confirmed" rather than guessing.
    """
    path = repo_root / "profile" / "memory" / "materiality.yaml"
    if not path.exists():
        return None
    with path.open() as f:
        m = yaml.safe_load(f) or {}
    rate = m.get("strategic_plan", {}).get("cash_tax_rate_proxy")
    if rate is None:
        return None
    return float(rate)


def _bucket_for(account_class: str, pnl_line: str) -> str:
    cls = (account_class or "").lower()
    if cls == "revenue":
        return "revenue"
    if cls == "cogs":
        return "cogs"
    if cls == "opex":
        return "rd" if (pnl_line or "").startswith("Opex / R&D") else "sga"
    return "other"


def _trio_for_rows(rows: pd.DataFrame, cash_tax_rate: float | None) -> dict[str, float | None]:
    """Compute sales / EBIT / FCF (light) for a set of assumption rows.

    FCF at strategic grain uses `ebit × (1 − cash_tax_rate)` because D&A /
    deferred-revenue / capex / cash-tax detail typically aren't authored
    here. When `cash_tax_rate` is None, FCF returns None rather than a
    guessed number — the prose layer surfaces the gap.
    """
    if rows.empty:
        fcf_zero = 0.0 if cash_tax_rate is not None else None
        return {"sales": 0.0, "ebit": 0.0, "fcf": fcf_zero,
                "revenue": 0.0, "cogs": 0.0, "rd": 0.0, "sga": 0.0}

    rows = rows.copy()
    rows["account_class"] = rows["account_class"].fillna("").astype(str).str.lower()
    rows["pnl_line"] = rows["pnl_line"].fillna("").astype(str)
    rows["period_amount_usd"] = pd.to_numeric(rows["period_amount_usd"], errors="coerce").fillna(0.0)
    rows["_bucket"] = rows.apply(
        lambda r: _bucket_for(r["account_class"], r["pnl_line"]), axis=1
    )

    buckets = {
        b: float(rows[rows["_bucket"] == b]["period_amount_usd"].sum())
        for b in ("revenue", "cogs", "rd", "sga")
    }
    sales = buckets["revenue"]
    ebit = buckets["revenue"] - buckets["cogs"] - buckets["rd"] - buckets["sga"]
    fcf = ebit * (1.0 - cash_tax_rate) if cash_tax_rate is not None else None
    return {"sales": sales, "ebit": ebit, "fcf": fcf, **buckets}


def walk(
    *,
    strategic_version: str,
    repo_root: Path,
) -> WalkResult:
    """Produce a Y1→Y3 walk anchored to plan_fy{YY} for the given strategic version."""
    validate_version(strategic_version)
    if not is_strategic_3yr(strategic_version):
        raise ValueError(
            f"{strategic_version!r} is not a plan_3yr_fy* version."
        )
    fy_year = fy_year_from_version(strategic_version)
    operational_version = f"plan_fy{fy_year - 2000:02d}"

    import sys
    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433

    ws = repo_root / "workspace"
    period = sorted(
        d.name for d in ws.iterdir()
        if d.is_dir() and (d / "inputs" / "manifest.yaml").exists()
        and len(d.name) == 7 and d.name[4] == "-"
    )[-1]
    entities = connectors.list_entities(period)
    notes: list[str] = []

    # Pull both versions across all entities
    op_frames: list[pd.DataFrame] = []
    strat_frames: list[pd.DataFrame] = []
    for entity in entities:
        op = connectors.get_assumptions(period=period, entity=entity, version=operational_version)
        st = connectors.get_assumptions(period=period, entity=entity, version=strategic_version)
        if not op.empty:
            op_frames.append(op)
        if not st.empty:
            strat_frames.append(st)

    op_rows = pd.concat(op_frames, ignore_index=True) if op_frames else pd.DataFrame()
    st_rows = pd.concat(strat_frames, ignore_index=True) if strat_frames else pd.DataFrame()

    if op_rows.empty:
        notes.append(
            f"No rows for operational anchor {operational_version!r}. "
            "Y1 walk values will be zero; the strategic outyears stand alone."
        )
    if st_rows.empty:
        notes.append(
            f"No rows for strategic version {strategic_version!r}. "
            "Walk reduces to Y1 only."
        )

    # CFO-confirmable cash tax rate. Default 0.21 in materiality.yaml; null
    # means CFO has not validated → walk emits FCF=None rather than a guess.
    cash_tax_rate = _cash_tax_rate(repo_root)
    if cash_tax_rate is None:
        notes.append(
            "FCF: cash_tax_rate_proxy is unset in profile/memory/materiality.yaml. "
            "Walk emits fcf=None rather than guessing. Set "
            "strategic_plan.cash_tax_rate_proxy and re-run, or author an "
            "explicit cash-tax assumption row."
        )
    else:
        notes.append(
            f"FCF computed with ETR={cash_tax_rate:.0%} from "
            f"materiality.yaml.strategic_plan.cash_tax_rate_proxy. "
            f"Reconfirm at the start of each planning cycle — historical "
            f"effective rate from prior-year actuals is the right source "
            f"when available."
        )

    # Y2/Y3 partitioning by period
    y2_period = f"{fy_year + 1}-12"
    y3_period = f"{fy_year + 2}-12"
    st_y2 = st_rows[st_rows["period"] == y2_period] if not st_rows.empty else pd.DataFrame()
    st_y3 = st_rows[st_rows["period"] == y3_period] if not st_rows.empty else pd.DataFrame()

    walk_by_year = {
        "Y1": _trio_for_rows(op_rows, cash_tax_rate),
        "Y2": _trio_for_rows(st_y2, cash_tax_rate),
        "Y3": _trio_for_rows(st_y3, cash_tax_rate),
    }

    # Per-entity walk
    by_entity: dict[str, dict[str, dict[str, float | None]]] = {}
    for entity in entities:
        op_e = op_rows[op_rows["entity"] == entity] if not op_rows.empty else pd.DataFrame()
        y2_e = st_y2[st_y2["entity"] == entity] if not st_y2.empty else pd.DataFrame()
        y3_e = st_y3[st_y3["entity"] == entity] if not st_y3.empty else pd.DataFrame()
        by_entity[entity] = {
            "Y1": _trio_for_rows(op_e, cash_tax_rate),
            "Y2": _trio_for_rows(y2_e, cash_tax_rate),
            "Y3": _trio_for_rows(y3_e, cash_tax_rate),
        }

    # By-mechanism: aggregate Y2+Y3 deltas by `driver_dim` (which carries
    # the growth_method) × bucket
    by_mechanism: dict[str, dict[str, float]] = {}
    if not st_rows.empty:
        st = st_rows.copy()
        st["account_class"] = st["account_class"].fillna("").str.lower()
        st["pnl_line"] = st["pnl_line"].fillna("").astype(str)
        st["period_amount_usd"] = pd.to_numeric(st["period_amount_usd"], errors="coerce").fillna(0.0)
        st["_bucket"] = st.apply(
            lambda r: _bucket_for(r["account_class"], r["pnl_line"]), axis=1
        )
        for mech, grp in st.groupby("driver_dim"):
            by_mechanism[str(mech)] = {
                b: float(grp[grp["_bucket"] == b]["period_amount_usd"].sum())
                for b in ("revenue", "cogs", "rd", "sga")
            }

    # Y1 reconciliation self-check: walk Y1 trio vs operational trio (should match)
    # Already encoded in walk_by_year['Y1'] which sums op_rows directly, so
    # by construction they reconcile.

    return WalkResult(
        strategic_version=strategic_version,
        operational_version=operational_version,
        fy_year=fy_year,
        cash_tax_rate_used=cash_tax_rate,
        walk_by_year=walk_by_year,
        by_entity=by_entity,
        by_mechanism=by_mechanism,
        notes=notes,
    )
