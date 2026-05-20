"""Background-thread supervisor.

Periodically checks the watchdog observer and APScheduler. Restarts
whichever is not alive and logs. No backoff — for a single-user local
dashboard the cost of one extra log line per tick is acceptable.

Exposed callables:
    start_supervisor(probe_interval_secs=15.0)  # called from lifespan
    stop_supervisor()                            # called from lifespan
    run_one_tick()                               # used by tests
"""

from __future__ import annotations

import asyncio
import logging

from web import scheduler, sse

_log = logging.getLogger("web.supervisor")

_task: asyncio.Task | None = None
_DEFAULT_INTERVAL_SECS = 15.0


async def run_one_tick() -> None:
    """Run a single probe-and-restart pass. Exposed for tests."""
    if not sse.is_observer_alive():
        _log.warning("watchdog observer not alive; restarting")
        try:
            sse.start_observer()
        except Exception:
            _log.exception("failed to restart watchdog observer")

    if not scheduler.is_scheduler_alive():
        _log.warning("APScheduler not alive; restarting")
        try:
            scheduler.start_scheduler()
        except Exception:
            _log.exception("failed to restart APScheduler")


async def _loop(probe_interval_secs: float) -> None:
    while True:
        try:
            await run_one_tick()
        except Exception:
            _log.exception("supervisor tick raised; continuing")
        await asyncio.sleep(probe_interval_secs)


def start_supervisor(probe_interval_secs: float = _DEFAULT_INTERVAL_SECS) -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop(probe_interval_secs))


def stop_supervisor() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    _task = None
