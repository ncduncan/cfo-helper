"""Runner functions for task_types/knowledge_refresh.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.runners._shared import _stub_error


def run_p1_kb_audit(task_dir: Path, **kwargs: Any) -> dict:
    """P1 knowledge refresh — scan knowledge/ for stale entries."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p1_kb_audit",
        does=(
            "walk knowledge/ entries, validate frontmatter, surface anything "
            "past the stale_window_months threshold (default 18) for CFO "
            "review; emit outputs/controller/work_product.json with the stale "
            "list as artifacts"
        ),
        calls="scripts.build_knowledge_index.scan + .validate",
        agent="agents/controller.md",
    )


def run_p2_kb_checklist(task_dir: Path, **kwargs: Any) -> dict:
    """P2 knowledge refresh — produce regulatory-update checklist."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p2_kb_checklist",
        does=(
            "produce a CFO checklist of regulatory updates to verify "
            "(FASB ASUs, IRS notices, HMRC guidance, Irish Revenue, OECD) "
            "for each stale knowledge area from P1; emit "
            "outputs/fpa/work_product.json with checklist artifact"
        ),
        calls="(no underlying module yet — Forge composes from P1 artifacts)",
        agent="agents/fpa.md",
    )


def run_p4_kb_review(task_dir: Path, **kwargs: Any) -> dict:
    """P4 knowledge refresh — review and bump last_reviewed dates."""
    del task_dir, kwargs  # signature-only on stubs; consumed when wired
    raise _stub_error(
        "run_p4_kb_review",
        does=(
            "after CFO completes the P2 checklist, bump last_reviewed in each "
            "reviewed knowledge file's frontmatter and re-run the index build "
            "so retrieval reflects the new dates"
        ),
        calls="scripts.build_knowledge_index.build_index",
        agent="agents/reviewer.md",
    )
