"""Seed standard_work rows from ``task_types/*.yaml``.

For each YAML file: produce one StandardWork row whose ``steps`` are the
YAML's ``pipeline`` entries, converted as follows::

    pipeline[i].phase            -> step.id     (lowercased, e.g. "p1")
    pipeline[i].agent            -> step.owner_role
                                  + step.ai_capability_hint
    pipeline[i].instructions     -> step.instructions_md
    pipeline[i].deterministic_runner -> appended to step.inputs
    pipeline[i].may_consult      -> appended to step.requires_access

Defaults:
- ``kind="ai"`` on every step. The CFO promotes steps to ``human`` in the UI
  (or in code) after seeding — typically the "approve" / "checkpoint" steps.
- ``default_assignee_id="forge"`` for ai steps (matches the seeded Forge id).
- ``depends_on=[previous step id]`` — pipelines are sequential.

Idempotent: re-running prints ``already seeded`` and exits 0 if any
template row exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from web import db
from web.models import StandardWork


REPO = Path(__file__).resolve().parent.parent
TASK_TYPES_DIR = REPO / "task_types"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _slug(s: str) -> str:
    return (
        s.lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("(", "")
        .replace(")", "")
    )


def _convert(yaml_path: Path, now: str) -> dict[str, Any]:
    spec = yaml.safe_load(yaml_path.read_text())
    name = spec.get("name") or yaml_path.stem
    title = spec.get("title_template", name)
    pipeline = spec.get("pipeline") or []

    steps: list[dict[str, Any]] = []
    prev_id: str | None = None
    for i, p in enumerate(pipeline, start=1):
        phase = (p.get("phase") or f"p{i}").lower()
        agent = p.get("agent") or "fpa"
        instructions = p.get("instructions") or ""
        inputs: list[str] = []
        det = p.get("deterministic_runner")
        if det:
            inputs.append(f"runner:{det}")
        requires_access: list[str] = []
        for who in p.get("may_consult") or []:
            requires_access.append(f"consult:{who}")
        step = {
            "id": phase,
            "name": f"{phase.upper()} — {agent}",
            "instructions_md": instructions.strip(),
            "owner_role": agent,
            "default_assignee_id": "forge",
            "kind": "ai",
            "depends_on": [prev_id] if prev_id else [],
            "est_minutes": None,
            "requires_access": requires_access,
            "inputs": inputs,
            "outputs": [],
            "ai_capability_hint": agent,
            "checkpoint": False,
        }
        steps.append(step)
        prev_id = phase

    requirements_lines: list[str] = []
    for f in spec.get("brief_schema") or []:
        field = f.get("field") or "?"
        ftype = f.get("type") or "?"
        label = f.get("label") or ""
        req = " (required)" if f.get("required") else ""
        requirements_lines.append(
            f"- **{field}** (`{ftype}`{req}) — {label}".rstrip(" —")
        )

    row = {
        "id": _slug(name),
        "name": title,
        "source_task_type": name,
        "owner_role": (steps[0]["owner_role"] if steps else "fpa"),
        "cadence": spec.get("cadence"),
        "context_md": (spec.get("description") or "").strip(),
        "requirements_md": "\n".join(requirements_lines),
        "due_offset_days": int(spec.get("due_offset_days") or 0),
        "steps": steps,
        "created_at": now,
        "updated_at": now,
    }
    StandardWork.model_validate(row)
    return row


def main() -> int:
    db.init_db()
    if db.rows("standard_work"):
        print("already seeded (standard_work non-empty) — no changes")
        return 0
    now = _now_iso()
    paths = sorted(TASK_TYPES_DIR.glob("*.yaml"))
    inserted = 0
    for p in paths:
        row = _convert(p, now)
        if db.find("standard_work", row["id"]):
            continue
        db.insert("standard_work", row)
        inserted += 1
    print(f"seeded {inserted} standard_work template(s) from {len(paths)} YAML file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
