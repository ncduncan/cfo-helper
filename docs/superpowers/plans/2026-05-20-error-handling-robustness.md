# Error-handling robustness implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local web dashboard self-healing under uncaught exceptions and background-thread failures, so a single error never requires restarting the app.

**Architecture:** Three layered additions to the existing FastAPI app: (1) a global exception handler in `web/errors.py` that branches HTMX/HTML/JSON responses and never destroys the page DOM, (2) a `web/supervisor.py` async probe that restarts the watchdog observer and APScheduler if they die, (3) a `safe_scheduler_reload()` helper so schedule CRUD writes don't 500 when reload misbehaves. A toast UI in `base.html` surfaces error messages without disrupting the page.

**Tech Stack:** FastAPI, HTMX, APScheduler, watchdog, Jinja2, pytest, fastapi TestClient.

**Source spec:** [docs/superpowers/specs/2026-05-20-error-handling-robustness-design.md](../specs/2026-05-20-error-handling-robustness-design.md)

---

## File map

**New:**
- `web/errors.py` — exception handler + `safe_scheduler_reload()` helper
- `web/supervisor.py` — background-thread probe loop
- `web/templates/error.html` — 500 page for non-HTMX browser requests
- `tests/test_web_errors.py` — unit + integration coverage for the new modules

**Modified:**
- `web/sse.py` — add `is_observer_alive()`
- `web/scheduler.py` — add `is_scheduler_alive()`
- `web/main.py` — register handler, start/stop supervisor in lifespan
- `web/templates/base.html` — toast target + HTMX `showToast` listener
- `web/routes/schedules.py` — swap three `scheduler.reload()` calls for `safe_scheduler_reload()`

---

## Task 1: Health probes on background systems

Add `is_alive()` accessors to the modules whose internals the supervisor needs to inspect. Keeps the supervisor decoupled from internal state shape.

**Files:**
- Modify: `web/sse.py`
- Modify: `web/scheduler.py`
- Test: inline in `tests/test_web_errors.py` (created in Task 4)

- [ ] **Step 1: Add `is_observer_alive()` to `web/sse.py`**

Add this function at the bottom of `web/sse.py`, after `stop_observer()`:

```python
def is_observer_alive() -> bool:
    """True if the watchdog Observer thread is currently alive."""
    return _observer is not None and _observer.is_alive()
```

- [ ] **Step 2: Add `is_scheduler_alive()` to `web/scheduler.py`**

Add this function at the bottom of `web/scheduler.py`, after `run_now()`:

```python
def is_scheduler_alive() -> bool:
    """True if the APScheduler BackgroundScheduler is running."""
    return _scheduler is not None and _scheduler.running
```

- [ ] **Step 3: Run existing tests to confirm no regressions**

Run: `.venv/bin/python -m pytest tests/test_web_schedules.py -q`
Expected: PASS (no behavior change yet; just new helpers).

- [ ] **Step 4: Commit**

```bash
git add web/sse.py web/scheduler.py
git commit -m "Add is_alive accessors to sse and scheduler modules"
```

---

## Task 2: Error response module — HTMX branch (test first)

Create `web/errors.py` with the global exception handler. Start with the HTMX branch since it's the highest-value path (the one that produced the reported incident).

**Files:**
- Create: `web/errors.py`
- Create: `tests/test_web_errors.py`

- [ ] **Step 1: Create the failing test for the HTMX branch**

Create `tests/test_web_errors.py`:

```python
"""Tests for web.errors and web.supervisor."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app_with_failing_route() -> FastAPI:
    """Build a tiny app that registers our handler and has one always-failing route."""
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/boom")
    def boom():
        raise RuntimeError("simulated failure")

    return app


def test_htmx_request_gets_toast_and_preserves_page():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"HX-Request": "true"})

    assert r.status_code == 204
    assert r.headers.get("HX-Reswap") == "none"
    trigger = json.loads(r.headers["HX-Trigger"])
    assert trigger["showToast"]["level"] == "error"
    assert "simulated failure" in trigger["showToast"]["message"]
    assert "request_id" in trigger["showToast"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py::test_htmx_request_gets_toast_and_preserves_page -v`
Expected: FAIL with `ImportError` or `AttributeError` on `web.errors` / `register_exception_handlers`.

- [ ] **Step 3: Create `web/errors.py` with the HTMX branch only**

Create `web/errors.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py::test_htmx_request_gets_toast_and_preserves_page -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/errors.py tests/test_web_errors.py
git commit -m "Add global exception handler with HTMX toast branch"
```

---

## Task 3: Error response — JSON and HTML branches

