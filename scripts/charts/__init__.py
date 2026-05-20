"""
Chart-rendering helpers for cfo-helper close-pack deliverables.

# Pattern source: cfo-helper-internal — none of Anthropic's open skills cover
# financial charts directly; we use the same blue/black/green/red palette as
# scripts.xlsx.styles for cross-deliverable visual consistency.

Outputs PNG (for embedding in xlsx/pptx/docx/pdf) and optionally SVG. All
chart functions return the output Path so callers can append the artifact
to a work_product's `artifacts[]`.
"""

from __future__ import annotations

from scripts.charts.library import (
    arr_snapshot,
    bbrr_waterfall,
    deferred_rev_rollforward_chart,
    kpi_dashboard_grid,
    pl_bridge,
    render_chart,
    top10_movement,
)

__all__ = [
    "arr_snapshot",
    "bbrr_waterfall",
    "deferred_rev_rollforward_chart",
    "kpi_dashboard_grid",
    "pl_bridge",
    "render_chart",
    "top10_movement",
]
