"""
Accounts-receivable connector stub.

Real wiring follows the Excel-manifest pattern. When a real AR feed lands,
replace this stub with `connectors/ar.py` and route 'ar' to the real backend
in connectors/config.yaml.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

AR_COLUMNS = [
    "invoice_id", "customer_id", "customer_name", "invoice_date",
    "due_date", "as_of_date", "currency", "amount_local", "amount_usd",
    "days_open", "status",  # open | paid | partial | written_off
]

_MSG = (
    "AR connector is a stub. Configure a real AR feed in connectors/ar.py "
    "and route 'ar' to the real backend in connectors/config.yaml. "
    "Until then, AR aging analysis and DSO cannot be computed."
)


def get_ar(period: str, workspace: Path) -> pd.DataFrame:
    """Open AR balances as of the period end. Not implemented in stub mode."""
    raise NotImplementedError(_MSG)
