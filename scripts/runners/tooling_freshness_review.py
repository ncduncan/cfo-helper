"""Runner functions for task_types/tooling_freshness_review.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_freshness_diff(task_dir: Path, **kwargs: Any) -> dict:
    """P1 tooling freshness — diff local pins against upstream SHAs."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_freshness_diff",
        does=(
            "call freshness_check.diff_report for each pin file under memory/ "
            "(upstream_skills_pin.json, upstream_fsi_skills_pin.json); write "
            "the combined report markdown to task artifacts; emit a claim for "
            "total deltas. If both reports show zero changes, short-circuit "
            "the rest of the pipeline and auto-complete the task."
        ),
        calls=(
            "scripts.tooling.freshness_check.diff_report + "
            ".render_combined_report_md"
        ),
        agent="(coordinator role — no narrative)",
    )


def run_p3_freshness_repin(task_dir: Path, **kwargs: Any) -> dict:
    """P3 tooling freshness — repin acknowledged skills after CFO approval."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p3_freshness_repin",
        does=(
            "after CFO sign-off in P2, run freshness_check.save_pin for each "
            "skill the CFO marked as 'adapt' or 'considered-not-adopted', "
            "updating memory/upstream_*_pin.json with the new upstream SHA"
        ),
        calls="scripts.tooling.freshness_check.save_pin",
        agent="(coordinator role — no narrative)",
    )
