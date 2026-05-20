"""Team directory — CRUD over ``db/team.json``.

Forge (``id="forge"``) is the named AI member. Two protections enforced:
- ``kind`` is immutable post-creation (the edit form omits the field and
  the handler ignores any posted kind).
- ``DELETE`` rejects ``forge`` with 409 — Forge is a structural row, not a
  garden-variety member.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from web import db
from web.models import TeamMember


router = APIRouter(prefix="/team")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)

FORGE_ID = "forge"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _validate(row: dict) -> dict:
    return TeamMember.model_validate(row).model_dump(mode="json")


def _members_sorted() -> list[dict]:
    return sorted(
        db.rows("team"),
        key=lambda r: (r.get("id") != FORGE_ID, (r.get("name") or "").lower()),
    )


# --- list ------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_team(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "team/list.html", {"members": _members_sorted()}
    )


@router.get("/fragments/list", response_class=HTMLResponse)
async def list_team_fragment(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "team/_list_table.html", {"members": _members_sorted()}
    )


# --- create ----------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
async def new_team_form(request: Request):
    return TEMPLATES.TemplateResponse(
        request, "team/edit.html", {"member": None, "is_new": True}
    )


@router.post("", response_class=HTMLResponse)
async def create_team_member(
    request: Request,
    id: str = Form(...),
    name: str = Form(...),
    kind: str = Form(...),
    email: str = Form(""),
    role_tags: str = Form(""),
):
    row = {
        "id": id.strip(),
        "name": name.strip(),
        "email": email.strip() or None,
        "kind": kind,
        "role_tags": [t.strip() for t in role_tags.split(",") if t.strip()],
        "active": True,
        "created_at": _now_iso(),
    }
    try:
        row = _validate(row)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    try:
        db.insert("team", row)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return RedirectResponse(url=f"/team/{row['id']}", status_code=303)


# --- detail / edit ---------------------------------------------------------


@router.get("/{member_id}", response_class=HTMLResponse)
async def member_detail(request: Request, member_id: str):
    member = db.find("team", member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    return TEMPLATES.TemplateResponse(
        request, "team/detail.html", {"member": member}
    )


@router.get("/{member_id}/edit", response_class=HTMLResponse)
async def edit_team_form(request: Request, member_id: str):
    member = db.find("team", member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    return TEMPLATES.TemplateResponse(
        request,
        "team/edit.html",
        {"member": member, "is_new": False, "is_forge": member_id == FORGE_ID},
    )


@router.post("/{member_id}", response_class=HTMLResponse)
async def update_team_member(
    request: Request,
    member_id: str,
    name: str = Form(...),
    email: str = Form(""),
    role_tags: str = Form(""),
    kind: str = Form(None),
):
    member = db.find("team", member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    # kind is immutable. If a non-Forge edit posts it, just ignore the value
    # and keep the stored one (we never trust client-side).
    new_row = {
        **member,
        "name": name.strip(),
        "email": email.strip() or None,
        "role_tags": [t.strip() for t in role_tags.split(",") if t.strip()],
    }
    try:
        new_row = _validate(new_row)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors())
    db.upsert("team", new_row)
    return RedirectResponse(url=f"/team/{member_id}", status_code=303)


# --- mutations -------------------------------------------------------------


@router.post("/{member_id}/toggle-active")
async def toggle_active(member_id: str):
    member = db.find("team", member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="member not found")
    new = {**member, "active": not member.get("active", True)}
    _validate(new)
    db.upsert("team", new)
    return RedirectResponse(url="/team", status_code=303)


@router.post("/{member_id}/delete")
async def delete_team_member(member_id: str):
    if member_id == FORGE_ID:
        raise HTTPException(
            status_code=409, detail="forge is protected and cannot be deleted"
        )
    if not db.delete("team", member_id):
        raise HTTPException(status_code=404, detail="member not found")
    return RedirectResponse(url="/team", status_code=303)
