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
from web.models import Schedule


router = APIRouter(prefix="/schedules")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _validate(row: dict[str, Any]) -> dict[str, Any]:
    return Schedule.model_validate(row).model_dump(mode="json")


def _sorted_list() -> list[dict[str, Any]]:
    return sorted(db.rows("schedules"), key=lambda r: r.get("name", "").lower())


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


@router.get("/new", response_class=HTMLResponse)
async def new_form(request: Request):
    return TEMPLATES.TemplateResponse(
        request,
        "schedules/edit.html",
        {"item": None, "is_new": True, "sw_list": _sw_list()},
    )


@router.post("")
async def create(
    request: Request,
    id: str = Form(...),
    name: str = Form(...),
    standard_work_id: str = Form(...),
    cron: str = Form(...),
    enabled: str = Form(""),
    period_template: str = Form(""),
):
    row = {
        "id": id.strip(),
        "name": name.strip(),
        "standard_work_id": standard_work_id.strip(),
        "cron": cron.strip(),
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
    try:
        db.insert("schedules", row)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    scheduler.reload()
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
        {"item": s, "is_new": False, "sw_list": _sw_list()},
    )


@router.post("/{sid}")
async def update(
    request: Request,
    sid: str,
    name: str = Form(...),
    standard_work_id: str = Form(...),
    cron: str = Form(...),
    enabled: str = Form(""),
    period_template: str = Form(""),
):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    new = {
        **s,
        "name": name.strip(),
        "standard_work_id": standard_work_id.strip(),
        "cron": cron.strip(),
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
    scheduler.reload()
    return RedirectResponse(url="/schedules", status_code=303)


@router.post("/{sid}/toggle-enabled")
async def toggle_enabled(sid: str):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    new = {**s, "enabled": not s.get("enabled", True)}
    _validate(new)
    db.upsert("schedules", new)
    scheduler.reload()
    return RedirectResponse(url="/schedules", status_code=303)


@router.post("/{sid}/delete")
async def delete(sid: str):
    if not db.delete("schedules", sid):
        raise HTTPException(status_code=404, detail="schedule not found")
    scheduler.reload()
    return RedirectResponse(url="/schedules", status_code=303)


@router.post("/{sid}/run-now")
async def run_now(sid: str):
    s = db.find("schedules", sid)
    if s is None:
        raise HTTPException(status_code=404, detail="schedule not found")
    scheduler.run_now(sid)
    return RedirectResponse(url="/schedules", status_code=303)
