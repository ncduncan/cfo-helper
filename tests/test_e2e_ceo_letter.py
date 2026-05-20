"""End-to-end smoke test — instantiate, queue, complete, audit-gate.

Walks a minimal 3-step pipeline (human → ai → ai) the way a CEO-letter
task moves through the system. Exercises:
- M3 standard_work + M4 instantiate
- M4 step start / complete with auto-queue
- M5 run_queue claim / complete
- M8 claim-id audit gate (rejects empty claims) + memory-write staging
"""

from __future__ import annotations

import json
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
    from scripts import run_queue
    from web import bundles

    monkeypatch.setattr(bundles, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(run_queue, "REPO_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def client(db_in_tmp, repo_in_tmp):
    from web.routes import tasks as tasks_routes

    app = FastAPI()
    app.include_router(tasks_routes.router)
    return TestClient(app)


def _now() -> str:
    return datetime(2026, 5, 16, tzinfo=timezone.utc).isoformat()


def _seed(db):
    db.insert(
        "team",
        {
            "id": "forge",
            "name": "Forge",
            "email": None,
            "kind": "ai",
            "role_tags": ["reporting", "reviewer"],
            "active": True,
            "created_at": _now(),
        },
    )
    db.insert(
        "team",
        {
            "id": "fpa_analyst",
            "name": "FPA Analyst",
            "email": None,
            "kind": "human",
            "role_tags": ["fpa", "fpa_analyst"],
            "active": True,
            "created_at": _now(),
        },
    )
    db.insert(
        "standard_work",
        {
            "id": "ceo_letter",
            "name": "CEO letter",
            "source_task_type": "ceo_letter",
            "owner_role": "fpa",
            "cadence": None,
            "context_md": "",
            "requirements_md": "",
            "due_offset_days": 0,
            "steps": [
                {
                    "id": "gather",
                    "name": "Gather inputs",
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
                    "id": "draft",
                    "name": "Forge drafts narrative",
                    "instructions_md": "",
                    "owner_role": "reporting",
                    "default_assignee_id": "forge",
                    "kind": "ai",
                    "depends_on": ["gather"],
                    "est_minutes": None,
                    "requires_access": [],
                    "inputs": [],
                    "outputs": [],
                    "ai_capability_hint": "reporting",
                    "checkpoint": False,
                },
                {
                    "id": "review",
                    "name": "Forge reviews",
                    "instructions_md": "",
                    "owner_role": "reviewer",
                    "default_assignee_id": "forge",
                    "kind": "ai",
                    "depends_on": ["draft"],
                    "est_minutes": None,
                    "requires_access": [],
                    "inputs": [],
                    "outputs": [],
                    "ai_capability_hint": "reviewer",
                    "checkpoint": False,
                },
            ],
            "created_at": _now(),
            "updated_at": _now(),
        },
    )


def test_full_walkthrough_with_claim_id_gate(client, db_in_tmp, repo_in_tmp):
    from scripts import run_queue
    from web import instantiate

    _seed(db_in_tmp)
    t = instantiate.instantiate_task("ceo_letter", period="2026-05")
    task_id = t["id"]

    # Step 1 — human gather: start + complete.
    assert client.post(f"/tasks/{task_id}/steps/gather/start", follow_redirects=False).status_code == 303
    art_dir = repo_in_tmp / f"tasks/{task_id}/artifacts/gather"
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "raw.csv").write_bytes(b"a,b\n1,2\n")
    r = client.post(
        f"/tasks/{task_id}/steps/gather/complete",
        data={"deliverable": f"tasks/{task_id}/artifacts/gather/raw.csv"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # Auto-queue fired step 2 for Forge.
    pending = [r for r in db_in_tmp.rows("queue") if r["step_id"] == "draft"]
    assert len(pending) == 1
    qid = pending[0]["id"]

    # Forge claims via CLI.
    assert run_queue.main(["--claim", qid]) == 0

    # Forge first tries to complete with an empty-claims work_product → audit gate would reject.
    # Simulate the CFO-side rejection by writing a proper work_product before --complete.
    draft_dir = repo_in_tmp / f"tasks/{task_id}/artifacts/draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    bad_wp = draft_dir / "work_product.json"
    bad_wp.write_text(json.dumps({"claims": []}))
    # The CLI's --complete doesn't run the audit (CLI is server-side; audit is in
    # the HTTP completion gate). The audit fires when the user uses the dashboard.
    # For this e2e we test the audit directly:
    from web import audit, bundles

    r1 = audit.audit_claim_ids(
        [f"tasks/{task_id}/artifacts/draft/work_product.json"],
        bundles.REPO_ROOT,
        required=True,
    )
    assert r1["ok"] is False  # empty claims rejected

    # Rewrite the work_product with proper claims + a memory-write request.
    good = {
        "claims": [
            {
                "id": "rev_total",
                "value": 8200000,
                "provenance": {"source": f"tasks/{task_id}/artifacts/gather/raw.csv"},
            }
        ],
        "requests": [
            {
                "kind": "memory_write",
                "target_path": "memory/recurring_items.md",
                "operation": "append",
                "payload": "- Customer X SaaS ramp (months 1-3)",
            }
        ],
    }
    bad_wp.write_text(json.dumps(good))
    r2 = audit.audit_claim_ids(
        [f"tasks/{task_id}/artifacts/draft/work_product.json"],
        bundles.REPO_ROOT,
        required=True,
    )
    assert r2["ok"] is True

    # Forge calls --complete on the CLI, which flips the queue + step.
    assert run_queue.main(
        ["--complete", qid, "--deliverable", f"tasks/{task_id}/artifacts/draft/work_product.json"]
    ) == 0

    # Step 3 (review) should have been auto-queued by the post-complete hook.
    pending_review = [
        r for r in db_in_tmp.rows("queue") if r["step_id"] == "review" and r["status"] == "pending"
    ]
    assert len(pending_review) == 1

    # Complete the review through the CLI (no audit on CLI; that's an HTTP-path gate).
    qid2 = pending_review[0]["id"]
    assert run_queue.main(["--claim", qid2]) == 0
    review_dir = repo_in_tmp / f"tasks/{task_id}/artifacts/review"
    review_dir.mkdir(parents=True, exist_ok=True)
    findings = {
        "agent": "reviewer",
        "period": "2026-05",
        "produced_at": _now(),
        "sign_off": "signed_off",
        "findings": [],
        "independent_recomputations": [],
    }
    (review_dir / "findings.json").write_text(json.dumps(findings))
    (review_dir / "work_product.json").write_text(
        json.dumps(
            {
                "claims": [
                    {
                        "id": "rev_recomp",
                        "value": 8200000,
                        "provenance": {"source": "independent recompute"},
                    }
                ]
            }
        )
    )
    assert run_queue.main(
        [
            "--complete",
            qid2,
            "--deliverable",
            f"tasks/{task_id}/artifacts/review/work_product.json",
            "--deliverable",
            f"tasks/{task_id}/artifacts/review/findings.json",
        ]
    ) == 0

    # The task is "complete" structurally, but memory_proposals isn't fed by
    # the CLI path. So status should derive complete here. (HTTP completion
    # would stage memory writes — covered by test_web_tasks_audit_gate below.)
    final_task = db_in_tmp.find("tasks", task_id)
    assert final_task["status"] == "complete"


def test_http_complete_stages_memory_writes_and_blocks_until_approved(
    client, db_in_tmp, repo_in_tmp
):
    """When the user completes a step via the HTTP form (not CLI), the
    audit + memory-write staging gates fire."""
    from web import instantiate

    _seed(db_in_tmp)
    t = instantiate.instantiate_task("ceo_letter", period="x")
    task_id = t["id"]

    # Pre-fill: start + complete gather → auto-queues draft.
    client.post(f"/tasks/{task_id}/steps/gather/start", follow_redirects=False)
    art = repo_in_tmp / f"tasks/{task_id}/artifacts/gather"
    art.mkdir(parents=True, exist_ok=True)
    (art / "x.txt").write_bytes(b"x")
    client.post(
        f"/tasks/{task_id}/steps/gather/complete",
        data={"deliverable": f"tasks/{task_id}/artifacts/gather/x.txt"},
        follow_redirects=False,
    )

    # Now simulate Forge having written its work_product with a memory write.
    draft_dir = repo_in_tmp / f"tasks/{task_id}/artifacts/draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    wp = {
        "claims": [
            {
                "id": "rev",
                "value": 100,
                "provenance": {"source": f"tasks/{task_id}/artifacts/gather/x.txt"},
            }
        ],
        "requests": [
            {
                "kind": "memory_write",
                "target_path": "memory/recurring_items.md",
                "operation": "append",
                "payload": "- noted pattern",
            }
        ],
    }
    (draft_dir / "work_product.json").write_text(json.dumps(wp))

    # Complete via HTTP — this is the path that runs the audit + stages
    # the memory proposal. Step `draft` is AI-kind; complete via the
    # endpoint requires status=in_progress, so flip it manually via DB
    # (Forge would normally do this via run_queue --claim).
    db_in_tmp.write(
        "tasks",
        lambda doc: _set_step_status(doc, task_id, "draft", "in_progress"),
    )
    r = client.post(
        f"/tasks/{task_id}/steps/draft/complete",
        data={"deliverable": f"tasks/{task_id}/artifacts/draft/work_product.json"},
        follow_redirects=False,
    )
    assert r.status_code == 303

    # One memory_proposals row should be staged, status=pending.
    proposals = [
        p for p in db_in_tmp.rows("memory_proposals") if p["task_id"] == task_id
    ]
    assert len(proposals) == 1
    assert proposals[0]["status"] == "pending"


def _set_step_status(doc, task_id, step_id, status):
    for t in doc["rows"]:
        if t.get("id") != task_id:
            continue
        for s in t.get("steps") or []:
            if s.get("step_id") == step_id:
                s["status"] = status
                if status == "in_progress" and not s.get("started_at"):
                    s["started_at"] = _now()
    return doc
