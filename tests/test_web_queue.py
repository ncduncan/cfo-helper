"""Tests for /queue (web.routes.queue)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

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
    from web.routes import queue as queue_routes

    app = FastAPI()
    app.include_router(queue_routes.router)
    return TestClient(app)


def _now_iso() -> str:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc).isoformat()


def _seed(db_in_tmp, repo: Path) -> str:
    db_in_tmp.insert(
        "standard_work",
        {
            "id": "sw-q",
            "name": "Queue SW",
            "source_task_type": None,
            "owner_role": "fpa",
            "cadence": None,
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": 0,
            "steps": [
                {
                    "id": "s1",
                    "name": "Up",
                    "instructions_md": "",
                    "owner_role": "fpa",
                    "default_assignee_id": "fpa_analyst",
                    "kind": "human",
                    "depends_on": [],
                    "est_minutes": None,
                    "requires_access": [],
                    "inputs": [],
                    "outputs": [],
                    "ai_capability_hint": None,
                    "checkpoint": False,
                },
                {
                    "id": "s2",
                    "name": "Forge step",
                    "instructions_md": "",
                    "owner_role": "fpa",
                    "default_assignee_id": "forge",
                    "kind": "ai",
                    "depends_on": ["s1"],
                    "est_minutes": None,
                    "requires_access": [],
                    "inputs": [],
                    "outputs": [],
                    "ai_capability_hint": "fpa",
                    "checkpoint": False,
                },
            ],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    )
    (repo / "tasks/t-q/artifacts/s1").mkdir(parents=True, exist_ok=True)
    (repo / "tasks/t-q/artifacts/s1/in.md").write_bytes(b"upstream content")
    db_in_tmp.insert(
        "tasks",
        {
            "id": "t-q",
            "standard_work_id": "sw-q",
            "period": "2026-05",
            "title": "Queue task title",
            "owner_id": "cfo",
            "status": "in_progress",
            "created_at": _now_iso(),
            "due_date": None,
            "started_at": _now_iso(),
            "completed_at": None,
            "notes_md": "",
            "steps": [
                {
                    "step_id": "s1",
                    "assignee_id": "fpa_analyst",
                    "status": "complete",
                    "started_at": _now_iso(),
                    "completed_at": _now_iso(),
                    "deliverable_paths": ["tasks/t-q/artifacts/s1/in.md"],
                    "findings_ref": None,
                    "comments": [],
                },
                {
                    "step_id": "s2",
                    "assignee_id": "forge",
                    "status": "pending",
                    "started_at": None,
                    "completed_at": None,
                    "deliverable_paths": [],
                    "findings_ref": None,
                    "comments": [],
                },
            ],
        },
    )
    from web import bundles

    return bundles.build_and_queue("t-q", "s2")


def test_list_empty(client):
    r = client.get("/queue")
    assert r.status_code == 200
    assert "Forge Queue" in r.text
    assert "No active queue items" in r.text


def test_list_shows_pending(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    r = client.get("/queue")
    assert r.status_code == 200
    assert qid in r.text
    assert "Queue task title" in r.text
    assert "Forge step" in r.text
    assert "Pending" in r.text


def test_fragment_returns_table_only(client, db_in_tmp, repo_in_tmp):
    _seed(db_in_tmp, repo_in_tmp)
    r = client.get("/queue/fragments/list")
    assert r.status_code == 200
    assert "Active" in r.text
    assert "<!DOCTYPE html>" not in r.text


def test_bundle_view_returns_markdown(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    r = client.get(f"/queue/{qid}/bundle")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert "task_id: t-q" in r.text
    assert "step_id: s2" in r.text


def test_bundle_html_view_has_nav_back_to_queue(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    r = client.get(f"/queue/{qid}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    # base.html chrome present
    assert "CFO Helper" in r.text
    assert 'href="/"' in r.text
    # back-to-queue affordance + raw-download link
    assert "Back to queue" in r.text
    assert f'href="/queue/{qid}/bundle"' in r.text
    # bundle content rendered inside the page
    assert "task_id: t-q" in r.text


def test_bundle_view_404_unknown_id(client):
    r = client.get("/queue/q-nope/bundle")
    assert r.status_code == 404
    r = client.get("/queue/q-nope")
    assert r.status_code == 404


def test_bundle_view_404_when_file_missing_on_disk(
    client, db_in_tmp, repo_in_tmp
):
    qid = _seed(db_in_tmp, repo_in_tmp)
    (repo_in_tmp / "tasks/t-q/queue/s2.md").unlink()
    r = client.get(f"/queue/{qid}/bundle")
    assert r.status_code == 404


def test_bundle_view_rejects_path_escape(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    db_in_tmp.update("queue", qid, {"bundle_path": "../../etc/passwd"})
    r = client.get(f"/queue/{qid}/bundle")
    assert r.status_code == 400
    assert "escapes repo" in r.json()["detail"]


def test_retry_flips_failed_to_pending(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    db_in_tmp.update(
        "queue",
        qid,
        {"status": "failed", "error": "boom", "completed_at": _now_iso()},
    )
    r = client.post(f"/queue/{qid}/retry", follow_redirects=False)
    assert r.status_code == 303
    row = db_in_tmp.find("queue", qid)
    assert row["status"] == "pending"
    assert row["error"] is None
    assert row["claimed_at"] is None
    assert row["completed_at"] is None


def test_retry_only_works_on_failed(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    r = client.post(f"/queue/{qid}/retry", follow_redirects=False)
    assert r.status_code == 409


def test_retry_404_unknown_id(client):
    r = client.post("/queue/q-nope/retry", follow_redirects=False)
    assert r.status_code == 404


def test_cancel_flips_pending_to_failed(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    r = client.post(f"/queue/{qid}/cancel", follow_redirects=False)
    assert r.status_code == 303
    row = db_in_tmp.find("queue", qid)
    assert row["status"] == "failed"
    assert row["error"] == "cancelled by user"
    assert row["completed_at"]


def test_cancel_refuses_non_pending(client, db_in_tmp, repo_in_tmp):
    qid = _seed(db_in_tmp, repo_in_tmp)
    db_in_tmp.update("queue", qid, {"status": "claimed", "claimed_at": _now_iso()})
    r = client.post(f"/queue/{qid}/cancel", follow_redirects=False)
    assert r.status_code == 409


def test_cancel_404_unknown_id(client):
    r = client.post("/queue/q-nope/cancel", follow_redirects=False)
    assert r.status_code == 404
