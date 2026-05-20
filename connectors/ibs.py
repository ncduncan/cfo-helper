"""
Intercompany Billing Subledger (IBS) — schema.

GE-internal cross-entity charges flow through IBS. A revenue or cost variance
on a given GL account can have both external (AP/AR) and internal (IBS)
contributors; the gl-drilldown bridge sums them.

Direction conventions:
  - `inbound`  — sister entity charges us (typical for COGS/opex accounts)
  - `outbound` — we bill the sister entity (typical for revenue accounts)

The actual reader lives in `connectors/excel.py:read_subledger("ibs", ...)`;
this module defines the column contract.
"""

from __future__ import annotations

IBS_COLUMNS = [
    "entity", "period", "account", "account_name",
    "counterparty_entity",   # the sister GE entity on the other side
    "direction",             # inbound | outbound
    "currency", "amount_local", "amount_usd",
    "allocation_id", "allocation_basis",  # human-readable: "infrastructure_share", "engineering_loan", ...
    "driver_dim", "driver_value",  # optional; when populated, aligns IBS rows with assumption-row grain
]

DIRECTIONS = {"inbound", "outbound"}
