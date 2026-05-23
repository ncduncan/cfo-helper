"""Runner functions for task_types/deal_underwriting.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_underwrite_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 deal underwriting — normalize the deal, find comparables."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_underwrite_intake",
        does=(
            "normalize the deal from brief_fields, score against "
            "profile/memory/strikezone.yaml, find comparables in the historical "
            "deals table; emit outputs/commercial/work_product.json with the "
            "Deal + Scorecard"
        ),
        calls=(
            "scripts.underwriting.normalize_deal + .score_against_strikezone "
            "+ .find_comparables"
        ),
        agent="agents/commercial.md",
    )


def run_p2_underwrite_screen(task_dir: Path, **kwargs: Any) -> dict:
    """P2 deal underwriting — economics, SSP allocation, risks, recommendation."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_underwrite_screen",
        does=(
            "compute deal economics (NPV, margin, payback), SSP allocation "
            "per ASC 606, top risks, delegation routing per "
            "profile/memory/delegation_matrix.yaml, and a "
            "recommendation; emit outputs/fpa/work_product.json"
        ),
        calls=(
            "scripts.underwriting.compute_economics + .allocate_ssp + "
            ".top_risks + .route_delegations + .recommendation"
        ),
        agent="agents/fpa.md",
    )


def run_p3_underwrite_memo(task_dir: Path, **kwargs: Any) -> dict:
    """P3 deal underwriting — assemble underwriting memo with comparables."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_underwrite_memo",
        does=(
            "assemble underwriting_memo.docx from P1 + P2 claims: deal "
            "summary, scorecard, economics table, comparables, top risks, "
            "delegation routing, and recommendation; cite every numeric to a "
            "claim_id"
        ),
        calls="scripts.docx + writing-style skill",
        agent="agents/reporting.md",
    )


def run_p4_underwrite_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 deal underwriting — independent re-derivation + strikezone gating."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_underwrite_review",
        does=(
            "re-derive deal economics from raw brief_fields, confirm SSP "
            "allocation math, validate strikezone scoring, verify the "
            "recommendation matches the delegation matrix; flag any deal "
            "outside strikezone for CFO elevation"
        ),
        calls=(
            "scripts.underwriting (re-derive) + scripts.reconcile (tolerance "
            "checks) + claim-id-discipline skill"
        ),
        agent="agents/reviewer.md",
    )
