"""
Variance computation and materiality flagging.

FP&A uses this to compare actuals (from Controller's consolidated output) to
budget and forecast, flagging items that breach the materiality thresholds in
memory/materiality.yaml.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import yaml


def _materiality(repo_root: Path) -> dict:
    path = repo_root / "profile" / "memory" / "materiality.yaml"
    with path.open() as f:
        return yaml.safe_load(f)


def compute_variance(actual: pd.DataFrame, baseline: pd.DataFrame, *,
                     baseline_label: str) -> pd.DataFrame:
    """Return per-account variance dataframe.

    actual / baseline must have columns [account, account_name, amount_usd].
    Returns columns: account, account_name, actual_usd, <baseline_label>_usd,
                     variance_usd, variance_pct.
    """
    a = actual.rename(columns={"amount_usd": "actual_usd"})
    b = baseline.rename(columns={"amount_usd": f"{baseline_label}_usd"})
    merged = a.merge(b, on=["account", "account_name"], how="outer").fillna(0)
    merged["variance_usd"] = merged["actual_usd"] - merged[f"{baseline_label}_usd"]
    merged["variance_pct"] = merged.apply(
        lambda r: (r["variance_usd"] / r[f"{baseline_label}_usd"])
                   if r[f"{baseline_label}_usd"] not in (0, 0.0) else None,
        axis=1,
    )
    return merged.sort_values("variance_usd", key=lambda s: s.abs(), ascending=False)


def flag_material(variances: pd.DataFrame, repo_root: Path) -> pd.DataFrame:
    """Add a `material` boolean column based on profile/memory/materiality.yaml."""
    mat = _materiality(repo_root).get("variance", {"abs_usd": 50000, "pct": 0.05})
    abs_threshold = float(mat.get("abs_usd", 50000))
    pct_threshold = float(mat.get("pct", 0.05))
    out = variances.copy()
    out["material"] = (out["variance_usd"].abs() >= abs_threshold) & (
        out["variance_pct"].fillna(0).abs() >= pct_threshold
    )
    return out


def variance_self_checks(variances: pd.DataFrame,
                         actual_total_claim: float,
                         baseline_total_claim: float,
                         tolerance_usd: float = 1.0) -> list[dict]:
    """Self-checks: variance math reconciles, totals tie back to upstream claims."""
    actual_sum = float(variances["actual_usd"].sum())
    baseline_col = [c for c in variances.columns if c.endswith("_usd")
                    and c not in ("actual_usd", "variance_usd")][0]
    baseline_sum = float(variances[baseline_col].sum())
    return [
        {
            "id": "variance_actual_total_ties",
            "name": "Sum of variance.actual_usd equals Controller's consolidated actual",
            "outcome": "pass" if abs(actual_sum - actual_total_claim) <= tolerance_usd else "fail",
            "expected": actual_total_claim,
            "actual": actual_sum,
            "tolerance": tolerance_usd,
        },
        {
            "id": "variance_baseline_total_ties",
            "name": f"Sum of variance.{baseline_col} equals baseline total",
            "outcome": "pass" if abs(baseline_sum - baseline_total_claim) <= tolerance_usd else "fail",
            "expected": baseline_total_claim,
            "actual": baseline_sum,
            "tolerance": tolerance_usd,
        },
    ]
