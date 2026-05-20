"""
JSON-file collection store under profile/db/.

Each collection is a single file ``profile/db/<name>.json`` with shape::

    {"version": 1, "rows": [...]}

All writes hold a cross-platform ``filelock.FileLock`` on the sibling
``profile/db/<name>.json.lock`` and land via tempfile + ``os.replace()`` so
readers never see a half-written file. Single uvicorn worker is assumed
(web.main warns on startup if WEB_CONCURRENCY != 1). The same lock is
honored by ``scripts/run_queue.py`` so a queue claim from VS Code and a step
edit from the dashboard cannot collide.

This module is the single mutator of all DB state. Routes and CLIs go
through ``insert/upsert/update/delete``; for compound transactions use
``write(name, mutator)`` which takes the lock once.
"""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from filelock import FileLock

from scripts.paths import profile_db_dir

REPO = Path(__file__).resolve().parent.parent
DB_DIR = profile_db_dir()

COLLECTIONS = (
    "team",
    "standard_work",
    "tasks",
    "queue",
    "schedules",
    "memory_proposals",
)


def _path(name: str) -> Path:
    if name not in COLLECTIONS:
        raise ValueError(f"unknown collection: {name!r}; allowed: {COLLECTIONS}")
    return DB_DIR / f"{name}.json"


def _lock_path(name: str) -> Path:
    return DB_DIR / f"{name}.json.lock"


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    for name in COLLECTIONS:
        p = _path(name)
        if not p.exists():
            _atomic_write(p, {"version": 1, "rows": []})


def read(name: str) -> dict[str, Any]:
    p = _path(name)
    if not p.exists():
        return {"version": 1, "rows": []}
    return json.loads(p.read_text())


def rows(name: str) -> list[dict[str, Any]]:
    return read(name).get("rows", [])


@contextmanager
def _exclusive_lock(name: str) -> Iterator[None]:
    lock = _lock_path(name)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(lock)):
        yield


def _atomic_write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f, indent=2, sort_keys=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def write(
    name: str, mutator: Callable[[dict[str, Any]], dict[str, Any]]
) -> dict[str, Any]:
    """Atomically read, mutate, and write. Mutator returns the new doc."""
    with _exclusive_lock(name):
        current = read(name)
        new = mutator(current)
        if not isinstance(new, dict) or "rows" not in new:
            raise ValueError("mutator must return {'version': int, 'rows': list}")
        _atomic_write(_path(name), new)
        return new


# --- Row helpers ------------------------------------------------------------


def find(name: str, row_id: str) -> dict[str, Any] | None:
    for r in rows(name):
        if r.get("id") == row_id:
            return r
    return None


def insert(name: str, row: dict[str, Any]) -> dict[str, Any]:
    if "id" not in row:
        raise ValueError("row missing required 'id'")

    def m(doc: dict[str, Any]) -> dict[str, Any]:
        if any(r.get("id") == row["id"] for r in doc["rows"]):
            raise ValueError(f"duplicate id in {name}: {row['id']!r}")
        doc["rows"].append(row)
        return doc

    write(name, m)
    return row


def upsert(name: str, row: dict[str, Any]) -> dict[str, Any]:
    if "id" not in row:
        raise ValueError("row missing required 'id'")

    def m(doc: dict[str, Any]) -> dict[str, Any]:
        existing = doc["rows"]
        for i, r in enumerate(existing):
            if r.get("id") == row["id"]:
                existing[i] = row
                return doc
        existing.append(row)
        return doc

    write(name, m)
    return row


def update(name: str, row_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    def m(doc: dict[str, Any]) -> dict[str, Any]:
        for r in doc["rows"]:
            if r.get("id") == row_id:
                r.update(patch)
                return doc
        raise KeyError(row_id)

    write(name, m)
    found = find(name, row_id)
    assert found is not None
    return found


def delete(name: str, row_id: str) -> bool:
    removed = False

    def m(doc: dict[str, Any]) -> dict[str, Any]:
        nonlocal removed
        before = len(doc["rows"])
        doc["rows"] = [r for r in doc["rows"] if r.get("id") != row_id]
        removed = len(doc["rows"]) < before
        return doc

    write(name, m)
    return removed
