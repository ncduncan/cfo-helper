"""Tests for web.instantiate — Task-from-StandardWork creator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest


@pytest.fixture
def db_in_tmp(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    db.init_db()
    return db


def _now_iso() -> str:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc).isoformat()


def _add_team(db, *, id, name="x", kind="human", role_tags=None):
    db.insert(
        "team",
        {
            "id": id,
            "name": name,
            "email": None,
            "kind": kind,
            "role_tags": role_tags or [],
            "active": True,
            "created_at": _now_iso(),
        },
    )


def _add_sw(
    db,
    *,
    sw_id: str = "sw1",
    owner_role: str = "fpa",
    due_offset_days: int = 0,
    steps: list[dict[str, Any]] | None = None,
):
    db.insert(
        "standard_work",
        {
            "id": sw_id,
            "name": "Template",
            "source_task_type": None,
            "owner_role": owner_role,
            "cadence": None,
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": due_offset_days,
            "steps": steps or [],
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    )


def _step(*, id, owner_role="fpa", kind="ai", default_assignee_id="forge"):
    return {
        "id": id,
        "name": id,
        "instructions_md": "",
        "owner_role": owner_role,
        "default_assignee_id": default_assignee_id,
        "kind": kind,
        "depends_on": [],
        "est_minutes": None,
        "requires_access": [],
        "inputs": [],
        "outputs": [],
        "ai_capability_hint": owner_role,
        "checkpoint": False,
    }


def test_instantiate_basic(db_in_tmp):
    from web.instantiate import instantiate_task

    _add_team(db_in_tmp, id="forge", kind="ai", role_tags=["fpa"])
    _add_team(db_in_tmp, id="alice", role_tags=["fpa"])
    _add_sw(db_in_tmp, steps=[_step(id="s1"), _step(id="s2")])

    t = instantiate_task("sw1", period="2026-05")
    assert t["status"] == "draft"
    assert t["period"] == "2026-05"
    assert t["title"] == "Template — 2026-05"
    assert t["owner_id"] == "alice"  # role-tag match (excluding ai)
    assert len(t["steps"]) == 2
    assert t["steps"][0]["status"] == "pending"


def test_instantiate_unknown_raises(db_in_tmp):
    from web.instantiate import instantiate_task

    with pytest.raises(KeyError):
        instantiate_task("nope")


def test_instantiate_collision_appends_suffix(db_in_tmp):
    from web.instantiate import instantiate_task

    _add_sw(db_in_tmp)
    t1 = instantiate_task("sw1", period="2026-05")
    t2 = instantiate_task("sw1", period="2026-05")
    assert t1["id"] != t2["id"]
    assert t2["id"].endswith("-2")


def test_instantiate_resolves_assignee_for_forge_step(db_in_tmp):
    from web.instantiate import instantiate_task

    _add_team(db_in_tmp, id="forge", kind="ai", role_tags=["fpa"])
    _add_sw(
        db_in_tmp,
        steps=[_step(id="ai_step", default_assignee_id="forge")],
    )
    t = instantiate_task("sw1")
    assert t["steps"][0]["assignee_id"] == "forge"


def test_instantiate_falls_back_to_role_match_when_default_missing(db_in_tmp):
    from web.instantiate import instantiate_task

    _add_team(db_in_tmp, id="bob", role_tags=["controller"])
    _add_sw(
        db_in_tmp,
        steps=[
            _step(
                id="step",
                owner_role="controller",
                default_assignee_id="ghost",
            )
        ],
    )
    t = instantiate_task("sw1")
    assert t["steps"][0]["assignee_id"] == "bob"


def test_instantiate_due_date_from_offset(db_in_tmp):
    from datetime import datetime, timezone

    from web.instantiate import instantiate_task

    _add_sw(db_in_tmp, due_offset_days=3)
    now = datetime(2026, 5, 16, tzinfo=timezone.utc)
    t = instantiate_task("sw1", now=now)
    assert t["due_date"].startswith("2026-05-19")


def test_instantiate_owner_override(db_in_tmp):
    from web.instantiate import instantiate_task

    _add_team(db_in_tmp, id="alice", role_tags=["fpa"])
    _add_team(db_in_tmp, id="bob", role_tags=[])
    _add_sw(db_in_tmp)
    t = instantiate_task("sw1", owner_id="bob")
    assert t["owner_id"] == "bob"
