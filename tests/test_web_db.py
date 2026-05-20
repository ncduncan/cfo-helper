"""Tests for web.db — JSON-collection store with flock + atomic rename."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def db_in_tmp(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    db.init_db()
    return db


def test_init_db_creates_all_collections(db_in_tmp, tmp_path):
    for name in ("team", "standard_work", "tasks", "queue", "schedules"):
        p = tmp_path / f"{name}.json"
        assert p.exists()
        doc = json.loads(p.read_text())
        assert doc == {"version": 1, "rows": []}


def test_init_db_is_idempotent(db_in_tmp, tmp_path):
    db_in_tmp.insert("team", {"id": "alice", "name": "Alice"})
    db_in_tmp.init_db()
    assert db_in_tmp.find("team", "alice") == {"id": "alice", "name": "Alice"}


def test_read_unknown_collection_raises(db_in_tmp):
    with pytest.raises(ValueError, match="unknown collection"):
        db_in_tmp.read("not_a_real_collection")


def test_insert_and_find(db_in_tmp):
    row = {"id": "r1", "x": 1}
    db_in_tmp.insert("team", row)
    assert db_in_tmp.find("team", "r1") == row
    assert db_in_tmp.find("team", "no") is None


def test_insert_rejects_missing_id(db_in_tmp):
    with pytest.raises(ValueError, match="missing required 'id'"):
        db_in_tmp.insert("team", {"name": "Bob"})


def test_insert_rejects_duplicate_id(db_in_tmp):
    db_in_tmp.insert("team", {"id": "x", "n": 1})
    with pytest.raises(ValueError, match="duplicate id"):
        db_in_tmp.insert("team", {"id": "x", "n": 2})


def test_upsert_inserts_or_replaces(db_in_tmp):
    db_in_tmp.upsert("team", {"id": "u", "n": 1})
    assert db_in_tmp.find("team", "u")["n"] == 1
    db_in_tmp.upsert("team", {"id": "u", "n": 2})
    assert db_in_tmp.find("team", "u")["n"] == 2
    assert len(db_in_tmp.rows("team")) == 1


def test_update_merges_patch(db_in_tmp):
    db_in_tmp.insert("team", {"id": "p", "a": 1, "b": 2})
    db_in_tmp.update("team", "p", {"b": 99, "c": 3})
    row = db_in_tmp.find("team", "p")
    assert row == {"id": "p", "a": 1, "b": 99, "c": 3}


def test_update_missing_raises_key_error(db_in_tmp):
    with pytest.raises(KeyError):
        db_in_tmp.update("team", "nope", {"a": 1})


def test_delete_removes_and_reports(db_in_tmp):
    db_in_tmp.insert("team", {"id": "d"})
    assert db_in_tmp.delete("team", "d") is True
    assert db_in_tmp.find("team", "d") is None
    assert db_in_tmp.delete("team", "d") is False


def test_write_validates_mutator_output(db_in_tmp):
    with pytest.raises(ValueError, match="mutator must return"):
        db_in_tmp.write("team", lambda _doc: {"version": 1})


def test_atomic_write_does_not_leave_partial_file(db_in_tmp, tmp_path, monkeypatch):
    """If json.dump raises mid-write, the original file must be intact."""
    db_in_tmp.insert("team", {"id": "stable", "name": "Stable"})
    original = (tmp_path / "team.json").read_text()

    real_dump = json.dump

    def boom(*args, **kwargs):
        raise RuntimeError("simulated mid-write failure")

    monkeypatch.setattr(json, "dump", boom)
    with pytest.raises(RuntimeError):
        db_in_tmp.insert("team", {"id": "boom", "name": "Boom"})
    monkeypatch.setattr(json, "dump", real_dump)

    assert (tmp_path / "team.json").read_text() == original
    assert db_in_tmp.find("team", "stable") is not None
    assert db_in_tmp.find("team", "boom") is None


def test_concurrent_writes_serialize_via_flock(db_in_tmp, tmp_path):
    """Two threads inserting into the same collection must both land."""
    import threading

    barrier = threading.Barrier(2)
    errors = []

    def insert(rid):
        try:
            barrier.wait()
            db_in_tmp.insert("team", {"id": rid, "name": rid})
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=insert, args=("a",))
    t2 = threading.Thread(target=insert, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    ids = sorted(r["id"] for r in db_in_tmp.rows("team"))
    assert ids == ["a", "b"]


def test_rows_returns_empty_for_uninitialized(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    assert db.rows("team") == []
