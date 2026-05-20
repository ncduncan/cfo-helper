"""Strategic-plan-walk stitches Y1 (operational plan) + Y2/Y3 (strategic).

Asserts continuity at the Y1→Y2 boundary and that the operational anchor
walk Y1 reconciles to plan_fy26 trio.
"""

from __future__ import annotations

import pytest
import yaml

from tests.fixtures.planning import (
    synthetic_assumption_rows,
    write_assumption_workbook,
)


@pytest.fixture
def strategic_root(tmp_path, monkeypatch):
    """Build a workspace/<period> layout (the walk + strategic_plan_build modules
    look there) plus a CFO_HELPER_TASK_DIR under tasks/ for connector reads.

    The walk reads from workspace/, so we create that layout. Connectors
    read from CFO_HELPER_TASK_DIR (we point that at the same workspace).
    """
    period = "2026-01"
    entity = "UK"
    root = tmp_path / "root"

    # Workspace directory (strategic_plan_walk reads from workspace/<period>)
    inputs_dir = root / "workspace" / period / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)

    op_rows = synthetic_assumption_rows(
        entity=entity, version="plan_fy26", fy_year=2026,
        revenue_per_month=100_000, cogs_per_month=30_000,
        rd_per_month=15_000, sga_per_month=12_000,
    )
    op_wb = inputs_dir / f"Assumptions_Plan_FY26_{entity}.xlsx"
    write_assumption_workbook(op_wb, op_rows)

    # Strategic Y2/Y3 rows: one revenue row at year-end Dec for each year
    strat_rows = []
    for year_offset, period_str in (("Y2", "2027-12"), ("Y3", "2028-12")):
        # Annual sales = 12 × monthly × 1.10 (Y2) and × 1.21 (Y3) for variety
        scale = 1.10 if year_offset == "Y2" else 1.21
        strat_rows.append({
            "entity": entity, "period": period_str, "version": "plan_3yr_fy26",
            "account": "4100", "pnl_line": "Revenue / Subscription",
            "account_class": "revenue",
            "product_line": "flight_ops", "functional_area": None,
            "driver_dim": "percent_growth", "driver_value": "+10%",
            "quantity": 0.10, "unit_cost": 12 * 100_000,
            "period_amount_usd": 12 * 100_000 * scale,
            "locked_at": "2026-04-01",
            "source_doc": "synthetic_strategic.xlsx",
        })
    import pandas as pd
    from connectors.assumptions import ASSUMPTION_COLUMNS
    strat_df = pd.DataFrame(strat_rows, columns=ASSUMPTION_COLUMNS)
    strat_wb = inputs_dir / f"Assumptions_Plan_3yr_{entity}.xlsx"
    write_assumption_workbook(strat_wb, strat_df)

    manifest = {
        "period": period,
        "entities": {
            entity: {
                "fx_rate_to_usd": 1.0,
                "gl": {"workbook": "missing.xlsx", "sheet": "GL"},
                "assumptions": [
                    {"workbook": op_wb.name, "sheet": "Detail",
                     "header_row": 1, "version": "plan_fy26"},
                    {"workbook": strat_wb.name, "sheet": "Detail",
                     "header_row": 1, "version": "plan_3yr_fy26"},
                ],
            }
        },
    }
    with (inputs_dir / "manifest.yaml").open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    # Materiality with cash_tax_rate_proxy so FCF is computed
    mat_dir = root / "profile" / "memory"
    mat_dir.mkdir(parents=True, exist_ok=True)
    with (mat_dir / "materiality.yaml").open("w") as f:
        yaml.safe_dump({"strategic_plan": {"cash_tax_rate_proxy": 0.21}}, f)

    monkeypatch.setenv("CFO_HELPER_ROOT", str(root))
    # connectors resolve via workspace_root → workspace/<period> when no
    # CFO_HELPER_TASK_DIR is set. Don't set the task-dir env var here so the
    # walk's workspace-based path resolution wins.
    monkeypatch.delenv("CFO_HELPER_TASK_DIR", raising=False)
    return root, period, entity


def test_walk_continuity_y1_to_y2(strategic_root):
    root, period, entity = strategic_root
    from scripts.planning.strategic_plan_walk import walk

    result = walk(strategic_version="plan_3yr_fy26", repo_root=root)

    y1 = result.walk_by_year["Y1"]
    y2 = result.walk_by_year["Y2"]
    y3 = result.walk_by_year["Y3"]

    # Y1 sales should match the plan_fy26 sales (12 × 100k)
    assert y1["sales"] == pytest.approx(12 * 100_000, abs=0.5)

    # Y2 sales is the strategic Y2 revenue row (12 × 100k × 1.10)
    assert y2["sales"] == pytest.approx(12 * 100_000 * 1.10, abs=0.5)

    # Y3 sales is the strategic Y3 revenue row (12 × 100k × 1.21)
    assert y3["sales"] == pytest.approx(12 * 100_000 * 1.21, abs=0.5)

    # FCF should be ebit × (1 - 0.21) per the proxy
    expected_y1_fcf = y1["ebit"] * (1 - 0.21)
    assert y1["fcf"] == pytest.approx(expected_y1_fcf, abs=0.5)


def test_walk_fcf_unset_when_etr_missing(strategic_root, monkeypatch):
    """No cash_tax_rate_proxy → FCF returns None across the walk."""
    root, period, entity = strategic_root
    # Overwrite materiality with no proxy
    mat_path = root / "profile" / "memory" / "materiality.yaml"
    mat_path.write_text(yaml.safe_dump({"strategic_plan": {}}))

    from scripts.planning.strategic_plan_walk import walk
    result = walk(strategic_version="plan_3yr_fy26", repo_root=root)
    for year in ("Y1", "Y2", "Y3"):
        assert result.walk_by_year[year]["fcf"] is None
    assert result.cash_tax_rate_used is None
