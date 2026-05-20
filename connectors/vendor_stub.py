"""
Vendor master connector stub.

Defines the interface for vendor-level spend and metadata. When real vendor
data is available, replace with a manifest-driven Excel reader (see
`excel.get_customers` for the pattern) or wire to AP/ERP.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

VENDOR_COLUMNS = ["vendor_id", "vendor_name", "category", "country",
                   "currency", "ytd_spend_usd"]

_MSG = (
    "Vendor connector is a stub. Add a vendor master to "
    "inputs/manifest.yaml under shared.vendors and wire connectors/vendor.py "
    "(real Excel reader) to enable vendor-concentration analysis."
)

_WARNED = False


def get_vendors(period: str, workspace: Path) -> pd.DataFrame:
    """Return the canonical vendor master. Returns an empty DataFrame with
    the right columns when no vendor data is available — callers should treat
    that as "vendor concentration analysis skipped" rather than an error."""
    global _WARNED
    if not _WARNED:
        sys.stderr.write("WARN: " + _MSG + "\n")
        _WARNED = True
    return pd.DataFrame(columns=VENDOR_COLUMNS)
