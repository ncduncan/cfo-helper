"""APScheduler background job runner — fires schedules from db/schedules.json.

On each fire, instantiates a Task from the named StandardWork via
``web.instantiate.instantiate_task`` and records ``last_fire`` +
``last_fire_result`` on the schedule row.

The scheduler keeps the in-memory job set in sync with ``db/schedules.json``:
- ``start_scheduler()`` reads the file and registers one job per enabled row.
- ``reload()`` rebuilds the job set (called after any CRUD write).
- ``stop_scheduler()`` shuts down cleanly on lifespan exit.

This module is invoked from ``web/main.py``'s lifespan as a strictly
additive integration.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from web import db, instantiate


_log = logging.getLogger("web.scheduler")

_scheduler: BackgroundScheduler | None = None


def scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _job_id(schedule_id: str) -> str:
    return f"sched-{schedule_id}"


def _register(s: dict[str, Any]) -> None:
    """Add a job for the schedule row to the BackgroundScheduler."""
    if not s.get("enabled", True):
        return
    cron = s.get("cron")
    if not cron:
        _log.warning("schedule %r missing cron expression; skipping", s.get("id"))
        return
    tz = s.get("timezone") or "America/New_York"
    try:
        trigger = CronTrigger.from_crontab(cron, timezone=tz)
    except Exception as exc:
        _log.warning(
            "schedule %r has invalid cron %r: %s", s.get("id"), cron, exc
        )
        return
    sched = scheduler()
    sched.add_job(
        _fire,
        trigger=trigger,
        args=[s["id"]],
        id=_job_id(s["id"]),
        replace_existing=True,
    )


def _fire(schedule_id: str) -> str:
    """Cron-fire callback. Idempotent on transient failures."""
    s = db.find("schedules", schedule_id)
    if s is None:
        _log.warning("fire: schedule %r no longer exists", schedule_id)
        return "missing"
    sw_id = s.get("standard_work_id")
    if not sw_id:
        msg = "no standard_work_id"
        db.update(
            "schedules",
            schedule_id,
            {"last_fire": _now_iso(), "last_fire_result": f"error: {msg}"},
        )
        return f"error: {msg}"
    period = _derive_period(s)
    try:
        task = instantiate.instantiate_task(
            sw_id, period=period, source=f"schedule:{schedule_id}"
        )
        db.update(
            "schedules",
            schedule_id,
            {
                "last_fire": _now_iso(),
                "last_fire_result": f"ok: {task['id']}",
            },
        )
        return f"ok: {task['id']}"
    except Exception as exc:
        db.update(
            "schedules",
            schedule_id,
            {
                "last_fire": _now_iso(),
                "last_fire_result": f"error: {exc}",
            },
        )
        return f"error: {exc}"


def _derive_period(s: dict[str, Any]) -> str:
    """Resolve a period string for the task being instantiated.

    Uses ``brief_template['period']`` if present, substituting tokens:
    - ``{this_month}`` → current YYYY-MM
    - ``{previous_month}`` → previous YYYY-MM
    Otherwise falls back to the current YYYY-MM.
    """
    now = datetime.now(tz=timezone.utc)
    this_month = now.strftime("%Y-%m")
    prev_month_dt = now.replace(day=1)
    if prev_month_dt.month == 1:
        prev_month_dt = prev_month_dt.replace(year=prev_month_dt.year - 1, month=12)
    else:
        prev_month_dt = prev_month_dt.replace(month=prev_month_dt.month - 1)
    previous_month = prev_month_dt.strftime("%Y-%m")

    tmpl = (s.get("brief_template") or {}).get("period")
    if not tmpl:
        return this_month
    return (
        str(tmpl)
        .replace("{this_month}", this_month)
        .replace("{previous_month}", previous_month)
    )


def start_scheduler() -> None:
    sched = scheduler()
    if sched.running:
        reload()
        return
    for s in db.rows("schedules"):
        _register(s)
    sched.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None


def reload() -> None:
    """Rebuild job set from db/schedules.json. Called after CRUD writes."""
    sched = scheduler()
    if not sched.running:
        start_scheduler()
        return
    existing = {j.id for j in sched.get_jobs()}
    desired = {
        _job_id(s["id"]) for s in db.rows("schedules") if s.get("enabled", True)
    }
    for jid in existing - desired:
        sched.remove_job(jid)
    for s in db.rows("schedules"):
        _register(s)


def run_now(schedule_id: str) -> str:
    """Fire a schedule synchronously (UI button)."""
    return _fire(schedule_id)
