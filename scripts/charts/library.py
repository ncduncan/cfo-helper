"""
Chart functions for the close-pack KPI list (CLAUDE.md §5/§6).

All charts use a consistent palette (cfo-helper blue/black/green/red, matching
`scripts.xlsx.styles`) and return the output `Path` after writing. PNG is the
default output for embedding in xlsx/pptx/docx; pass `format="svg"` for
print-quality output.

Every chart accepts a `title` and an optional `claim_id` that gets stamped
in small text in the corner of the figure — analogous to the cell-comment
provenance in XLSX.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import matplotlib

matplotlib.use("Agg")  # headless — no display required
import matplotlib.pyplot as plt
import numpy as np

# Palette mirrors scripts.xlsx.styles for visual continuity.
COLOR_INPUT = "#1F4E79"          # blue
COLOR_FORMULA = "#000000"        # black
COLOR_INTERNAL = "#2E7D32"       # green (favorable)
COLOR_EXTERNAL = "#B00020"       # red (unfavorable)
COLOR_NEUTRAL = "#6B7280"        # gray (gridlines, annotations)


def _new_fig(figsize: tuple[float, float] = (10, 6)) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors=COLOR_NEUTRAL)
    return fig, ax


def _stamp_provenance(fig: plt.Figure, claim_id: str | None) -> None:
    if claim_id:
        fig.text(
            0.99, 0.01, f"claim_id: {claim_id}",
            ha="right", va="bottom",
            fontsize=7, color=COLOR_NEUTRAL, alpha=0.8,
        )


def _save(fig: plt.Figure, path: Path, *, format: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format=format, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def render_chart(spec: Mapping, output_path: Path) -> Path:
    """Dispatch a declarative chart spec to the right builder.

    `spec` shape: {kind, title, data, claim_id?, format?}. `kind` selects
    one of the named builders below.
    """
    kind = spec["kind"]
    builders = {
        "pl_bridge": pl_bridge,
        "bbrr_waterfall": bbrr_waterfall,
        "arr_snapshot": arr_snapshot,
        "top10_movement": top10_movement,
        "kpi_dashboard_grid": kpi_dashboard_grid,
        "deferred_rev_rollforward": deferred_rev_rollforward_chart,
    }
    if kind not in builders:
        raise ValueError(f"unknown chart kind: {kind!r}")
    builder = builders[kind]
    return builder(
        output_path=output_path,
        title=spec.get("title", ""),
        claim_id=spec.get("claim_id"),
        format=spec.get("format", "png"),
        **spec["data"],
    )


def pl_bridge(
    *,
    output_path: Path,
    title: str,
    budget: float,
    actual: float,
    drivers: Sequence[Mapping],
    claim_id: str | None = None,
    format: str = "png",
) -> Path:
    """Waterfall: budget → drivers → actual.

    `drivers` is a sequence of {label, value} dicts; positives shown in
    green, negatives in red.
    """
    fig, ax = _new_fig(figsize=(11, 5.5))
    labels = ["Budget"] + [d["label"] for d in drivers] + ["Actual"]
    values = [budget] + [d["value"] for d in drivers] + [actual]
    cumulative = [budget]
    for d in drivers:
        cumulative.append(cumulative[-1] + d["value"])
    cumulative.append(actual)

    bottoms = [0]
    for d in drivers:
        bottoms.append(cumulative[-(len(drivers) + 1):][drivers.index(d)] - max(0, d["value"]))
    # Simpler: rebuild bottoms based on running cumulative, treating drivers as floating bars.
    bottoms = [0]
    running = budget
    for d in drivers:
        if d["value"] >= 0:
            bottoms.append(running)
        else:
            bottoms.append(running + d["value"])  # negative shifts down
        running += d["value"]
    bottoms.append(0)

    colors = [COLOR_INPUT]
    for d in drivers:
        colors.append(COLOR_INTERNAL if d["value"] >= 0 else COLOR_EXTERNAL)
    colors.append(COLOR_INPUT)

    heights = [budget] + [abs(d["value"]) for d in drivers] + [actual]
    ax.bar(labels, heights, bottom=bottoms, color=colors, edgecolor="white", linewidth=1)

    # Annotate values
    for i, (label, h, b) in enumerate(zip(labels, heights, bottoms)):
        ax.text(i, b + h, f"{h:,.0f}", ha="center", va="bottom", fontsize=9)

    ax.set_title(title, fontsize=14, fontweight="bold", color=COLOR_FORMULA, loc="left")
    ax.set_ylabel("USD")
    ax.grid(axis="y", color=COLOR_NEUTRAL, alpha=0.2)
    plt.xticks(rotation=20, ha="right")
    _stamp_provenance(fig, claim_id)
    return _save(fig, Path(output_path), format=format)


def bbrr_waterfall(
    *,
    output_path: Path,
    title: str,
    bookings: float,
    billings: float,
    rpo: float,
    revenue: float,
    claim_id: str | None = None,
    format: str = "png",
) -> Path:
    """Bookings / Billings / RPO / Revenue waterfall — the four-way reconciliation."""
    fig, ax = _new_fig(figsize=(9, 5.5))
    labels = ["Bookings", "Billings", "RPO", "Revenue"]
    values = [bookings, billings, rpo, revenue]
    colors = [COLOR_INPUT] * 4
    bars = ax.bar(labels, values, color=colors, edgecolor="white")
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                f"{v/1_000_000:.1f}M", ha="center", va="bottom", fontsize=10)
    ax.set_title(title, fontsize=14, fontweight="bold", color=COLOR_FORMULA, loc="left")
    ax.set_ylabel("USD")
    ax.grid(axis="y", color=COLOR_NEUTRAL, alpha=0.2)
    _stamp_provenance(fig, claim_id)
    return _save(fig, Path(output_path), format=format)


def arr_snapshot(
    *,
    output_path: Path,
    title: str,
    periods: Sequence[str],
    arr: Sequence[float],
    nrr: Sequence[float] | None = None,
    grr: Sequence[float] | None = None,
    claim_id: str | None = None,
    format: str = "png",
) -> Path:
    """ARR over time with optional NRR/GRR overlay on a secondary axis."""
    fig, ax = _new_fig(figsize=(11, 5.5))
    ax.plot(periods, arr, color=COLOR_INPUT, linewidth=2.5, marker="o", label="ARR")
    ax.fill_between(periods, arr, alpha=0.1, color=COLOR_INPUT)
    ax.set_ylabel("ARR (USD)", color=COLOR_INPUT)
    ax.set_title(title, fontsize=14, fontweight="bold", color=COLOR_FORMULA, loc="left")
    ax.grid(color=COLOR_NEUTRAL, alpha=0.2)

    if nrr or grr:
        ax2 = ax.twinx()
        if nrr:
            ax2.plot(periods, [v * 100 for v in nrr], color=COLOR_INTERNAL,
                     linewidth=1.8, marker="s", label="NRR")
        if grr:
            ax2.plot(periods, [v * 100 for v in grr], color=COLOR_EXTERNAL,
                     linewidth=1.5, marker="^", linestyle="--", label="GRR")
        ax2.set_ylabel("Retention %", color=COLOR_NEUTRAL)
        ax2.spines["top"].set_visible(False)

        lines, labels = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax.legend(lines + lines2, labels + labels2, loc="upper left", frameon=False)

    plt.xticks(rotation=30, ha="right")
    _stamp_provenance(fig, claim_id)
    return _save(fig, Path(output_path), format=format)


def top10_movement(
    *,
    output_path: Path,
    title: str,
    customers: Sequence[str],
    additions: Sequence[float],
    expansions: Sequence[float],
    contractions: Sequence[float],
    churn: Sequence[float],
    claim_id: str | None = None,
    format: str = "png",
) -> Path:
    """Stacked bar chart of additions/expansions/contractions/churn by customer."""
    fig, ax = _new_fig(figsize=(12, 6))
    x = np.arange(len(customers))
    ax.bar(x, additions, color=COLOR_INTERNAL, label="Additions")
    ax.bar(x, expansions, bottom=additions, color="#A5D6A7", label="Expansions")
    contractions_neg = [-abs(v) for v in contractions]
    churn_neg = [-abs(v) for v in churn]
    ax.bar(x, contractions_neg, color=COLOR_EXTERNAL, label="Contractions")
    ax.bar(x, churn_neg, bottom=contractions_neg, color="#EF9A9A", label="Churn")
    ax.axhline(0, color=COLOR_FORMULA, linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(customers, rotation=30, ha="right")
    ax.set_title(title, fontsize=14, fontweight="bold", color=COLOR_FORMULA, loc="left")
    ax.set_ylabel("USD ARR")
    ax.legend(loc="upper right", frameon=False)
    ax.grid(axis="y", color=COLOR_NEUTRAL, alpha=0.2)
    _stamp_provenance(fig, claim_id)
    return _save(fig, Path(output_path), format=format)


def kpi_dashboard_grid(
    *,
    output_path: Path,
    title: str,
    kpis: Sequence[Mapping],
    cols: int = 3,
    claim_id: str | None = None,
    format: str = "png",
) -> Path:
    """Small-multiples grid of KPIs — each tile shows label, value, comparator delta.

    `kpis` items: {label, value, units, prior?, claim_id?, value_fmt?}.
    """
    rows = (len(kpis) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 2.5 * rows), dpi=120)
    if rows == 1 and cols == 1:
        axes = [axes]
    elif rows == 1 or cols == 1:
        axes = list(np.atleast_1d(axes).flatten())
    else:
        axes = list(axes.flatten())

    for idx, ax in enumerate(axes):
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        if idx >= len(kpis):
            ax.set_visible(False)
            continue
        k = kpis[idx]
        ax.text(0.05, 0.78, k["label"], fontsize=10, color=COLOR_NEUTRAL, transform=ax.transAxes)
        value_str = k.get("value_fmt") or f"{k['value']:,.0f} {k.get('units', '')}".strip()
        ax.text(0.05, 0.42, value_str, fontsize=18, fontweight="bold",
                color=COLOR_INPUT, transform=ax.transAxes)
        if k.get("prior") not in (None, 0):
            delta_pct = (k["value"] - k["prior"]) / k["prior"]
            color = COLOR_INTERNAL if delta_pct >= 0 else COLOR_EXTERNAL
            sign = "+" if delta_pct >= 0 else ""
            ax.text(0.05, 0.18, f"{sign}{delta_pct*100:.1f}% vs prior",
                    fontsize=9, color=color, transform=ax.transAxes)

    fig.suptitle(title, fontsize=14, fontweight="bold", color=COLOR_FORMULA, x=0.05, ha="left")
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    _stamp_provenance(fig, claim_id)
    return _save(fig, Path(output_path), format=format)


def deferred_rev_rollforward_chart(
    *,
    output_path: Path,
    title: str,
    opening: float,
    billings: float,
    recognized: float,
    adjustments: float = 0.0,
    closing: float | None = None,
    claim_id: str | None = None,
    format: str = "png",
) -> Path:
    """Waterfall: opening + billings − recognized + adjustments = closing."""
    fig, ax = _new_fig(figsize=(10, 5.5))
    labels = ["Opening", "+ Billings", "− Recognized", "+/- Adjustments", "= Closing"]
    contribs = [opening, billings, -abs(recognized), adjustments,
                (closing if closing is not None else opening + billings - abs(recognized) + adjustments)]
    cumulative = [opening]
    for v in contribs[1:-1]:
        cumulative.append(cumulative[-1] + v)
    cumulative.append(contribs[-1])

    bottoms = [0]
    running = opening
    for v in contribs[1:-1]:
        if v >= 0:
            bottoms.append(running)
        else:
            bottoms.append(running + v)
        running += v
    bottoms.append(0)

    heights = [opening, billings, abs(recognized), abs(adjustments), contribs[-1]]
    colors = [COLOR_INPUT, COLOR_INTERNAL, COLOR_EXTERNAL, COLOR_NEUTRAL, COLOR_INPUT]
    ax.bar(labels, heights, bottom=bottoms, color=colors, edgecolor="white")
    for i, (h, b) in enumerate(zip(heights, bottoms)):
        ax.text(i, b + h, f"{h/1_000_000:.1f}M", ha="center", va="bottom", fontsize=9)

    ax.set_title(title, fontsize=14, fontweight="bold", color=COLOR_FORMULA, loc="left")
    ax.set_ylabel("USD")
    ax.grid(axis="y", color=COLOR_NEUTRAL, alpha=0.2)
    plt.xticks(rotation=15, ha="right")
    _stamp_provenance(fig, claim_id)
    return _save(fig, Path(output_path), format=format)


__all__ = [
    "render_chart",
    "pl_bridge",
    "bbrr_waterfall",
    "arr_snapshot",
    "top10_movement",
    "kpi_dashboard_grid",
    "deferred_rev_rollforward_chart",
]
