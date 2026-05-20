"""
Accounts-payable connector stub.

Mirrors `ar_stub.py` shape. Real wiring follows the same Excel-manifest pattern.
When a real AP feed lands, replace this stub with `connectors/ap.py` and route
'ap' to the real backend in connectors/config.yaml.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

AP_COLUMNS = [
    "bill_id", "vendor_id", "vendor_name", "bill_date",
    "due_date", "as_of_date", "currency", "amount_local", "amount_usd",
    "days_open", "status",
]

_MSG = (
    "AP connector is a stub. Configure a real AP feed in connectors/ap.py "
    "and route 'ap' to the real backend in connectors/config.yaml. "
    "Until then, AP-driven metrics (DSO/DPO, working-capital cycle) cannot "
    "be computed."
)


def get_ap(period: str, workspace: Path) -> pd.DataFrame:
    """Open AP balances as of the period end. Not implemented in stub mode."""
    raise NotImplementedError(_MSG)
