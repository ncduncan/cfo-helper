"""Instantiate a Task from a StandardWork template.

Shared by M4 (user-driven "new task" form) and M7 (cron-fired schedule).
Resolves the owner from the team roster by role tag, materializes a step
instance per template step, and validates the resulting Task before
inserting it into ``db/tasks.json``.

Task IDs follow the pattern ``t-<sw_id>-<period or YYYYMMDD>`` with a
numeric suffix on collision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from web import db
from web.models import Task


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _resolve_owner(
    sw: dict[str, Any], explicit_owner: Optional[str]
) -> Optional[str]:
    """Pick a human owner whose role_tags include the SW's owner_role.

    Ownership implies sign-off and checkpoint approval — responsibilities
    that belong to a human, never to Forge. Falls back to any role-matching
    member only if no human qualifies, and returns None if nobody does.
    """
    if explicit_owner:
        return explicit_owner
    role = sw.get("owner_role")
    if not role:
        return None
    members = [m for m in db.rows("team") if m.get("active", True)]
    for m in members:
        if m.get("kind") == "human" and role in (m.get("role_tags") or []):
            return m["id"]
    for m in members:
        if role in (m.get("role_tags") or []):
            return m["id"]
    return None


def _resolve_assignee(
    sw_step: dict[str, Any], team_index: dict[str, dict[str, Any]]
) -> Optional[str]:
    """Pick default assignee from the step. Fall back to a role-tag match if the
    named assignee doesn't exist on the active roster.
    """
    default = sw_step.get("default_assignee_id")
    if default and default in team_index and team_index[default].get("active", True):
        return default
    role = sw_step.get("owner_role")
    if role:
        for m in team_index.values():
            if m.get("active", True) and role in (m.get("role_tags") or []):
                return m["id"]
    return None


def _materialize_steps(sw: dict[str, Any]) -> list[dict[str, Any]]:
    team_index = {m["id"]: m for m in db.rows("team")}
    out: list[dict[str, Any]] = []
    for s in sw.get("steps") or []:
        out.append(
            {
                "step_id": s["id"],
                "assignee_id": _resolve_assignee(s, team_index),
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "deliverable_paths": [],
                "findings_ref": None,
                "comments": [],
            }
        )
    return out


def _unique_id(base: str) -> str:
    if db.find("tasks", base) is None:
        return base
    i = 2
    while db.find("tasks", f"{base}-{i}") is not None:
        i += 1
    return f"{base}-{i}"


def instantiate_task(
    standard_work_id: str,
    *,
    period: Optional[str] = None,
    title: Optional[str] = None,
    owner_id: Optional[str] = None,
    due_date: Optional[datetime] = None,
    source: str = "manual",
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    sw = db.find("standard_work", standard_work_id)
    if sw is None:
        raise KeyError(f"standard_work not found: {standard_work_id!r}")

    when = now or _now()
    period_for_id = (period or when.strftime("%Y-%m-%d")).lower()
    # Slugify: keep only lowercase alnum, dash, underscore.
    period_for_id = "".join(
        c if (c.isalnum() or c in "-_") else "-" for c in period_for_id
    )
    base_id = f"t-{standard_work_id}-{period_for_id}"
    task_id = _unique_id(base_id)

    if title is None:
        title = sw["name"]
        if period:
            title = f"{title} — {period}"

    if due_date is None:
        offset_days = int(sw.get("due_offset_days") or 0)
        due_date = when + timedelta(days=offset_days) if offset_days else None

    row = {
        "id": task_id,
        "standard_work_id": standard_work_id,
        "period": period,
        "title": title,
        "owner_id": _resolve_owner(sw, owner_id),
        "status": "draft",
        "created_at": when.isoformat(),
        "due_date": due_date.isoformat() if due_date else None,
        "started_at": None,
        "completed_at": None,
        "notes_md": f"_source: {source}_",
        "steps": _materialize_steps(sw),
    }
    validated = Task.model_validate(row).model_dump(mode="json")
    db.insert("tasks", validated)
    return validated
