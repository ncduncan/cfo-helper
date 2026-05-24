"""Current-state WIP / pull-flow metrics.

Inspects in-progress work right now (not the historical record) to detect
push/overload dysfunction. Reads:

- ``profile/db/tasks.json`` — current step instances per task.
- ``profile/db/queue.json`` — current queue depth and per-item age.

Six checks, each producing a structured result the agent can claim:

1. ``wip_per_assignee`` — count of ``in_progress`` step instances per
   ``assignee_id``. Threshold: ``wip_limit_per_assignee`` (default 3).
2. ``queue_age`` — age of ``pending`` / ``claimed`` queue items.
   Threshold: ``queue_dwell_max_hours`` (default 24).
3. ``push_signals`` — assignees with new ``in_progress`` work *and* an
   existing ``in_progress`` step older than the configurable threshold
   ``push_overdue_hours`` (default 48).
4. ``bottleneck`` — role with the largest ratio of pending+queued to
   completed over a window of ``bottleneck_window_n`` tasks (default 20).
5. ``batch_coefficient`` — coefficient of variation of inter-completion
   gaps. Values close to 0 = even flow. Values > 1 = batched / clustered.
6. ``context_switching`` — assignees with simultaneous ``in_progress``
   steps spanning ``context_switch_simultaneous_max`` (default 2)
   distinct task ids.

Thresholds load from ``profile/memory/lean_thresholds.yaml`` (CFO-editable).
Falls back to baked-in defaults if absent.

CLI for smoke testing::

    python -m scripts.lean.wip_flow --json
"""

from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.lean import NOT_APPLICABLE
from scripts.paths import REPO_ROOT


DEFAULT_THRESHOLDS = {
    "wip_limit_per_assignee": 3,
    "queue_dwell_max_hours": 24,
    "push_overdue_hours": 48,
    "bottleneck_window_n": 20,
    "context_switch_simultaneous_max": 2,
}


def load_thresholds(profile_memory_dir: Path | None = None) -> dict[str, Any]:
    """Merge ``profile/memory/lean_thresholds.yaml`` over the defaults."""
    if profile_memory_dir is None:
        profile_memory_dir = REPO_ROOT / "profile" / "memory"
    path = profile_memory_dir / "lean_thresholds.yaml"
    merged = dict(DEFAULT_THRESHOLDS)
    if path.exists():
        try:
            with path.open() as f:
                user = yaml.safe_load(f) or {}
            if isinstance(user, dict):
                for k, v in user.items():
                    if k in merged and v is not None:
                        merged[k] = v
        except yaml.YAMLError:
            pass
    return merged


def _parse_iso(s: Any) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _hours_since(dt: datetime | None, now: datetime) -> float | None:
    if dt is None:
        return None
    return (now - dt).total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Individual checks — each returns a dict shaped for claim emission.
# ---------------------------------------------------------------------------


def wip_per_assignee(tasks: list[dict], thresholds: dict) -> dict[str, Any]:
    """Active step count per assignee. Flags any over the limit."""
    counts: dict[str, int] = {}
    for t in tasks:
        for s in t.get("steps") or []:
            if s.get("status") == "in_progress":
                a = s.get("assignee_id") or "(unassigned)"
                counts[a] = counts.get(a, 0) + 1
    limit = thresholds["wip_limit_per_assignee"]
    over = {a: n for a, n in counts.items() if n > limit}
    return {
        "by_assignee": counts,
        "wip_total": sum(counts.values()),
        "limit": limit,
        "over_limit": over,
    }


