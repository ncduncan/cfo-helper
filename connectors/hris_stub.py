"""
HRIS connector stub (Workday, BambooHR, etc.).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_MSG = (
    "HRIS connector is a stub. Configure a real backend in connectors/hris.py "
    "and route 'headcount' to 'hris' in connectors/config.yaml."
)


def get_headcount(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)
