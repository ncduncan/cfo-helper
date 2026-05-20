"""Standard Work templates — CRUD + step graph editor.

Each StandardWork has an ordered list of steps. Steps form a DAG via
``depends_on``. Two structural invariants enforced server-side:

- **No cycles.** Saving a step's ``depends_on`` runs a Kahn topo-sort over
  the full graph; on cycle, the write is refused with 409.
- **No orphan references.** ``depends_on`` IDs must exist in the same
  StandardWork.

Step deletions are refused if another step still depends on the target.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from web import db
from web.models import StandardWork, StandardWorkStep


router = APIRouter(prefix="/standard-work")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _validate_sw(row: dict[str, Any]) -> dict[str, Any]:
    return StandardWork.model_validate(row).model_dump(mode="json")


def _validate_step(row: dict[str, Any]) -> dict[str, Any]:
    return StandardWorkStep.model_validate(row).model_dump(mode="json")


def _sw_or_404(sw_id: str) -> dict[str, Any]:
    sw = db.find("standard_work", sw_id)
    if sw is None:
        raise HTTPException(status_code=404, detail="standard_work not found")
    return sw


def _topo_or_raise(steps: list[dict[str, Any]]) -> list[str]:
    """Kahn's algorithm. Raises HTTPException(409) on cycle or orphan dep."""
    ids = {s["id"] for s in steps}
    indeg: dict[str, int] = {s["id"]: 0 for s in steps}
    edges: dict[str, list[str]] = {s["id"]: [] for s in steps}
    for s in steps:
        for dep in s.get("depends_on") or []:
            if dep not in ids:
                raise HTTPException(
                    status_code=409,
                    detail=f"step {s['id']!r} depends on unknown step {dep!r}",
                )
            edges[dep].append(s["id"])
            indeg[s["id"]] += 1
    q = deque([sid for sid, d in indeg.items() if d == 0])
    order: list[str] = []
    while q:
        sid = q.popleft()
        order.append(sid)
        for nxt in edges[sid]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                q.append(nxt)
    if len(order) != len(steps):
        cycle = [sid for sid, d in indeg.items() if d > 0]
        raise HTTPException(
            status_code=409,
            detail=f"step graph has a cycle involving: {cycle}",
        )
    return order


def _sorted_list() -> list[dict[str, Any]]:
    return sorted(db.rows("standard_work"), key=lambda r: r.get("name", "").lower())


# --- list / create ---------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_sw(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "standard_work/list.html", {"items": _sorted_list()}
    )


@router.get("/fragments/list", response_class=HTMLResponse)
async def list_sw_fragment(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "standard_work/_list_table.html", {"items": _sorted_list()}
    )


@router.get("/new", response_class=HTMLResponse)
async def new_sw_form(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "standard_work/edit.html", {"item": None, "is_new": True}
    )


@router.post("", response_class=HTMLResponse)
async def create_sw(
    request: Request,
    id: str = Form(...),
    name: str = Form(...),
    owner_role: str = Form(...),
    cadence: str = Form(""),
    context_md: str = Form(""),
    requirements_md: str = Form(""),
    due_offset_days: int = Form(0),
):
    now = _now_iso()
    row = {
        "id": id.strip(),
        "name": name.strip(),
        "source_task_type": None,
        "owner_role": owner_role.strip(),
        "cadence": cadence.strip() or None,
        "context_md": context_md,
        "requirements_md": requirements_md,
        "due_offset_days": int(due_offset_days),
        "steps": [],
        "created_at": now,
        "updated_at": now,
    }
    try:
        row = _validate_sw(row)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    try:
        db.insert("standard_work", row)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(url=f"/standard-work/{row['id']}", status_code=303)


# --- detail / edit ---------------------------------------------------------


@router.get("/{sw_id}", response_class=HTMLResponse)
async def sw_detail(request: Request, sw_id: str):
    sw = _sw_or_404(sw_id)
    team = sorted(
        (r for r in db.rows("team") if r.get("active", True)),
        key=lambda r: r.get("name", ""),
    )
    return TEMPLATES.TemplateResponse(
        request, "standard_work/detail.html", {"item": sw, "team": team}
    )


@router.get("/{sw_id}/edit", response_class=HTMLResponse)
async def sw_edit_form(request: Request, sw_id: str):
    sw = _sw_or_404(sw_id)
    return TEMPLATES.TemplateResponse(
        request, "standard_work/edit.html", {"item": sw, "is_new": False}
    )


@router.post("/{sw_id}", response_class=HTMLResponse)
async def sw_save_header(
    request: Request,
    sw_id: str,
    name: str = Form(...),
    owner_role: str = Form(...),
    cadence: str = Form(""),
    context_md: str = Form(""),
    requirements_md: str = Form(""),
    due_offset_days: int = Form(0),
):
    sw = _sw_or_404(sw_id)
    new = {
        **sw,
        "name": name.strip(),
        "owner_role": owner_role.strip(),
        "cadence": cadence.strip() or None,
        "context_md": context_md,
        "requirements_md": requirements_md,
        "due_offset_days": int(due_offset_days),
        "updated_at": _now_iso(),
    }
    try:
        new = _validate_sw(new)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    db.upsert("standard_work", new)
    return RedirectResponse(url=f"/standard-work/{sw_id}", status_code=303)


