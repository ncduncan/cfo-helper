"""
Monthly Management Operating Review (MOR) deck composer.

# Pattern source: cfo-helper-internal — section list per CLAUDE.md §6
# (Reporting close-pack defaults). The MOR is FP&A-owned (CLAUDE.md §8 rule
# 8) but Reporting agent assembles using FP&A's variance content.

The composer reads a MOR-shaped payload (typically built from a task's
work_product.json) and emits a `.pptx`. It does NOT load work_product.json
itself — that wiring lives in `scripts.dispatch` for the dispatcher path
and in the agent prompt for the narrative-assembly path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from pptx import Presentation

from scripts.pptx import templates as tpl
from scripts.profile_loader import org_name


@dataclass
class MORPayload:
    """Structured input for the MOR composer.

    Each field references upstream claim_ids so the composer can stamp the
    speaker-notes pane with provenance. The composer doesn't validate the
    claims dict — that's `scripts.workproduct`'s job upstream.
    """
    period: str
    title: str = "Management Operating Review"
    subtitle: str | None = None              # default: org_name from profile
    author: str = "FP&A"

    # Headline strip (3-6 KPIs)
    headline_kpis: Sequence[Mapping] = field(default_factory=list)

    # ARR + retention block
    arr_chart_path: Path | None = None
    arr_callouts: Sequence[str] = field(default_factory=list)

    # BBRR (Bookings/Billings/RPO/Revenue) waterfall
    bbrr_chart_path: Path | None = None
    bbrr_callouts: Sequence[str] = field(default_factory=list)

    # Top-10 customer movement
    top10_chart_path: Path | None = None
    top10_callouts: Sequence[str] = field(default_factory=list)

    # Product-line P&L table
    product_pl_headers: Sequence[str] = field(default_factory=list)
    product_pl_rows: Sequence[Sequence] = field(default_factory=list)

    # Variance commentary (archetype × product × mechanism)
    variance_rows: Sequence[Mapping] = field(default_factory=list)

    # Cash & deferred rev
    deferred_rev_chart_path: Path | None = None
    cash_callouts: Sequence[str] = field(default_factory=list)

    # KPI dashboard image
    kpi_dashboard_path: Path | None = None
    kpi_dashboard_callouts: Sequence[str] = field(default_factory=list)

    # Parent-reporting reconciliation (text-heavy)
    parent_reconciliation_text: str = ""

    # Open items
    open_items_text: str = ""

    # Provenance
    headline_claim_ids: Sequence[str] = field(default_factory=list)
    variance_claim_ids: Sequence[str] = field(default_factory=list)
    bbrr_claim_ids: Sequence[str] = field(default_factory=list)
    arr_claim_ids: Sequence[str] = field(default_factory=list)
    top10_claim_ids: Sequence[str] = field(default_factory=list)
    cash_claim_ids: Sequence[str] = field(default_factory=list)
    kpi_claim_ids: Sequence[str] = field(default_factory=list)


def build_mor_deck(payload: MORPayload, output_path: Path) -> Path:
    """Assemble the MOR deck and save to `output_path`. Returns the path."""
    prs = tpl.new_deck()

    tpl.add_title_slide(
        prs,
        title=payload.title,
        subtitle=payload.subtitle or org_name(),
        period=payload.period,
        author=payload.author,
    )

    # 1. Headline P&L / KPI strip
    if payload.headline_kpis:
        tpl.add_kpi_strip_slide(
            prs,
            title=f"Headline — {payload.period}",
            kpis=payload.headline_kpis,
            period=payload.period,
            claim_ids=payload.headline_claim_ids,
        )

    # 2. ARR snapshot + NRR/GRR
    if payload.arr_chart_path:
        tpl.add_chart_with_callouts_slide(
            prs,
            title=f"ARR snapshot · NRR/GRR",
            chart_image_path=payload.arr_chart_path,
            callouts=payload.arr_callouts,
            period=payload.period,
            claim_ids=payload.arr_claim_ids,
        )

    # 3. BBRR waterfall
    if payload.bbrr_chart_path:
        tpl.add_chart_with_callouts_slide(
            prs,
            title="Bookings · Billings · RPO · Revenue",
            chart_image_path=payload.bbrr_chart_path,
            callouts=payload.bbrr_callouts,
            period=payload.period,
            claim_ids=payload.bbrr_claim_ids,
        )

    # 4. Top-10 customer movement
    if payload.top10_chart_path:
        tpl.add_chart_with_callouts_slide(
            prs,
            title="Top-10 customer movement",
            chart_image_path=payload.top10_chart_path,
            callouts=payload.top10_callouts,
            period=payload.period,
            claim_ids=payload.top10_claim_ids,
        )

    # 5. Product-line P&L
    if payload.product_pl_rows:
        tpl.add_table_slide(
            prs,
            title="Product-line P&L (Flight Ops · Tech Ops · APM/Other)",
            headers=payload.product_pl_headers,
            rows=payload.product_pl_rows,
            period=payload.period,
            highlight_negative_col=None,
        )

    # 6. Variance commentary (archetype × product × mechanism)
    if payload.variance_rows:
        tpl.add_section_divider(
            prs, title="Variance commentary", period=payload.period,
        )
        tpl.add_variance_commentary_slide(
            prs,
            title="Variance commentary — archetype × product × mechanism",
            rows=payload.variance_rows,
            period=payload.period,
            claim_ids=payload.variance_claim_ids,
        )

    # 7. Cash & deferred revenue
    if payload.deferred_rev_chart_path:
        tpl.add_chart_with_callouts_slide(
            prs,
            title="Cash & deferred revenue",
            chart_image_path=payload.deferred_rev_chart_path,
            callouts=payload.cash_callouts,
            period=payload.period,
            claim_ids=payload.cash_claim_ids,
        )

    # 8. KPI dashboard
    if payload.kpi_dashboard_path:
        tpl.add_chart_with_callouts_slide(
            prs,
            title="KPI dashboard",
            chart_image_path=payload.kpi_dashboard_path,
            callouts=payload.kpi_dashboard_callouts,
            period=payload.period,
            claim_ids=payload.kpi_claim_ids,
        )

    # 9. Parent-reporting reconciliation (only when parent reporting applies)
    if payload.parent_reconciliation_text:
        tpl.add_two_column_slide(
            prs,
            title="Parent reconciliation",
            left_text=payload.parent_reconciliation_text,
            right_text="(See close pack > 'Parent Map' sheet for line-by-line detail.)",
            period=payload.period,
        )

    # 10. Open items
    if payload.open_items_text:
        tpl.add_two_column_slide(
            prs,
            title="Open items · routed to next close",
            left_text=payload.open_items_text,
            right_text="",
            period=payload.period,
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(output_path))
    return output_path


def slide_count(payload: MORPayload) -> int:
    """How many slides the composer would emit for this payload (used in tests)."""
    n = 1  # title
    if payload.headline_kpis: n += 1
    if payload.arr_chart_path: n += 1
    if payload.bbrr_chart_path: n += 1
    if payload.top10_chart_path: n += 1
    if payload.product_pl_rows: n += 1
    if payload.variance_rows: n += 2  # divider + table
    if payload.deferred_rev_chart_path: n += 1
    if payload.kpi_dashboard_path: n += 1
    if payload.parent_reconciliation_text: n += 1
    if payload.open_items_text: n += 1
    return n


__all__ = ["MORPayload", "build_mor_deck", "slide_count"]
