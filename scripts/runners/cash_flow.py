"""Runner functions for task_types/cash_flow.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_cash_intake(task_dir: Path, **kwargs: Any) -> dict:
    """P1 cash flow — read AR/AP/deferred-rev/FX subledgers."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_cash_intake",
        does=(
            "read AR aging, AP aging, deferred-rev opening balance, and FX "
            "exposure from connectors; emit outputs/controller/work_product.json "
            "with per-subledger summary claims"
        ),
        calls=(
            "connectors.ar / .ap / .subledger + "
            "scripts.cash_flow.ar_aging_buckets + .fx_exposure"
        ),
        agent="agents/controller.md",
    )


def run_p2_cash_snapshot(task_dir: Path, **kwargs: Any) -> dict:
    """P2 cash flow — DSO, CCC, deferred-rev rollforward, hedge sizing."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_cash_snapshot",
        does=(
            "compute DSO by customer archetype, cash conversion cycle, "
            "deferred-rev rollforward, and hedge sizing per fx_hedge_policy; "
            "emit outputs/fpa/work_product.json with one claim per metric"
        ),
        calls=(
            "scripts.cash_flow.dso_by_archetype + .cash_conversion_cycle + "
            ".deferred_rev_rollforward + .hedge_sizing"
        ),
        agent="agents/fpa.md",
    )


def run_p3_cash_optimization(task_dir: Path, **kwargs: Any) -> dict:
    """P3 cash flow — prepay-incentive ROI, payment-term migration analysis."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_cash_optimization",
        does=(
            "run prepay_incentive_roi and payment_term_migration analyses; "
            "assemble cash optimization memo citing each numeric to a claim_id"
        ),
        calls=(
            "scripts.cash_flow.prepay_incentive_roi + .payment_term_migration "
            "+ scripts.docx"
        ),
        agent="agents/reporting.md",
    )


def run_p4_cash_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 cash flow — independent re-derivation + tie-out."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_cash_review",
        does=(
            "re-derive cash metrics from raw subledgers, confirm rollforward "
            "math (opening + bookings − recognition = closing), validate every "
            "memo number traces to a claim_id"
        ),
        calls=(
            "scripts.cash_flow + deferred-rev-rollforward skill + "
            "claim-id-discipline skill"
        ),
        agent="agents/reviewer.md",
    )
