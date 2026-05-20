"""Tests for web.models — pydantic row schemas."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


def _now() -> datetime:
    return datetime(2026, 5, 16, 13, 0, 0, tzinfo=timezone.utc)


def test_team_member_minimum_valid():
    from web.models import TeamMember

    m = TeamMember(id="alice", name="Alice", kind="human", created_at=_now())
    assert m.active is True
    assert m.role_tags == []


def test_team_member_rejects_bad_id():
    from web.models import TeamMember

    with pytest.raises(ValidationError):
        TeamMember(id="UPPER", name="x", kind="human", created_at=_now())
    with pytest.raises(ValidationError):
        TeamMember(id="-leading-dash", name="x", kind="human", created_at=_now())


def test_team_member_rejects_extra_fields():
    from web.models import TeamMember

    with pytest.raises(ValidationError, match="extra_forbidden"):
        TeamMember(
            id="x", name="X", kind="human", created_at=_now(), made_up_field=True
        )


def test_team_member_kind_must_be_human_or_ai():
    from web.models import TeamMember

    with pytest.raises(ValidationError):
        TeamMember(id="x", name="X", kind="alien", created_at=_now())


def test_standard_work_with_steps():
    from web.models import StandardWork, StandardWorkStep

    sw = StandardWork(
        id="sw-1",
        name="Monthly close",
        owner_role="controller",
        steps=[
            StandardWorkStep(
                id="step1",
                name="Pull GL",
                owner_role="controller",
                kind="ai",
                ai_capability_hint="controller",
            ),
            StandardWorkStep(
                id="step2",
                name="Review",
                owner_role="cfo",
                kind="human",
                depends_on=["step1"],
                checkpoint=True,
            ),
        ],
        created_at=_now(),
        updated_at=_now(),
    )
    assert len(sw.steps) == 2
    assert sw.steps[1].depends_on == ["step1"]
    assert sw.steps[1].checkpoint is True


def test_task_status_enums():
    from web.models import Task

    t = Task(
        id="t-001",
        standard_work_id="sw-1",
        title="Close 2026-05",
        created_at=_now(),
    )
    assert t.status == "draft"
    with pytest.raises(ValidationError):
        Task(
            id="t-002",
            standard_work_id="sw-1",
            title="x",
            status="invalid_status",
            created_at=_now(),
        )


def test_task_step_instance_default_status_is_pending():
    from web.models import TaskStepInstance

    s = TaskStepInstance(step_id="step1")
    assert s.status == "pending"
    assert s.deliverable_paths == []
    assert s.comments == []


def test_queue_item_serializes_round_trip():
    from web.models import QueueItem

    raw = {
        "id": "q-1",
        "task_id": "t-1",
        "step_id": "s-1",
        "queued_at": _now().isoformat(),
        "status": "pending",
        "bundle_path": "tasks/t-1/queue/s-1.md",
        "agent_role": "fpa",
        "skill_hints": [],
        "upstream_hash": "deadbeef",
    }
    item = QueueItem.model_validate(raw)
    dumped = item.model_dump(mode="json")
    assert dumped["id"] == "q-1"
    assert dumped["status"] == "pending"


def test_schedule_minimum_valid():
    from web.models import Schedule

    s = Schedule(
        id="sch-1",
        name="Monthly close",
        standard_work_id="sw-1",
        cron="0 9 1 * *",
        created_at=_now(),
    )
    assert s.enabled is True
    assert s.brief_template == {}
