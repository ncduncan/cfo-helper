"""Forge queue bundle writer.

Builds a markdown bundle on disk for a (task, step) pair and appends a row
to the queue collection. The bundle is the single source of truth the
runner reads when draining from VS Code: it carries the standard-work
context, the step's instructions, and the deliverables of every upstream
step the work depends on.

The producer (M4: auto-queue on step-complete) calls ``build_and_queue``;
the consumer (M5: scripts/run_queue.py) reads the bundle, runs the work,
and writes results back via ``--complete``. Staleness is detected via the
``upstream_hash`` field — if upstream deliverables change between queue
and claim, the runner aborts with ``error="upstream changed"``.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from web import db
from web.models import QueueItem

# REPO_ROOT is the filesystem root for tasks/<task_id>/queue/<step_id>.md.
# Tests monkeypatch this to a tmp directory.
REPO_ROOT: Path = Path(__file__).resolve().parent.parent


def build_and_queue(task_id: str, step_id: str) -> str:
    """Write a queue bundle to disk and append a row to db/queue.json.

    Returns the queue item id. Raises ``KeyError`` if task or step cannot
    be resolved, ``ValueError`` if a ``depends_on`` reference is broken.
    """
    task = db.find("tasks", task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id!r}")

    step_instance = _find_step_instance(task, step_id)
    if step_instance is None:
        raise KeyError(
            f"step instance {step_id!r} not found on task {task_id!r}"
        )

    sw_id = task.get("standard_work_id")
    if not sw_id:
        raise ValueError(f"task {task_id!r} missing standard_work_id")
    sw = db.find("standard_work", sw_id)
    if sw is None:
        raise KeyError(f"standard_work not found: {sw_id!r}")

    sw_step = _find_sw_step(sw, step_id)
    if sw_step is None:
        raise KeyError(
            f"standard_work {sw_id!r} has no step {step_id!r}"
        )

    upstream_paths = _resolve_upstream_paths(task, sw_step)
    upstream_hash = _hash_paths(upstream_paths)

    bundle_rel = f"tasks/{task_id}/queue/{step_id}.md"
    bundle_abs = REPO_ROOT / bundle_rel
    bundle_abs.parent.mkdir(parents=True, exist_ok=True)
    bundle_abs.write_text(
        _render_bundle(
            task=task,
            sw=sw,
            sw_step=sw_step,
            upstream_paths=upstream_paths,
            upstream_hash=upstream_hash,
        )
    )

    queue_id = f"q-{task_id}-{step_id}-{_epoch_ms()}"
    agent_role = sw_step.get("ai_capability_hint") or sw_step.get("owner_role")
    queued_at = _now_iso()
    item = QueueItem.model_validate(
        {
            "id": queue_id,
            "task_id": task_id,
            "step_id": step_id,
            "queued_at": queued_at,
            "status": "pending",
            "bundle_path": bundle_rel,
            "agent_role": agent_role,
            "skill_hints": [],
            "upstream_hash": upstream_hash,
        }
    )
    db.insert("queue", item.model_dump(mode="json"))
    return queue_id


def compute_upstream_hash(task_id: str, step_id: str) -> str:
    """Recompute the upstream hash for a (task, step).

    Used by the runner to detect staleness — if the queue item's stored
    ``upstream_hash`` differs from the current value, the run is rejected
    with ``status=failed``, ``error="upstream changed"``.
    """
    task = db.find("tasks", task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id!r}")
    sw_id = task.get("standard_work_id")
    if not sw_id:
        raise ValueError(f"task {task_id!r} missing standard_work_id")
    sw = db.find("standard_work", sw_id)
    if sw is None:
        raise KeyError(f"standard_work not found: {sw_id!r}")
    sw_step = _find_sw_step(sw, step_id)
    if sw_step is None:
        raise KeyError(
            f"standard_work {sw_id!r} has no step {step_id!r}"
        )
    upstream_paths = _resolve_upstream_paths(task, sw_step)
    return _hash_paths(upstream_paths)


# --- internals --------------------------------------------------------------


def _find_step_instance(task: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    for s in task.get("steps", []):
        if s.get("step_id") == step_id:
            return s
    return None


def _find_sw_step(sw: dict[str, Any], step_id: str) -> dict[str, Any] | None:
    for s in sw.get("steps", []):
        if s.get("id") == step_id:
            return s
    return None


def _resolve_upstream_paths(
    task: dict[str, Any], sw_step: dict[str, Any]
) -> list[str]:
    """Return sorted list of deliverable paths from completed predecessors.

    A predecessor without ``status == "complete"`` contributes no paths
    (the queue producer is expected to gate on all-deps-complete; here we
    just snapshot what's present).
    """
    deps = list(sw_step.get("depends_on") or [])
    by_step: dict[str, dict[str, Any]] = {
        s.get("step_id"): s for s in task.get("steps", []) if s.get("step_id")
    }
    paths: list[str] = []
    for dep_id in deps:
        inst = by_step.get(dep_id)
        if not inst:
            raise ValueError(
                f"depends_on references unknown step {dep_id!r} on task "
                f"{task.get('id')!r}"
            )
        if inst.get("status") != "complete":
            continue
        for p in inst.get("deliverable_paths") or []:
            paths.append(p)
    paths.sort()
    return paths


def _hash_paths(paths: list[str]) -> str:
    """SHA256 over the sorted list of ``(relative_path, file_bytes)`` pairs.

    Missing files contribute their path + an empty body so a later
    appearance still changes the hash. Paths are encoded as UTF-8 with a
    trailing NUL so ``a/b`` cannot collide with ``a`` + ``b``.
    """
    h = hashlib.sha256()
    for rel in paths:
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        abs_path = REPO_ROOT / rel
        try:
            h.update(abs_path.read_bytes())
        except FileNotFoundError:
            h.update(b"")
        h.update(b"\x00")
    return h.hexdigest()


def _render_bundle(
    *,
    task: dict[str, Any],
    sw: dict[str, Any],
    sw_step: dict[str, Any],
    upstream_paths: list[str],
    upstream_hash: str,
) -> str:
    frontmatter = _yaml_frontmatter(
        {
            "task_id": task["id"],
            "step_id": sw_step["id"],
            "agent_role": (
                sw_step.get("ai_capability_hint") or sw_step.get("owner_role")
            ),
            "skill_hints": [],
            "upstream_hash": upstream_hash,
        }
    )

    sections: list[str] = [frontmatter]
    sections.append(f"# {task.get('title') or task['id']}\n")
    sections.append(f"**Step:** {sw_step.get('name') or sw_step['id']}\n")
    sections.append(f"**Standard Work:** {sw.get('name') or sw['id']}\n")

    sections.append("\n## Standard Work — Context\n")
    sections.append((sw.get("context_md") or "_(empty)_").rstrip() + "\n")

    sections.append("\n## Standard Work — Requirements\n")
    sections.append((sw.get("requirements_md") or "_(empty)_").rstrip() + "\n")

    sections.append("\n## Step Instructions\n")
    sections.append((sw_step.get("instructions_md") or "_(empty)_").rstrip() + "\n")

    sections.append("\n## Inputs (deliverables of upstream steps)\n")
    if upstream_paths:
        for p in upstream_paths:
            sections.append(f"- `{p}`\n")
    else:
        sections.append("_(no upstream deliverables)_\n")

    sections.append("\n## Upstream Hash\n")
    sections.append(f"`{upstream_hash}`\n")
    sections.append(
        "\nIf this hash no longer matches at claim time, the runner aborts "
        'with `error="upstream changed"`.\n'
    )
    return "".join(sections)


def _yaml_frontmatter(meta: dict[str, Any]) -> str:
    """Minimal YAML frontmatter writer — no external dep.

    Handles strings, ints, bools, None, and flat ``list[str]``. Sufficient
    for our metadata shape (task_id, step_id, agent_role, skill_hints,
    upstream_hash).
    """
    lines = ["---"]
    for key, val in meta.items():
        if val is None:
            lines.append(f"{key}: null")
        elif isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key}: {val}")
        elif isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(val)}")
    lines.append("---\n")
    return "\n".join(lines)


def _yaml_scalar(val: Any) -> str:
    s = str(val)
    if any(c in s for c in [":", "#", "'", '"', "\n", "{", "}", "[", "]", ","]):
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _epoch_ms() -> int:
    return int(time.time() * 1000)


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(tz=timezone.utc).isoformat()
