"""Tests for /team (web.routes.team)."""

from __future__ import annotations

from datetime import datetime, timezone

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
    from web.routes import team as team_routes

    app = FastAPI()
    app.include_router(team_routes.router)
    return TestClient(app)


def _now_iso() -> str:
    return datetime(2026, 5, 16, tzinfo=timezone.utc).isoformat()


def _add(db, *, id, name, kind="human", email=None, role_tags=None, active=True):
    db.insert(
        "team",
        {
            "id": id,
            "name": name,
            "email": email,
            "kind": kind,
            "role_tags": role_tags or [],
            "active": active,
            "created_at": _now_iso(),
        },
    )


def _add_forge(db):
    _add(db, id="forge", name="Forge", kind="ai", role_tags=["fpa"])


def test_list_empty(client):
    r = client.get("/team")
    assert r.status_code == 200
    assert "No team members yet" in r.text


def test_list_renders_member(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice", role_tags=["fpa"])
    r = client.get("/team")
    assert r.status_code == 200
    assert "Alice" in r.text
    assert "alice" in r.text


def test_fragment_returns_table_only(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice")
    r = client.get("/team/fragments/list")
    assert r.status_code == 200
    assert "Alice" in r.text
    assert "<!DOCTYPE html>" not in r.text


def test_create_human_member(client):
    r = client.post(
        "/team",
        data={
            "id": "bob",
            "name": "Bob Builder",
            "email": "bob@example.com",
            "kind": "human",
            "role_tags": "controller, fpa",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/team/bob"


def test_create_rejects_bad_id(client):
    r = client.post(
        "/team",
        data={"id": "Bad-Upper", "name": "x", "kind": "human"},
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_create_rejects_duplicate(client, db_in_tmp):
    _add(db_in_tmp, id="dup", name="First")
    r = client.post(
        "/team",
        data={"id": "dup", "name": "Second", "kind": "human"},
        follow_redirects=False,
    )
    assert r.status_code == 409


def test_detail_404_for_unknown(client):
    r = client.get("/team/ghost")
    assert r.status_code == 404


def test_detail_shows_member(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice", email="a@x.com", role_tags=["fpa"])
    r = client.get("/team/alice")
    assert r.status_code == 200
    assert "Alice" in r.text
    assert "a@x.com" in r.text
    assert "fpa" in r.text


def test_edit_form_renders(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice")
    r = client.get("/team/alice/edit")
    assert r.status_code == 200
    assert "Edit Alice" in r.text


def test_update_member(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice")
    r = client.post(
        "/team/alice",
        data={"name": "Alice Smith", "email": "alice@x.com", "role_tags": "fpa"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    row = db_in_tmp.find("team", "alice")
    assert row["name"] == "Alice Smith"
    assert row["email"] == "alice@x.com"
    assert row["role_tags"] == ["fpa"]


def test_update_ignores_posted_kind(client, db_in_tmp):
    """Kind is immutable — posting kind in the update form is ignored."""
    _add(db_in_tmp, id="alice", name="Alice", kind="human")
    client.post(
        "/team/alice",
        data={
            "name": "Alice",
            "email": "",
            "role_tags": "",
            "kind": "ai",  # attempt to flip kind
        },
        follow_redirects=False,
    )
    assert db_in_tmp.find("team", "alice")["kind"] == "human"


def test_toggle_active(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice", active=True)
    client.post("/team/alice/toggle-active", follow_redirects=False)
    assert db_in_tmp.find("team", "alice")["active"] is False
    client.post("/team/alice/toggle-active", follow_redirects=False)
    assert db_in_tmp.find("team", "alice")["active"] is True


def test_delete_member(client, db_in_tmp):
    _add(db_in_tmp, id="alice", name="Alice")
    r = client.post("/team/alice/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db_in_tmp.find("team", "alice") is None


def test_delete_forge_refused(client, db_in_tmp):
    _add_forge(db_in_tmp)
    r = client.post("/team/forge/delete", follow_redirects=False)
    assert r.status_code == 409
    assert db_in_tmp.find("team", "forge") is not None


def test_delete_404_unknown(client):
    r = client.post("/team/ghost/delete", follow_redirects=False)
    assert r.status_code == 404