def queue_age(queue: list[dict], thresholds: dict, *, now: datetime | None = None) -> dict[str, Any]:
    """Age in hours of pending/claimed queue items."""
    if now is None:
        now = datetime.now(timezone.utc)
    ages_h: list[float] = []
    breaches: list[dict] = []
    threshold_h = thresholds["queue_dwell_max_hours"]
    for q in queue:
        if q.get("status") not in ("pending", "claimed"):
            continue
        age = _hours_since(_parse_iso(q.get("queued_at")), now)
        if age is None:
            continue
        ages_h.append(age)
        if age > threshold_h:
            breaches.append({
                "queue_id": q.get("id"),
                "task_id": q.get("task_id"),
                "step_id": q.get("step_id"),
                "agent_role": q.get("agent_role"),
                "age_hours": round(age, 2),
                "status": q.get("status"),
            })
    if not ages_h:
        return {
            "p50_hours": NOT_APPLICABLE,
            "p90_hours": NOT_APPLICABLE,
            "n_open": 0,
            "breach_threshold_hours": threshold_h,
            "breaches": [],
        }
    return {
        "p50_hours": round(statistics.median(ages_h), 2),
        "p90_hours": round(_percentile(ages_h, 0.9), 2),
        "n_open": len(ages_h),
        "breach_threshold_hours": threshold_h,
        "breaches": breaches,
    }


def push_signals(tasks: list[dict], thresholds: dict, *, now: datetime | None = None) -> dict[str, Any]:
    """Assignees who picked up new work while existing work has gone overdue."""
    if now is None:
        now = datetime.now(timezone.utc)
    overdue_h = thresholds["push_overdue_hours"]
    by_assignee: dict[str, dict[str, list]] = {}
    for t in tasks:
        for s in t.get("steps") or []:
            if s.get("status") != "in_progress":
                continue
            a = s.get("assignee_id") or "(unassigned)"
            age = _hours_since(_parse_iso(s.get("started_at")), now)
            if age is None:
                continue
            slot = by_assignee.setdefault(a, {"fresh": [], "overdue": []})
            entry = {
                "task_id": t.get("id"),
                "step_id": s.get("step_id"),
                "age_hours": round(age, 2),
            }
            if age > overdue_h:
                slot["overdue"].append(entry)
            else:
                slot["fresh"].append(entry)
    signals = [
        {"assignee_id": a, "fresh_count": len(d["fresh"]), "overdue_count": len(d["overdue"])}
        for a, d in by_assignee.items()
        if d["overdue"] and d["fresh"]
    ]
    return {
        "overdue_threshold_hours": overdue_h,
        "push_count": len(signals),
        "signals": signals,
    }


def bottleneck(tasks: list[dict], standard_work: list[dict], thresholds: dict) -> dict[str, Any]:
    """Role with the largest ratio of waiting to completed over the window.

    "Waiting" = step instances with status in {pending, queued, blocked,
    in_progress}. "Completed" = status complete. Higher ratio means more
    work piling up than getting done. The role with the highest ratio
    over the most-recent ``window_n`` task completions is the bottleneck.
    """
    window_n = thresholds["bottleneck_window_n"]
    sw_by_id = {sw.get("id"): sw for sw in standard_work}

    def step_role(task: dict, step_id: str) -> str | None:
        sw = sw_by_id.get(task.get("standard_work_id"))
        if not sw:
            return None
        for st in sw.get("steps") or []:
            if st.get("id") == step_id:
                return st.get("owner_role")
        return None

    # Limit attention to the most recently created tasks (or all if fewer)
    recent_tasks = sorted(
        tasks, key=lambda t: t.get("created_at") or "", reverse=True
    )[:window_n]

    waiting: dict[str, int] = {}
    completed: dict[str, int] = {}
    for t in recent_tasks:
        for s in t.get("steps") or []:
            role = step_role(t, s.get("step_id"))
            if not role:
                continue
            if s.get("status") == "complete":
                completed[role] = completed.get(role, 0) + 1
            elif s.get("status") in ("pending", "queued", "blocked", "in_progress"):
                waiting[role] = waiting.get(role, 0) + 1
    ratios: dict[str, float] = {}
    for role in set(waiting) | set(completed):
        w = waiting.get(role, 0)
        c = completed.get(role, 0)
        if w + c == 0:
            continue
        ratios[role] = round(w / (c + 1), 3)  # +1 smooths div-by-zero
    if not ratios:
        return {"window_n": window_n, "ratios": {}, "bottleneck_role": NOT_APPLICABLE}
    worst = max(ratios.items(), key=lambda kv: kv[1])
    return {
        "window_n": window_n,
        "ratios": ratios,
        "bottleneck_role": worst[0],
        "bottleneck_ratio": worst[1],
    }


