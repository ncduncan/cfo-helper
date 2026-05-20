"""Tests for web.bundles — Forge queue bundle writer."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


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


def _now_iso() -> str:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc).isoformat()


def _seed_sw(db, *, sw_id: str = "sw-test") -> dict[str, Any]:
    sw = {
        "id": sw_id,
        "name": "Test SW",
        "source_task_type": None,
        "owner_role": "fpa",
        "cadence": None,
        "context_md": "Context here.",
        "requirements_md": "Reqs here.",
        "due_offset_days": 0,
        "steps": [
            {
                "id": "step1",
                "name": "Gather inputs",
                "instructions_md": "Pull the source files.",
                "owner_role": "fpa",
                "default_assignee_id": "fpa_analyst",
                "kind": "human",
                "depends_on": [],
                "est_minutes": 30,
                "requires_access": [],
                "inputs": [],
                "outputs": ["raw.csv"],
                "ai_capability_hint": None,
                "checkpoint": False,
            },
            {
                "id": "step2",
                "name": "Draft narrative",
                "instructions_md": "Write the variance commentary.",
                "owner_role": "fpa",
                "default_assignee_id": "forge",
                "kind": "ai",
                "depends_on": ["step1"],
                "est_minutes": 45,
                "requires_access": [],
                "inputs": ["raw.csv"],
                "outputs": ["narrative.md"],
                "ai_capability_hint": "fpa",
                "checkpoint": False,
            },
        ],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    db.insert("standard_work", sw)
    return sw


def _seed_task(
    db,
    *,
    task_id: str = "t-test",
    sw_id: str = "sw-test",
    step1_status: str = "complete",
    step1_deliverables: list[str] | None = None,
) -> dict[str, Any]:
    task = {
        "id": task_id,
        "standard_work_id": sw_id,
        "period": "2026-05",
        "title": "Test task",
        "owner_id": "cfo",
        "status": "in_progress",
        "created_at": _now_iso(),
        "due_date": None,
        "started_at": _now_iso(),
        "completed_at": None,
        "notes_md": "",
        "steps": [
            {
                "step_id": "step1",
                "assignee_id": "fpa_analyst",
                "status": step1_status,
                "started_at": _now_iso(),
                "completed_at": _now_iso() if step1_status == "complete" else None,
                "deliverable_paths": step1_deliverables or [],
                "findings_ref": None,
                "comments": [],
            },
            {
                "step_id": "step2",
                "assignee_id": "forge",
                "status": "pending",
                "started_at": None,
                "completed_at": None,
                "deliverable_paths": [],
                "findings_ref": None,
                "comments": [],
            },
        ],
    }
    db.insert("tasks", task)
    return task


def _write(repo: Path, rel: str, contents: bytes) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(contents)


def test_build_and_queue_writes_bundle_and_inserts_row(db_in_tmp, repo_in_tmp):
    from web import bundles

    _seed_sw(db_in_tmp)
    _write(repo_in_tmp, "tasks/t-test/artifacts/step1/raw.csv", b"a,b\n1,2\n")
    _seed_task(
        db_in_tmp,
        step1_deliverables=["tasks/t-test/artifacts/step1/raw.csv"],
    )

    queue_id = bundles.build_and_queue("t-test", "step2")

    assert queue_id.startswith("q-t-test-step2-")
    bundle_rel = "tasks/t-test/queue/step2.md"
    bundle_abs = repo_in_tmp / bundle_rel
    assert bundle_abs.exists()
    body = bundle_abs.read_text()
    assert body.startswith("---\n")
    assert "task_id: t-test" in body
    assert "step_id: step2" in body
    assert "agent_role: fpa" in body
    assert "upstream_hash:" in body
    assert "## Step Instructions" in body
    assert "Write the variance commentary." in body
    assert "tasks/t-test/artifacts/step1/raw.csv" in body

    row = db_in_tmp.find("queue", queue_id)
    assert row is not None
    assert row["status"] == "pending"
    assert row["bundle_path"] == bundle_rel
    assert row["agent_role"] == "fpa"
    assert row["upstream_hash"]


def test_build_and_queue_missing_task_raises(db_in_tmp, repo_in_tmp):
    from web import bundles

    with pytest.raises(KeyError, match="task not found"):
        bundles.build_and_queue("t-nope", "step2")


def test_build_and_queue_missing_step_raises(db_in_tmp, repo_in_tmp):
    from web import bundles

    _seed_sw(db_in_tmp)
    _seed_task(db_in_tmp)
    with pytest.raises(KeyError, match="not found on task"):
        bundles.build_and_queue("t-test", "nonexistent")


def test_build_and_queue_broken_depends_on_raises_value_error(
    db_in_tmp, repo_in_tmp
):
    from web import bundles

    sw = _seed_sw(db_in_tmp)
    sw["id"] = "sw-broken"
    sw["steps"][1]["depends_on"] = ["ghost_step"]
    db_in_tmp.insert("standard_work", sw)
    _seed_task(db_in_tmp, task_id="t-broken", sw_id="sw-broken")
    with pytest.raises(ValueError, match="depends_on references unknown step"):
        bundles.build_and_queue("t-broken", "step2")


def test_compute_upstream_hash_stable(db_in_tmp, repo_in_tmp):
    from web import bundles

    _seed_sw(db_in_tmp)
    _write(repo_in_tmp, "tasks/t-test/artifacts/step1/raw.csv", b"stable bytes")
    _seed_task(
        db_in_tmp,
        step1_deliverables=["tasks/t-test/artifacts/step1/raw.csv"],
    )
    h1 = bundles.compute_upstream_hash("t-test", "step2")
    h2 = bundles.compute_upstream_hash("t-test", "step2")
    assert h1 == h2
    assert len(h1) == 64


def test_compute_upstream_hash_changes_when_rewritten(db_in_tmp, repo_in_tmp):
    from web import bundles

    _seed_sw(db_in_tmp)
    _write(repo_in_tmp, "tasks/t-test/artifacts/step1/raw.csv", b"original")
    _seed_task(
        db_in_tmp,
        step1_deliverables=["tasks/t-test/artifacts/step1/raw.csv"],
    )
    h_before = bundles.compute_upstream_hash("t-test", "step2")

    _write(repo_in_tmp, "tasks/t-test/artifacts/step1/raw.csv", b"REWRITTEN")
    h_after = bundles.compute_upstream_hash("t-test", "step2")
    assert h_before != h_after


def test_compute_upstream_hash_ignores_incomplete_predecessor(db_in_tmp, repo_in_tmp):
    from web import bundles

    _seed_sw(db_in_tmp)
    _write(repo_in_tmp, "tasks/t-test/artifacts/step1/raw.csv", b"data")
    _seed_task(
        db_in_tmp,
        step1_status="pending",
        step1_deliverables=["tasks/t-test/artifacts/step1/raw.csv"],
    )
    h = bundles.compute_upstream_hash("t-test", "step2")
    assert h == hashlib.sha256().hexdigest()


def test_compute_upstream_hash_missing_file_still_hashes(db_in_tmp, repo_in_tmp):
    from web import bundles

    _seed_sw(db_in_tmp)
    _seed_task(
        db_in_tmp,
        step1_deliverables=["tasks/t-test/artifacts/step1/missing.csv"],
    )
    h_missing = bundles.compute_upstream_hash("t-test", "step2")
    _write(repo_in_tmp, "tasks/t-test/artifacts/step1/missing.csv", b"now here")
    h_present = bundles.compute_upstream_hash("t-test", "step2")
    assert h_missing != h_present
