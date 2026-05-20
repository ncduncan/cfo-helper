"""
Quarterly Balance Sheet Review (BSR) deck composer.

# Pattern source: cfo-helper-internal — Controllership-owned (CLAUDE.md §8 rule 8),
# distinct from the FP&A-owned reporting trio. This is the single
# Controllership-to-parent-Controllership pipe.

The BSR deck pairs with `final/bsr_account_roll.xlsx` (built via
`scripts.xlsx.builders.build_bsr_account_roll`). The deck summarizes the
account roll, walks flux explanations, lists material reserves/accruals,
and surfaces Reviewer's sample selections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from scripts.pptx import templates as tpl
from scripts.profile_loader import org_name


@dataclass
class BSRPayload:
    period: str
    title: str = "Balance Sheet Review"
    subtitle: str | None = None             # default: "<org_name> · Controllership"
    author: str = "Controller"

    # High-level balance sheet summary (KPI strip)
    bs_summary_kpis: Sequence[Mapping] = field(default_factory=list)
    bs_summary_claim_ids: Sequence[str] = field(default_factory=list)

    # Account roll table (top N accounts by balance)
    account_roll_headers: Sequence[str] = field(default_factory=list)
    account_roll_rows: Sequence[Sequence] = field(default_factory=list)
    account_roll_claim_ids: Sequence[str] = field(default_factory=list)

    # Flux explanations (MoM / QoQ)
    flux_rows: Sequence[Mapping] = field(default_factory=list)
    flux_claim_ids: Sequence[str] = field(default_factory=list)

    # Material reserves / accruals
    reserves_headers: Sequence[str] = field(default_factory=list)
    reserves_rows: Sequence[Sequence] = field(default_factory=list)
    reserves_claim_ids: Sequence[str] = field(default_factory=list)

    # Reviewer sample selections
    reviewer_samples_text: str = ""

    # Open items / parent follow-ups
    open_items_text: str = ""

    # Optional supporting xlsx pointer (referenced in footer)
    supporting_xlsx_name: str = ""


def build_bsr_deck(payload: BSRPayload, output_path: Path) -> Path:
    prs = tpl.new_deck()

    subtitle = payload.subtitle or f"{org_name()} · Controllership"
    tpl.add_title_slide(
        prs,
        title=payload.title,
        subtitle=f"{subtitle} · {payload.period}",
        period=payload.period,
        author=payload.author,
    )

    if payload.bs_summary_kpis:
        tpl.add_kpi_strip_slide(
            prs,
            title=f"Balance sheet summary — {payload.period}",
            kpis=payload.bs_summary_kpis,
            period=payload.period,
            claim_ids=payload.bs_summary_claim_ids,
        )

    if payload.account_roll_rows:
        tpl.add_section_divider(
            prs, title="Account roll", period=payload.period,
        )
        tpl.add_table_slide(
            prs,
            title="Account-by-account roll (top balances)",
            headers=payload.account_roll_headers,
            rows=payload.account_roll_rows,
            period=payload.period,
            claim_ids=payload.account_roll_claim_ids,
        )

    if payload.flux_rows:
        tpl.add_section_divider(
            prs, title="Flux explanations", period=payload.period,
        )
        tpl.add_variance_commentary_slide(
            prs,
            title="Material flux — driver / quantum / explanation",
            rows=payload.flux_rows,
            period=payload.period,
            claim_ids=payload.flux_claim_ids,
        )

    if payload.reserves_rows:
        tpl.add_table_slide(
            prs,
            title="Material reserves & accruals",
            headers=payload.reserves_headers,
            rows=payload.reserves_rows,
            period=payload.period,
            claim_ids=payload.reserves_claim_ids,
        )

    if payload.reviewer_samples_text:
        tpl.add_two_column_slide(
            prs,
            title="Reviewer sample selections",
            left_text=payload.reviewer_samples_text,
            right_text="(Full Reviewer findings: review/findings.json — sign-off required to finalize.)",
            period=payload.period,
        )

    if payload.open_items_text:
        tpl.add_two_column_slide(
            prs,
            title="Open items · parent follow-ups",
            left_text=payload.open_items_text,
            right_text=(
                f"Supporting workbook: {payload.supporting_xlsx_name}"
                if payload.supporting_xlsx_name else ""
            ),
            period=payload.period,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return output_path


__all__ = ["BSRPayload", "build_bsr_deck"]
