"""FCF identity for scripts.planning.trio.

Asserts FCF = sales − cogs − opex − tax + Δcontract_liab − Δcontract_asset
within float tolerance, including edge cases.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests.fixtures.planning import (
    synthetic_assumption_rows,
    write_assumption_workbook,
)


def _setup_root(tmp_path: Path, rows: pd.DataFrame, *, period: str,
                entity: str, version: str, lock_file: Path | None = None) -> Path:
    """Build a self-contained CFO_HELPER_ROOT with one entity + one version."""
    root = tmp_path / "root"
    inputs_dir = root / "tasks" / f"close-{period}" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    workbook = inputs_dir / f"Assumptions_{version.title()}_{entity}.xlsx"
    write_assumption_workbook(workbook, rows)

    manifest = {
        "period": period,
        "entities": {
            entity: {
                "fx_rate_to_usd": 1.0,
                "gl": {"workbook": "missing.xlsx", "sheet": "GL"},
                "assumptions": [
                    {"workbook": workbook.name, "sheet": "Detail",
                     "header_row": 1, "version": version},
                ],
            }
        },
    }
    with (inputs_dir / "manifest.yaml").open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)
    return root


@pytest.fixture
def planning_env(tmp_path, monkeypatch):
    monkeypatch.setenv("CFO_HELPER_ROOT", "")  # set per test

    def _setup(rows: pd.DataFrame, *, period: str = "2026-01",
                entity: str = "UK", version: str = "plan_fy26") -> Path:
        root = _setup_root(tmp_path, rows, period=period, entity=entity,
                            version=version)
        monkeypatch.setenv("CFO_HELPER_ROOT", str(root))
        # Use a per-test lock file so test runs don't pollute the real one.
        monkeypatch.setenv("ASSUMPTIONS_LOCK_FILE",
                            str(root / "profile" / "memory" / "assumptions_locked.json"))
        # Tell connectors to read from this task dir.
        task_dir = root / "tasks" / f"close-{period}"
        monkeypatch.setenv("CFO_HELPER_TASK_DIR", str(task_dir))
        return root

    return _setup


def test_fcf_identity_no_deferred_revenue(planning_env):
    """No deferred-rev movement: FCF reduces to ebit + da + Δap − Δar − capex − tax."""
    rows = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
        revenue_per_month=100_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
    )
    root = planning_env(rows)

    from scripts.planning.trio import compute_trio
    r = compute_trio(version="plan_fy26", entity="UK",
                      period="2026-01", repo_root=root)

    # Sales = 12 × 100k = 1.2M; EBIT = revenue − cogs − rd − sga
    expected_sales = 12 * 100_000
    expected_ebit = 12 * (100_000 - 30_000 - 15_000 - 12_000)
    assert r.sales_usd == pytest.approx(expected_sales, abs=0.5)
    assert r.ebit_usd == pytest.approx(expected_ebit, abs=0.5)

    # FCF identity: with no D&A, no AP/AR, no capex, no deferred rev, no
    # cap-comm, the formula is EBIT − cash_tax. Default cash tax = 21% × EBIT
    # (positive), so FCF = EBIT × (1 − 0.21).
    expected_fcf = expected_ebit * (1 - 0.21)
    assert r.fcf_usd == pytest.approx(expected_fcf, abs=0.5)


def test_fcf_identity_with_deferred_revenue(planning_env):
    """With multi-year prepay (deferred rev grows), FCF picks up the swing."""
    rows = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
        revenue_per_month=100_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
        deferred_rev_per_month=50_000,
    )
    root = planning_env(rows)
    from scripts.planning.trio import compute_trio
    r = compute_trio(version="plan_fy26", entity="UK",
                      period="2026-01", repo_root=root)

    expected_ebit = 12 * (100_000 - 30_000 - 15_000 - 12_000)
    cash_tax = 0.21 * max(0.0, expected_ebit)
    expected_fcf = expected_ebit - cash_tax + 12 * 50_000

    assert r.fcf_usd == pytest.approx(expected_fcf, abs=0.5)


def test_fcf_identity_negative(planning_env):
    """Negative EBIT: cash tax floors at zero, FCF can be deeply negative."""
    rows = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
        revenue_per_month=20_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
    )
    root = planning_env(rows)
    from scripts.planning.trio import compute_trio
    r = compute_trio(version="plan_fy26", entity="UK",
                      period="2026-01", repo_root=root)

    expected_ebit = 12 * (20_000 - 30_000 - 15_000 - 12_000)
    assert expected_ebit < 0
    # Cash tax = 0 when EBIT negative, so FCF == EBIT in this minimal case.
    assert r.fcf_usd == pytest.approx(expected_ebit, abs=0.5)


def test_fcf_identity_explicit_cash_tax(planning_env):
    """Explicit cash-tax row overrides the default rate proxy."""
    rows = synthetic_assumption_rows(
        entity="UK", version="plan_fy26", fy_year=2026,
        revenue_per_month=100_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
        cash_tax_per_month=10_000,
    )
    root = planning_env(rows)
    from scripts.planning.trio import compute_trio
    r = compute_trio(version="plan_fy26", entity="UK",
                      period="2026-01", repo_root=root)

    expected_ebit = 12 * (100_000 - 30_000 - 15_000 - 12_000)
    expected_fcf = expected_ebit - 12 * 10_000
    assert r.fcf_usd == pytest.approx(expected_fcf, abs=0.5)
