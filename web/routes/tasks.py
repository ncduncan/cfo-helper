"""Tasks — kanban, list, detail, and per-step action handlers.

This is the integration nexus for the dashboard. Completing a human step
calls ``tasks_helpers.maybe_queue_successors`` which enqueues any AI
successor whose dependencies are now satisfied, so Forge's queue stays in
sync with the step graph without a manual nudge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any  # noqa: F401  (used by mutator closures)

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from web import audit, bundles, db, instantiate, tasks_helpers


router = APIRouter(prefix="/tasks")

TEMPLATES = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


_KANBAN_COLUMNS = ["draft", "in_progress", "blocked", "complete"]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _bucket_tasks(tasks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {c: [] for c in _KANBAN_COLUMNS}
    for t in tasks:
        status = t.get("status", "draft")
        if status == "aborted":
            continue
        out.setdefault(status, []).append(t)
    for col in out:
        out[col].sort(key=lambda r: r.get("due_date") or "")
    return out


def _filter_tasks(
    tasks: list[dict[str, Any]],
    *,
    assignee: str | None = None,
    standard_work_id: str | None = None,
) -> list[dict[str, Any]]:
    out = tasks
    if assignee:
        out = [
            t
            for t in out
            if t.get("owner_id") == assignee
            or any(s.get("assignee_id") == assignee for s in t.get("steps") or [])
        ]
    if standard_work_id:
        out = [t for t in out if t.get("standard_work_id") == standard_work_id]
    return out


def _enrich_with_lookup(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tack on owner_name + sw_name for template display."""
    team = {m["id"]: m for m in db.rows("team")}
    sw = {s["id"]: s for s in db.rows("standard_work")}
    out = []
    for t in tasks:
        c = dict(t)
        owner = team.get(t.get("owner_id") or "")
        c["owner_name"] = (owner or {}).get("name") or t.get("owner_id") or "—"
        s = sw.get(t.get("standard_work_id") or "")
        c["sw_name"] = (s or {}).get("name") or t.get("standard_work_id") or "—"
        c["step_count"] = len(t.get("steps") or [])
        c["steps_complete"] = sum(
            1 for st in (t.get("steps") or []) if st.get("status") == "complete"
        )
        out.append(c)
    return out


def _task_or_404(task_id: str) -> dict[str, Any]:
    task = db.find("tasks", task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


def _sw_step(sw: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    for s in sw.get("steps") or []:
        if s.get("id") == step_id:
            return s
    return None


# --- list / kanban ---------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_tasks(
    request: Request,
    view: str = "kanban",
    assignee: str | None = None,
    standard_work_id: str | None = None,
):
    tasks = _enrich_with_lookup(
        _filter_tasks(db.rows("tasks"), assignee=assignee, standard_work_id=standard_work_id)
    )
    team = sorted(db.rows("team"), key=lambda r: r.get("name", ""))
    sw_list = sorted(db.rows("standard_work"), key=lambda r: r.get("name", ""))
    return TEMPLATES.TemplateResponse(
        request,
        "tasks/list.html",
        {
            "view": view,
            "tasks": tasks,
            "buckets": _bucket_tasks(tasks),
            "kanban_columns": _KANBAN_COLUMNS,
            "team": team,
            "sw_list": sw_list,
            "filter_assignee": assignee or "",
            "filter_sw": standard_work_id or "",
        },
    )


@router.get("/fragments/kanban", response_class=HTMLResponse)
async def kanban_fragment(request: Request):
    tasks = _enrich_with_lookup(db.rows("tasks"))
    return TEMPLATES.TemplateResponse(
        request,
        "tasks/_kanban.html",
        {"buckets": _bucket_tasks(tasks), "kanban_columns": _KANBAN_COLUMNS},
    )


@router.get("/fragments/list", response_class=HTMLResponse)
async def list_fragment(
    request: Request,
    assignee: str | None = None,
    standard_work_id: str | None = None,
):
    tasks = _enrich_with_lookup(
        _filter_tasks(db.rows("tasks"), assignee=assignee, standard_work_id=standard_work_id)
    )
    return TEMPLATES.TemplateResponse(
        request, "tasks/_list_table.html", {"tasks": tasks}
    )


# --- new -------------------------------------------------------------------


@router.get("/new", response_class=HTMLResponse)
async def new_task_form(request: Request):
    sw_list = sorted(db.rows("standard_work"), key=lambda r: r.get("name", ""))
    team = sorted(
        (r for r in db.rows("team") if r.get("active", True)),
        key=lambda r: r.get("name", ""),
    )
    return TEMPLATES.TemplateResponse(
        request,
        "tasks/new.html",
        {"sw_list": sw_list, "team": team},
    )


@router.post("/new")
async def new_task_submit(
    request: Request,
    standard_work_id: str = Form(...),
    period: str = Form(""),
    title: str = Form(""),
    owner_id: str = Form(""),
    due_date: str = Form(""),
):
    sw = db.find("standard_work", standard_work_id)
    if sw is None:
        raise HTTPException(status_code=400, detail="standard_work_id not found")
    due: datetime | None = None
    if due_date.strip():
        try:
            due = datetime.fromisoformat(due_date)
            if due.tzinfo is None:
                due = due.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="due_date not ISO format")
    try:
        t = instantiate.instantiate_task(
            standard_work_id,
            period=period.strip() or None,
            title=title.strip() or None,
            owner_id=owner_id.strip() or None,
            due_date=due,
            source="manual",
        )
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(url=f"/tasks/{t['id']}", status_code=303)