def batch_coefficient(tasks: list[dict]) -> dict[str, Any]:
    """Coefficient of variation of inter-completion gaps for completed tasks.

    0 = perfectly even flow. >1 = clustered / batched (e.g., everything
    finishing in the last 3 days of the month).
    """
    ts = sorted(
        [
            _parse_iso(t.get("completed_at"))
            for t in tasks
            if t.get("status") == "complete" and t.get("completed_at")
        ]
    )
    ts = [t for t in ts if t is not None]
    if len(ts) < 3:
        return {"cv": NOT_APPLICABLE, "n_completions": len(ts)}
    gaps = [(b - a).total_seconds() for a, b in zip(ts, ts[1:])]
    mean = statistics.mean(gaps)
    if mean <= 0:
        return {"cv": NOT_APPLICABLE, "n_completions": len(ts)}
    stdev = statistics.pstdev(gaps)
    return {
        "cv": round(stdev / mean, 3),
        "n_completions": len(ts),
    }


def context_switching(tasks: list[dict], thresholds: dict) -> dict[str, Any]:
    """Assignees with simultaneous in_progress steps across multiple tasks."""
    limit = thresholds["context_switch_simultaneous_max"]
    by_assignee: dict[str, set[str]] = {}
    for t in tasks:
        for s in t.get("steps") or []:
            if s.get("status") != "in_progress":
                continue
            a = s.get("assignee_id")
            if not a:
                continue
            by_assignee.setdefault(a, set()).add(t.get("id") or "")
    flagged = {
        a: sorted(task_ids)
        for a, task_ids in by_assignee.items()
        if len(task_ids) > limit
    }
    return {
        "simultaneous_task_limit": limit,
        "flagged": flagged,
        "flagged_count": len(flagged),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _percentile(values: list[float], pct: float) -> float:
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def compute(
    *,
    db_dir: Path | None = None,
    profile_memory_dir: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Compute all current-state WIP/pull-flow metrics.

    All sections degrade gracefully when ``profile/db`` is absent or empty:
    metric values are still present, but counts are zero and lists empty.
    The agent claims each section directly.
    """
    thresholds = load_thresholds(profile_memory_dir)
    try:
        from web import db
        tasks = db.rows("tasks")
        queue = db.rows("queue")
        standard_work = db.rows("standard_work")
    except Exception:
        tasks, queue, standard_work = [], [], []

    if not tasks and not queue:
        return {
            "thresholds": thresholds,
            "wip_per_assignee": NOT_APPLICABLE,
            "queue_age": NOT_APPLICABLE,
            "push_signals": NOT_APPLICABLE,
            "bottleneck": NOT_APPLICABLE,
            "batch_coefficient": NOT_APPLICABLE,
            "context_switching": NOT_APPLICABLE,
        }
    return {
        "thresholds": thresholds,
        "wip_per_assignee": wip_per_assignee(tasks, thresholds),
        "queue_age": queue_age(queue, thresholds, now=now),
        "push_signals": push_signals(tasks, thresholds, now=now),
        "bottleneck": bottleneck(tasks, standard_work, thresholds),
        "batch_coefficient": batch_coefficient(tasks),
        "context_switching": context_switching(tasks, thresholds),
    }


def _cli() -> None:
    p = argparse.ArgumentParser(prog="scripts.lean.wip_flow")
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON (default: pretty print sections)",
    )
    args = p.parse_args()
    out = compute()
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        for section, value in out.items():
            print(f"\n== {section} ==")
            print(json.dumps(value, indent=2, default=str))


if __name__ == "__main__":
    _cli()
