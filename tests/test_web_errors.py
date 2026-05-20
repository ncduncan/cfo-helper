"""Tests for web.errors and web.supervisor."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app_with_failing_route() -> FastAPI:
    """Build a tiny app that registers our handler and has one always-failing route."""
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("simulated failure")

    return app


def test_htmx_request_gets_toast_and_preserves_page():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"HX-Request": "true"})

    assert r.status_code == 204
    assert r.headers.get("HX-Reswap") == "none"
    trigger = json.loads(r.headers["HX-Trigger"])
    assert trigger["showToast"]["level"] == "error"
    assert "simulated failure" in trigger["showToast"]["message"]
    assert "request_id" in trigger["showToast"]


def test_json_request_gets_structured_error():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"Accept": "application/json"})

    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_error"
    assert "simulated failure" in body["detail"]
    assert "request_id" in body


def test_api_path_gets_json_even_without_accept_header():
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/api/boom")
    def api_boom():
        raise RuntimeError("api failure")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/boom")

    assert r.status_code == 500
    assert r.json()["error"] == "internal_error"


def test_browser_request_gets_html_error_page():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"Accept": "text/html"})

    assert r.status_code == 500
    assert "text/html" in r.headers["content-type"]
    assert "simulated failure" in r.text
    assert "Something went wrong" in r.text
    assert "request_id" in r.text


def test_message_is_truncated_at_200_chars():
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)
    long_msg = "x" * 500

    @app.get("/long")
    def long_route():
        raise RuntimeError(long_msg)

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/long", headers={"Accept": "application/json"})

    detail = r.json()["detail"]
    assert len(detail) <= 200
    assert detail.endswith("…")


def test_safe_scheduler_reload_returns_true_on_success(monkeypatch):
    from web import errors, scheduler

    called = {"n": 0}

    def fake_reload():
        called["n"] += 1

    monkeypatch.setattr(scheduler, "reload", fake_reload)
    assert errors.safe_scheduler_reload() is True
    assert called["n"] == 1


def test_safe_scheduler_reload_swallows_exception_and_logs(monkeypatch, caplog):
    from web import errors, scheduler

    def boom():
        raise RuntimeError("scheduler is angry")

    monkeypatch.setattr(scheduler, "reload", boom)
    with caplog.at_level("ERROR", logger="web.errors"):
        result = errors.safe_scheduler_reload()
    assert result is False
    assert any("scheduler.reload()" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_supervisor_restarts_dead_observer(tmp_path, monkeypatch):
    from web import sse, supervisor

    # Point watchdog at a tmpdir so we don't litter the real DB dir.
    monkeypatch.setattr(sse, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(sse, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(sse, "_observer", None)

    sse.start_observer()
    assert sse.is_observer_alive() is True

    # Kill the observer behind the supervisor's back.
    sse._observer.stop()
    sse._observer.join(timeout=1)
    sse._observer = None
    assert sse.is_observer_alive() is False

    # Run one supervisor tick.
    await supervisor.run_one_tick()
    assert sse.is_observer_alive() is True

    sse.stop_observer()


@pytest.mark.asyncio
async def test_supervisor_restarts_dead_scheduler(monkeypatch):
    from web import scheduler, supervisor

    calls = {"start": 0}

    def fake_is_alive():
        return False

    def fake_start():
        calls["start"] += 1

    monkeypatch.setattr(scheduler, "is_scheduler_alive", fake_is_alive)
    monkeypatch.setattr(scheduler, "start_scheduler", fake_start)
    # Keep observer healthy so the test focuses on scheduler.
    monkeypatch.setattr("web.sse.is_observer_alive", lambda: True)

    await supervisor.run_one_tick()
    assert calls["start"] == 1


def test_schedule_update_survives_broken_reload(tmp_path, monkeypatch):
    """POST /schedules/<id> should return success even if scheduler.reload raises."""
    from web import db as db_mod
    from web import errors, scheduler as scheduler_mod
    from web.routes import schedules as schedules_routes

    # Isolate the DB into tmpdir.
    monkeypatch.setattr(db_mod, "DB_DIR", tmp_path / "db")
    db_mod.init_db()

    # Seed a standard_work and a schedule.
    from datetime import datetime, timezone
    now_iso = datetime(2026, 5, 16, tzinfo=timezone.utc).isoformat()
    db_mod.insert("standard_work", {
        "id": "sw1", "name": "SW", "source_task_type": None,
        "owner_role": "fpa", "cadence": None, "context_md": "",
        "requirements_md": "", "due_offset_days": 0, "steps": [],
        "created_at": now_iso, "updated_at": now_iso,
    })
    db_mod.insert("schedules", {
        "id": "s1", "name": "S1", "standard_work_id": "sw1",
        "cron": "0 9 1 * *", "enabled": True, "brief_template": {},
        "created_at": now_iso, "last_fire": None, "last_fire_result": None,
    })

    # Make scheduler.reload() blow up.
    def boom():
        raise RuntimeError("scheduler is having a bad day")
    monkeypatch.setattr(scheduler_mod, "reload", boom)

    # Mount the route.
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(schedules_routes.router)
    errors.register_exception_handlers(app)
    client = TestClient(app, follow_redirects=False)

    r = client.post(
        "/schedules/s1",
        data={
            "name": "S1 updated",
            "standard_work_id": "sw1",
            "frequency": "monthly",
            "hour": "9", "minute": "0",
            "day_of_week": "1", "day_of_month": "1", "month": "1",
            "cron_raw": "",
            "timezone": "America/New_York",
            "enabled": "on",
        },
    )

    # Route should still return its normal 303 redirect.
    assert r.status_code == 303
    # DB write should have stuck.
    row = db_mod.find("schedules", "s1")
    assert row["name"] == "S1 updated"
