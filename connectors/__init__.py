"""
Data connector layer.

Every read of source data goes through this module. Agents call e.g.
`connectors.get_gl(period='2026-05', entity='UK')` and receive a normalized
pandas DataFrame regardless of the underlying system.

Today, all domains route to `excel.py`. To add NetSuite later, implement
`erp.py` and flip the routing in `_route()` below — no agent code changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml

from . import excel, erp_stub, crm_stub, hris_stub, vendor_stub, ar_stub, ap_stub
from . import subledger as _subledger_mod
from . import assumptions as _assumptions_mod

Domain = Literal["gl", "budget", "forecast", "customers", "deals", "headcount",
                  "fx", "vendors", "ar", "ap",
                  "subledger", "assumptions"]

_DEFAULT_ROUTING = {
    "gl": "excel",
    "budget": "excel",
    "forecast": "excel",
    "customers": "excel",
    "deals": "excel",
    "headcount": "excel",
    "fx": "excel",
    "vendors": "vendor_stub",
    "ar": "ar_stub",
    "ap": "ap_stub",
    # subledger and assumptions always go through excel today; the routing
    # entry exists so future backends (a real ERP subledger feed) can flip it
    # in connectors/config.yaml without code changes.
    "subledger": "excel",
    "assumptions": "excel",
}

_BACKENDS = {
    "excel": excel,
    "erp": erp_stub,
    "crm": crm_stub,
    "hris": hris_stub,
    "vendor_stub": vendor_stub,
    "ar_stub": ar_stub,
    "ap_stub": ap_stub,
}


def _load_routing() -> dict[str, str]:
    """Load routing from connectors/config.yaml if present, else defaults."""
    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f) or {}
        return {**_DEFAULT_ROUTING, **cfg.get("routing", {})}
    return dict(_DEFAULT_ROUTING)


def _route(domain: Domain):
    backend_name = _load_routing()[domain]
    return _BACKENDS[backend_name]


def workspace_root(period: str) -> Path:
    """Resolve the data root for a period.

    Resolution order (first hit wins):
      1. `CFO_HELPER_TASK_DIR` — explicit task directory (used by the dashboard
         and `scripts/dispatch.py`). Returned as-is.
      2. `CFO_HELPER_ROOT` + `workspace/<period>/` — legacy layout, kept for
         backward compatibility with the original smoke test.
      3. Repo root + `workspace/<period>/` — default.
    """
    task_dir = os.environ.get("CFO_HELPER_TASK_DIR")
    if task_dir:
        return Path(task_dir)
    root = Path(os.environ.get("CFO_HELPER_ROOT", Path(__file__).parent.parent))
    return root / "workspace" / period


# --- Public API: domain-specific readers --------------------------------------

def get_gl(period: str, entity: str) -> pd.DataFrame:
    """General ledger / trial balance lines for a period and entity.

    Required columns: entity, period, account, account_name, debit, credit, currency, amount_local, amount_usd
    """
    return _route("gl").get_gl(period=period, entity=entity, workspace=workspace_root(period))


def get_budget(period: str, entity: str) -> pd.DataFrame:
    """Budget for a period and entity. Same shape as GL with `amount_usd` as the value column."""
    return _route("budget").get_budget(period=period, entity=entity, workspace=workspace_root(period))


def get_forecast(period: str, entity: str, version: str = "latest") -> pd.DataFrame:
    """Forecast for a period and entity. `version` selects the forecast vintage."""
    return _route("forecast").get_forecast(period=period, entity=entity, version=version, workspace=workspace_root(period))


def get_customers(period: str) -> pd.DataFrame:
    """Customer-level revenue and ARR data for the period."""
    return _route("customers").get_customers(period=period, workspace=workspace_root(period))


def get_deals(period: str) -> pd.DataFrame:
    """Deal-level data closed/expected to close in the period."""
    return _route("deals").get_deals(period=period, workspace=workspace_root(period))


def get_headcount(period: str, entity: str) -> pd.DataFrame:
    """Headcount snapshot for the period and entity."""
    return _route("headcount").get_headcount(period=period, entity=entity, workspace=workspace_root(period))


def get_fx(period: str) -> pd.DataFrame:
    """FX rates used for the period (period-end and period-average)."""
    return _route("fx").get_fx(period=period, workspace=workspace_root(period))


def get_vendors(period: str) -> pd.DataFrame:
    """Vendor master with YTD spend. May return an empty DataFrame when no
    vendor master is configured — callers treat that as "concentration
    analysis skipped" rather than an error."""
    return _route("vendors").get_vendors(period=period, workspace=workspace_root(period))


def get_ar(period: str) -> pd.DataFrame:
    """Open accounts-receivable balances as of the period.

    Raises NotImplementedError until an AR feed is wired. Callers should catch
    and elevate to an open_question per CLAUDE.md §8 rule 7 — see
    run_p1_cash_flow for the canonical pattern.
    """
    return _route("ar").get_ar(period=period, workspace=workspace_root(period))


def get_ap(period: str) -> pd.DataFrame:
    """Open accounts-payable balances as of the period.

    Raises NotImplementedError until an AP feed is wired. Callers should catch
    and elevate to an open_question per CLAUDE.md §8 rule 7 — see
    run_p1_cash_flow for the canonical pattern.
    """
    return _route("ap").get_ap(period=period, workspace=workspace_root(period))


def get_subledger(name: str, period: str, entity: str) -> pd.DataFrame:
    """Per-entity, per-account subledger flow detail for the given period.

    Distinct from `get_ap(period)` / `get_ar(period)` which return open-balance
    snapshots for aging analysis. This view is period-flow keyed by
    (entity, account, driver_id) and is consumed by the gl-drilldown skill.

    `name` ∈ {ap, ar, ibs, ats, headcount}. Returns an empty DataFrame
    (with the right column shape) when the named subledger has no manifest
    entry for the entity. Caller treats that as 'feed not wired'.
    """
    return _subledger_mod.get_subledger(
        name=name, period=period, entity=entity, workspace=workspace_root(period)
    )


def get_assumptions(period: str, entity: str, version: str = "all") -> pd.DataFrame:
    """Plan / outlook assumption rows for the entity and period.

    Append-only by version. `version='all'` concatenates every extant version
    (plan_fy{YY}, outlook_q[1-4]_{YYYY}, ...). Specific version filters to one.
    Returns empty DataFrame when no manifest entry exists.

    Schema: see `connectors/assumptions.py:ASSUMPTION_COLUMNS`.
    """
    return _route("assumptions").read_assumptions(
        period=period, entity=entity,
        workspace=workspace_root(period),
        columns=_assumptions_mod.ASSUMPTION_COLUMNS,
        version=version,
    )


# --- Public API: discovery ---------------------------------------------------

def list_entities(period: str) -> list[str]:
    """Return the entities with data available for a period."""
    return _route("gl").list_entities(period=period, workspace=workspace_root(period))
