"""Orchestrate dispatch + connector reads + bridge for one account.

This is the function the SKILL.md references when it says "iterate each
material variance row, run drilldown." A material-variance loop calls
`drilldown(...)` once per (entity, account) and accumulates the results.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from .dispatch import dispatch as dispatch_decision
from .bridge import bridge as compute_bridge


def _account_map(repo_root: Path) -> list[dict]:
    path = repo_root / "profile" / "memory" / "account_map.json"
    with path.open() as f:
        return json.load(f).get("entries", [])


def _materiality(repo_root: Path) -> dict:
    path = repo_root / "profile" / "memory" / "materiality.yaml"
    with path.open() as f:
        return yaml.safe_load(f) or {}


def _lookup_map(account_map: list[dict], entity: str, account: str) -> dict | None:
    account = str(account).strip()
    for row in account_map:
        if row.get("entity") == entity and str(row.get("account", "")).strip() == account:
            return row
    return None


def _sign_convention(account_class: str) -> str:
    return "revenue" if account_class.lower() == "revenue" else "spend"


def drilldown(
    *,
    period: str,
    entity: str,
    account: str,
    repo_root: Path,
    tolerance_usd: float | None = None,
) -> dict:
    """Run a single-account drilldown and return a structured result dict.

    Result shape:
      {
        "status": "ok" | "not_applicable" | "no_gl_row",
        "reason": str,
        "dispatch": {...},
        "bridge": {...} | None,
        "drivers": [...]            # list of dicts (drivers[].to_dict('records'))
      }
    """
    # Late import to keep this module light
    import sys
    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433

    am = _account_map(repo_root)
    map_row = _lookup_map(am, entity, account)
    if map_row is None:
        return {
            "status": "no_account_map",
            "reason": f"No account_map entry for entity={entity} account={account}.",
            "dispatch": None, "bridge": None, "drivers": [],
        }

    decision = dispatch_decision(map_row)
    if decision.status != "ok":
        return {
            "status": decision.status,
            "reason": decision.reason,
            "dispatch": {
                "subledgers": list(decision.subledgers),
                "assumption_dim": decision.assumption_dim,
            },
            "bridge": None, "drivers": [],
        }

    # Resolve tolerance
    if tolerance_usd is None:
        mat = _materiality(repo_root)
        # Skill-specific tolerance, falling back to the variance abs floor.
        tolerance_usd = float(
            mat.get("drilldown", {}).get("bridge_tolerance_usd")
            or mat.get("variance", {}).get("abs_usd")
            or 100.0
        )

    # Fetch GL line for this account
    gl = connectors.get_gl(period=period, entity=entity)
    gl["account"] = gl["account"].astype(str).str.strip()
    gl_row = gl[gl["account"] == str(account).strip()]
    if gl_row.empty:
        return {
            "status": "no_gl_row",
            "reason": f"No GL row for entity={entity} account={account} period={period}.",
            "dispatch": {
                "subledgers": list(decision.subledgers),
                "assumption_dim": decision.assumption_dim,
            },
            "bridge": None, "drivers": [],
        }
    gl_actual_usd = float(gl_row["amount_usd"].iloc[0])

    # Pull subledgers per dispatch decision
    subledger_lines: dict[str, pd.DataFrame] = {}
    missing_feeds: list[str] = []
    for name in decision.subledgers:
        sl = connectors.get_subledger(name, period=period, entity=entity)
        if sl.empty:
            missing_feeds.append(name)
            continue
        sl["account"] = sl["account"].astype(str).str.strip()
        scoped = sl[sl["account"] == str(account).strip()].copy()
        if scoped.empty:
            continue
        subledger_lines[name] = scoped

    # Pull assumptions (all versions) and filter to this account
    assumptions = connectors.get_assumptions(period=period, entity=entity, version="all")
    if not assumptions.empty:
        assumptions["account"] = assumptions["account"].astype(str).str.strip()
        assumptions = assumptions[assumptions["account"] == str(account).strip()].copy()

    sign = _sign_convention(map_row.get("account_class", ""))
    result = compute_bridge(
        gl_actual_usd=gl_actual_usd,
        sign_convention=sign,
        subledger_lines=subledger_lines,
        assumptions=assumptions,
        tolerance_usd=tolerance_usd,
    )

    return {
        "status": "ok",
        "reason": decision.reason,
        "dispatch": {
            "subledgers": list(decision.subledgers),
            "assumption_dim": decision.assumption_dim,
            "missing_feeds": missing_feeds,
        },
        "bridge": {
            "actual_usd": result.actual_usd,
            "subledger_totals": result.subledger_totals,
            "subledger_total": result.subledger_total,
            "reconciling_usd": result.reconciling_usd,
            "tieout_pass": result.tieout_pass,
            "tieout_tolerance_usd": result.tieout_tolerance_usd,
            "version_totals": result.version_totals,
            "deltas_to_versions": result.deltas_to_versions,
            "most_recent_outlook": result.most_recent_outlook,
            "notes": result.notes,
        },
        "drivers": result.drivers.to_dict(orient="records"),
        "_drivers_df": result.drivers,  # caller may persist as parquet
    }
