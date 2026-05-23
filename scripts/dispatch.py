"""Forge deterministic-runner facade.

Every ``deterministic_runner`` string in ``task_types/*.yaml`` resolves to a
function in this module. Forge looks up the runner here when it picks up a
queue bundle whose step carries an ``inputs[]`` entry of the form
``runner:scripts.dispatch.<name>``.

Runner implementations live in ``scripts/runners/<task_type>.py``. This
module re-exports every public runner symbol so that existing
``task_types/*.yaml`` ``deterministic_runner`` strings and any code that
imports from ``scripts.dispatch`` continue to work without changes.

Three kinds of entries live here:

1. **Re-exports** — every runner function delegated to its task-type module.
2. **Helpers** — :func:`gather_memory_write_proposals` (CLAUDE.md §2 rule 4)
   is implemented here. It scans a task's deliverables for ``kind=memory_write``
   requests and returns them so the dashboard's finalize gate can stage
   each into ``profile/db/memory_proposals.json``.
3. **Registry** — :data:`RUNNERS` maps every public runner name to its
   function. ``tests/test_dispatch.py`` walks every YAML's
   ``deterministic_runner`` and asserts the name is in this registry.
"""

from __future__ import annotations

from typing import Any, Callable

# ---------------------------------------------------------------------------
# Re-exports from per-task-type runner modules
# ---------------------------------------------------------------------------

from scripts.runners.month_end_close import (
    run_p1_controller,
    run_p2_fpa,
    run_p3_reporting,
    run_p4_reviewer,
    run_p5_finalize,
)
from scripts.runners.knowledge_refresh import (
    run_p1_kb_audit,
    run_p2_kb_checklist,
    run_p4_kb_review,
)
from scripts.runners.tooling_freshness_review import (
    run_p1_freshness_diff,
    run_p3_freshness_repin,
)
from scripts.runners.cost_structure import (
    run_p1_cost_intake,
    run_p2_cost_analysis,
    run_p3_cost_memo,
    run_p4_cost_review,
)
from scripts.runners.cash_flow import (
    run_p1_cash_intake,
    run_p2_cash_snapshot,
    run_p3_cash_optimization,
    run_p4_cash_review,
)
from scripts.runners.accounting_qa import (
    run_p1_qa_intake,
    run_p2_qa_research,
    run_p3_qa_memo,
    run_p4_qa_review,
)
from scripts.runners.deal_underwriting import (
    run_p1_underwrite_intake,
    run_p2_underwrite_screen,
    run_p3_underwrite_memo,
    run_p4_underwrite_review,
)

# ---------------------------------------------------------------------------
# Memory-write helper (CLAUDE.md §2 rule 4)
# ---------------------------------------------------------------------------


def gather_memory_write_proposals(task_id: str) -> list[dict]:
    """Collect ``kind=memory_write`` requests from every deliverable of a task.

    Walks the task's step deliverable_paths (recorded in
    ``profile/db/tasks.json``), reads each ``work_product.json``, and pulls
    out the ``requests[]`` entries whose ``kind == "memory_write"``. The
    caller (the finalize gate in ``run_p5_finalize``, or the dashboard route
    in ``web/routes/memory_proposals.py``) stages each request into
    ``profile/db/memory_proposals.json`` for CFO approval.

    Per CLAUDE.md §2 rule 4: ``run_p5_finalize`` blocks until every staged
    proposal is resolved (approved or rejected) by the CFO.
    """
    from web import audit, db
    from scripts.paths import REPO_ROOT

    task = db.find("tasks", task_id)
    if task is None:
        raise ValueError(f"task not found: {task_id!r}")

    proposals: list[dict] = []
    for step in task.get("steps", []):
        deliverables = step.get("deliverable_paths") or []
        if not deliverables:
            continue
        wp_path = audit._find_work_product(deliverables, REPO_ROOT)
        if wp_path is None:
            continue
        for req in audit.extract_memory_writes(wp_path):
            proposals.append({
                "task_id": task_id,
                "step_id": step.get("step_id"),
                "agent_role": step.get("owner_role"),
                "request": req,
            })
    return proposals


# ---------------------------------------------------------------------------
# Registry — every YAML-referenced runner name maps to its function here.
# ---------------------------------------------------------------------------


RUNNERS: dict[str, Callable[..., Any]] = {
    # month_end_close
    "run_p1_controller": run_p1_controller,
    "run_p2_fpa": run_p2_fpa,
    "run_p3_reporting": run_p3_reporting,
    "run_p4_reviewer": run_p4_reviewer,
    "run_p5_finalize": run_p5_finalize,
    # knowledge_refresh
    "run_p1_kb_audit": run_p1_kb_audit,
    "run_p2_kb_checklist": run_p2_kb_checklist,
    "run_p4_kb_review": run_p4_kb_review,
    # tooling_freshness_review
    "run_p1_freshness_diff": run_p1_freshness_diff,
    "run_p3_freshness_repin": run_p3_freshness_repin,
    # cost_structure
    "run_p1_cost_intake": run_p1_cost_intake,
    "run_p2_cost_analysis": run_p2_cost_analysis,
    "run_p3_cost_memo": run_p3_cost_memo,
    "run_p4_cost_review": run_p4_cost_review,
    # cash_flow
    "run_p1_cash_intake": run_p1_cash_intake,
    "run_p2_cash_snapshot": run_p2_cash_snapshot,
    "run_p3_cash_optimization": run_p3_cash_optimization,
    "run_p4_cash_review": run_p4_cash_review,
    # accounting_qa
    "run_p1_qa_intake": run_p1_qa_intake,
    "run_p2_qa_research": run_p2_qa_research,
    "run_p3_qa_memo": run_p3_qa_memo,
    "run_p4_qa_review": run_p4_qa_review,
    # deal_underwriting
    "run_p1_underwrite_intake": run_p1_underwrite_intake,
    "run_p2_underwrite_screen": run_p2_underwrite_screen,
    "run_p3_underwrite_memo": run_p3_underwrite_memo,
    "run_p4_underwrite_review": run_p4_underwrite_review,
}


def resolve(runner_name: str) -> Callable[..., Any]:
    """Look up a runner by name (e.g. ``run_p1_controller``).

    Raises :class:`KeyError` if the name is not in :data:`RUNNERS`. Forge
    uses this when processing a queue bundle whose ``inputs[]`` carries
    ``runner:scripts.dispatch.<name>``.
    """
    if runner_name not in RUNNERS:
        raise KeyError(
            f"unknown runner: {runner_name!r}. "
            f"Known runners: {sorted(RUNNERS)}"
        )
    return RUNNERS[runner_name]
