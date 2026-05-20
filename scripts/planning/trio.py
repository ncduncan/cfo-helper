"""Headline trio computation: sales, EBIT, free cash flow.

Sales = sum of revenue assumption rows.
EBIT  = revenue − cogs − opex (signs: revenue positive, cogs/opex magnitudes
        are stored positive in the assumptions schema and subtracted here).
FCF   = EBIT
        + D&A                     (add back non-cash; opex rows where pnl_line
                                   starts with "Opex / D&A")
        − Δ AR  (working capital; v1 reads assumption rows where account_class
                 = 'asset' and pnl_line starts with "BS / AR"; absent → 0)
        + Δ AP  (account_class = 'liability' and pnl_line starts with "BS / AP")
        + Δ Deferred Revenue (contract liability; account_class = 'liability'
                              and pnl_line contains "Deferred Revenue")
        − Δ Capitalized Commissions (contract asset; account_class = 'asset'
                                     and pnl_line contains "Capitalized
                                     Commissions" or "Capitalized Commission")
        − Capex (account_class = 'asset' and pnl_line starts with "BS / Capex")
        − Cash taxes (account_class = 'tax' or pnl_line starts with "Cash Tax")

Sign convention for assumption rows: `period_amount_usd` is the magnitude.
The component formula handles the sign per the FCF identity above.

Δ values for plan/outlook are *period* movements — the assumption row is
already "the change for this period," not a balance. (Plan rows are usually
authored that way; if a CFO wants to author balances instead, they need a
separate balance-grain assumption layer, which is out of scope v1.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class TrioResult:
    version: str
    entity: str
    period: str
    sales_usd: float
    ebit_usd: float
    fcf_usd: float
    fcf_components: dict[str, float] = field(default_factory=dict)
    bucket_totals: dict[str, float] = field(default_factory=dict)  # revenue, cogs, rd, sga
    notes: list[str] = field(default_factory=list)


def _matches(rows: pd.DataFrame, account_class: str | tuple[str, ...] | None = None,
             pnl_line_prefix: str | tuple[str, ...] | None = None,
             pnl_line_contains: str | tuple[str, ...] | None = None) -> pd.DataFrame:
    """Filter rows by the three optional predicates. None means 'don't restrict'.

    Bypasses on already-empty input: pandas drops columns when masking an
    empty DataFrame, which breaks downstream `.sum()` calls. Returning the
    empty input as-is preserves the column shape.
    """
    out = rows
    if out.empty:
        return out
    if account_class is not None:
        targets = (account_class,) if isinstance(account_class, str) else account_class
        out = out[out["account_class"].isin(targets)]
        if out.empty:
            return out
    if pnl_line_prefix is not None:
        prefixes = (pnl_line_prefix,) if isinstance(pnl_line_prefix, str) else pnl_line_prefix
        out = out[out["pnl_line"].fillna("").str.startswith(tuple(prefixes))]
        if out.empty:
            return out
    if pnl_line_contains is not None:
        needles = (pnl_line_contains,) if isinstance(pnl_line_contains, str) else pnl_line_contains
        mask = out["pnl_line"].fillna("").apply(
            lambda s: any(n in s for n in needles)
        )
        out = out[mask]
    return out


def _bucket_totals(rows: pd.DataFrame) -> dict[str, float]:
    """Sales / COGS / R&D / SG&A bucket totals, derived from class+pnl_line."""
    return {
        "revenue": float(_matches(rows, account_class="revenue")["period_amount_usd"].sum()),
        "cogs":    float(_matches(rows, account_class="cogs")["period_amount_usd"].sum()),
        "rd":      float(_matches(rows, account_class="opex",
                                  pnl_line_prefix="Opex / R&D")["period_amount_usd"].sum()),
        "sga":     float(
            _matches(rows, account_class="opex")["period_amount_usd"].sum()
            - _matches(rows, account_class="opex",
                       pnl_line_prefix="Opex / R&D")["period_amount_usd"].sum()
        ),
    }


def _fcf_components(rows: pd.DataFrame, ebit_usd: float,
                    cash_tax_rate: float = 0.21) -> tuple[dict[str, float], list[str]]:
    """Decompose FCF into named line items. Missing components contribute 0
    and are flagged as notes so the prose can name what's stubbed.
    """
    notes: list[str] = []
    comps: dict[str, float] = {"ebit": ebit_usd}

    da = float(_matches(rows, account_class="opex",
                        pnl_line_prefix="Opex / D&A")["period_amount_usd"].sum())
    comps["da_addback"] = da
    if da == 0.0:
        notes.append("FCF: D&A line is zero — no Opex / D&A assumption rows present.")

    delta_ar = float(_matches(rows, account_class="asset",
                              pnl_line_prefix="BS / AR")["period_amount_usd"].sum())
    comps["delta_ar"] = -delta_ar  # AR increase is a use of cash

    delta_ap = float(_matches(rows, account_class="liability",
                              pnl_line_prefix="BS / AP")["period_amount_usd"].sum())
    comps["delta_ap"] = delta_ap

    delta_def_rev = float(_matches(rows, account_class="liability",
                                   pnl_line_contains="Deferred Revenue")["period_amount_usd"].sum())
    comps["delta_deferred_revenue"] = delta_def_rev
    if delta_def_rev == 0.0:
        notes.append(
            "FCF: contract-liability movement (deferred revenue) line is zero — "
            "this is the SaaS multi-year-prepay swing; expected to be material in production. "
            "Verify the plan workbook carries deferred-revenue assumption rows."
        )

    delta_cap_comm = float(_matches(rows, account_class="asset",
                                    pnl_line_contains=("Capitalized Commissions",
                                                       "Capitalized Commission"))["period_amount_usd"].sum())
    comps["delta_capitalized_commissions"] = -delta_cap_comm  # capitalization is a use of cash

    capex = float(_matches(rows, account_class="asset",
                           pnl_line_prefix="BS / Capex")["period_amount_usd"].sum())
    comps["capex"] = -capex

    # Cash tax: prefer an explicit cash-tax assumption row; else estimate as
    # cash_tax_rate × max(EBIT, 0). v1 scope.
    explicit_tax = float(_matches(rows, account_class="tax")["period_amount_usd"].sum())
    if explicit_tax > 0:
        comps["cash_tax"] = -explicit_tax
    else:
        est = max(0.0, ebit_usd) * cash_tax_rate
        comps["cash_tax"] = -est
        notes.append(
            f"FCF: cash tax estimated as {cash_tax_rate:.0%} × max(EBIT, 0) = "
            f"{est:,.0f}. Author an explicit assumption row with account_class='tax' "
            "to override."
        )

    return comps, notes


def compute_trio(
    *,
    version: str,
    period: str,
    repo_root: Path,
    entity: str | None = None,         # None ⇒ consolidated across all entities
    consolidated: bool = False,        # alias for entity=None
    cash_tax_rate: float = 0.21,
) -> TrioResult:
    """Sales / EBIT / FCF for a plan or outlook version.

    Per-entity mode (default): pass `entity="UK"`. Returns the trio for that
    one company code.

    Consolidated mode: pass `consolidated=True` (or omit `entity`). Returns
    the trio summed across every entity that has an assumption-manifest
    entry for this version. Use for the corporate-facing view; the per-entity
    mode is for FP&A drill-down.
    """
    import sys
    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433

    if consolidated or entity is None:
        # Roll up across all entities discoverable in the manifest.
        entities = connectors.list_entities(period)
        frames: list[pd.DataFrame] = []
        for ent in entities:
            f = connectors.get_assumptions(period=period, entity=ent, version=version)
            if not f.empty:
                frames.append(f)
        rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        entity_label = "_consolidated"
    else:
        rows = connectors.get_assumptions(period=period, entity=entity, version=version)
        entity_label = entity

    if rows.empty:
        return TrioResult(
            version=version, entity=entity_label, period=period,
            sales_usd=0.0, ebit_usd=0.0, fcf_usd=0.0,
            notes=[f"No assumption rows for entity={entity_label} version={version!r} period={period}."],
        )

    rows = rows.copy()
    rows["account_class"] = rows["account_class"].fillna("").astype(str).str.lower().str.strip()
    rows["pnl_line"] = rows["pnl_line"].fillna("").astype(str)
    rows["period_amount_usd"] = pd.to_numeric(rows["period_amount_usd"], errors="coerce").fillna(0.0)

    buckets = _bucket_totals(rows)
    sales = buckets["revenue"]
    ebit = buckets["revenue"] - buckets["cogs"] - buckets["rd"] - buckets["sga"]

    comps, notes = _fcf_components(rows, ebit, cash_tax_rate=cash_tax_rate)
    # Assemble FCF = EBIT + D&A + Δ AP − Δ AR + Δ DeferredRev − Δ CapComm − Capex − CashTax
    fcf = (
        comps["ebit"]
        + comps["da_addback"]
        + comps["delta_ar"]                     # already signed (negative when AR grew)
        + comps["delta_ap"]                     # positive when AP grew
        + comps["delta_deferred_revenue"]
        + comps["delta_capitalized_commissions"]  # already signed (negative when cap'd)
        + comps["capex"]                        # already signed (negative)
        + comps["cash_tax"]                     # already signed (negative)
    )

    return TrioResult(
        version=version, entity=entity_label, period=period,
        sales_usd=sales, ebit_usd=ebit, fcf_usd=fcf,
        fcf_components=comps,
        bucket_totals=buckets,
        notes=notes,
    )
