"""Tests for /schedules (web.routes.schedules) + web.scheduler."""

from __future__ import annotations

from datetime import datetime, timezone

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
def client(db_in_tmp, repo_in_tmp, monkeypatch):
    # Replace the real scheduler with a no-op so tests don't spawn threads.
    from web import scheduler as scheduler_mod
    from web.routes import schedules as schedules_routes

    class _NoOpScheduler:
        running = True

        def __init__(self):
            self._jobs: dict[str, str] = {}

        def get_jobs(self):
            return [type("J", (), {"id": jid})() for jid in self._jobs]

        def add_job(self, *args, **kwargs):
            self._jobs[kwargs["id"]] = "ok"

        def remove_job(self, jid):
            self._jobs.pop(jid, None)

        def start(self):
            pass

        def shutdown(self, *, wait=False):
            pass

    no_op = _NoOpScheduler()
    monkeypatch.setattr(scheduler_mod, "_scheduler", no_op)
    monkeypatch.setattr(scheduler_mod, "scheduler", lambda: no_op)

    app = FastAPI()
    app.include_router(schedules_routes.router)
    return TestClient(app)


def _now() -> str:
    return datetime(2026, 5, 16, tzinfo=timezone.utc).isoformat()


def _add_sw(db, *, sw_id="sw1"):
    db.insert(
        "standard_work",
        {
            "id": sw_id,
            "name": "Monthly close",
            "source_task_type": None,
            "owner_role": "fpa",
            "cadence": None,
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": 0,
            "steps": [],
            "created_at": _now(),
            "updated_at": _now(),
        },
    )


def _add_sched(db, *, sid="s1", sw_id="sw1", cron="0 9 1 * *", enabled=True):
    db.insert(
        "schedules",
        {
            "id": sid,
            "name": f"Schedule {sid}",
            "standard_work_id": sw_id,
            "cron": cron,
            "enabled": enabled,
            "brief_template": {},
            "created_at": _now(),
            "last_fire": None,
            "last_fire_result": None,
        },
    )


# --- list / CRUD ----------------------------------------------------------


def test_list_empty(client):
    r = client.get("/schedules")
    assert r.status_code == 200
    assert "No schedules" in r.text


def test_create_schedule(client, db_in_tmp):
    _add_sw(db_in_tmp)
    r = client.post(
        "/schedules",
        data={
            "id": "s-monthly",
            "name": "Monthly close",
            "standard_work_id": "sw1",
            "cron": "0 9 1 * *",
            "enabled": "on",
            "period_template": "{previous_month}",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = db_in_tmp.find("schedules", "s-monthly")
    assert row["cron"] == "0 9 1 * *"
    assert row["brief_template"]["period"] == "{previous_month}"


def test_create_rejects_bad_id(client, db_in_tmp):
    _add_sw(db_in_tmp)
    # Missing required field (cron) → 400.
    r = client.post(
        "/schedules",
        data={"id": "s1", "name": "x", "standard_work_id": "sw1", "cron": ""},
        follow_redirects=False,
    )
    assert r.status_code in (400, 422)


def test_edit_form_renders(client, db_in_tmp):
    _add_sw(db_in_tmp)
    _add_sched(db_in_tmp)
    r = client.get("/schedules/s1/edit")
    assert r.status_code == 200
    assert "Edit Schedule s1" in r.text


def test_update_schedule(client, db_in_tmp):
    _add_sw(db_in_tmp)
    _add_sched(db_in_tmp, cron="0 9 1 * *")
    r = client.post(
        "/schedules/s1",
        data={
            "name": "Renamed",
            "standard_work_id": "sw1",
            "cron": "*/5 * * * *",
            "enabled": "on",
            "period_template": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = db_in_tmp.find("schedules", "s1")
    assert row["name"] == "Renamed"
    assert row["cron"] == "*/5 * * * *"


def test_toggle_enabled(client, db_in_tmp):
    _add_sw(db_in_tmp)
    _add_sched(db_in_tmp, enabled=True)
    client.post("/schedules/s1/toggle-enabled", follow_redirects=False)
    assert db_in_tmp.find("schedules", "s1")["enabled"] is False
    client.post("/schedules/s1/toggle-enabled", follow_redirects=False)
    assert db_in_tmp.find("schedules", "s1")["enabled"] is True


def test_delete_schedule(client, db_in_tmp):
    _add_sw(db_in_tmp)
    _add_sched(db_in_tmp)
    r = client.post("/schedules/s1/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db_in_tmp.find("schedules", "s1") is None


def test_delete_404_unknown(client):
    r = client.post("/schedules/ghost/delete", follow_redirects=False)
    assert r.status_code == 404


# --- run-now / fire -------------------------------------------------------


def test_run_now_creates_task(client, db_in_tmp):
    _add_sw(db_in_tmp)
    _add_sched(db_in_tmp)
    r = client.post("/schedules/s1/run-now", follow_redirects=False)
    assert r.status_code == 303
    tasks = db_in_tmp.rows("tasks")
    assert len(tasks) == 1
    assert tasks[0]["standard_work_id"] == "sw1"
    s = db_in_tmp.find("schedules", "s1")
    assert s["last_fire"]
    assert s["last_fire_result"].startswith("ok:")


def test_fire_with_missing_sw_records_error(client, db_in_tmp):
    # Insert a schedule whose sw_id doesn't exist.
    _add_sched(db_in_tmp, sw_id="ghost")
    from web import scheduler

    result = scheduler._fire("s1")
    assert result.startswith("error:")
    s = db_in_tmp.find("schedules", "s1")
    assert "error" in (s["last_fire_result"] or "")


def test_fire_substitutes_this_month(client, db_in_tmp):
    _add_sw(db_in_tmp)
    db_in_tmp.insert(
        "schedules",
        {
            "id": "s-tm",
            "name": "x",
            "standard_work_id": "sw1",
            "cron": "0 9 1 * *",
            "enabled": True,
            "brief_template": {"period": "close-{this_month}"},
            "created_at": _now(),
            "last_fire": None,
            "last_fire_result": None,
        },
    )
    from datetime import datetime, timezone

    from web import scheduler

    scheduler._fire("s-tm")
    tasks = db_in_tmp.rows("tasks")
    assert len(tasks) == 1
    # Period contains the literal "close-YYYY-MM" form.
    assert tasks[0]["period"].startswith("close-")
    now_yyyymm = datetime.now(tz=timezone.utc).strftime("%Y-%m")
    assert now_yyyymm in tasks[0]["period"]
