"""Pure helpers used by web.routes.tasks.

Kept out of ``web/routes/`` so the auto-discoverer doesn't try to mount
them as a router. No HTTP concerns here — just step-graph reasoning.
"""

from __future__ import annotations

from typing import Any

from web import bundles, db


def _has_pending_memory_proposals(task_id: str) -> bool:
    return any(
        r.get("task_id") == task_id and r.get("status") == "pending"
        for r in db.rows("memory_proposals")
    )


def derive_task_status(steps: list[dict[str, Any]]) -> str:
    """Roll up step statuses into the parent task's status.

    Ordering matters: ``complete`` only if **all** steps are complete;
    ``blocked`` if any step is failed/blocked; ``in_progress`` if any step
    moved past pending; else ``draft``. ``aborted`` is never derived — it's
    only set via an explicit user action.
    """
    if not steps:
        return "draft"
    statuses = [s.get("status", "pending") for s in steps]
    if all(s == "complete" for s in statuses):
        return "complete"
    if any(s in ("failed", "blocked") for s in statuses):
        return "blocked"
    if any(s != "pending" for s in statuses):
        return "in_progress"
    return "draft"


def maybe_queue_successors(task_id: str) -> list[str]:
    """For each AI step whose deps are all complete and which isn't already
    queued/in-flight, enqueue it via ``bundles.build_and_queue``.

    Returns the list of queue ids newly inserted. Idempotent: a step that
    already has a live queue row is skipped.
    """
    task = db.find("tasks", task_id)
    if task is None:
        return []
    sw = db.find("standard_work", task.get("standard_work_id") or "")
    if sw is None:
        return []
    sw_steps = {s["id"]: s for s in sw.get("steps") or []}
    instances = {s["step_id"]: s for s in task.get("steps") or []}

    live_statuses = {"pending", "claimed", "done"}
    queued_step_ids = {
        r["step_id"]
        for r in db.rows("queue")
        if r.get("task_id") == task_id and r.get("status") in live_statuses
    }

    newly_queued: list[str] = []
    for step_id, sw_step in sw_steps.items():
        if sw_step.get("kind") != "ai":
            continue
        inst = instances.get(step_id)
        if inst is None or inst.get("status") != "pending":
            continue
        if step_id in queued_step_ids:
            continue
        deps = sw_step.get("depends_on") or []
        if not all(
            (instances.get(d) or {}).get("status") == "complete" for d in deps
        ):
            continue
        qid = bundles.build_and_queue(task_id, step_id)
        newly_queued.append(qid)
    return newly_queued


def recompute_task_status(task_id: str) -> str:
    """Compute and persist the derived status. Returns the new status.

    A task that would otherwise be ``complete`` is held at ``blocked`` if any
    of its memory_write proposals are still pending (CLAUDE.md §8 rule 4).
    """
    task = db.find("tasks", task_id)
    if task is None:
        raise KeyError(task_id)
    if task.get("status") == "aborted":
        return "aborted"
    new = derive_task_status(task.get("steps") or [])
    if new == "complete" and _has_pending_memory_proposals(task_id):
        new = "blocked"
    if new != task.get("status"):
        db.update("tasks", task_id, {"status": new})
    return new
