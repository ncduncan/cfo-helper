"""
ERP connector stub (NetSuite, Sage Intacct, SAP, etc.).

Defines the interface; raises NotImplementedError until a real backend is wired.
The interface mirrors `excel.py` exactly so swapping is a routing flip in
`connectors/config.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

_MSG = (
    "ERP connector is a stub. Configure a real backend in connectors/erp.py "
    "and route the relevant domain to 'erp' in connectors/config.yaml."
)


def get_gl(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)


def get_budget(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)


def get_forecast(period: str, entity: str, version: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)


def get_headcount(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)


def get_fx(period: str, workspace: Path) -> pd.DataFrame:
    raise NotImplementedError(_MSG)


def list_entities(period: str, workspace: Path) -> list[str]:
    raise NotImplementedError(_MSG)
