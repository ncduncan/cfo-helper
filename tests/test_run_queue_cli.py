"""Tests for scripts.run_queue — Forge queue runner CLI.

We call ``main(argv=...)`` in-process so the monkeypatch on ``web.db.DB_DIR``
and ``web.bundles.REPO_ROOT`` reaches the SUT.
"""

from __future__ import annotations

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
    from scripts import run_queue
    from web import bundles

    monkeypatch.setattr(bundles, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_queue, "REPO_ROOT", tmp_path)
    return tmp_path


def _now_iso() -> str:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc).isoformat()


def _seed_for_queue(db, repo: Path) -> str:
    db.insert(
        "standard_work",
        {
            "id": "sw-runq",
            "name": "Run-queue SW",
            "source_task_type": None,
            "owner_role": "fpa",
            "cadence": None,
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": 0,
            "steps": [
                {
                    "id": "s1",
                    "name": "Gather",
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
                    "name": "Draft",
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
    (repo / "tasks/t-runq/artifacts/s1").mkdir(parents=True, exist_ok=True)
    (repo / "tasks/t-runq/artifacts/s1/notes.md").write_bytes(b"upstream")
    db.insert(
        "tasks",
        {
            "id": "t-runq",
            "standard_work_id": "sw-runq",
            "period": "2026-05",
            "title": "Run-queue task",
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
                    "deliverable_paths": ["tasks/t-runq/artifacts/s1/notes.md"],
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
    from web import bundles as bundles_mod

    return bundles_mod.build_and_queue("t-runq", "s2")


def test_list_empty(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    rc = run_queue.main(["--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "queue is empty" in out


def test_list_default_argv(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    rc = run_queue.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert "queue is empty" in out


def test_list_shows_pending_only(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    rc = run_queue.main(["--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 pending queue item" in out
    assert qid in out

    db_in_tmp.update("queue", qid, {"status": "done", "completed_at": _now_iso()})
    rc = run_queue.main(["--list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "queue is empty" in out


def test_claim_happy_path(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    rc = run_queue.main(["--claim", qid])
    captured = capsys.readouterr()
    assert rc == 0
    assert str(repo_in_tmp / "tasks/t-runq/queue/s2.md") in captured.out

    row = db_in_tmp.find("queue", qid)
    assert row["status"] == "claimed"
    assert row["claimed_at"]


def test_claim_stale_upstream_fails(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    (repo_in_tmp / "tasks/t-runq/artifacts/s1/notes.md").write_bytes(
        b"REWRITTEN AFTER BUNDLE"
    )

    rc = run_queue.main(["--claim", qid])
    captured = capsys.readouterr()
    assert rc == 2
    assert "upstream changed" in captured.err

    row = db_in_tmp.find("queue", qid)
    assert row["status"] == "failed"
    assert row["error"] == "upstream changed"


def test_claim_unknown_id(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    rc = run_queue.main(["--claim", "q-does-not-exist"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "not found" in captured.err


def test_claim_already_claimed(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    assert run_queue.main(["--claim", qid]) == 0
    capsys.readouterr()
    rc = run_queue.main(["--claim", qid])
    captured = capsys.readouterr()
    assert rc == 1
    assert "cannot claim" in captured.err


def test_complete_flips_done_and_attaches_deliverable(
    db_in_tmp, repo_in_tmp, capsys
):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    assert run_queue.main(["--claim", qid]) == 0
    capsys.readouterr()

    rc = run_queue.main(
        ["--complete", qid, "--deliverable", "tasks/t-runq/artifacts/s2/out.md"]
    )
    assert rc == 0

    qrow = db_in_tmp.find("queue", qid)
    assert qrow["status"] == "done"
    assert qrow["result_path"] == "tasks/t-runq/artifacts/s2/out.md"

    trow = db_in_tmp.find("tasks", "t-runq")
    s2 = next(s for s in trow["steps"] if s["step_id"] == "s2")
    assert s2["status"] == "complete"
    assert "tasks/t-runq/artifacts/s2/out.md" in s2["deliverable_paths"]


def test_complete_requires_deliverable(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    rc = run_queue.main(["--complete", qid])
    captured = capsys.readouterr()
    assert rc == 1
    assert "requires at least one --deliverable" in captured.err


def test_fail_marks_failed_with_error(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    rc = run_queue.main(["--fail", qid, "--error", "data feed offline"])
    captured = capsys.readouterr()
    assert rc == 0
    assert "data feed offline" in captured.out

    row = db_in_tmp.find("queue", qid)
    assert row["status"] == "failed"
    assert row["error"] == "data feed offline"


def test_fail_requires_error(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    rc = run_queue.main(["--fail", qid])
    captured = capsys.readouterr()
    assert rc == 1
    assert "requires --error" in captured.err


def test_fail_refuses_already_done(db_in_tmp, repo_in_tmp, capsys):
    from scripts import run_queue

    qid = _seed_for_queue(db_in_tmp, repo_in_tmp)
    db_in_tmp.update("queue", qid, {"status": "done", "completed_at": _now_iso()})

    rc = run_queue.main(["--fail", qid, "--error", "too late"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "already" in captured.err
