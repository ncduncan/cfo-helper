"""Retrospective Lean metrics — handoff count, cycle time, queue dwell, VA ratio.

Pure functions over inputs. Reads:

- ``task_types/*.yaml`` — for handoff count and CFO-checkpoint inflation.
- ``profile/db/tasks.json`` via :func:`web.db.rows` — for completed cycle
  time and value-add ratio (active-time / wall-time).
- ``profile/db/queue.json`` via :func:`web.db.rows` — for completed
  queue-item dwell (queued → claimed).

CLI for smoke testing::

    python -m scripts.lean.metrics --task-types task_types/ --json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from scripts.lean import NOT_APPLICABLE
from scripts.paths import REPO_ROOT


# ---------------------------------------------------------------------------
# Template-level metrics (from task_types/*.yaml)
# ---------------------------------------------------------------------------


def _load_task_type(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f) or {}


def handoff_count(task_type_doc: dict) -> int:
    """Count owner_role transitions across a task_type pipeline.

    A "handoff" is a phase boundary where the agent role changes. Five
    phases by five different agents = 4 handoffs. Five phases by one agent
    = 0 handoffs. Lean prefers fewer handoffs.
    """
    pipeline = task_type_doc.get("pipeline") or []
    roles = [p.get("agent") for p in pipeline if p.get("agent")]
    if len(roles) < 2:
        return 0
    return sum(1 for a, b in zip(roles, roles[1:]) if a != b)


def cfo_checkpoint_count(task_type_doc: dict) -> int:
    """Count phases that imply a synchronous CFO checkpoint.

    Heuristic: any phase whose instructions or description mention
    ``CFO`` and ``approval`` or ``sign-off`` is treated as a checkpoint.
    The Lean lens flags excess checkpoints as a waiting/over-processing
    pattern.
    """
    pipeline = task_type_doc.get("pipeline") or []
    count = 0
    for phase in pipeline:
        text = " ".join(
            str(phase.get(k, "")) for k in ("description", "instructions")
        ).lower()
        if "cfo" in text and ("approval" in text or "sign-off" in text or "approve" in text):
            count += 1
    return count


def phase_count(task_type_doc: dict) -> int:
    return len(task_type_doc.get("pipeline") or [])


def scan_task_types(task_types_dir: Path) -> dict[str, dict[str, int]]:
    """Per-template summary: phase count, handoff count, CFO checkpoint count."""
    out: dict[str, dict[str, int]] = {}
    for yml in sorted(task_types_dir.glob("*.yaml")):
        doc = _load_task_type(yml)
        name = doc.get("name") or yml.stem
        out[name] = {
            "phases": phase_count(doc),
            "handoffs": handoff_count(doc),
            "cfo_checkpoints": cfo_checkpoint_count(doc),
        }
    return out


# ---------------------------------------------------------------------------
# Live-history metrics (from profile/db/tasks.json + queue.json)
# ---------------------------------------------------------------------------


def _parse_iso(s: Any) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _completed_task_cycle_days(task: dict) -> float | None:
    """Wall-clock days between created_at and completed_at for a complete task."""
    if task.get("status") != "complete":
        return None
    created = _parse_iso(task.get("created_at"))
    completed = _parse_iso(task.get("completed_at"))
    if not created or not completed:
        return None
    return (completed - created).total_seconds() / 86400.0


def _completed_task_active_days(task: dict) -> float | None:
    """Sum of in-progress (started_at → completed_at) durations across steps.

    This is the Lean "value-add time" proxy at task grain: time the work
    was actually being touched, not waiting in a queue or between steps.
    """
    if task.get("status") != "complete":
        return None
    total_s = 0.0
    for step in task.get("steps") or []:
        s = _parse_iso(step.get("started_at"))
        c = _parse_iso(step.get("completed_at"))
        if s and c and c >= s:
            total_s += (c - s).total_seconds()
    if total_s <= 0:
        return None
    return total_s / 86400.0


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def cycle_time_percentiles(tasks: list[dict]) -> dict[str, Any]:
    """p50, p90 wall-clock cycle days across completed tasks."""
    cycles = [d for t in tasks if (d := _completed_task_cycle_days(t)) is not None]
    if not cycles:
        return {"p50_days": NOT_APPLICABLE, "p90_days": NOT_APPLICABLE, "n": 0}
    return {
        "p50_days": round(_percentile(cycles, 0.5) or 0.0, 2),
        "p90_days": round(_percentile(cycles, 0.9) or 0.0, 2),
        "n": len(cycles),
    }


def value_add_ratio(tasks: list[dict]) -> dict[str, Any]:
    """Across completed tasks, ratio of summed active-step time to wall-clock cycle.

    100% means no wait between steps. 20% means 80% of elapsed time was
    waiting (queue, checkpoint, idle).
    """
    pairs = []
    for t in tasks:
        wall = _completed_task_cycle_days(t)
        active = _completed_task_active_days(t)
        if wall is not None and active is not None and wall > 0:
            pairs.append((active, wall))
    if not pairs:
        return {"va_pct": NOT_APPLICABLE, "flow_efficiency_pct": NOT_APPLICABLE, "n": 0}
    total_active = sum(a for a, _ in pairs)
    total_wall = sum(w for _, w in pairs)
    pct = round(100.0 * total_active / total_wall, 2) if total_wall > 0 else 0.0
    return {"va_pct": pct, "flow_efficiency_pct": pct, "n": len(pairs)}


def queue_dwell_percentiles(queue: list[dict]) -> dict[str, Any]:
    """p50, p90 hours from queued_at to claimed_at for completed queue items."""
    dwells_s: list[float] = []
    for q in queue:
        queued = _parse_iso(q.get("queued_at"))
        claimed = _parse_iso(q.get("claimed_at"))
        if queued and claimed and claimed >= queued:
            dwells_s.append((claimed - queued).total_seconds())
    if not dwells_s:
        return {"p50_hours": NOT_APPLICABLE, "p90_hours": NOT_APPLICABLE, "n": 0}
    hours = [s / 3600.0 for s in dwells_s]
    return {
        "p50_hours": round(_percentile(hours, 0.5) or 0.0, 2),
        "p90_hours": round(_percentile(hours, 0.9) or 0.0, 2),
        "n": len(hours),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute(
    *,
    task_types_dir: Path | None = None,
    db_dir: Path | None = None,
) -> dict[str, Any]:
    """Compute all retrospective Lean metrics.

    Both inputs are optional. Missing inputs surface as ``not_applicable``
    in their section of the result rather than failing the run.
    """
    result: dict[str, Any] = {
        "templates": NOT_APPLICABLE,
        "cycle_time": NOT_APPLICABLE,
        "value_add": NOT_APPLICABLE,
        "queue_dwell": NOT_APPLICABLE,
    }

    if task_types_dir is None:
        task_types_dir = REPO_ROOT / "task_types"
    if task_types_dir.exists():
        result["templates"] = scan_task_types(task_types_dir)

    # Live db reads — empty list when file absent (web.db.rows already
    # handles that). NOT_APPLICABLE is reserved for "no completed data
    # in the window," not "file missing."
    try:
        from web import db
        tasks = db.rows("tasks")
        queue = db.rows("queue")
    except Exception:
        tasks, queue = [], []

    if tasks:
        result["cycle_time"] = cycle_time_percentiles(tasks)
        result["value_add"] = value_add_ratio(tasks)
    if queue:
        result["queue_dwell"] = queue_dwell_percentiles(queue)

    return result


def _cli() -> None:
    p = argparse.ArgumentParser(prog="scripts.lean.metrics")
    p.add_argument(
        "--task-types",
        type=Path,
        default=REPO_ROOT / "task_types",
        help="Path to task_types/ directory (default: repo-root/task_types)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON (default: pretty print)",
    )
    args = p.parse_args()
    out = compute(task_types_dir=args.task_types)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for section, value in out.items():
            print(f"\n== {section} ==")
            print(json.dumps(value, indent=2))


if __name__ == "__main__":
    _cli()
