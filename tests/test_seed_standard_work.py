"""Tests for scripts.seed_standard_work."""

from __future__ import annotations

import pytest


@pytest.fixture
def db_in_tmp(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    db.init_db()
    return db


def test_seed_imports_all_task_types(db_in_tmp, capsys):
    from scripts import seed_standard_work

    rc = seed_standard_work.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "seeded" in out
    # task_types/ should have ≥10 YAMLs (currently 17)
    assert len(db_in_tmp.rows("standard_work")) >= 10


def test_seed_is_idempotent(db_in_tmp, capsys):
    from scripts import seed_standard_work

    seed_standard_work.main()
    before = len(db_in_tmp.rows("standard_work"))
    capsys.readouterr()
    rc = seed_standard_work.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "already seeded" in out
    assert len(db_in_tmp.rows("standard_work")) == before


def test_seed_ceo_letter_has_expected_shape(db_in_tmp):
    from scripts import seed_standard_work

    seed_standard_work.main()
    sw = db_in_tmp.find("standard_work", "ceo_letter")
    assert sw is not None
    assert sw["source_task_type"] == "ceo_letter"
    assert "CEO letter" in sw["name"]
    assert len(sw["steps"]) >= 2  # P1 (reporting) + P2 (reviewer)
    assert sw["steps"][0]["owner_role"] == "reporting"
    assert sw["steps"][1]["owner_role"] == "reviewer"
    assert sw["steps"][1]["depends_on"] == [sw["steps"][0]["id"]]


def test_seed_steps_default_to_ai_and_forge(db_in_tmp):
    from scripts import seed_standard_work

    seed_standard_work.main()
    for sw in db_in_tmp.rows("standard_work"):
        for s in sw["steps"]:
            assert s["kind"] == "ai"
            assert s["default_assignee_id"] == "forge"


def test_seed_rows_validate_against_model(db_in_tmp):
    from scripts import seed_standard_work
    from web.models import StandardWork

    seed_standard_work.main()
    for row in db_in_tmp.rows("standard_work"):
        StandardWork.model_validate(row)


def test_seed_month_end_close_steps_are_sequential(db_in_tmp):
    from scripts import seed_standard_work

    seed_standard_work.main()
    sw = db_in_tmp.find("standard_work", "month_end_close")
    assert sw is not None
    ids = [s["id"] for s in sw["steps"]]
    assert ids == ["p1", "p2", "p3", "p4", "p5"]
    # Each step (except first) depends on the previous one
    for i, s in enumerate(sw["steps"][1:], start=1):
        assert s["depends_on"] == [ids[i - 1]]


def test_seed_inputs_carry_runner_hint(db_in_tmp):
    from scripts import seed_standard_work

    seed_standard_work.main()
    sw = db_in_tmp.find("standard_work", "month_end_close")
    p1 = sw["steps"][0]
    assert any("runner:scripts.dispatch.run_p1_controller" in i for i in p1["inputs"])
