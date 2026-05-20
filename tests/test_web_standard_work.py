"""Tests for /standard-work (web.routes.standard_work)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
    from web.routes import standard_work as sw_routes

    app = FastAPI()
    app.include_router(sw_routes.router)
    return TestClient(app)


def _now() -> str:
    return datetime(2026, 5, 16, tzinfo=timezone.utc).isoformat()


def _seed_sw(
    db,
    *,
    sw_id: str = "sw1",
    name: str = "Template",
    steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    row = {
        "id": sw_id,
        "name": name,
        "source_task_type": None,
        "owner_role": "fpa",
        "cadence": None,
        "context_md": "",
        "requirements_md": "",
        "due_offset_days": 0,
        "steps": steps or [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    db.insert("standard_work", row)
    return row


def _step(
    *,
    id: str,
    name: str = "Step",
    owner_role: str = "fpa",
    kind: str = "ai",
    depends_on: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "instructions_md": "",
        "owner_role": owner_role,
        "default_assignee_id": "forge",
        "kind": kind,
        "depends_on": depends_on or [],
        "est_minutes": None,
        "requires_access": [],
        "inputs": [],
        "outputs": [],
        "ai_capability_hint": owner_role,
        "checkpoint": False,
    }


# --- list / create / detail ------------------------------------------------


def test_list_empty(client):
    r = client.get("/standard-work")
    assert r.status_code == 200
    assert "No standard work templates yet" in r.text


def test_list_shows_template(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1", name="Monthly close")
    r = client.get("/standard-work")
    assert r.status_code == 200
    assert "Monthly close" in r.text


def test_fragment_returns_table_only(client, db_in_tmp):
    _seed_sw(db_in_tmp)
    r = client.get("/standard-work/fragments/list")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" not in r.text


def test_create_template(client):
    r = client.post(
        "/standard-work",
        data={
            "id": "my-template",
            "name": "My template",
            "owner_role": "fpa",
            "cadence": "0 9 1 * *",
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": "3",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/standard-work/my-template"


def test_create_rejects_bad_id(client):
    r = client.post(
        "/standard-work",
        data={"id": "BAD-UPPER", "name": "x", "owner_role": "fpa"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_detail_404_unknown(client):
    r = client.get("/standard-work/ghost")
    assert r.status_code == 404


def test_detail_renders_step_count(client, db_in_tmp):
    _seed_sw(
        db_in_tmp,
        sw_id="sw1",
        steps=[_step(id="step1"), _step(id="step2", depends_on=["step1"])],
    )
    r = client.get("/standard-work/sw1")
    assert r.status_code == 200
    assert "Steps (2)" in r.text
    assert "step1" in r.text
    assert "step2" in r.text


def test_update_header(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1", name="Old")
    r = client.post(
        "/standard-work/sw1",
        data={
            "name": "New",
            "owner_role": "fpa",
            "cadence": "",
            "context_md": "ctx",
            "requirements_md": "",
            "due_offset_days": "0",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert db_in_tmp.find("standard_work", "sw1")["name"] == "New"
    assert db_in_tmp.find("standard_work", "sw1")["context_md"] == "ctx"


def test_delete_template(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1")
    r = client.post("/standard-work/sw1/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db_in_tmp.find("standard_work", "sw1") is None


# --- step CRUD -------------------------------------------------------------


def test_add_step(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1")
    r = client.post(
        "/standard-work/sw1/steps",
        data={
            "id": "step1",
            "name": "First step",
            "kind": "ai",
            "owner_role": "fpa",
            "instructions_md": "Do it",
            "default_assignee_id": "forge",
            "ai_capability_hint": "fpa",
            "depends_on": "",
            "est_minutes": "30",
            "checkpoint": "",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    sw = db_in_tmp.find("standard_work", "sw1")
    assert len(sw["steps"]) == 1
    assert sw["steps"][0]["id"] == "step1"
    assert sw["steps"][0]["est_minutes"] == 30


def test_add_step_rejects_duplicate_id(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1", steps=[_step(id="step1")])
    r = client.post(
        "/standard-work/sw1/steps",
        data={
            "id": "step1",
            "name": "dup",
            "kind": "ai",
            "owner_role": "fpa",
        },
        follow_redirects=False,
    )
    assert r.status_code == 409


def test_add_step_rejects_unknown_dep(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1")
    r = client.post(
        "/standard-work/sw1/steps",
        data={
            "id": "step1",
            "name": "x",
            "kind": "ai",
            "owner_role": "fpa",
            "depends_on": "ghost_step",
        },
        follow_redirects=False,
    )
    assert r.status_code == 409
    assert "ghost_step" in r.json()["detail"]


def test_update_step(client, db_in_tmp):
    _seed_sw(
        db_in_tmp,
        sw_id="sw1",
        steps=[_step(id="step1", name="Old name")],
    )
    r = client.post(
        "/standard-work/sw1/steps/step1",
        data={
            "name": "New name",
            "kind": "human",
            "owner_role": "fpa",
            "instructions_md": "",
            "default_assignee_id": "",
            "ai_capability_hint": "",
            "depends_on": "",
            "est_minutes": "",
            "checkpoint": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    s = db_in_tmp.find("standard_work", "sw1")["steps"][0]
    assert s["name"] == "New name"
    assert s["kind"] == "human"
    assert s["checkpoint"] is True


def test_update_step_rejects_cycle(client, db_in_tmp):
    _seed_sw(
        db_in_tmp,
        sw_id="sw1",
        steps=[
            _step(id="a"),
            _step(id="b", depends_on=["a"]),
            _step(id="c", depends_on=["b"]),
        ],
    )
    # Update 'a' to depend on 'c' → creates a→b→c→a cycle
    r = client.post(
        "/standard-work/sw1/steps/a",
        data={
            "name": "A",
            "kind": "ai",
            "owner_role": "fpa",
            "depends_on": "c",
        },
        follow_redirects=False,
    )
    assert r.status_code == 409
    assert "cycle" in r.json()["detail"]


def test_delete_step_refuses_with_dependents(client, db_in_tmp):
    _seed_sw(
        db_in_tmp,
        sw_id="sw1",
        steps=[_step(id="a"), _step(id="b", depends_on=["a"])],
    )
    r = client.post("/standard-work/sw1/steps/a/delete", follow_redirects=False)
    assert r.status_code == 409
    assert "b" in r.json()["detail"]


def test_delete_step_happy_path(client, db_in_tmp):
    _seed_sw(db_in_tmp, sw_id="sw1", steps=[_step(id="orphan")])
    r = client.post(
        "/standard-work/sw1/steps/orphan/delete", follow_redirects=False
    )
    assert r.status_code == 303
    assert db_in_tmp.find("standard_work", "sw1")["steps"] == []
