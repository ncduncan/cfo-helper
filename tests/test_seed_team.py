"""Tests for scripts.seed_team."""

from __future__ import annotations

import pytest


@pytest.fixture
def db_in_tmp(monkeypatch, tmp_path):
    from web import db

    monkeypatch.setattr(db, "DB_DIR", tmp_path)
    db.init_db()
    return db


def test_seed_creates_full_roster(db_in_tmp, capsys):
    from scripts import seed_team

    rc = seed_team.main()
    assert rc == 0
    assert "seeded 6" in capsys.readouterr().out

    expected = {"forge", "cfo", "controller", "fpa_manager", "fpa_senior", "fpa_analyst"}
    actual = {r["id"] for r in db_in_tmp.rows("team")}
    assert expected == actual


def test_seed_is_idempotent(db_in_tmp, capsys):
    from scripts import seed_team

    seed_team.main()
    capsys.readouterr()
    rc = seed_team.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "already seeded" in out
    assert len(db_in_tmp.rows("team")) == 6


def test_seed_marks_forge_as_ai(db_in_tmp):
    from scripts import seed_team

    seed_team.main()
    forge = db_in_tmp.find("team", "forge")
    assert forge["kind"] == "ai"
    assert "fpa" in forge["role_tags"]
    assert "controller" in forge["role_tags"]


def test_seed_cfo_defaults_to_generic_when_profile_missing(db_in_tmp, monkeypatch):
    """With no profile/company_profile.yaml, the cfo row is a generic placeholder."""
    from scripts import profile_loader, seed_team

    profile_loader.load_profile.cache_clear()
    # Patch the binding inside seed_team's namespace (which imported the symbol at load time).
    monkeypatch.setattr(seed_team, "load_profile", lambda: None)

    seed_team.main()
    cfo = db_in_tmp.find("team", "cfo")
    assert cfo["name"] == "CFO"
    assert cfo["email"] is None
    assert cfo["kind"] == "human"
    profile_loader.load_profile.cache_clear()


def test_seed_cfo_reads_from_profile_when_present(db_in_tmp, monkeypatch):
    """When profile/company_profile.yaml provides cfo_name/cfo_email, the seed uses them."""
    from scripts import profile_loader, seed_team

    fake = profile_loader.Profile(
        company=profile_loader.Company(cfo_name="Test CFO", cfo_email="cfo@example.com"),
        parent_company=profile_loader.ParentCompany(),
    )
    profile_loader.load_profile.cache_clear()
    monkeypatch.setattr(seed_team, "load_profile", lambda: fake)

    seed_team.main()
    cfo = db_in_tmp.find("team", "cfo")
    assert cfo["name"] == "Test CFO"
    assert cfo["email"] == "cfo@example.com"
    assert cfo["kind"] == "human"
    profile_loader.load_profile.cache_clear()


def test_seed_rows_validate_against_model(db_in_tmp):
    """Every seeded row must round-trip through TeamMember."""
    from scripts import seed_team
    from web.models import TeamMember

    seed_team.main()
    for row in db_in_tmp.rows("team"):
        TeamMember.model_validate(row)
