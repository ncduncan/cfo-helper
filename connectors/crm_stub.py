"""
CRM connector stub (Salesforce, HubSpot, etc.).

Defines the interface for customer- and deal-level data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_MSG = (
    "CRM connector is a stub. Configure a real backend in connectors/crm.py "
    "and route 'customers' and/or 'deals' to 'crm' in connectors/config.yaml."
)


def get_customers(period: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)


def get_deals(period: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)
