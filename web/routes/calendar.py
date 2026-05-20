"""Calendar — month + week grids over the ``tasks`` collection.

Tasks plot on ``due_date``. Server-rendered HTMX (no JS calendar lib).
Auto-refreshes on ``db-changed:tasks`` via the SSE → HTMX bridge.
"""

from __future__ import annotations

import calendar as cal
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from web import db


router = APIRouter(prefix="/calendar")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

_STATUS_COLOR = {
    "draft": "bg-slate-200 text-slate-800",
    "in_progress": "bg-sky-200 text-sky-900",
    "blocked": "bg-amber-200 text-amber-900",
    "complete": "bg-emerald-200 text-emerald-900",
    "aborted": "bg-rose-200 text-rose-900 line-through",
}


def _today_utc() -> date:
    return datetime.now(tz=timezone.utc).date()


def _parse_month(month: str | None) -> date:
    if month:
        try:
            return datetime.strptime(month, "%Y-%m").date().replace(day=1)
        except ValueError:
            pass
    t = _today_utc()
    return date(t.year, t.month, 1)


def _shift_month(d: date, by: int) -> date:
    m = d.month + by
    y = d.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return date(y, m, 1)


def _month_grid(month_start: date) -> list[date]:
    """Return a 42-day grid (6 weeks) starting on Monday of the first row."""
    weekday = month_start.weekday()  # Monday=0
    grid_start = month_start - timedelta(days=weekday)
    return [grid_start + timedelta(days=i) for i in range(42)]


def _week_grid(start: date) -> list[date]:
    monday = start - timedelta(days=start.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def _due_date(task: dict[str, Any]) -> date | None:
    s = task.get("due_date")
    if not s:
        return None
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _tasks_for(grid: list[date]) -> dict[date, list[dict[str, Any]]]:
    bucket: dict[date, list[dict[str, Any]]] = {d: [] for d in grid}
    for t in db.rows("tasks"):
        d = _due_date(t)
        if d is None or d not in bucket:
            continue
        bucket[d].append(t)
    for d in bucket:
        bucket[d].sort(key=lambda t: t.get("title", ""))
    return bucket


def _truncate(s: str, n: int = 24) -> str:
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


# --- pages -----------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    month: str | None = None,
    view: str = "month",
    start: str | None = None,
):
    today = _today_utc()
    if view == "week":
        try:
            week_anchor = date.fromisoformat(start) if start else today
        except ValueError:
            week_anchor = today
        grid = _week_grid(week_anchor)
        bucket = _tasks_for(grid)
        return TEMPLATES.TemplateResponse(
            request,
            "calendar/week.html",
            {
                "today": today,
                "grid": grid,
                "bucket": bucket,
                "status_color": _STATUS_COLOR,
                "truncate": _truncate,
            },
        )

    month_start = _parse_month(month)
    grid = _month_grid(month_start)
    bucket = _tasks_for(grid)
    return TEMPLATES.TemplateResponse(
        request,
        "calendar/month.html",
        {
            "today": today,
            "month_start": month_start,
            "month_label": f"{_MONTH_NAMES[month_start.month-1]} {month_start.year}",
            "prev_month": _shift_month(month_start, -1).strftime("%Y-%m"),
            "next_month": _shift_month(month_start, 1).strftime("%Y-%m"),
            "grid": grid,
            "bucket": bucket,
            "status_color": _STATUS_COLOR,
            "truncate": _truncate,
        },
    )


@router.get("/fragments/grid", response_class=HTMLResponse)
async def grid_fragment(
    request: Request,
    month: str | None = None,
    view: str = "month",
    start: str | None = None,
):
    today = _today_utc()
    if view == "week":
        try:
            week_anchor = date.fromisoformat(start) if start else today
        except ValueError:
            week_anchor = today
        grid = _week_grid(week_anchor)
        bucket = _tasks_for(grid)
        return TEMPLATES.TemplateResponse(
            request,
            "calendar/_grid_week.html",
            {
                "today": today,
                "grid": grid,
                "bucket": bucket,
                "status_color": _STATUS_COLOR,
                "truncate": _truncate,
            },
        )
    month_start = _parse_month(month)
    grid = _month_grid(month_start)
    bucket = _tasks_for(grid)
    return TEMPLATES.TemplateResponse(
        request,
        "calendar/_grid.html",
        {
            "today": today,
            "month_start": month_start,
            "grid": grid,
            "bucket": bucket,
            "status_color": _STATUS_COLOR,
            "truncate": _truncate,
        },
    )


@router.get("/tasks")
async def calendar_tasks_json(month: str):
    month_start = _parse_month(month)
    end = _shift_month(month_start, 1)
    out = []
    for t in db.rows("tasks"):
        d = _due_date(t)
        if d is None or not (month_start <= d < end):
            continue
        out.append(
            {
                "id": t["id"],
                "title": t.get("title"),
                "status": t.get("status"),
                "due_date": d.isoformat(),
            }
        )
    out.sort(key=lambda r: (r["due_date"], r["title"]))
    return JSONResponse({"month": month_start.strftime("%Y-%m"), "tasks": out})