# --- detail ----------------------------------------------------------------


@router.get("/{task_id}", response_class=HTMLResponse)
async def task_detail(request: Request, task_id: str):
    task = _task_or_404(task_id)
    sw = db.find("standard_work", task.get("standard_work_id") or "")
    team = {m["id"]: m for m in db.rows("team")}
    queue_by_step: dict[str, dict[str, Any]] = {}
    for r in db.rows("queue"):
        if r.get("task_id") != task_id:
            continue
        if r.get("status") in ("pending", "claimed"):
            queue_by_step[r["step_id"]] = r

    # Build a render-friendly list joining instance + sw step.
    rendered_steps: list[dict[str, Any]] = []
    sw_steps = {s["id"]: s for s in (sw or {}).get("steps") or []}
    instance_index = {s["step_id"]: s for s in task.get("steps") or []}
    for inst in task.get("steps") or []:
        sw_s = sw_steps.get(inst["step_id"]) or {}
        deps = sw_s.get("depends_on") or []
        deps_met = all(
            (instance_index.get(d) or {}).get("status") == "complete" for d in deps
        )
        rendered_steps.append(
            {
                "step_id": inst["step_id"],
                "name": sw_s.get("name") or inst["step_id"],
                "kind": sw_s.get("kind") or "human",
                "owner_role": sw_s.get("owner_role") or "—",
                "checkpoint": sw_s.get("checkpoint", False),
                "instructions_md": sw_s.get("instructions_md") or "",
                "depends_on": deps,
                "depends_met": deps_met,
                "ai_capability_hint": sw_s.get("ai_capability_hint"),
                "instance": inst,
                "assignee": team.get(inst.get("assignee_id") or ""),
                "live_queue_row": queue_by_step.get(inst["step_id"]),
            }
        )

    owner = team.get(task.get("owner_id") or "")
    return TEMPLATES.TemplateResponse(
        request,
        "tasks/detail.html",
        {
            "task": task,
            "sw": sw,
            "owner": owner,
            "steps": rendered_steps,
            "team": sorted(team.values(), key=lambda r: r.get("name", "")),
        },
    )


# --- step mutations --------------------------------------------------------


def _mutate_step(
    task_id: str, step_id: str, mutator
) -> dict[str, Any]:
    def m(doc: dict[str, Any]) -> dict[str, Any]:
        for t in doc["rows"]:
            if t.get("id") != task_id:
                continue
            for s in t.get("steps") or []:
                if s.get("step_id") != step_id:
                    continue
                mutator(s)
        return doc

    db.write("tasks", m)
    return _task_or_404(task_id)