Add coverage for the other two request types and create the `error.html` template.

**Files:**
- Create: `web/templates/error.html`
- Modify: `tests/test_web_errors.py`

- [ ] **Step 1: Add failing tests for JSON and HTML branches**

Append to `tests/test_web_errors.py`:

```python
def test_json_request_gets_structured_error():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"Accept": "application/json"})

    assert r.status_code == 500
    body = r.json()
    assert body["error"] == "internal_error"
    assert "simulated failure" in body["detail"]
    assert "request_id" in body


def test_api_path_gets_json_even_without_accept_header():
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)

    @app.get("/api/boom")
    def api_boom():
        raise RuntimeError("api failure")

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/boom")

    assert r.status_code == 500
    assert r.json()["error"] == "internal_error"


def test_browser_request_gets_html_error_page():
    app = _app_with_failing_route()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get("/boom", headers={"Accept": "text/html"})

    assert r.status_code == 500
    assert "text/html" in r.headers["content-type"]
    assert "simulated failure" in r.text
    assert "Something went wrong" in r.text


def test_message_is_truncated_at_200_chars():
    from web import errors

    app = FastAPI()
    errors.register_exception_handlers(app)
    long_msg = "x" * 500

    @app.get("/long")
    def long_route():
        raise RuntimeError(long_msg)

    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/long", headers={"Accept": "application/json"})

    detail = r.json()["detail"]
    assert len(detail) <= 200
    assert detail.endswith("…")
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py -v`
Expected: JSON and truncation tests PASS (logic already in place); `test_browser_request_gets_html_error_page` FAILS because the template doesn't exist (Jinja2 `TemplateNotFound`).

- [ ] **Step 3: Create `web/templates/error.html`**

Create `web/templates/error.html`:

```html
{% extends "base.html" %}
{% block title %}Something went wrong — CFO Helper{% endblock %}
{% block content %}
<div class="max-w-2xl mx-auto bg-white border border-slate-200 rounded p-6">
  <h1 class="text-xl font-semibold text-slate-900">Something went wrong</h1>
  <p class="mt-3 text-sm text-slate-700">{{ message }}</p>
  <div class="mt-6 flex items-center gap-4">
    <a href="javascript:history.back()" class="text-sm text-blue-600 hover:underline">&larr; Back</a>
    <a href="/" class="text-sm text-slate-500 hover:underline">Home</a>
  </div>
  <p class="mt-6 text-xs text-slate-400">request_id: {{ request_id }}</p>
</div>
{% endblock %}
```

- [ ] **Step 4: Run all error tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py -v`
Expected: all four new tests PASS, plus the HTMX test from Task 2.

- [ ] **Step 5: Commit**

```bash
git add tests/test_web_errors.py web/templates/error.html
git commit -m "Add JSON and HTML branches to global exception handler"
```

---

## Task 4: `safe_scheduler_reload` helper

Wraps `scheduler.reload()` so a failure there doesn't 500 a CRUD request. The DB write is the source of truth; the supervisor recovers the scheduler.

**Files:**
- Modify: `web/errors.py`
- Modify: `tests/test_web_errors.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_web_errors.py`:

```python
def test_safe_scheduler_reload_returns_true_on_success(monkeypatch):
    from web import errors, scheduler

    called = {"n": 0}

    def fake_reload():
        called["n"] += 1

    monkeypatch.setattr(scheduler, "reload", fake_reload)
    assert errors.safe_scheduler_reload() is True
    assert called["n"] == 1


def test_safe_scheduler_reload_swallows_exception_and_logs(monkeypatch, caplog):
    from web import errors, scheduler

    def boom():
        raise RuntimeError("scheduler is angry")

    monkeypatch.setattr(scheduler, "reload", boom)
    with caplog.at_level("ERROR", logger="web.errors"):
        result = errors.safe_scheduler_reload()
    assert result is False
    assert any("scheduler.reload()" in rec.message for rec in caplog.records)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py::test_safe_scheduler_reload_returns_true_on_success tests/test_web_errors.py::test_safe_scheduler_reload_swallows_exception_and_logs -v`
Expected: FAIL with `AttributeError: module 'web.errors' has no attribute 'safe_scheduler_reload'`.

- [ ] **Step 3: Add the helper to `web/errors.py`**

Append to `web/errors.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web/errors.py tests/test_web_errors.py
git commit -m "Add safe_scheduler_reload helper that swallows reload errors"
```

---

## Task 5: Supervisor module

A background async task that probes the watchdog observer and APScheduler every N seconds and restarts whichever is dead.

**Files:**
- Create: `web/supervisor.py`
- Modify: `tests/test_web_errors.py`

- [ ] **Step 1: Add a failing test for supervisor observer restart**

Append to `tests/test_web_errors.py`:

```python
import asyncio


