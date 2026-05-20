"""Tests for /calendar (web.routes.calendar)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def db_in_tmp(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    db.init_db()
    return db


@pytest.fixture
def client(db_in_tmp):
    from web.routes import calendar as cal_routes

    app = FastAPI()
    app.include_router(cal_routes.router)
    return TestClient(app)


@pytest.fixture
def pinned_today(monkeypatch):
    from web.routes import calendar as cal_routes

    fixed = date(2026, 5, 16)
    monkeypatch.setattr(cal_routes, "_today_utc", lambda: fixed)
    return fixed


def _now_iso() -> str:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc).isoformat()


def _insert_task(
    db,
    *,
    id: str,
    title: str,
    due_date: str,
    status: str = "draft",
):
    db.insert(
        "tasks",
        {
            "id": id,
            "standard_work_id": "sw-test",
            "period": None,
            "title": title,
            "owner_id": None,
            "status": status,
            "created_at": _now_iso(),
            "due_date": due_date,
            "started_at": None,
            "completed_at": None,
            "notes_md": "",
            "steps": [],
        },
    )


def test_empty_calendar_renders_current_month(client, pinned_today):
    r = client.get("/calendar")
    assert r.status_code == 200
    assert "May 2026" in r.text
    assert "Prev" in r.text
    assert "Today" in r.text
    assert "Next" in r.text


def test_three_tasks_render_in_correct_cells(client, db_in_tmp, pinned_today):
    _insert_task(db_in_tmp, id="t-001", title="Customer X QBR",
                 due_date="2026-05-04T17:00:00+00:00", status="in_progress")
    _insert_task(db_in_tmp, id="t-002", title="MOR May 2026",
                 due_date="2026-05-11T17:00:00+00:00", status="draft")
    _insert_task(db_in_tmp, id="t-003", title="BSR Q2 2026",
                 due_date="2026-05-28T17:00:00+00:00", status="blocked")

    r = client.get("/calendar?month=2026-05")
    assert r.status_code == 200
    assert "Customer X QBR" in r.text
    assert "MOR May 2026" in r.text
    assert "BSR Q2 2026" in r.text
    assert 'href="/tasks/t-001"' in r.text


def test_status_color_classes(client, db_in_tmp, pinned_today):
    _insert_task(db_in_tmp, id="t-a", title="A", due_date="2026-05-05", status="draft")
    _insert_task(db_in_tmp, id="t-b", title="B", due_date="2026-05-06", status="in_progress")
    _insert_task(db_in_tmp, id="t-c", title="C", due_date="2026-05-07", status="blocked")
    _insert_task(db_in_tmp, id="t-d", title="D", due_date="2026-05-08", status="complete")
    _insert_task(db_in_tmp, id="t-e", title="E", due_date="2026-05-09", status="aborted")

    r = client.get("/calendar?month=2026-05")
    assert "bg-slate-200" in r.text
    assert "bg-sky-200" in r.text
    assert "bg-amber-200" in r.text
    assert "bg-emerald-200" in r.text
    assert "bg-rose-200" in r.text
    assert "line-through" in r.text


def test_today_cell_has_ring_class(client, pinned_today):
    r = client.get("/calendar?month=2026-05")
    assert "ring-2 ring-sky-500" in r.text


def test_overflow_shows_plus_n_more(client, db_in_tmp, pinned_today):
    for i in range(5):
        _insert_task(db_in_tmp, id=f"t-{i:02d}", title=f"Task {i}",
                     due_date="2026-05-12", status="draft")
    r = client.get("/calendar?month=2026-05")
    assert "Task 0" in r.text
    assert "Task 1" in r.text
    assert "Task 2" in r.text
    assert "+2 more" in r.text
    assert 'href="/tasks/t-03"' not in r.text


def test_navigation_to_feb_2026(client, pinned_today):
    r = client.get("/calendar?month=2026-02")
    assert "February 2026" in r.text
    assert "month=2026-01" in r.text
    assert "month=2026-03" in r.text


def test_json_endpoint_returns_month_tasks(client, db_in_tmp, pinned_today):
    _insert_task(db_in_tmp, id="t-may-1", title="May 1",
                 due_date="2026-05-04", status="draft")
    _insert_task(db_in_tmp, id="t-may-2", title="May 2",
                 due_date="2026-05-29T17:00:00+00:00", status="in_progress")
    _insert_task(db_in_tmp, id="t-jun-1", title="June 1",
                 due_date="2026-06-01", status="draft")
    db_in_tmp.insert("tasks", {
        "id": "t-undated", "standard_work_id": "sw", "period": None,
        "title": "Undated", "owner_id": None, "status": "draft",
        "created_at": _now_iso(), "due_date": None, "started_at": None,
        "completed_at": None, "notes_md": "", "steps": []
    })

    r = client.get("/calendar/tasks?month=2026-05")
    payload = r.json()
    ids = [t["id"] for t in payload["tasks"]]
    assert ids == ["t-may-1", "t-may-2"]


def test_fragment_route_returns_grid_only(client, db_in_tmp, pinned_today):
    _insert_task(db_in_tmp, id="t-1", title="Frag", due_date="2026-05-04")
    r = client.get("/calendar/fragments/grid?month=2026-05&view=month")
    assert r.status_code == 200
    assert "Frag" in r.text
    assert "<!DOCTYPE html>" not in r.text


def test_week_view_renders(client, db_in_tmp, pinned_today):
    _insert_task(db_in_tmp, id="t-w", title="Week task", due_date="2026-05-13",
                 status="in_progress")
    r = client.get("/calendar?view=week")
    assert r.status_code == 200
    assert "Week of" in r.text
    assert "Week task" in r.text


def test_malformed_month_falls_back_to_today(client, pinned_today):
    r = client.get("/calendar?month=not-a-month")
    assert r.status_code == 200
    assert "May 2026" in r.text


def test_chip_truncation(client, db_in_tmp, pinned_today):
    long_title = "A" * 60
    _insert_task(db_in_tmp, id="t-long", title=long_title, due_date="2026-05-04")
    r = client.get("/calendar?month=2026-05")
    assert ("A" * 23 + "…") in r.text
    assert long_title in r.text  # appears in title attr