@router.post("/{task_id}/steps/{step_id}/start")
async def start_step(task_id: str, step_id: str):
    task = _task_or_404(task_id)
    sw = db.find("standard_work", task.get("standard_work_id") or "")
    if sw is None:
        raise HTTPException(status_code=409, detail="standard_work missing")
    sw_step = _sw_step(sw, step_id)
    if sw_step is None:
        raise HTTPException(status_code=404, detail="step not found in template")
    inst = next((s for s in task.get("steps") or [] if s["step_id"] == step_id), None)
    if inst is None:
        raise HTTPException(status_code=404, detail="step instance missing")
    if inst.get("status") != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"can only start pending steps (status={inst.get('status')!r})",
        )
    inst_lookup = {s["step_id"]: s for s in task.get("steps") or []}
    for dep in sw_step.get("depends_on") or []:
        if (inst_lookup.get(dep) or {}).get("status") != "complete":
            raise HTTPException(
                status_code=409,
                detail=f"unmet dependency: step {dep!r} is not complete",
            )

    now = _now_iso()

    def upd(s: dict[str, Any]) -> None:
        s["status"] = "in_progress"
        s["started_at"] = now

    _mutate_step(task_id, step_id, upd)
    if task.get("started_at") is None:
        db.update("tasks", task_id, {"started_at": now})
    tasks_helpers.recompute_task_status(task_id)
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/steps/{step_id}/complete")
async def complete_step(
    task_id: str,
    step_id: str,
    deliverable: list[str] = Form(default=[]),
):
    task = _task_or_404(task_id)
    inst = next((s for s in task.get("steps") or [] if s["step_id"] == step_id), None)
    if inst is None:
        raise HTTPException(status_code=404, detail="step instance missing")
    if inst.get("status") not in ("pending", "in_progress"):
        raise HTTPException(
            status_code=409,
            detail=f"cannot complete from status {inst.get('status')!r}",
        )

    paths = [p.strip() for p in deliverable if p.strip()]
    # Merge already-attached paths so the audit sees the full set.
    merged_paths = list(inst.get("deliverable_paths") or [])
    for p in paths:
        if p not in merged_paths:
            merged_paths.append(p)

    # Claim-id audit for numeric-role AI steps.
    sw = db.find("standard_work", task.get("standard_work_id") or "")
    sw_step = _sw_step(sw or {}, step_id)
    role_hint = (sw_step or {}).get("ai_capability_hint")
    is_ai_numeric = (
        (sw_step or {}).get("kind") == "ai"
        and role_hint in audit.NUMERIC_ROLES
    )
    if is_ai_numeric:
        result = audit.audit_claim_ids(merged_paths, bundles.REPO_ROOT, required=True)
        if not result["ok"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "claim-id audit refused completion",
                    "issues": result["issues"],
                },
            )

    # Persist deliverables + flip step state.
    now = _now_iso()

    def upd(s: dict[str, Any]) -> None:
        s["status"] = "complete"
        s["completed_at"] = now
        existing = list(s.get("deliverable_paths") or [])
        for p in paths:
            if p not in existing:
                existing.append(p)
        s["deliverable_paths"] = existing
        findings = audit.extract_findings(merged_paths, bundles.REPO_ROOT)
        if findings is not None:
            for p in merged_paths:
                if p.endswith("findings.json"):
                    s["findings_ref"] = p
                    break
        lean_recs = audit.extract_lean_recommendations(merged_paths, bundles.REPO_ROOT)
        if lean_recs is not None:
            for p in merged_paths:
                if p.endswith("kaizen_recommendations.json"):
                    s["lean_recommendations_ref"] = p
                    break

    _mutate_step(task_id, step_id, upd)

    # Stage any memory_write requests as proposals (CLAUDE.md §8 rule 4).
    proposals = audit.extract_memory_writes(merged_paths, bundles.REPO_ROOT)
    for i, req in enumerate(proposals):
        pid = f"mp-{task_id}-{step_id}-{int(datetime.now(tz=timezone.utc).timestamp()*1000)}-{i}"
        db.insert(
            "memory_proposals",
            {
                "id": pid,
                "task_id": task_id,
                "step_id": step_id,
                "target_path": req.get("target_path") or req.get("path") or "",
                "operation": req.get("operation") or req.get("op") or "append",
                "payload": req.get("payload") or req.get("content") or "",
                "rationale": req.get("rationale") or "",
                "status": "pending",
                "staged_at": now,
                "resolved_at": None,
            },
        )

    tasks_helpers.maybe_queue_successors(task_id)
    new_status = tasks_helpers.recompute_task_status(task_id)
    if new_status == "complete" and not (db.find("tasks", task_id) or {}).get("completed_at"):
        db.update("tasks", task_id, {"completed_at": now})
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/steps/{step_id}/queue")
async def manual_queue_step(task_id: str, step_id: str):
    task = _task_or_404(task_id)
    sw = db.find("standard_work", task.get("standard_work_id") or "")
    sw_step = _sw_step(sw or {}, step_id)
    if sw_step is None or sw_step.get("kind") != "ai":
        raise HTTPException(
            status_code=400, detail="can only queue AI-kind steps"
        )
    inst = next((s for s in task.get("steps") or [] if s["step_id"] == step_id), None)
    if inst is None or inst.get("status") != "pending":
        raise HTTPException(
            status_code=409, detail="step must be pending to queue"
        )
    inst_lookup = {s["step_id"]: s for s in task.get("steps") or []}
    for dep in sw_step.get("depends_on") or []:
        if (inst_lookup.get(dep) or {}).get("status") != "complete":
            raise HTTPException(
                status_code=409,
                detail=f"unmet dependency: {dep!r} not complete",
            )
    live = {"pending", "claimed", "done"}
    for r in db.rows("queue"):
        if r.get("task_id") == task_id and r.get("step_id") == step_id and r.get("status") in live:
            raise HTTPException(
                status_code=409,
                detail=f"step already has a live queue row ({r.get('status')})",
            )
    bundles.build_and_queue(task_id, step_id)
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/steps/{step_id}/comment")
async def comment_step(
    task_id: str,
    step_id: str,
    author_id: str = Form(...),
    body_md: str = Form(...),
):
    now = _now_iso()

    def upd(s: dict[str, Any]) -> None:
        comments = list(s.get("comments") or [])
        comments.append({"author_id": author_id, "body_md": body_md, "at": now})
        s["comments"] = comments

    _mutate_step(task_id, step_id, upd)
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/abort")
async def abort_task(task_id: str):
    _task_or_404(task_id)
    db.update("tasks", task_id, {"status": "aborted", "completed_at": _now_iso()})
    return RedirectResponse(url=f"/tasks/{task_id}", status_code=303)
