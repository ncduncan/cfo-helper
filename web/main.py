"""
FastAPI app entry point — slim shell, no business logic.

Run with::

    .venv/bin/uvicorn web.main:app --port 8765 --reload

Auto-discovers any ``web/routes/*.py`` module that exposes a module-level
``router: APIRouter`` and includes it. **Never edit this file to add a
new page area** — drop the router module into ``web/routes/`` and it will
be picked up on next startup.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from web import db, scheduler, sse

_log = logging.getLogger("web.main")

REPO = Path(__file__).resolve().parent.parent

# Tracked for the /api/health response so external monitors can see what's
# wired in without scraping the route table.
_included: list[str] = []


def _discover_routers(app: FastAPI) -> None:
    """Import every web/routes/*.py module and include its ``router`` if any."""
    import web.routes as routes_pkg

    for mod_info in pkgutil.iter_modules(routes_pkg.__path__):
        name = mod_info.name
        if name.startswith("_"):
            continue
        full = f"web.routes.{name}"
        mod = importlib.import_module(full)
        router = getattr(mod, "router", None)
        if isinstance(router, APIRouter):
            app.include_router(router)
            _included.append(name)
            _log.info("included router: %s", full)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    workers = os.environ.get("WEB_CONCURRENCY", "1")
    if workers != "1":
        _log.warning(
            "WEB_CONCURRENCY=%s: dashboard assumes single uvicorn worker; "
            "multi-worker invalidates the JSON DB file lock + SSE hub.",
            workers,
        )
    db.init_db()
    sse.hub.attach_loop(asyncio.get_running_loop())
    sse.start_observer()
    scheduler.start_scheduler()
    yield
    scheduler.stop_scheduler()
    sse.stop_observer()


app = FastAPI(title="CFO Helper — Team Console", lifespan=lifespan)
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "static")),
    name="static",
)

_discover_routers(app)


@app.get("/events")
async def events():
    return StreamingResponse(sse.event_stream(), media_type="text/event-stream")


@app.get("/api/health")
async def health():
    return {"ok": True, "routers": list(_included)}
