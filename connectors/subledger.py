"""
Uniform subledger interface.

`get_subledger(name, period, entity)` returns a normalized DataFrame for any
of: ap, ar, ibs, ats, headcount. Routing goes through the same Excel/manifest
mechanism as GL/budget/forecast.

This is distinct from the legacy `connectors.get_ap(period)` /
`connectors.get_ar(period)` which return open-balance snapshots for aging
analysis. The drilldown view is period-flow, per-entity, per-account.

V1 wires `ap`, `ibs`, and `assumptions` (the latter via `get_assumptions`).
The other names return empty DataFrames with a one-time WARN, matching the
ap_stub/ar_stub pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from . import excel
from .ibs import IBS_COLUMNS

# Optional `driver_dim` and `driver_value` columns: when the subledger feed
# carries enough metadata to align with the assumption-row grain (e.g., Azure
# billing tagged by SKU), populate them. The drilldown bridge groups by
# (driver_dim, driver_value) when present, falling back to the natural
# subledger key (vendor_id, customer_id, ...) otherwise.
AP_SUBLEDGER_COLUMNS = [
    "entity", "period", "account", "account_name",
    "vendor_id", "vendor_name",
    "currency", "amount_local", "amount_usd",
    "invoice_id", "invoice_date",
    "driver_dim", "driver_value",
]

AR_SUBLEDGER_COLUMNS = [
    "entity", "period", "account", "account_name",
    "customer_id", "customer_name",
    "currency", "amount_local", "amount_usd",
    "invoice_id", "invoice_date",
    "driver_dim", "driver_value",
]

ATS_SUBLEDGER_COLUMNS = [
    "entity", "period", "account", "account_name",
    "tail_number", "transaction_id",
    "currency", "amount_local", "amount_usd",
    "driver_dim", "driver_value",
]

HC_SUBLEDGER_COLUMNS = [
    "entity", "period", "account", "account_name",
    "employee_id", "department", "function",
    "currency", "amount_local", "amount_usd",
    "driver_dim", "driver_value",
]

_COLUMN_SETS = {
    "ap":        AP_SUBLEDGER_COLUMNS,
    "ar":        AR_SUBLEDGER_COLUMNS,
    "ibs":       IBS_COLUMNS,
    "ats":       ATS_SUBLEDGER_COLUMNS,
    "headcount": HC_SUBLEDGER_COLUMNS,
}

# Manifest key mapping. Most subledger names match their manifest key
# directly; `headcount` is special because the existing manifest key
# `headcount` already names the period-end snapshot (different schema). The
# per-account headcount allocation subledger lives under `headcount_alloc`.
_MANIFEST_KEYS = {
    "ap":        "ap",
    "ar":        "ar",
    "ibs":       "ibs",
    "ats":       "ats",
    "headcount": "headcount_alloc",
}

_WARNED: set[str] = set()


def column_contract(name: str) -> list[str]:
    if name not in _COLUMN_SETS:
        raise KeyError(f"Unknown subledger {name!r}. Known: {sorted(_COLUMN_SETS)}")
    return list(_COLUMN_SETS[name])


def get_subledger(name: str, period: str, entity: str, workspace: Path) -> pd.DataFrame:
    """Return per-entity, per-account flow detail for the named subledger.

    Returns an empty DataFrame (with the right column shape) when the
    subledger has no manifest entry — caller treats that as "feed not
    wired" rather than an error. The skill's dispatch table emits a
    `not_applicable` self-check naming the missing feed in that case.
    """
    if name not in _COLUMN_SETS:
        raise KeyError(f"Unknown subledger {name!r}. Known: {sorted(_COLUMN_SETS)}")

    cols = _COLUMN_SETS[name]
    manifest_key = _MANIFEST_KEYS[name]
    df = excel.read_subledger(name=manifest_key, period=period, entity=entity,
                              workspace=workspace, columns=cols)
    if df is None:
        if name not in _WARNED:
            sys.stderr.write(
                f"WARN: subledger {name!r} has no manifest entry for entity={entity}; "
                f"returning empty DataFrame.\n"
            )
            _WARNED.add(name)
        return pd.DataFrame(columns=cols)
    return df
