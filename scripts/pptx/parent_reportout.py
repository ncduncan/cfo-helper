"""
Quarterly parent FP&A report-out deck composer (when parent reporting applies).

# Pattern source: cfo-helper-internal — closely mirrors the MOR deck
# (framework CLAUDE.md §3) but adds a segment-reconciliation slide and
# tightens the variance commentary to items material at parent-segment
# granularity. Per CLAUDE.md §2 rule 9, this is FP&A-owned and
# CFO-presented peer-to-peer. Only run when
# `profile/company_profile.yaml:parent_company.has_parent_chart` is true.

The composer accepts a MORPayload with optional parent-specific extensions
so we don't duplicate fields. Use `ParentReportoutPayload` (subclass) when
parent-specific data is available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from scripts.pptx import templates as tpl
from scripts.pptx.mor import MORPayload, build_mor_deck
from scripts.profile_loader import org_name


@dataclass
class ParentReportoutPayload(MORPayload):
    """Extends MORPayload with parent-segment reconciliation specifics."""
    title: str = "Parent FP&A Report-out"
    author: str | None = None                # default: "<org_name> · FP&A"

    def __post_init__(self):
        if self.author is None:
            self.author = f"{org_name()} · FP&A"

    # Segment reconciliation table
    segment_recon_headers: Sequence[str] = field(default_factory=list)
    segment_recon_rows: Sequence[Sequence] = field(default_factory=list)
    segment_recon_claim_ids: Sequence[str] = field(default_factory=list)

    # Account-map deltas vs. parent chart
    account_map_deltas: Sequence[Mapping] = field(default_factory=list)


def build_parent_reportout_deck(
    payload: ParentReportoutPayload, output_path: Path,
) -> Path:
    """Build the parent FP&A report-out. Reuses the MOR composer and appends
    parent-specific slides at the end."""
    # First, build the MOR-shape body
    output_path = Path(output_path)
    build_mor_deck(payload, output_path)

    # Then re-open and append the parent-specific slides
    from pptx import Presentation
    prs = Presentation(str(output_path))

    # Segment reconciliation table
    if payload.segment_recon_rows:
        tpl.add_section_divider(
            prs, title="Parent segment reconciliation", period=payload.period,
        )
        tpl.add_table_slide(
            prs,
            title="Segment reconciliation — internal vs. parent chart",
            headers=payload.segment_recon_headers,
            rows=payload.segment_recon_rows,
            period=payload.period,
            claim_ids=payload.segment_recon_claim_ids,
            highlight_negative_col=None,
        )

    # Account-map deltas
    if payload.account_map_deltas:
        rows = [
            [d.get("internal_account", "—"),
             d.get("parent_account", "—"),
             d.get("status", "—"),
             d.get("notes", "")]
            for d in payload.account_map_deltas
        ]
        tpl.add_table_slide(
            prs,
            title="Account-map deltas vs. parent chart",
            headers=["Internal", "Parent", "Status", "Notes"],
            rows=rows,
            period=payload.period,
        )

    prs.save(str(output_path))
    return output_path


__all__ = ["ParentReportoutPayload", "build_parent_reportout_deck"]