@pytest.mark.asyncio
async def test_supervisor_restarts_dead_observer(tmp_path, monkeypatch):
    from web import sse, supervisor

    # Point watchdog at a tmpdir so we don't litter the real DB dir.
    monkeypatch.setattr(sse, "DB_DIR", tmp_path / "db")
    monkeypatch.setattr(sse, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(sse, "_observer", None)

    sse.start_observer()
    assert sse.is_observer_alive() is True

    # Kill the observer behind the supervisor's back.
    sse._observer.stop()
    sse._observer.join(timeout=1)
    sse._observer = None
    assert sse.is_observer_alive() is False

    # Run one supervisor tick.
    await supervisor.run_one_tick()
    assert sse.is_observer_alive() is True

    sse.stop_observer()


@pytest.mark.asyncio
async def test_supervisor_restarts_dead_scheduler(monkeypatch):
    from web import scheduler, supervisor

    calls = {"start": 0}

    def fake_is_alive():
        return False

    def fake_start():
        calls["start"] += 1

    monkeypatch.setattr(scheduler, "is_scheduler_alive", fake_is_alive)
    monkeypatch.setattr(scheduler, "start_scheduler", fake_start)
    # Keep observer healthy so the test focuses on scheduler.
    monkeypatch.setattr("web.sse.is_observer_alive", lambda: True)

    await supervisor.run_one_tick()
    assert calls["start"] == 1
```

Also at the top of `tests/test_web_errors.py`, after the imports already there, add:

```python
pytest_plugins = ["pytest_asyncio"]
```

(If the project already configures `pytest-asyncio` via `pyproject.toml` / `pytest.ini`, this line is unnecessary — check `pyproject.toml` and skip if `asyncio_mode = "auto"` or the plugin is already declared.)

- [ ] **Step 2: Verify pytest-asyncio is available**

Run: `.venv/bin/python -c "import pytest_asyncio; print(pytest_asyncio.__version__)"`

If it errors, install it: `.venv/bin/pip install pytest-asyncio` (and add to `pyproject.toml` or `requirements*.txt` per project convention).

- [ ] **Step 3: Run the supervisor tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py::test_supervisor_restarts_dead_observer tests/test_web_errors.py::test_supervisor_restarts_dead_scheduler -v`
Expected: FAIL with `ModuleNotFoundError: web.supervisor`.

- [ ] **Step 4: Create `web/supervisor.py`**

Create `web/supervisor.py`:

```python
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
```

- [ ] **Step 5: Run the supervisor tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add web/supervisor.py tests/test_web_errors.py
git commit -m "Add background-thread supervisor for watchdog observer and APScheduler"
```

---

## Task 6: Wire handler and supervisor into the FastAPI app

Register the exception handler and start/stop the supervisor inside `lifespan`. Smallest possible change to `web/main.py`.

**Files:**
- Modify: `web/main.py`

- [ ] **Step 1: Read the current `web/main.py` lifespan and imports**

Open `web/main.py` and locate:
- Line 28: `from web import db, scheduler, sse`
- Lines 56-71: the `lifespan` async context manager
- Line 81: `_discover_routers(app)`

- [ ] **Step 2: Update the imports**

Replace line 28:

```python
from web import db, errors, scheduler, sse, supervisor
```

- [ ] **Step 3: Update `lifespan` to start and stop the supervisor**

Replace the `lifespan` function body (currently lines 57-71) with:

```python
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
    supervisor.start_supervisor()
    yield
    supervisor.stop_supervisor()
    scheduler.stop_scheduler()
    sse.stop_observer()
```

- [ ] **Step 4: Register the exception handler after router discovery**

Below the existing `_discover_routers(app)` call (line 81), add:

```python
errors.register_exception_handlers(app)
```

- [ ] **Step 5: Run all existing tests to confirm no regression**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS (no behavior change visible to existing tests; we've added handlers and a supervisor but no current route relies on them).

- [ ] **Step 6: Smoke-test the app starts**

Run: `.venv/bin/uvicorn web.main:app --port 8765 &`
Wait 2 seconds, then `curl -s http://localhost:8765/api/health`
Expected: `{"ok": true, "routers": [...]}`

Then `curl -s http://localhost:8765/api/does-not-exist -H 'Accept: application/json'`
Expected: standard 404 from FastAPI (not the new handler — 404 is an HTTPException already).

Kill the server: `kill %1`

- [ ] **Step 7: Commit**

```bash
git add web/main.py
git commit -m "Register exception handler and start supervisor in lifespan"
```

---

## Task 7: Toast UI in base template

Add a fixed-position toast target and an HTMX `showToast` event listener. Pure HTML/CSS/JS, no new dependencies.

**Files:**
- Modify: `web/templates/base.html`

- [ ] **Step 1: Add the toast target div and event listener**

In `web/templates/base.html`, after the `<main>` block closes (line 45) and before `</body>` (line 46), insert:

```html
  <div id="toast-container" class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none"></div>
  <script>
    document.body.addEventListener("showToast", function (evt) {
      const detail = evt.detail || {};
      const level = detail.level || "info";
      const message = detail.message || "Something went wrong.";
      const requestId = detail.request_id || "";

      const colors = {
        error: "bg-red-600",
        info: "bg-slate-700",
        success: "bg-emerald-600",
      };
      const bg = colors[level] || colors.info;

      const el = document.createElement("div");
      el.className = `${bg} text-white text-sm rounded shadow-lg px-4 py-3 pointer-events-auto max-w-sm`;
      el.innerHTML = `<div class="font-medium">${message}</div>` +
        (requestId ? `<div class="text-xs opacity-75 mt-1">id: ${requestId}</div>` : "");
      document.getElementById("toast-container").appendChild(el);
      setTimeout(() => { el.style.transition = "opacity 0.4s"; el.style.opacity = "0"; }, 4000);
      setTimeout(() => { el.remove(); }, 4500);
    });
  </script>
```

- [ ] **Step 2: Visual smoke test**

Start the dashboard:
```bash
.venv/bin/uvicorn web.main:app --port 8765 &
```

In a browser, open `http://localhost:8765`. Open the dev console. Paste:

```javascript
htmx.trigger(document.body, "showToast", {level: "error", message: "Manual test message", request_id: "abc123"});
```

Expected: a red toast appears in the bottom-right corner showing "Manual test message" and "id: abc123", fading after ~4s. Page DOM otherwise unchanged.

Kill the server: `kill %1`

- [ ] **Step 3: Commit**

```bash
git add web/templates/base.html
git commit -m "Add toast UI for error messages in base template"
```

---

## Task 8: Use `safe_scheduler_reload` in schedule routes + integration test

Swap the three `scheduler.reload()` call sites in `web/routes/schedules.py`. Add an integration test that proves a broken reload no longer 500s the request.

**Files:**
- Modify: `web/routes/schedules.py`
- Modify: `tests/test_web_errors.py`

- [ ] **Step 1: Add failing integration test**

Append to `tests/test_web_errors.py`:

```python
def test_schedule_update_survives_broken_reload(tmp_path, monkeypatch):
    """POST /schedules/<id> should return success even if scheduler.reload raises."""
    from web import db as db_mod
    from web import errors, scheduler as scheduler_mod
    from web.routes import schedules as schedules_routes

    # Isolate the DB into tmpdir.
    monkeypatch.setattr(db_mod, "DB_DIR", tmp_path / "db")
    db_mod.init_db()

    # Seed a standard_work and a schedule.
    from datetime import datetime, timezone
    now_iso = datetime(2026, 5, 16, tzinfo=timezone.utc).isoformat()
    db_mod.insert("standard_work", {
        "id": "sw1", "name": "SW", "source_task_type": None,
        "owner_role": "fpa", "cadence": None, "context_md": "",
        "requirements_md": "", "due_offset_days": 0, "steps": [],
        "created_at": now_iso, "updated_at": now_iso,
    })
    db_mod.insert("schedules", {
        "id": "s1", "name": "S1", "standard_work_id": "sw1",
        "cron": "0 9 1 * *", "enabled": True, "brief_template": {},
        "created_at": now_iso, "last_fire": None, "last_fire_result": None,
    })

    # Make scheduler.reload() blow up.
    def boom():
        raise RuntimeError("scheduler is having a bad day")
    monkeypatch.setattr(scheduler_mod, "reload", boom)

    # Mount the route.
    app = FastAPI()
    app.include_router(schedules_routes.router)
    errors.register_exception_handlers(app)
    client = TestClient(app, follow_redirects=False)

    r = client.post(
        "/schedules/s1",
        data={
            "name": "S1 updated",
            "standard_work_id": "sw1",
            "frequency": "monthly",
            "hour": "9", "minute": "0",
            "day_of_week": "1", "day_of_month": "1", "month": "1",
            "cron_raw": "",
            "timezone": "America/New_York",
            "enabled": "on",
        },
    )

    # Route should still return its normal 303 redirect.
    assert r.status_code == 303
    # DB write should have stuck.
    row = db_mod.find("schedules", "s1")
    assert row["name"] == "S1 updated"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py::test_schedule_update_survives_broken_reload -v`
Expected: FAIL — the route currently calls `scheduler.reload()` directly, so the exception bubbles up and the global handler converts it to a 500 (or for non-HTMX, the HTML error page). Either way, status is NOT 303.

- [ ] **Step 3: Patch `web/routes/schedules.py` to use `safe_scheduler_reload`**

Find the three `scheduler.reload()` call sites in `web/routes/schedules.py` (currently at line 162 in `create`, line 225 in `update`, line 237 in `toggle_enabled`).

Update the import at the top of the file. Find:
```python
from web import db, scheduler
```
(or whatever the current `scheduler` import line looks like; the file imports `web.scheduler` somewhere near the top.)

Add an import of the helper:
```python
from web.errors import safe_scheduler_reload
```

Replace each of the three lines:

```python
scheduler.reload()
```

with:

```python
safe_scheduler_reload()
```

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_web_errors.py::test_schedule_update_survives_broken_reload -v`
Expected: PASS.

- [ ] **Step 5: Run the full schedule test suite for regressions**

Run: `.venv/bin/python -m pytest tests/test_web_schedules.py tests/test_web_errors.py -v`
Expected: all PASS. (The existing schedule tests monkeypatch a no-op scheduler that has no failing reload, so behavior is unchanged for them.)

- [ ] **Step 6: Commit**

```bash
git add web/routes/schedules.py tests/test_web_errors.py
git commit -m "Use safe_scheduler_reload in schedule CRUD routes"
```

---

## Task 9: End-to-end smoke verification

Manual verification that the full integration works in a live app.

**Files:** (none — verification only)

- [ ] **Step 1: Start the dashboard**

```bash
.venv/bin/uvicorn web.main:app --port 8765 &
sleep 2
```

- [ ] **Step 2: Confirm health endpoint**

Run: `curl -s http://localhost:8765/api/health`
Expected: `{"ok": true, "routers": [...]}`

- [ ] **Step 3: Trigger an HTMX-style error**

Run:
```bash
curl -s -i -H "HX-Request: true" -H "Accept: text/html" "http://localhost:8765/schedules/does-not-exist/edit"
```
Expected: this is a *known* error path (404 via HTTPException), so the response is 404 with FastAPI's default body — NOT the new handler. Confirms the handler is only a backstop, not interfering with known paths.

- [ ] **Step 4: Trigger an *un*known error path**

Temporarily add to `web/main.py` (just for this smoke test — revert after):

```python
@app.get("/__boom__")
def _boom():
    raise RuntimeError("smoke test")
```

Then restart the server (`kill %1 && .venv/bin/uvicorn web.main:app --port 8765 & sleep 2`).

Run:
```bash
curl -s -i -H "HX-Request: true" "http://localhost:8765/__boom__"
```
Expected: 204 with `HX-Reswap: none` and `HX-Trigger: {"showToast": {...}}` containing "smoke test".

Run:
```bash
curl -s -i -H "Accept: application/json" "http://localhost:8765/__boom__"
```
Expected: 500 with JSON body `{"error": "internal_error", "detail": "smoke test", "request_id": "..."}`.

Run:
```bash
curl -s -i -H "Accept: text/html" "http://localhost:8765/__boom__"
```
Expected: 500 with HTML body containing "Something went wrong" and "smoke test".

Remove the `__boom__` route from `web/main.py`. Restart the server to confirm normal operation.

Kill the server: `kill %1`

- [ ] **Step 5: Confirm no leftover changes**

Run: `git status`
Expected: clean working tree (the `__boom__` route was added and removed without commits).

---

## Self-review notes

**Spec coverage:**
- Global exception handler (HTMX/HTML/JSON branches, logging, request_id): Tasks 2–3
- Background supervisor probing observer and scheduler: Task 5
- `safe_scheduler_reload` helper: Task 4
- Toast UI in `base.html`: Task 7
- Schedule route migration: Task 8
- `is_alive()` accessors on sse and scheduler modules: Task 1
- New `error.html` template: Task 3
- Wiring into `web/main.py`: Task 6
- Tests for all of the above: Tasks 2, 3, 4, 5, 8
- Smoke verification: Task 9

All spec sections are mapped to tasks. No gaps.

**Risk reminder:** Task 5 introduces a new dev dep (`pytest-asyncio`). If the project's `pyproject.toml` already configures it, Task 5 Step 1's `pytest_plugins` line is redundant — verify before adding to keep the test file lean.
