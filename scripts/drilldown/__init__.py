"""GL-to-subledger drilldown — driver-level decomposition of GL movement.

Public entry points:
  - dispatch.dispatch(account_map_row) -> DispatchDecision
  - bridge.bridge(...) -> BridgeResult
  - drilldown(...) -> dict (orchestrates dispatch + bridge for one account)

Invoked by FP&A in P2 for each row in material_variances.parquet.
"""
from .dispatch import dispatch, DispatchDecision  # noqa: F401
from .bridge import bridge, BridgeResult  # noqa: F401
from .runner import drilldown  # noqa: F401
