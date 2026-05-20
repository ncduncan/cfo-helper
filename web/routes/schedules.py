"""Cron-driven Task instantiation — CRUD over ``db/schedules.json``."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from web import db, scheduler
from web.errors import safe_scheduler_reload
from web.ids import unique_id
from web.models import Schedule
from web.schedule_spec import build_cron, describe, parse_cron


router = APIRouter(prefix="/schedules")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _validate(row: dict[str, Any]) -> dict[str, Any]:
    return Schedule.model_validate(row).model_dump(mode="json")


def _sorted_list() -> list[dict[str, Any]]:
    rows = sorted(db.rows("schedules"), key=lambda r: r.get("name", "").lower())
    for r in rows:
        r["cadence_label"] = describe(
            r.get("cron", ""), r.get("timezone", "America/New_York")
        )
    return rows


def _sw_list() -> list[dict[str, Any]]:
    return sorted(db.rows("standard_work"), key=lambda r: r.get("name", ""))


# --- list ------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_sched(request: Request):
    return TEMPLATES.TemplateResponse(
        request,
        "schedules/list.html",
        {"items": _sorted_list(), "sw_list": _sw_list()},
    )


@router.get("/fragments/list", response_class=HTMLResponse)
async def list_fragment(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "schedules/_list_table.html", {"items": _sorted_list()}
    )


# --- create -----------------------------------------------------------------


def _spec_from_item(item: dict[str, Any] | None) -> dict[str, Any]:
    """Build the form-spec dict the edit template uses to prefill controls."""
    if not item:
        return {"frequency": "monthly", "hour": 9, "minute": 0, "day_of_month": 1}
    parsed = parse_cron(item.get("cron", ""))
    if parsed is None:
        return {"frequency": "custom", "hour": 9, "minute": 0}
    return parsed


def _resolve_cron(
    frequency: str,
    hour: str,
    minute: str,
    day_of_week: str,
    day_of_month: str,
    month: str,
    cron_raw: str,
) -> str:
    spec = {
        "frequency": frequency,
        "hour": hour,
        "minute": minute,
        "day_of_week": day_of_week,
        "day_of_month": day_of_month,
        "month": month,
        "cron": cron_raw,
    }
    built = build_cron(spec).strip()
    if not built:
        raise HTTPException(
            status_code=400,
            detail="A cron expression is required (use Advanced mode if frequency is Custom).",
        )
    return built


@router.get("/new", response_class=HTMLResponse)
async def new_form(request: Request):
    return TEMPLATES.TemplateResponse(
        request,
        "schedules/edit.html",
        {
            "item": None,
            "is_new": True,
            "sw_list": _sw_list(),
            "spec": _spec_from_item(None),
        },
    )


@router.post("")
async def create(
    request: Request,
    name: str = Form(...),
    standard_work_id: str = Form(...),
    frequency: str = Form("monthly"),
    hour: str = Form("9"),
    minute: str = Form("0"),
    day_of_week: str = Form("1"),
    day_of_month: str = Form("1"),
    month: str = Form("1"),
    cron_raw: str = Form(""),
    timezone: str = Form("America/New_York"),
    enabled: str = Form(""),
    period_template: str = Form(""),
):
    cron = _resolve_cron(
        frequency, hour, minute, day_of_week, day_of_month, month, cron_raw
    )
    clean_name = name.strip()
    row = {
        "id": unique_id(
            clean_name,
            (r["id"] for r in db.rows("schedules")),
            fallback="schedule",
        ),
        "name": clean_name,
        "standard_work_id": standard_work_id.strip(),
        "cron": cron,
        "timezone": timezone.strip() or "America/New_York",
        "enabled": bool(enabled),
        "brief_template": (
            {"period": period_template.strip()} if period_template.strip() else {}
        ),
        "created_at": _now_iso(),
    }
    try:
        row = _validate(row)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    db.insert("schedules", row)
    safe_scheduler_reload()
    return RedirectResponse(url="/schedules", status_code=303)


# --- edit ------------------------------------------------------------------


@router.get("/{sid}/edit", response_class=HTMLResponse)
async def edit_form(request: Request, sid: str):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    return TEMPLATES.TemplateResponse(
        request,
        "schedules/edit.html",
        {
            "item": s,
            "is_new": False,
            "sw_list": _sw_list(),
            "spec": _spec_from_item(s),
        },
    )


@router.post("/{sid}")
async def update(
    request: Request,
    sid: str,
    name: str = Form(...),
    standard_work_id: str = Form(...),
    frequency: str = Form("monthly"),
    hour: str = Form("9"),
    minute: str = Form("0"),
    day_of_week: str = Form("1"),
    day_of_month: str = Form("1"),
    month: str = Form("1"),
    cron_raw: str = Form(""),
    timezone: str = Form("America/New_York"),
    enabled: str = Form(""),
    period_template: str = Form(""),
):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    cron = _resolve_cron(
        frequency, hour, minute, day_of_week, day_of_month, month, cron_raw
    )
    new = {
        **s,
        "name": name.strip(),
        "standard_work_id": standard_work_id.strip(),
        "cron": cron,
        "timezone": timezone.strip() or "America/New_York",
        "enabled": bool(enabled),
        "brief_template": (
            {"period": period_template.strip()} if period_template.strip() else {}
        ),
    }
    try:
        new = _validate(new)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    db.upsert("schedules", new)
    safe_scheduler_reload()
    return RedirectResponse(url="/schedules", status_code=303)


@router.post("/{sid}/toggle-enabled")
async def toggle_enabled(sid: str):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    new = {**s, "enabled": not s.get("enabled", True)}
    _validate(new)
    db.upsert("schedules", new)
    safe_scheduler_reload()
    return RedirectResponse(url="/schedules", status_code=303)


@router.post("/{sid}/delete")
async def delete(sid: str):
    if not db.delete("schedules", sid):
        raise HTTPException(status_code=404, detail="schedule not found")
    safe_scheduler_reload()
    return RedirectResponse(url="/schedules", status_code=303)


@router.post("/{sid}/run-now")
async def run_now(sid: str):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    scheduler.run_now(sid)
    return RedirectResponse(url="/schedules", status_code=303)
