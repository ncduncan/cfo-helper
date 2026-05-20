"""
File-watch → SSE event broadcaster.

Watches the JSON DB collections under ``profile/db/*.json`` and the Forge
queue bundle drops under ``tasks/<id>/queue/`` (created by ``web.bundles``).
On any change, publishes ``db_changed`` events to all connected SSE clients.
Clients re-fetch the affected fragment via HTMX ``hx-trigger=
"db-changed:<collection> from:body"``.

Decisions:
- We watch *only* ``profile/db/`` (not all of ``tasks/``) so we don't fire
  thousands of events when a step produces a multi-file artifact dump.
- ``tasks/<id>/queue/`` is watched separately to surface bundle re-writes
  from M5's queue producer.
- A 200ms debounce per (collection, path) suppresses duplicate observer
  events (some editors stat → write → stat).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path
from typing import AsyncIterator

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from scripts.paths import profile_db_dir

REPO = Path(__file__).resolve().parent.parent
DB_DIR = profile_db_dir()
TASKS_DIR = REPO / "tasks"

_DB_FILE_RE = re.compile(r"profile/db/([a-z_]+)\.json$|db/([a-z_]+)\.json$")
_VALID_COLLECTIONS = {
    "team", "standard_work", "tasks", "queue", "schedules", "memory_proposals",
}
_QUEUE_PATH_RE = re.compile(r"tasks/([^/]+)/queue/")
_DEBOUNCE_SECS = 0.2


class _Hub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[dict]:
        q: asyncio.Queue[dict] = asyncio.Queue(maxsize=128)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict]) -> None:
        self._subscribers.discard(q)

    def publish(self, event: dict) -> None:
        if self._loop is None:
            return
        for q in list(self._subscribers):
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, event)
            except asyncio.QueueFull:
                pass


hub = _Hub()


class _Handler(FileSystemEventHandler):
    def __init__(self) -> None:
        super().__init__()
        self._last: dict[str, float] = {}

    def _emit(self, path: str) -> None:
        key = path
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        if now - last < _DEBOUNCE_SECS:
            return
        self._last[key] = now

        norm = path.replace("\\", "/")
        m = _DB_FILE_RE.search(norm)
        if m:
            collection = m.group(1)
            if collection not in _VALID_COLLECTIONS:
                return
            hub.publish(
                {
                    "type": "db_changed",
                    "collection": collection,
                    "path": norm,
                }
            )
            return

        m = _QUEUE_PATH_RE.search(norm)
        if m and norm.endswith(".md"):
            task_id = m.group(1)
            hub.publish(
                {
                    "type": "queue_bundle_changed",
                    "task_id": task_id,
                    "path": norm,
                }
            )

    def on_modified(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._emit(event.src_path)

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._emit(event.src_path)


_observer: Observer | None = None


def start_observer() -> None:
    global _observer
    if _observer is not None:
        return
    DB_DIR.mkdir(parents=True, exist_ok=True)
    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    handler = _Handler()
    obs = Observer()
    obs.schedule(handler, str(DB_DIR), recursive=False)
    obs.schedule(handler, str(TASKS_DIR), recursive=True)
    obs.daemon = True
    obs.start()
    _observer = obs


def stop_observer() -> None:
    global _observer
    if _observer is None:
        return
    _observer.stop()
    _observer.join(timeout=1)
    _observer = None


def is_observer_alive() -> bool:
    """True if the watchdog Observer thread is currently alive."""
    return _observer is not None and _observer.is_alive()


async def event_stream() -> AsyncIterator[str]:
    """Async generator that yields SSE-formatted strings."""
    q = hub.subscribe()
    try:
        yield "event: ready\ndata: {}\n\n"
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=15)
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
    finally:
        hub.unsubscribe(q)
