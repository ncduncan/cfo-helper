"""Account-class → subledger and assumption-dim dispatch."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DispatchDecision:
    status: str                  # 'ok' | 'not_applicable'
    reason: str                  # human-readable
    subledgers: tuple[str, ...]  # ordered: external first, intercompany last
    assumption_dim: str | None   # 'product_line' | 'functional_area' | None


def dispatch(account_map_row: dict) -> DispatchDecision:
    """Decide which subledgers and assumption-dim apply to a GL account.

    `account_map_row` must carry `account_class` and `pnl_line`.
    Returns a DispatchDecision; `status='not_applicable'` accounts are
    skipped by the drilldown skill with a self-check naming the reason.
    """
    cls = (account_map_row.get("account_class") or "").lower()
    pnl_line = (account_map_row.get("pnl_line") or "")

    if cls == "revenue":
        return DispatchDecision(
            status="ok",
            reason="Revenue account: subledger is AR (external) + IBS (intercompany).",
            subledgers=("ar", "ibs"),
            assumption_dim="product_line",
        )
    if cls == "cogs":
        return DispatchDecision(
            status="ok",
            reason="COGS account: subledger is AP + headcount + IBS.",
            subledgers=("ap", "headcount", "ibs"),
            assumption_dim="product_line",
        )
    if cls == "opex":
        # R&D opex carries product-line attribution; everything else is functional.
        if pnl_line.startswith("Opex / R&D"):
            return DispatchDecision(
                status="ok",
                reason="R&D opex: product-line assumption slice.",
                subledgers=("ap", "headcount", "ibs"),
                assumption_dim="product_line",
            )
        return DispatchDecision(
            status="ok",
            reason="SG&A opex: functional-area assumption slice.",
            subledgers=("ap", "headcount", "ibs"),
            assumption_dim="functional_area",
        )

    # Out of scope for v1: balance-sheet, intercompany clearing, taxes,
    # other-income. Drilldown skips these with a not_applicable self-check.
    skip_reasons = {
        "asset":         "Balance-sheet asset account — drilldown out of scope for v1.",
        "liability":     "Balance-sheet liability account — drilldown out of scope for v1.",
        "equity":        "Equity account — drilldown out of scope for v1.",
        "intercompany":  "Intercompany clearing account — covered by reconcile.intercompany_nets_zero, not drilldown.",
        "other_income":  "Other-income account — drilldown out of scope for v1.",
        "tax":           "Tax account — drilldown out of scope for v1.",
    }
    return DispatchDecision(
        status="not_applicable",
        reason=skip_reasons.get(cls, f"Unknown account_class={cls!r}; cannot dispatch."),
        subledgers=(),
        assumption_dim=None,
    )
