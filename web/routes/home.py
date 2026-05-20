"""Home dashboard — landing page surfacing today's work + alerts.

Alerts (M8):
- Overdue tasks (due_date < today, status not in {complete, aborted})
- Blocked tasks
- Stale queue bundles (stored upstream_hash != current hash)
- Pending memory-write proposals
- Forge queue depth
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from web import bundles, db


router = APIRouter()

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _today_iso() -> str:
    return datetime.now(tz=timezone.utc).date().isoformat()


def _overdue_tasks() -> list[dict]:
    today = _today_iso()
    out = []
    for t in db.rows("tasks"):
        due = (t.get("due_date") or "")[:10]
        if not due or due >= today:
            continue
        if t.get("status") in ("complete", "aborted"):
            continue
        out.append(t)
    return out


def _stale_queue_rows() -> list[dict]:
    out = []
    for r in db.rows("queue"):
        if r.get("status") not in ("pending", "claimed"):
            continue
        stored = r.get("upstream_hash")
        if stored is None:
            continue
        try:
            now = bundles.compute_upstream_hash(r["task_id"], r["step_id"])
        except (KeyError, ValueError):
            continue
        if stored != now:
            out.append(r)
    return out


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    overdue = _overdue_tasks()
    blocked = [t for t in db.rows("tasks") if t.get("status") == "blocked"]
    pending_memory = [
        r for r in db.rows("memory_proposals") if r.get("status") == "pending"
    ]
    stale = _stale_queue_rows()
    return TEMPLATES.TemplateResponse(
        request,
        "home.html",
        {
            "team_count": len(db.rows("team")),
            "standard_work_count": len(db.rows("standard_work")),
            "task_count": len(db.rows("tasks")),
            "queue_pending": sum(
                1 for r in db.rows("queue") if r.get("status") == "pending"
            ),
            "overdue": overdue,
            "blocked": blocked,
            "stale": stale,
            "pending_memory": pending_memory,
        },
    )
