"""Tests for /tasks (web.routes.tasks).

Covers the integration nexus — instantiation, step actions, auto-queue
on human-step completion, kanban bucketing, filters, status derivation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def db_in_tmp(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path / "db")
    db.init_db()
    return db


@pytest.fixture
def repo_in_tmp(monkeypatch, tmp_path):
    from web import bundles

    monkeypatch.setattr(bundles, "REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def client(db_in_tmp, repo_in_tmp):
    from web.routes import tasks as tasks_routes

    app = FastAPI()
    app.include_router(tasks_routes.router)
    return TestClient(app)


def _now() -> str:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc).isoformat()


def _step(*, id, owner_role="fpa", kind="ai", depends_on=None, default_assignee_id="forge"):
    return {
        "id": id,
        "name": id,
        "instructions_md": "",
        "owner_role": owner_role,
        "default_assignee_id": default_assignee_id,
        "kind": kind,
        "depends_on": depends_on or [],
        "est_minutes": None,
        "requires_access": [],
        "inputs": [],
        "outputs": [],
        "ai_capability_hint": owner_role,
        "checkpoint": False,
    }


def _seed_sw_team(db, *, sw_steps, sw_id="sw1", owner_role="fpa"):
    db.insert(
        "team",
        {
            "id": "forge",
            "name": "Forge",
            "email": None,
            "kind": "ai",
            "role_tags": ["fpa", "controller"],
            "active": True,
            "created_at": _now(),
        },
    )
    db.insert(
        "team",
        {
            "id": "alice",
            "name": "Alice",
            "email": None,
            "kind": "human",
            "role_tags": ["fpa"],
            "active": True,
            "created_at": _now(),
        },
    )
    db.insert(
        "standard_work",
        {
            "id": sw_id,
            "name": "Test SW",
            "source_task_type": None,
            "owner_role": owner_role,
            "cadence": None,
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": 0,
            "steps": sw_steps,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )


# --- list / kanban / filter ------------------------------------------------


def test_list_empty(client):
    r = client.get("/tasks")
    assert r.status_code == 200
    assert "No tasks" in r.text or "kanban" in r.text.lower() or "Tasks" in r.text


def test_kanban_buckets_tasks(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t1 = instantiate.instantiate_task("sw1", period="A")
    t2 = instantiate.instantiate_task("sw1", period="B")
    db_in_tmp.update("tasks", t1["id"], {"status": "in_progress"})
    db_in_tmp.update("tasks", t2["id"], {"status": "complete"})

    r = client.get("/tasks?view=kanban")
    assert r.status_code == 200
    # Both tasks should appear in their columns.
    assert t1["title"] in r.text
    assert t2["title"] in r.text


def test_list_filter_by_assignee(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.get(f"/tasks?view=list&assignee={t['owner_id']}")
    assert r.status_code == 200
    assert t["title"] in r.text

    r2 = client.get("/tasks?view=list&assignee=nobody")
    assert "No tasks" in r2.text or t["title"] not in r2.text


def test_list_fragment(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    instantiate.instantiate_task("sw1", period="X")
    r = client.get("/tasks/fragments/list")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" not in r.text


# --- new --------------------------------------------------------------------


def test_new_task_form(client, db_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[])
    r = client.get("/tasks/new")
    assert r.status_code == 200
    assert "Standard work template" in r.text


def test_new_task_submit(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    r = client.post(
        "/tasks/new",
        data={"standard_work_id": "sw1", "period": "2026-05"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/tasks/t-sw1-2026-05")
    assert len(db_in_tmp.rows("tasks")) == 1


def test_new_task_rejects_unknown_sw(client, db_in_tmp):
    r = client.post(
        "/tasks/new",
        data={"standard_work_id": "ghost"},
        follow_redirects=False,
    )
    assert r.status_code == 400


# --- detail -----------------------------------------------------------------


def test_detail_renders_steps(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(
        db_in_tmp,
        sw_steps=[
            _step(id="s1", kind="human"),
            _step(id="s2", kind="ai", depends_on=["s1"]),
        ],
    )
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.get(f"/tasks/{t['id']}")
    assert r.status_code == 200
    assert "s1" in r.text
    assert "s2" in r.text


def test_detail_404_unknown(client):
    r = client.get("/tasks/ghost")
    assert r.status_code == 404


# --- step actions -----------------------------------------------------------


def test_start_human_step(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.post(
        f"/tasks/{t['id']}/steps/s1/start", follow_redirects=False
    )
    assert r.status_code == 303
    inst = next(s for s in db_in_tmp.find("tasks", t["id"])["steps"] if s["step_id"] == "s1")
    assert inst["status"] == "in_progress"
    assert inst["started_at"]


def test_start_step_refused_when_deps_unmet(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(
        db_in_tmp,
        sw_steps=[
            _step(id="s1", kind="human"),
            _step(id="s2", kind="human", depends_on=["s1"]),
        ],
    )
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.post(f"/tasks/{t['id']}/steps/s2/start", follow_redirects=False)
    assert r.status_code == 409
    assert "unmet dependency" in r.json()["detail"]


def test_complete_human_step_auto_queues_ai_successor(
    client, db_in_tmp, repo_in_tmp
):
    _seed_sw_team(
        db_in_tmp,
        sw_steps=[
            _step(id="s1", kind="human"),
            _step(id="s2", kind="ai", depends_on=["s1"]),
        ],
    )
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    client.post(f"/tasks/{t['id']}/steps/s1/start", follow_redirects=False)

    r = client.post(
        f"/tasks/{t['id']}/steps/s1/complete",
        data={"deliverable": "tasks/" + t["id"] + "/artifacts/s1/out.md"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    queue_rows = db_in_tmp.rows("queue")
    assert len(queue_rows) == 1
    assert queue_rows[0]["task_id"] == t["id"]
    assert queue_rows[0]["step_id"] == "s2"


def test_complete_does_not_double_queue(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(
        db_in_tmp,
        sw_steps=[
            _step(id="s1", kind="human"),
            _step(id="s2", kind="ai", depends_on=["s1"]),
        ],
    )
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    client.post(f"/tasks/{t['id']}/steps/s1/start", follow_redirects=False)
    client.post(
        f"/tasks/{t['id']}/steps/s1/complete",
        data={"deliverable": "tasks/" + t["id"] + "/artifacts/s1/x.md"},
        follow_redirects=False,
    )
    # Imagine the user then completes s2 manually (impossible via the AI
    # path here, but we test the helper's idempotence by trying to
    # re-queue.)
    r = client.post(f"/tasks/{t['id']}/steps/s2/queue", follow_redirects=False)
    assert r.status_code == 409  # already queued


def test_manual_queue_only_for_ai(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.post(f"/tasks/{t['id']}/steps/s1/queue", follow_redirects=False)
    assert r.status_code == 400


def test_manual_queue_for_ai_with_deps_met(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="ai")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.post(f"/tasks/{t['id']}/steps/s1/queue", follow_redirects=False)
    assert r.status_code == 303
    assert len(db_in_tmp.rows("queue")) == 1


def test_status_recomputes_to_complete_when_all_done(
    client, db_in_tmp, repo_in_tmp
):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    client.post(f"/tasks/{t['id']}/steps/s1/start", follow_redirects=False)
    client.post(
        f"/tasks/{t['id']}/steps/s1/complete",
        data={"deliverable": ""},
        follow_redirects=False,
    )
    assert db_in_tmp.find("tasks", t["id"])["status"] == "complete"
    assert db_in_tmp.find("tasks", t["id"])["completed_at"]


def test_comment_appended(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.post(
        f"/tasks/{t['id']}/steps/s1/comment",
        data={"author_id": "alice", "body_md": "looks good"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    inst = next(s for s in db_in_tmp.find("tasks", t["id"])["steps"] if s["step_id"] == "s1")
    assert len(inst["comments"]) == 1
    assert inst["comments"][0]["body_md"] == "looks good"


def test_abort_task(client, db_in_tmp, repo_in_tmp):
    _seed_sw_team(db_in_tmp, sw_steps=[_step(id="s1", kind="human")])
    from web import instantiate

    t = instantiate.instantiate_task("sw1", period="X")
    r = client.post(f"/tasks/{t['id']}/abort", follow_redirects=False)
    assert r.status_code == 303
    assert db_in_tmp.find("tasks", t["id"])["status"] == "aborted"


# --- helpers ----------------------------------------------------------------


def test_derive_task_status_all_states():
    from web.tasks_helpers import derive_task_status

    assert derive_task_status([]) == "draft"
    assert derive_task_status([{"status": "pending"}, {"status": "pending"}]) == "draft"
    assert derive_task_status([{"status": "in_progress"}, {"status": "pending"}]) == "in_progress"
    assert derive_task_status([{"status": "failed"}, {"status": "pending"}]) == "blocked"
    assert derive_task_status([{"status": "complete"}, {"status": "complete"}]) == "complete"
