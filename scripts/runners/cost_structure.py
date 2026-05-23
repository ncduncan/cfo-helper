"""Runner functions for task_types/cost_structure.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_cost_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 cost structure — categorize GL, compute period totals per bucket."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_cost_intake",
        does=(
            "read connector:excel.gl for the period, categorize each posting "
            "via profile/memory/cost_categories.yaml, produce per-category "
            "totals; emit outputs/controller/work_product.json with one claim "
            "per category"
        ),
        calls="scripts.cost_structure.categorize_gl",
        agent="agents/controller.md",
    )


def run_p2_cost_analysis(task_dir: Path, **kwargs: Any) -> dict:
    """P2 cost structure — trend, top movers, vendor concentration."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_cost_analysis",
        does=(
            "run trend (current vs prior), top_movers, vendor_concentration, "
            "headcount_unit_cost, and unit_economics analyses against the P1 "
            "categorized GL; emit outputs/fpa/work_product.json with claims "
            "per analysis"
        ),
        calls=(
            "scripts.cost_structure.trend + .top_movers + .vendor_concentration "
            "+ .headcount_unit_cost + .unit_economics"
        ),
        agent="agents/fpa.md",
    )


def run_p3_cost_memo(task_dir: Path, **kwargs: Any) -> dict:
    """P3 cost structure — assemble cost memo from P2 analysis."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_cost_memo",
        does=(
            "assemble cost_memo.docx from P2 claims; cite each numeric to a "
            "claim_id; apply writing-style skill"
        ),
        calls="scripts.docx + writing-style skill",
        agent="agents/reporting.md",
    )


def run_p4_cost_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 cost structure — independent re-derivation + tie-out."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_cost_review",
        does=(
            "re-derive category totals from connector:excel.gl, confirm trend "
            "math, validate every memo number traces to a claim_id"
        ),
        calls="scripts.cost_structure (re-derive) + claim-id-discipline skill",
        agent="agents/reviewer.md",
    )
