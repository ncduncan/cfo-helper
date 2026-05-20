"""
Pydantic row models for the JSON DB.

Validation is invoked by route handlers before passing rows to ``web.db``
``upsert/insert/update``. Field shapes are designed to evolve additively —
adding an optional field does not require a migration; removing or renaming
requires a one-shot migrator under ``scripts/migrate_db_*.py``.

Shared rules:
- ``id`` is lowercase + digits + ``-``/``_`` only; max 64 chars (80 for tasks).
- All datetimes are timezone-aware ISO 8601. Pydantic serializes with a
  trailing ``Z`` for UTC — tests should parse with
  ``datetime.fromisoformat(s.replace("Z", "+00:00"))``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Team -------------------------------------------------------------------

MemberKind = Literal["human", "ai"]


class TeamMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    email: Optional[str] = None
    kind: MemberKind
    role_tags: list[str] = Field(default_factory=list)
    active: bool = True
    created_at: datetime


# --- Standard Work ----------------------------------------------------------

StepKind = Literal["human", "ai"]


class StandardWorkStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
    name: str = Field(min_length=1, max_length=160)
    instructions_md: str = ""
    owner_role: str
    default_assignee_id: Optional[str] = None
    kind: StepKind
    depends_on: list[str] = Field(default_factory=list)
    est_minutes: Optional[int] = Field(default=None, ge=0)
    requires_access: list[str] = Field(default_factory=list)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    ai_capability_hint: Optional[str] = None
    checkpoint: bool = False


class StandardWork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
    name: str = Field(min_length=1, max_length=160)
    source_task_type: Optional[str] = None
    owner_role: str
    cadence: Optional[str] = None
    context_md: str = ""
    requirements_md: str = ""
    due_offset_days: int = 0
    steps: list[StandardWorkStep] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# --- Tasks ------------------------------------------------------------------

TaskStatus = Literal["draft", "in_progress", "blocked", "complete", "aborted"]
StepStatus = Literal[
    "pending", "blocked", "queued", "in_progress", "complete", "failed"
]


class TaskComment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_id: str
    body_md: str
    at: datetime


class TaskStepInstance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str
    assignee_id: Optional[str] = None
    status: StepStatus = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    deliverable_paths: list[str] = Field(default_factory=list)
    findings_ref: Optional[str] = None
    comments: list[TaskComment] = Field(default_factory=list)


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=80)
    standard_work_id: str
    period: Optional[str] = None
    title: str = Field(min_length=1, max_length=200)
    owner_id: Optional[str] = None
    status: TaskStatus = "draft"
    created_at: datetime
    due_date: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes_md: str = ""
    steps: list[TaskStepInstance] = Field(default_factory=list)


# --- Queue ------------------------------------------------------------------

QueueStatus = Literal["pending", "claimed", "done", "failed"]


class QueueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    task_id: str
    step_id: str
    queued_at: datetime
    claimed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: QueueStatus = "pending"
    bundle_path: str
    result_path: Optional[str] = None
    agent_role: Optional[str] = None
    skill_hints: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    upstream_hash: Optional[str] = None


# --- Schedules --------------------------------------------------------------


class Schedule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    standard_work_id: str
    cron: str
    timezone: str = "America/New_York"
    enabled: bool = True
    brief_template: dict = Field(default_factory=dict)
    created_at: datetime
    last_fire: Optional[datetime] = None
    last_fire_result: Optional[str] = None