@router.post("/{sw_id}/delete")
async def sw_delete(sw_id: str):
    if not db.delete("standard_work", sw_id):
        raise HTTPException(status_code=404, detail="standard_work not found")
    return RedirectResponse(url="/standard-work", status_code=303)


# --- step CRUD -------------------------------------------------------------


@router.get("/{sw_id}/steps/new", response_class=HTMLResponse)
async def new_step_form(request: Request, sw_id: str):
    sw = _sw_or_404(sw_id)
    team = sorted(
        (r for r in db.rows("team") if r.get("active", True)),
        key=lambda r: r.get("name", ""),
    )
    return TEMPLATES.TemplateResponse(
        request,
        "standard_work/step_edit.html",
        {"item": sw, "step": None, "is_new": True, "team": team},
    )


@router.post("/{sw_id}/steps")
async def create_step(
    request: Request,
    sw_id: str,
    id: str = Form(...),
    name: str = Form(...),
    owner_role: str = Form(...),
    kind: str = Form(...),
    instructions_md: str = Form(""),
    default_assignee_id: str = Form(""),
    ai_capability_hint: str = Form(""),
    depends_on: str = Form(""),
    est_minutes: str = Form(""),
    checkpoint: str = Form(""),
):
    sw = _sw_or_404(sw_id)
    new_step = {
        "id": id.strip(),
        "name": name.strip(),
        "instructions_md": instructions_md,
        "owner_role": owner_role.strip(),
        "default_assignee_id": default_assignee_id.strip() or None,
        "kind": kind,
        "depends_on": [d.strip() for d in depends_on.split(",") if d.strip()],
        "est_minutes": int(est_minutes) if est_minutes.strip() else None,
        "requires_access": [],
        "inputs": [],
        "outputs": [],
        "ai_capability_hint": ai_capability_hint.strip() or None,
        "checkpoint": bool(checkpoint),
    }
    try:
        new_step = _validate_step(new_step)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    if any(s["id"] == new_step["id"] for s in sw.get("steps") or []):
        raise HTTPException(
            status_code=409, detail=f"step id {new_step['id']!r} already exists"
        )
    new_steps = list(sw.get("steps") or []) + [new_step]
    _topo_or_raise(new_steps)
    db.upsert(
        "standard_work",
        {**sw, "steps": new_steps, "updated_at": _now_iso()},
    )
    return RedirectResponse(url=f"/standard-work/{sw_id}", status_code=303)


@router.get("/{sw_id}/steps/{step_id}/edit", response_class=HTMLResponse)
async def edit_step_form(request: Request, sw_id: str, step_id: str):
    sw = _sw_or_404(sw_id)
    step = next((s for s in sw.get("steps") or [] if s["id"] == step_id), None)
    if step is None:
        raise HTTPException(status_code=404, detail="step not found")
    team = sorted(
        (r for r in db.rows("team") if r.get("active", True)),
        key=lambda r: r.get("name", ""),
    )
    return TEMPLATES.TemplateResponse(
        request,
        "standard_work/step_edit.html",
        {"item": sw, "step": step, "is_new": False, "team": team},
    )


@router.post("/{sw_id}/steps/{step_id}")
async def update_step(
    request: Request,
    sw_id: str,
    step_id: str,
    name: str = Form(...),
    owner_role: str = Form(...),
    kind: str = Form(...),
    instructions_md: str = Form(""),
    default_assignee_id: str = Form(""),
    ai_capability_hint: str = Form(""),
    depends_on: str = Form(""),
    est_minutes: str = Form(""),
    checkpoint: str = Form(""),
):
    sw = _sw_or_404(sw_id)
    steps = list(sw.get("steps") or [])
    found_at = next((i for i, s in enumerate(steps) if s["id"] == step_id), -1)
    if found_at < 0:
        raise HTTPException(status_code=404, detail="step not found")
    updated = {
        **steps[found_at],
        "name": name.strip(),
        "instructions_md": instructions_md,
        "owner_role": owner_role.strip(),
        "default_assignee_id": default_assignee_id.strip() or None,
        "kind": kind,
        "depends_on": [d.strip() for d in depends_on.split(",") if d.strip()],
        "est_minutes": int(est_minutes) if est_minutes.strip() else None,
        "ai_capability_hint": ai_capability_hint.strip() or None,
        "checkpoint": bool(checkpoint),
    }
    try:
        updated = _validate_step(updated)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    steps[found_at] = updated
    _topo_or_raise(steps)
    db.upsert(
        "standard_work",
        {**sw, "steps": steps, "updated_at": _now_iso()},
    )
    return RedirectResponse(url=f"/standard-work/{sw_id}", status_code=303)


@router.post("/{sw_id}/steps/{step_id}/delete")
async def delete_step(sw_id: str, step_id: str):
    sw = _sw_or_404(sw_id)
    steps = list(sw.get("steps") or [])
    target = next((s for s in steps if s["id"] == step_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="step not found")
    dependents = [
        s["id"] for s in steps if step_id in (s.get("depends_on") or [])
    ]
    if dependents:
        raise HTTPException(
            status_code=409,
            detail=(
                f"cannot delete step {step_id!r}: "
                f"depended on by {dependents}"
            ),
        )
    steps = [s for s in steps if s["id"] != step_id]
    db.upsert(
        "standard_work",
        {**sw, "steps": steps, "updated_at": _now_iso()},
    )
    return RedirectResponse(url=f"/standard-work/{sw_id}", status_code=303)
