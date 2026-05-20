"""Outlook refresh: compute is read-only; lock writes rows + lock entries.

Also covers the rejection path: lock against a non-existent base raises.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from tests.fixtures.planning import (
    synthetic_assumption_rows,
    write_assumption_workbook,
    write_empty_shared_workbooks,
    write_empty_support_workbooks,
)


@pytest.fixture
def base_locked_root(tmp_path, monkeypatch):
    """A fresh root with one entity, plan_fy26 base, and a fresh lock file."""
    period = "2026-04"   # Q1 has just closed
    entity = "UK"
    root = tmp_path / "root"
    inputs_dir = root / "tasks" / f"close-{period}" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    base_rows = synthetic_assumption_rows(
        entity=entity, version="plan_fy26", fy_year=2026,
        revenue_per_month=100_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
    )
    base_wb = inputs_dir / f"Assumptions_Plan_FY26_{entity}.xlsx"
    write_assumption_workbook(base_wb, base_rows)
    support = write_empty_support_workbooks(inputs_dir, entity)
    shared = write_empty_shared_workbooks(inputs_dir)

    manifest = {
        "period": period,
        "shared": shared,
        "entities": {
            entity: {
                "fx_rate_to_usd": 1.0,
                **support,
                "assumptions": [
                    {"workbook": base_wb.name, "sheet": "Detail",
                     "header_row": 1, "version": "plan_fy26"},
                ],
            }
        },
    }
    with (inputs_dir / "manifest.yaml").open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    lock_file = root / "profile" / "memory" / "assumptions_locked.json"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    # Empty initial lock; ingest registers the canonical hash on first sight.
    with lock_file.open("w") as f:
        json.dump({}, f)

    monkeypatch.setenv("CFO_HELPER_ROOT", str(root))
    monkeypatch.setenv("CFO_HELPER_TASK_DIR",
                        str(root / "tasks" / f"close-{period}"))
    monkeypatch.setenv("ASSUMPTIONS_LOCK_FILE", str(lock_file))
    # Force scripts.ingest to re-read its module-level LOCK_FILE under the
    # new env vars; the repo's checked-in lock file would otherwise leak.
    import importlib
    import scripts.ingest as ingest_mod
    importlib.reload(ingest_mod)
    return root, period, entity


def test_compute_is_read_only(base_locked_root):
    root, period, entity = base_locked_root
    from scripts.planning.outlook_refresh import compute

    inputs_dir = root / "tasks" / f"close-{period}" / "inputs"
    before_files = sorted(p.name for p in inputs_dir.iterdir())

    proposal = compute(
        repo_root=root,
        base_version="plan_fy26",
        target_version="outlook_q1_2026",
        fy_year=2026, quarter=1,
        corporate_challenges=[{"bucket": "sga", "amount_usd": 50_000}],
        operational_responses=[],
        base_period=period,
    )
    assert not proposal.proposed_rows.empty
    after_files = sorted(p.name for p in inputs_dir.iterdir())
    assert before_files == after_files, "compute must not write any new workbook"


def test_lock_writes_rows_and_lock_entry(base_locked_root):
    root, period, entity = base_locked_root
    from scripts.planning.outlook_refresh import compute, lock

    proposal = compute(
        repo_root=root,
        base_version="plan_fy26",
        target_version="outlook_q1_2026",
        fy_year=2026, quarter=1,
        corporate_challenges=[],
        operational_responses=[],
        base_period=period,
    )

    inputs_dir = root / "tasks" / f"close-{period}" / "inputs"
    lock_result = lock(
        proposal=proposal,
        repo_root=root,
        workbook_stem="Assumptions_Outlook_Q1_2026",
        inputs_dir=inputs_dir,
    )

    # Per-entity workbook on disk
    assert (inputs_dir / "Assumptions_Outlook_Q1_2026_UK.xlsx").exists()

    # Lock entry created
    lock_file = Path(root / "profile" / "memory" / "assumptions_locked.json")
    locks = json.loads(lock_file.read_text())
    assert f"{entity}/outlook_q1_2026" in locks
    entry = locks[f"{entity}/outlook_q1_2026"]
    assert entry.get("locked_against") == f"{entity}/plan_fy26"
    assert lock_result, "lock must return per-entity result map"


def test_lock_rejects_unknown_base(base_locked_root):
    """compute against a missing base_version returns no rows; lock has nothing
    to write, raising a recognizable error."""
    root, period, entity = base_locked_root
    from scripts.planning.outlook_refresh import compute

    with pytest.raises(RuntimeError, match="No assumption rows for base_version"):
        compute(
            repo_root=root,
            base_version="bottoms_up_fy99",   # not present
            target_version="outlook_q1_2026",
            fy_year=2026, quarter=1,
            corporate_challenges=[],
            operational_responses=[],
            base_period=period,
        )
