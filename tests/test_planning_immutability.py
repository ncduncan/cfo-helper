"""Append-only enforcement: a locked (entity, version) cannot be re-locked
with different content."""

from __future__ import annotations

import pytest

from scripts.ingest import enforce_assumption_immutability
from tests.fixtures.planning import synthetic_assumption_rows


@pytest.fixture(autouse=True)
def isolate_lock_file(tmp_path, monkeypatch):
    lock_file = tmp_path / "assumptions_locked.json"
    monkeypatch.setenv("ASSUMPTIONS_LOCK_FILE", str(lock_file))
    # Re-import the module-level LOCK_FILE binding so the env override sticks.
    import importlib
    import scripts.ingest as ingest_mod
    importlib.reload(ingest_mod)
    yield
    importlib.reload(ingest_mod)


def test_relock_with_different_content_raises():
    from scripts.ingest import enforce_assumption_immutability as enforce

    rows_a = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
        revenue_per_month=100_000,
    )
    rows_b = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
        revenue_per_month=110_000,
    )
    enforce(rows_a)
    with pytest.raises(RuntimeError, match="immutability") as e:
        enforce(rows_b)
    msg = str(e.value)
    # Both hashes must appear in the rejection so the operator can verify.
    assert "locked hash" in msg
    assert "new hash" in msg


def test_relock_with_same_content_idempotent():
    from scripts.ingest import enforce_assumption_immutability as enforce

    rows = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
    )
    locks_first = enforce(rows)
    locks_second = enforce(rows)
    assert locks_first == locks_second


def test_distinct_entities_lock_separately():
    from scripts.ingest import enforce_assumption_immutability as enforce

    uk = synthetic_assumption_rows(entity="UK", version="plan_fy26", fy_year=2026)
    us = synthetic_assumption_rows(entity="US", version="plan_fy26", fy_year=2026,
                                    revenue_per_month=200_000)
    locks = enforce(uk)
    locks = enforce(us)
    assert "UK/plan_fy26" in locks
    assert "US/plan_fy26" in locks
    assert locks["UK/plan_fy26"]["hash"] != locks["US/plan_fy26"]["hash"]
