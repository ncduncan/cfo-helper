"""Bridge math: GL actual = Σ(subledger lines) + reconciling.

Driver decomposition: subledger lines grouped by (driver_dim, driver_value)
when both are populated; otherwise grouped by the natural subledger key
(vendor_id, customer_id, counterparty_entity, etc.). For each driver group
the bridge computes the actual_usd, looks up matching assumption rows for
each extant version, and emits a delta row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

# Per-subledger fallback key when (driver_dim, driver_value) are absent.
_NATURAL_KEYS = {
    "ap":         ("vendor_id", "vendor_name"),
    "ar":         ("customer_id", "customer_name"),
    "ibs":        ("counterparty_entity", "allocation_basis"),
    "ats":        ("tail_number", "transaction_id"),
    "headcount":  ("employee_id", "function"),
}


@dataclass(frozen=True)
class BridgeResult:
    actual_usd: float                 # GL actual, expressed as positive spend (or revenue)
    subledger_totals: dict[str, float]  # per-source totals
    subledger_total: float            # sum of all subledger sources
    reconciling_usd: float            # actual − subledger_total
    tieout_pass: bool
    tieout_tolerance_usd: float
    drivers: pd.DataFrame             # one row per driver; columns below
    version_totals: dict[str, float]  # {version: total period_amount_usd}
    deltas_to_versions: dict[str, float]  # {version: actual − version_total}
    most_recent_outlook: str | None   # the version key used for delta_to_outlook
    notes: list[str]                  # human-readable observations

    def driver_columns(self) -> list[str]:
        return list(self.drivers.columns)


_OUTLOOK_RE = re.compile(r"^outlook_q[1-4]_\d{4}$")


def _slug(s: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_") or "unknown"


def _driver_key(source: str, row: pd.Series) -> tuple[str, str, str]:
    """Return (driver_key, driver_dim, driver_value) for a subledger row.

    When driver_dim and driver_value are both populated, those win. Else
    fall back to the natural key for the subledger source.
    """
    dim = row.get("driver_dim")
    val = row.get("driver_value")
    if pd.notna(dim) and pd.notna(val) and str(dim).strip() and str(val).strip():
        return (f"{source}.{_slug(dim)}.{_slug(val)}", str(dim), str(val))
    nk = _NATURAL_KEYS.get(source, ("__row__",))
    parts = []
    for k in nk:
        if k in row.index and pd.notna(row[k]):
            parts.append(str(row[k]))
    label = " / ".join(parts) if parts else "unknown"
    return (f"{source}.natural.{_slug(label)}", source, label)


def _most_recent_outlook(versions: Iterable[str]) -> str | None:
    outlooks = [v for v in versions if _OUTLOOK_RE.match(v or "")]
    return max(outlooks) if outlooks else None


def bridge(
    *,
    gl_actual_usd: float,
    sign_convention: str,            # 'spend' (cogs/opex) | 'revenue'
    subledger_lines: dict[str, pd.DataFrame],   # name → frame; empty frames OK
    assumptions: pd.DataFrame,                  # all versions for this (entity, account)
    tolerance_usd: float,
) -> BridgeResult:
    """Compute the bridge for a single (entity, account, period).

    GL is signed (negative for cost, positive for revenue). Pass
    `sign_convention='spend'` to flip costs into positive spend numbers
    so deltas read naturally; pass 'revenue' to keep revenue positive.
    """
    if sign_convention not in ("spend", "revenue"):
        raise ValueError(f"sign_convention must be 'spend' or 'revenue', got {sign_convention!r}")

    actual_usd = -gl_actual_usd if sign_convention == "spend" else gl_actual_usd

    # Per-source totals
    subledger_totals = {
        name: float(df["amount_usd"].sum()) if (df is not None and not df.empty) else 0.0
        for name, df in subledger_lines.items()
    }
    subledger_total = sum(subledger_totals.values())
    reconciling = actual_usd - subledger_total

    # Driver decomposition
    driver_rows: list[dict] = []
    for source, df in subledger_lines.items():
        if df is None or df.empty:
            continue
        keyed = df.copy()
        # Build driver key per row
        keys = keyed.apply(lambda r: _driver_key(source, r), axis=1)
        keyed["__driver_key__"] = [k[0] for k in keys]
        keyed["__driver_dim__"] = [k[1] for k in keys]
        keyed["__driver_value__"] = [k[2] for k in keys]
        for (dk, ddim, dval), grp in keyed.groupby(
            ["__driver_key__", "__driver_dim__", "__driver_value__"], dropna=False
        ):
            driver_rows.append({
                "driver_key": dk,
                "source_subledger": source,
                "driver_dim": ddim,
                "driver_value": dval,
                "actual_usd": float(grp["amount_usd"].sum()),
            })

    drivers = pd.DataFrame(driver_rows)
    if drivers.empty:
        drivers = pd.DataFrame(columns=[
            "driver_key", "source_subledger", "driver_dim", "driver_value",
            "actual_usd",
        ])

    # Assumption versions
    versions: list[str] = (
        sorted(assumptions["version"].dropna().unique().tolist())
        if not assumptions.empty else []
    )
    version_totals = {
        v: float(assumptions.loc[assumptions["version"] == v, "period_amount_usd"].sum())
        for v in versions
    }
    deltas = {v: actual_usd - t for v, t in version_totals.items()}
    most_recent_outlook = _most_recent_outlook(versions)

    # Per-driver version columns
    for v in versions:
        amap = (assumptions[assumptions["version"] == v]
                .groupby(["driver_dim", "driver_value"])["period_amount_usd"]
                .sum()
                .to_dict())
        col_actual = f"{v}_usd"
        col_delta = f"delta_to_{v}_usd"
        if drivers.empty:
            drivers[col_actual] = []
            drivers[col_delta] = []
        else:
            drivers[col_actual] = drivers.apply(
                lambda r, _amap=amap: float(_amap.get((r["driver_dim"], r["driver_value"]), 0.0)),
                axis=1,
            )
            drivers[col_delta] = drivers["actual_usd"] - drivers[col_actual]

    # Sort drivers by absolute delta-to-plan if a plan exists; else by actual
    sort_col = None
    plan_versions = [v for v in versions if v.startswith("plan_")]
    if plan_versions and not drivers.empty:
        sort_col = f"delta_to_{plan_versions[0]}_usd"
    elif not drivers.empty:
        sort_col = "actual_usd"
    if sort_col is not None:
        drivers = drivers.sort_values(sort_col, key=lambda s: s.abs(), ascending=False).reset_index(drop=True)

    # Share of total absolute delta vs. plan, per driver
    if plan_versions and not drivers.empty:
        col_delta = f"delta_to_{plan_versions[0]}_usd"
        total_abs = float(drivers[col_delta].abs().sum())
        drivers["share_of_total_delta_pct"] = (
            drivers[col_delta].abs() / total_abs * 100.0 if total_abs > 0 else 0.0
        )

    notes: list[str] = []
    if not versions:
        notes.append("No assumption versions found for this account; deltas vs plan/outlook not computed.")
    if reconciling and abs(reconciling) > tolerance_usd:
        notes.append(
            f"Bridge does not tie within tolerance: GL actual={actual_usd:,.0f}, "
            f"subledger total={subledger_total:,.0f}, reconciling={reconciling:,.0f}, "
            f"tolerance={tolerance_usd:,.0f}."
        )
    unplanned = []
    if versions and not drivers.empty:
        for v in versions:
            col = f"{v}_usd"
            if col in drivers.columns:
                unplanned_rows = drivers[(drivers[col] == 0.0) & (drivers["actual_usd"] != 0.0)]
                if not unplanned_rows.empty:
                    unplanned.append(
                        f"{len(unplanned_rows)} driver(s) absent from {v} (e.g. "
                        f"{unplanned_rows.iloc[0]['driver_value']!r} on {unplanned_rows.iloc[0]['source_subledger']})"
                    )
    notes.extend(unplanned)

    return BridgeResult(
        actual_usd=actual_usd,
        subledger_totals=subledger_totals,
        subledger_total=subledger_total,
        reconciling_usd=reconciling,
        tieout_pass=abs(reconciling) <= tolerance_usd,
        tieout_tolerance_usd=tolerance_usd,
        drivers=drivers,
        version_totals=version_totals,
        deltas_to_versions=deltas,
        most_recent_outlook=most_recent_outlook,
        notes=notes,
    )
