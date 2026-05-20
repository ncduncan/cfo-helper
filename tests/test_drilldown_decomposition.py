"""Drilldown driver decomposition: subledger sum reconciles to GL movement;
runner emits per-driver claims with provenance.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from scripts.drilldown.bridge import bridge


def test_subledger_sum_reconciles_to_gl():
    """Σ subledger lines + reconciling = GL actual (within tolerance)."""
    gl_actual = -1_000_000.0   # cogs is negative in GL
    ap_lines = pd.DataFrame([
        {"entity": "UK", "period": "2026-04", "account": "5100",
         "account_name": "COGS / Hosting", "vendor_id": "V1",
         "vendor_name": "Azure", "currency": "USD",
         "amount_local": 600_000, "amount_usd": 600_000,
         "invoice_id": "I1", "invoice_date": "2026-04-15",
         "driver_dim": "azure_sku", "driver_value": "A1"},
        {"entity": "UK", "period": "2026-04", "account": "5100",
         "account_name": "COGS / Hosting", "vendor_id": "V2",
         "vendor_name": "AWS", "currency": "USD",
         "amount_local": 400_000, "amount_usd": 400_000,
         "invoice_id": "I2", "invoice_date": "2026-04-15",
         "driver_dim": "azure_sku", "driver_value": "A2"},
    ])
    result = bridge(
        gl_actual_usd=gl_actual,
        sign_convention="spend",
        subledger_lines={"ap": ap_lines},
        assumptions=pd.DataFrame(),
        tolerance_usd=100.0,
    )
    # Spend convention: actual flipped to positive
    assert result.actual_usd == pytest.approx(1_000_000, abs=0.5)
    assert result.subledger_total == pytest.approx(1_000_000, abs=0.5)
    assert abs(result.reconciling_usd) <= 100.0
    assert result.tieout_pass is True

    # Driver-level decomposition reconciles to subledger total
    driver_sum = float(result.drivers["actual_usd"].sum())
    assert driver_sum == pytest.approx(result.subledger_total, abs=0.5)


def test_runner_emits_status_when_no_account_map(tmp_path, monkeypatch):
    """run_drilldown(...) for an unmapped account writes a status work_product."""
    from scripts.drilldown import runners as drill_runners

    # Point the runner at a fresh repo root with no account_map entries.
    fake_root = tmp_path / "fake_repo"
    (fake_root / "profile" / "memory").mkdir(parents=True)
    (fake_root / "profile" / "memory" / "account_map.json").write_text(
        '{"entries": []}'
    )
    (fake_root / "profile" / "memory" / "materiality.yaml").write_text(
        "drilldown:\n  bridge_tolerance_usd: 100.0\n"
        "variance:\n  abs_usd: 100.0\n"
    )
    monkeypatch.setenv("CFO_HELPER_ROOT", str(fake_root))

    task_dir = tmp_path / "task"
    task_dir.mkdir()
    drill_runners.run_drilldown(
        task_dir, period="2026-04", entity="UK", account="9999",
    )

    wp_path = task_dir / "outputs" / "fpa" / "work_product.json"
    assert wp_path.exists()
    import json
    doc = json.loads(wp_path.read_text())
    assert any(c["id"].endswith(".status") for c in doc["claims"])
    status_claim = next(c for c in doc["claims"] if c["id"].endswith(".status"))
    assert status_claim["value"] == "no_account_map"
