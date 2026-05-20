# Error-handling robustness — design

**Date:** 2026-05-20
**Status:** Approved, ready for implementation plan
**Trigger:** CFO hit an Internal Server Error while updating a scheduled task and had to exit + reload the app to restore. Investigation showed multiple gaps that could produce the same failure mode.

## Problem

The FastAPI dashboard at `web/` has three failure modes that combine to produce "the app is broken until I restart it":

1. **No global exception handler.** Any uncaught exception in a route becomes a bare 500. When the request is HTMX-driven, the 500 body gets swapped into the page fragment, corrupting the UI. The user is left looking at a half-broken page.
2. **Background threads have no supervisor.** `scheduler.start_scheduler()` (APScheduler) and `sse.start_observer()` (watchdog) both run as daemon threads started in the `lifespan` context. If either dies — uncaught exception in the thread, OS-level interruption, internal corruption — the web layer keeps serving requests but the dashboard stops updating and schedules stop firing. The user has to restart the process.
3. **`scheduler.reload()` runs synchronously inside CRUD requests.** Every schedule write calls it (see `web/routes/schedules.py`). If the reload raises (e.g., `JobLookupError` from `remove_job`, internal APScheduler state inconsistency), the route 500s *after* the DB write succeeded — confusing the user and leaving an inconsistent UI state.

The most likely root cause of the reported incident is path 3 cascading into path 1: `scheduler.reload()` raised during schedule update, the 500 swapped into the HTMX target, the page looked stuck, the user reloaded the app.

## Goals

- A single uncaught exception in a request should never corrupt the UI.
- Background system failures should self-heal without process restart.
- Schedule CRUD should not 500 when the scheduler reload misbehaves; the DB write is the source of truth.
- Every unhandled exception is logged with enough context (method, path, request id) to investigate.

## Non-goals

- Replacing the existing `raise HTTPException(...)` pattern in routes. These are explicit, intentional, and already produce useful client responses. The new handler is a backstop, not a refactor target.
- Form idempotency, retry queues, circuit breakers — these are Approach C in the brainstorm and are YAGNI for now.
- A structured `AppError` class hierarchy (Approach B). Can be promoted later if the pattern proves useful.
- Touching `db.py`. Its raw `ValueError`/`KeyError` raises now get caught by the global handler instead of leaking to users as a 500 page; that's sufficient.

## Architecture

Three layered changes:

### 1. Global exception handler

Registered on the FastAPI app via `app.exception_handler(Exception)`. Catches anything not already an `HTTPException`. Branches the response based on request type:

- **HTMX request** (header `HX-Request: true`):
  ```
  HTTP/1.1 204 No Content
  HX-Reswap: none
  HX-Trigger: {"showToast": {"level": "error", "message": "<one-line reason>", "request_id": "<uuid4>"}}
  ```
  The page DOM is untouched. A toast appears for ~4s, then fades.

- **Browser HTML request** (Accept includes `text/html`, no `HX-Request`):
  ```
  HTTP/1.1 500 Internal Server Error
  Content-Type: text/html
  ```
  Body is a new `web/templates/error.html` — title, one-line message, "← back" link to `Referer` (or `/` if absent). Request id in footer. No traceback shown to the user.

- **JSON / API request** (Accept is `application/json` *or* path starts with `/api/`):
  ```
  HTTP/1.1 500 Internal Server Error
  Content-Type: application/json
  {"error": "internal_error", "detail": "<one-line reason>", "request_id": "<uuid4>"}
  ```

Every branch logs the full traceback before responding:
```
ERROR web.errors: unhandled exception request_id=<uuid4> method=POST path=/schedules/<id>
<full traceback>
```

`str(exc)` is the one-line reason, truncated to 200 chars. The exception class name is never exposed to users.

### 2. Background thread supervisor

A single async task started in `lifespan`. Loops on a configurable sleep interval (default 15s, overridable via env var for tests) and probes:

- `sse.is_observer_alive()` → `_observer is not None and _observer.is_alive()`
- `scheduler.is_scheduler_alive()` → `_scheduler is not None and _scheduler.running`

If either returns False, the supervisor calls the corresponding `start_observer()` / `start_scheduler()` and logs the restart. No exponential backoff — just "is it alive, restart if not." If restart itself fails, log and try again next tick.

Supervisor lifecycle:
- Started after `scheduler.start_scheduler()` and `sse.start_observer()` in `lifespan`.
- Cancelled before they stop on shutdown.

### 3. `safe_scheduler_reload()` helper

Lives in `web/errors.py`. Wraps `scheduler.reload()` so route handlers can call it without 500ing if the reload itself fails:

