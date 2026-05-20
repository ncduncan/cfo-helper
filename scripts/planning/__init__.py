"""Planning system — bottom-up build, outlook refresh, gap-to-stretch.

Public entry points:
  - trio.compute_trio(...)            — sales / EBIT / FCF for a plan version
  - plan_build.build(...)             — assumption rows from a driver workbook
  - outlook_refresh.compute(...)      — propose a refreshed outlook (no rows written)
  - outlook_refresh.lock(...)         — write proposed rows to the assumption store
  - gap_to_stretch.gap(...)           — three-layer delta between two version ids

Invoked by FP&A in `annual_plan_cycle` and `outlook_refresh_quarterly` task types.
"""

from .trio import compute_trio, TrioResult  # noqa: F401
