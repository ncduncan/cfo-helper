"""Three-layer roll-up for scripts.planning.gap_to_stretch.

Asserts:
  ΔEBIT = Δrevenue − Δcogs − Δrd − Δsga
  Σ driver_deltas (grouped by bucket) = bucket_delta
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests.fixtures.planning import (
    synthetic_assumption_rows,
    write_assumption_workbook,
)


@pytest.fixture
def two_version_root(tmp_path, monkeypatch):
    """Build a CFO_HELPER_ROOT with one entity and two assumption versions."""
    period = "2026-01"
    entity = "UK"
    root = tmp_path / "root"
    inputs_dir = root / "tasks" / f"close-{period}" / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    base = synthetic_assumption_rows(
        entity=entity, version="bottoms_up_fy26", fy_year=2026,
        revenue_per_month=100_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
    )
    target = synthetic_assumption_rows(
        entity=entity, version="plan_fy26", fy_year=2026,
        revenue_per_month=110_000, cogs_per_month=32_000,
        rd_per_month=15_000, sga_per_month=14_000,
    )
    base_wb = inputs_dir / f"Assumptions_BottomsUp_FY26_{entity}.xlsx"
    target_wb = inputs_dir / f"Assumptions_Plan_FY26_{entity}.xlsx"
    write_assumption_workbook(base_wb, base)
    write_assumption_workbook(target_wb, target)

    manifest = {
        "period": period,
        "entities": {
            entity: {
                "fx_rate_to_usd": 1.0,
                "gl": {"workbook": "missing.xlsx", "sheet": "GL"},
                "assumptions": [
                    {"workbook": base_wb.name, "sheet": "Detail",
                     "header_row": 1, "version": "bottoms_up_fy26"},
                    {"workbook": target_wb.name, "sheet": "Detail",
                     "header_row": 1, "version": "plan_fy26"},
                ],
            }
        },
    }
    with (inputs_dir / "manifest.yaml").open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    monkeypatch.setenv("CFO_HELPER_ROOT", str(root))
    monkeypatch.setenv("CFO_HELPER_TASK_DIR",
                        str(root / "tasks" / f"close-{period}"))
    monkeypatch.setenv("ASSUMPTIONS_LOCK_FILE",
                        str(root / "profile" / "memory" / "assumptions_locked.json"))
    return root, period, entity


def test_gap_three_layer_reconciles(two_version_root):
    root, period, entity = two_version_root
    from scripts.planning.gap_to_stretch import gap

    result = gap(
        from_version="bottoms_up_fy26",
        to_version="plan_fy26",
        period=period,
        repo_root=root,
    )

    # ΔEBIT identity
    expected_ebit_delta = (
        result.bucket_delta["revenue"]
        - result.bucket_delta["cogs"]
        - result.bucket_delta["rd"]
        - result.bucket_delta["sga"]
    )
    assert result.trio_delta["delta_ebit_usd"] == pytest.approx(
        expected_ebit_delta, abs=0.5
    )

    # Bucket reconciliation: sum of driver deltas grouped by bucket equals
    # the bucket_delta entry.
    if not result.driver_deltas.empty:
        for bucket in ("revenue", "cogs", "rd", "sga"):
            driver_sum = float(
                result.driver_deltas[result.driver_deltas["bucket"] == bucket]
                ["delta_usd"].sum()
            )
            assert driver_sum == pytest.approx(
                result.bucket_delta[bucket], abs=0.5
            ), f"bucket {bucket!r}: driver sum {driver_sum} vs bucket {result.bucket_delta[bucket]}"


def test_gap_with_no_change_is_zero(two_version_root, tmp_path, monkeypatch):
    """Identical from/to versions produce zero deltas."""
    root, period, entity = two_version_root
    from scripts.planning.gap_to_stretch import gap

    result = gap(
        from_version="bottoms_up_fy26",
        to_version="bottoms_up_fy26",
        period=period,
        repo_root=root,
    )
    for k in ("delta_sales_usd", "delta_ebit_usd", "delta_fcf_usd"):
        assert result.trio_delta[k] == pytest.approx(0.0, abs=0.5)
    for b in ("revenue", "cogs", "rd", "sga"):
        assert result.bucket_delta[b] == pytest.approx(0.0, abs=0.5)
