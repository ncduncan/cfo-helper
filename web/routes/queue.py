"""Forge queue — consumer-side dashboard surface.

The queue collection is fed by M4 (auto-queue on step-complete via
``web.bundles.build_and_queue``) and drained by the operator in VS Code
via the ``/run-queue`` slash command (``scripts/run_queue.py``). This
module renders the operator-facing pages: pending list, completed
history, bundle viewer, and retry/cancel actions.

The table fragment auto-refreshes via the dashboard's SSE → HTMX bridge
(``db-changed:queue from:body``), so a queue claim from VS Code shows up
in the browser within ~1s of the JSON write.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from web import bundles, db
from web.models import QueueItem


router = APIRouter(prefix="/queue")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _split(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    active: list[dict[str, Any]] = []
    recent: list[dict[str, Any]] = []
    for r in items:
        status = r.get("status")
        if status in ("pending", "claimed"):
            active.append(r)
        elif status in ("done", "failed"):
            recent.append(r)
    active.sort(key=lambda r: r.get("queued_at") or "")
    recent.sort(key=lambda r: r.get("completed_at") or "", reverse=True)
    return {"active": active, "recent": recent[:20]}


def _enrich(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    task_index = {t["id"]: t for t in db.rows("tasks") if t.get("id")}
    sw_index = {s["id"]: s for s in db.rows("standard_work") if s.get("id")}
    out = []
    for r in rows:
        copy = dict(r)
        task = task_index.get(r.get("task_id"))
        copy["task_title"] = (task or {}).get("title") or r.get("task_id")
        step_name = None
        if task:
            sw = sw_index.get(task.get("standard_work_id"))
            if sw:
                for s in sw.get("steps") or []:
                    if s.get("id") == r.get("step_id"):
                        step_name = s.get("name")
                        break
        copy["step_name"] = step_name or r.get("step_id")
        out.append(copy)
    return out


def _validate_item_dict(row: dict[str, Any]) -> dict[str, Any]:
    return QueueItem.model_validate(row).model_dump(mode="json")


def _resolve_bundle_path(rel_path: str) -> Path:
    """Resolve a bundle path inside the repo, refusing escapes via ``..``."""
    repo = bundles.REPO_ROOT.resolve()
    candidate = (repo / rel_path).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError:
        raise HTTPException(status_code=400, detail="bundle path escapes repo")
    return candidate


# --- list -------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_queue(request: Request):
    buckets = _split(_enrich(db.rows("queue")))
    return TEMPLATES.TemplateResponse(
        request,
        "queue/list.html",
        {"buckets": buckets},
    )


@router.get("/fragments/list", response_class=HTMLResponse)
async def list_queue_fragment(request: Request):
    buckets = _split(_enrich(db.rows("queue")))
    return TEMPLATES.TemplateResponse(
        request,
        "queue/_list_table.html",
        {"buckets": buckets},
    )


# --- bundle viewer ----------------------------------------------------------


def _load_bundle(queue_id: str) -> tuple[dict[str, Any], str]:
    row = db.find("queue", queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="queue item not found")
    rel = row.get("bundle_path") or ""
    if not rel:
        raise HTTPException(status_code=404, detail="bundle path missing")
    abs_path = _resolve_bundle_path(rel)
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="bundle file missing on disk")
    return row, abs_path.read_text()


@router.get("/{queue_id}", response_class=HTMLResponse)
async def view_bundle(request: Request, queue_id: str):
    row, content = _load_bundle(queue_id)
    return TEMPLATES.TemplateResponse(
        request,
        "queue/bundle.html",
        {
            "queue_id": queue_id,
            "task_id": row.get("task_id"),
            "step_id": row.get("step_id"),
            "content": content,
        },
    )


@router.get("/{queue_id}/bundle")
async def serve_bundle(queue_id: str):
    _row, content = _load_bundle(queue_id)
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
    )


# --- mutations --------------------------------------------------------------


@router.post("/{queue_id}/retry")
async def retry(queue_id: str):
    row = db.find("queue", queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="queue item not found")
    if row.get("status") != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"can only retry failed items (status={row.get('status')!r})",
        )
    try:
        new_hash = bundles.compute_upstream_hash(row["task_id"], row["step_id"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail=f"cannot recompute upstream hash: {exc}",
        )

    patch: dict[str, Any] = {
        "status": "pending",
        "claimed_at": None,
        "completed_at": None,
        "error": None,
        "upstream_hash": new_hash,
    }
    _validate_item_dict({**row, **patch})
    db.update("queue", queue_id, patch)
    return RedirectResponse(url="/queue", status_code=303)


@router.post("/{queue_id}/cancel")
async def cancel(queue_id: str):
    row = db.find("queue", queue_id)
    if row is None:
        raise HTTPException(status_code=404, detail="queue item not found")
    if row.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"can only cancel pending items (status={row.get('status')!r})",
        )
    patch = {
        "status": "failed",
        "completed_at": _now_iso(),
        "error": "cancelled by user",
    }
    _validate_item_dict({**row, **patch})
    db.update("queue", queue_id, patch)
    return RedirectResponse(url="/queue", status_code=303)
