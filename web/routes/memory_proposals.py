"""Memory-write proposals — CFO approval queue (CLAUDE.md §8 rule 4).

When an AI step's ``work_product.json`` declares a ``memory_write`` request,
the dashboard stages it here for explicit approval. ``_derive_task_status``
treats the task as ``blocked`` if any proposal for it is still ``pending``,
so finalizing a task without addressing memory writes is impossible.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from web import db


router = APIRouter(prefix="/memory-proposals")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _enriched() -> list[dict[str, Any]]:
    tasks = {t["id"]: t for t in db.rows("tasks")}
    out = []
    for r in db.rows("memory_proposals"):
        c = dict(r)
        c["task_title"] = (tasks.get(r.get("task_id")) or {}).get("title") or r.get("task_id")
        out.append(c)
    out.sort(key=lambda r: (r.get("status") != "pending", r.get("staged_at") or ""))
    return out


@router.get("", response_class=HTMLResponse)
async def list_proposals(request: Request):
    return TEMPLATES.TemplateResponse(
        request,
        "memory_proposals/list.html",
        {"items": _enriched()},
    )


@router.post("/{proposal_id}/approve")
async def approve(proposal_id: str):
    p = db.find("memory_proposals", proposal_id)
    if p is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.get("status") != "pending":
        raise HTTPException(
            status_code=409, detail=f"status is {p.get('status')!r}"
        )
    db.update(
        "memory_proposals",
        proposal_id,
        {"status": "approved", "resolved_at": _now_iso()},
    )
    # After approval, recompute the parent task's status — it may unblock.
    from web import tasks_helpers

    try:
        tasks_helpers.recompute_task_status(p["task_id"])
    except KeyError:
        pass
    return RedirectResponse(url="/memory-proposals", status_code=303)


@router.post("/{proposal_id}/reject")
async def reject(proposal_id: str):
    p = db.find("memory_proposals", proposal_id)
    if p is None:
        raise HTTPException(status_code=404, detail="proposal not found")
    if p.get("status") != "pending":
        raise HTTPException(
            status_code=409, detail=f"status is {p.get('status')!r}"
        )
    db.update(
        "memory_proposals",
        proposal_id,
        {"status": "rejected", "resolved_at": _now_iso()},
    )
    from web import tasks_helpers

    try:
        tasks_helpers.recompute_task_status(p["task_id"])
    except KeyError:
        pass
    return RedirectResponse(url="/memory-proposals", status_code=303)
