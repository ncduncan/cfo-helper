"""Global exception handler and scheduler-reload safety wrapper.

Catches anything a route raises that isn't an HTTPException. Branches
the response shape based on request type so HTMX requests never get a
destructive DOM swap, browser HTML requests get a friendly error page,
and JSON/API clients get a structured error body. The full traceback
is logged with a request_id for cross-referencing.
"""

from __future__ import annotations

import json
import logging
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

_log = logging.getLogger("web.errors")

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

_MAX_MESSAGE_CHARS = 200


def _short_message(exc: BaseException) -> str:
    msg = str(exc) or exc.__class__.__name__
    if len(msg) > _MAX_MESSAGE_CHARS:
        msg = msg[: _MAX_MESSAGE_CHARS - 1] + "…"
    return msg


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _is_json(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept and "text/html" not in accept


async def _handle(request: Request, exc: Exception) -> Response:
    request_id = uuid.uuid4().hex
    _log.error(
        "unhandled exception request_id=%s method=%s path=%s\n%s",
        request_id,
        request.method,
        request.url.path,
        "".join(traceback.format_exception(exc)),
    )
    message = _short_message(exc)

    if _is_htmx(request):
        trigger = {
            "showToast": {
                "level": "error",
                "message": message,
                "request_id": request_id,
            }
        }
        return Response(
            status_code=204,
            headers={
                "HX-Reswap": "none",
                "HX-Trigger": json.dumps(trigger),
            },
        )

    if _is_json(request):
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": message,
                "request_id": request_id,
            },
        )

    # Browser HTML fallback (filled in by Task 3).
    return _TEMPLATES.TemplateResponse(
        request,
        "error.html",
        {"message": message, "request_id": request_id},
        status_code=500,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the global exception handler to the FastAPI app."""

    @app.exception_handler(Exception)
    async def _on_exception(request: Request, exc: Exception) -> Response:
        return await _handle(request, exc)


def safe_scheduler_reload() -> bool:
    """Call scheduler.reload(); swallow and log any exception.

    Returns True on success, False if reload raised. The supervisor will
    restart the scheduler if it is genuinely dead; the DB write that
    preceded this call is the source of truth either way.
    """
    from web import scheduler

    try:
        scheduler.reload()
        return True
    except Exception:
        _log.exception("scheduler.reload() failed; supervisor will retry")
        return False