```python
def safe_scheduler_reload() -> bool:
    try:
        scheduler.reload()
        return True
    except Exception:
        _log.exception("scheduler.reload() failed; supervisor will retry")
        return False
```

The DB write has already succeeded by the time the route calls this. If the reload throws, the helper logs and lets the route return success. The supervisor picks the scheduler back up on the next tick if it's genuinely broken.

### Toast UI

A small `<div id="toast-target">` added to `web/templates/base.html`. An HTMX event listener pops the message for ~4s on `showToast`. Standard HTMX pattern, ~15 lines of HTML+CSS+JS, no new dependencies.

## Files

**New files:**
- `web/errors.py` — `register_exception_handlers(app)`, the three response branches, `safe_scheduler_reload()`. ~80 lines.
- `web/supervisor.py` — `start_supervisor()` / `stop_supervisor()`. Owns the async probe task. ~50 lines.
- `web/templates/error.html` — fallback HTML page for non-HTMX 500s. ~20 lines.
- `tests/test_web_errors.py` — coverage for handler branches, supervisor restart, `safe_scheduler_reload`.

**Modified files:**
- `web/main.py` — call `errors.register_exception_handlers(app)` after `_discover_routers`. Start/stop supervisor in `lifespan`. ~5 lines added.
- `web/templates/base.html` — toast target div + HTMX listener + minimal CSS. ~15 lines added.
- `web/routes/schedules.py` — replace three `scheduler.reload()` call sites with `safe_scheduler_reload()`. 3-line change.
- `web/sse.py` — expose `is_observer_alive()`. ~3 lines added.
- `web/scheduler.py` — expose `is_scheduler_alive()`. ~3 lines added.

**Untouched:**
- All existing `raise HTTPException(...)` patterns in routes.
- `web/db.py`.
- Every other route module.

## Data flow

**Happy path (unchanged):** route runs, returns response, handler is never invoked.

**Known error path (unchanged):** route raises `HTTPException` → FastAPI's built-in handler produces the response with the route's chosen status code and detail.

**Unknown error path (new):**
1. Route raises some other exception.
2. Global handler catches it.
3. Handler generates a request id (uuid4), logs traceback + context, branches on request headers, returns the appropriate response shape.
4. If HTMX, the page DOM is preserved; user sees a toast.

**Background-system failure path (new):**
1. Watchdog observer thread or APScheduler dies for any reason.
2. Within ~15s, supervisor's probe sees `is_alive() == False`.
3. Supervisor calls the corresponding restart function and logs.
4. Next probe confirms recovery.
5. User sees no disruption (or, in the worst case, ~15s of missed SSE events).

**Schedule update path (new):**
1. POST `/schedules/<id>` arrives with form data.
2. Route validates and writes via `db.upsert("schedules", ...)`.
3. Route calls `safe_scheduler_reload()` (new). If reload raises, the helper logs and returns False; the route returns success anyway.
4. The next supervisor tick will restart the scheduler if it's genuinely dead.
5. Either way, the DB is the source of truth — the schedule row is durable.

## Testing

`tests/test_web_errors.py` covers:

- **Three response branches** — mount a small test app with a route that always raises. Three requests (HTMX header, HTML accept, JSON accept) — assert status, headers (`HX-Reswap`, `HX-Trigger`), and body shape.
- **Supervisor restart** — start the supervisor with a short tick interval. Manually call `sse._observer.stop()`. Wait for one tick. Assert `is_observer_alive()` returns True again.
- **`safe_scheduler_reload`** — monkeypatch `scheduler.reload` to raise. Call the helper. Assert it returns False and logs an error (caplog).
- **Schedule CRUD with broken reload** — integration test. POST `/schedules/<id>` with valid form data where `scheduler.reload` is monkeypatched to raise. Assert: route returns the normal redirect response (303), the schedule row was updated in the DB, no `HX-Trigger` error toast was emitted. Reload failure is silent on the user-facing side and recovered by the supervisor.

## Risk / open questions

- **Toast UX inside long-form pages** — does the toast target need to be fixed-position so it appears regardless of scroll? Assumption: yes, `position: fixed; bottom: 1rem; right: 1rem`. Confirmed at implementation time by visual check.
- **Request id correlation** — for now the request id is just for log-grepping. No persistent store. Sufficient.
- **Supervisor restart loop** — if the underlying system is genuinely broken (e.g., disk full → watchdog can't start), the supervisor will log on every tick. Acceptable noise; not worth backoff logic for a single-user local dashboard.

## Out of scope (deferred)

- Approach B (structured `AppError` hierarchy, dashboard health indicator). Revisit if the global handler proves too coarse.
- Approach C (idempotency, retries). YAGNI.
- Tightening `db.py` to raise typed exceptions. Backstop handler is enough.
