"""Gap-to-stretch: three-layer roll-up of the delta between two version IDs.

Layers (coarse → fine):
  1. **Trio**: Δsales, ΔEBIT, ΔFCF (per-entity and consolidated).
  2. **Bucket**: revenue, COGS, R&D, SG&A.
  3. **Driver**: one row per cube cell delta, with mechanism_hint and the
     to_version's `change_source` lineage from `assumptions_locked.json`.

Used to characterize:
  - Initial corporate stretch on plan-lock: gap(`bottoms_up_fy26`, `plan_fy26`)
  - Quarterly outlook movement: gap(`plan_fy26`, `outlook_q1_2026`)
  - Quarter-over-quarter outlook drift: gap(`outlook_q1_2026`, `outlook_q2_2026`)

Mechanism hint per driver row:

| Condition (vs prior version) | hint |
|---|---|
| only quantity changed (unit_cost equal within tolerance) | volume |
| only unit_cost changed (quantity equal) | price |
| both changed in the same direction | scale |
| both changed in opposite directions | mix |
| driver absent in from_version | new_driver |
| driver absent in to_version | removed_driver |
| only period_amount_usd changed (qty/unit_cost both null in one) | amount_only |
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from connectors.assumptions import natural_key_columns, validate_version


@dataclass(frozen=True)
class GapResult:
    from_version: str
    to_version: str
    period: str
    trio_delta: dict[str, float]                 # {sales, ebit, fcf} per-entity and _consolidated
    trio_per_entity: dict[str, dict[str, float]]  # {entity: {sales, ebit, fcf}}
    bucket_delta: dict[str, float]               # {revenue, cogs, rd, sga}
    driver_deltas: pd.DataFrame                   # one row per delta
    to_version_lineage: dict[str, dict]           # per-entity lock-file annotations
    notes: list[str] = field(default_factory=list)


def _hint(qty_from, uc_from, amt_from, qty_to, uc_to) -> str:
    if pd.isna(qty_from) and pd.isna(uc_from) and amt_from > 0:
        # from-side was authored as amount-only
        if pd.isna(qty_to) and pd.isna(uc_to):
            return "amount_only"
        return "amount_only"
    if pd.isna(qty_to) and pd.isna(uc_to):
        return "amount_only"
    qty_d = (qty_to or 0) - (qty_from or 0)
    uc_d = (uc_to or 0) - (uc_from or 0)
    qty_changed = abs(qty_d) > 0.0001
    uc_changed = abs(uc_d) > 0.01
    if qty_changed and not uc_changed:
        return "volume"
    if uc_changed and not qty_changed:
        return "price"
    if qty_changed and uc_changed:
        if (qty_d > 0) == (uc_d > 0):
            return "scale"
        return "mix"
    return "amount_only"


def _bucket_for(account_class: str, pnl_line: str) -> str:
    cls = (account_class or "").lower()
    if cls == "revenue":
        return "revenue"
    if cls == "cogs":
        return "cogs"
    if cls == "opex":
        return "rd" if (pnl_line or "").startswith("Opex / R&D") else "sga"
    return "other"


def _read_lock_lineage(repo_root: Path) -> dict:
    path = repo_root / "memory" / "assumptions_locked.json"
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def gap(
    *,
    from_version: str,
    to_version: str,
    period: str,
    repo_root: Path,
) -> GapResult:
    """Return the three-layer gap between two versions.

    `period` is used to resolve the connector's manifest; the gap covers
    every (entity, period) tuple where either version has rows.
    """
    validate_version(from_version)
    validate_version(to_version)

    import sys
    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433
    from .trio import compute_trio  # local import to avoid cycle at module load

    entities = connectors.list_entities(period)
    from_frames: list[pd.DataFrame] = []
    to_frames: list[pd.DataFrame] = []
    trio_per_entity: dict[str, dict[str, float]] = {}
    notes: list[str] = []

    for entity in entities:
        f = connectors.get_assumptions(period=period, entity=entity, version=from_version)
        t = connectors.get_assumptions(period=period, entity=entity, version=to_version)
        if not f.empty:
            from_frames.append(f)
        if not t.empty:
            to_frames.append(t)
        # Per-entity trio
        f_trio = compute_trio(version=from_version, entity=entity, period=period, repo_root=repo_root)
        t_trio = compute_trio(version=to_version,   entity=entity, period=period, repo_root=repo_root)
        trio_per_entity[entity] = {
            "delta_sales_usd": t_trio.sales_usd - f_trio.sales_usd,
            "delta_ebit_usd":  t_trio.ebit_usd  - f_trio.ebit_usd,
            "delta_fcf_usd":   t_trio.fcf_usd   - f_trio.fcf_usd,
        }

    if not from_frames and not to_frames:
        notes.append(
            f"Neither {from_version!r} nor {to_version!r} has assumption rows; "
            "gap is trivially zero."
        )

    from_rows = pd.concat(from_frames, ignore_index=True) if from_frames else pd.DataFrame()
    to_rows = pd.concat(to_frames, ignore_index=True) if to_frames else pd.DataFrame()

    # Consolidated trio delta
    f_cons = compute_trio(version=from_version, consolidated=True, period=period, repo_root=repo_root)
    t_cons = compute_trio(version=to_version,   consolidated=True, period=period, repo_root=repo_root)
    trio_delta = {
        "delta_sales_usd": t_cons.sales_usd - f_cons.sales_usd,
        "delta_ebit_usd":  t_cons.ebit_usd  - f_cons.ebit_usd,
        "delta_fcf_usd":   t_cons.fcf_usd   - f_cons.fcf_usd,
    }

    # Bucket delta (consolidated)
    bucket_delta: dict[str, float] = {"revenue": 0.0, "cogs": 0.0, "rd": 0.0, "sga": 0.0}
    for sign, frame in [(-1.0, from_rows), (1.0, to_rows)]:
        if frame.empty:
            continue
        f = frame.copy()
        f["_bucket"] = f.apply(
            lambda r: _bucket_for(r["account_class"], r.get("pnl_line", "")), axis=1
        )
        for bucket, grp in f.groupby("_bucket"):
            bucket_delta[bucket] = bucket_delta.get(bucket, 0.0) + sign * float(
                grp["period_amount_usd"].sum()
            )

    # Driver-grain delta — full outer join on natural key
    nk = natural_key_columns()
    join_keys = [c for c in nk if c != "version"]   # version is the merge dimension itself

    keep = join_keys + ["account_class", "pnl_line",
                        "quantity", "unit_cost", "period_amount_usd"]
    f_proj = from_rows[keep].copy() if not from_rows.empty else pd.DataFrame(columns=keep)
    t_proj = to_rows[keep].copy()   if not to_rows.empty   else pd.DataFrame(columns=keep)

    merged = f_proj.merge(
        t_proj, on=join_keys, how="outer", suffixes=("_from", "_to"),
    )

    driver_rows: list[dict] = []
    if not merged.empty:
        for _, row in merged.iterrows():
            raw_from = row.get("period_amount_usd_from")
            raw_to = row.get("period_amount_usd_to")
            amt_from = 0.0 if pd.isna(raw_from) else float(raw_from)
            amt_to = 0.0 if pd.isna(raw_to) else float(raw_to)
            delta = amt_to - amt_from
            if abs(delta) < 0.005:
                continue

            # Hint computation
            present_from = pd.notna(row.get("period_amount_usd_from"))
            present_to = pd.notna(row.get("period_amount_usd_to"))
            if not present_from:
                hint = "new_driver"
            elif not present_to:
                hint = "removed_driver"
            else:
                hint = _hint(
                    row.get("quantity_from"), row.get("unit_cost_from"), amt_from,
                    row.get("quantity_to"),   row.get("unit_cost_to"),
                )

            def _coalesce(*candidates) -> str:
                for c in candidates:
                    if c is not None and pd.notna(c) and str(c).strip():
                        return str(c)
                return ""
            account_class = _coalesce(row.get("account_class_to"), row.get("account_class_from"))
            pnl_line = _coalesce(row.get("pnl_line_to"), row.get("pnl_line_from"))
            driver_rows.append({
                **{k: row[k] for k in join_keys},
                "from_amount_usd": amt_from,
                "to_amount_usd":   amt_to,
                "delta_usd":       delta,
                "bucket":          _bucket_for(account_class, pnl_line),
                "mechanism_hint":  hint,
            })
    driver_deltas = pd.DataFrame(driver_rows)
    if not driver_deltas.empty:
        driver_deltas = driver_deltas.sort_values(
            "delta_usd", key=lambda s: s.abs(), ascending=False
        ).reset_index(drop=True)

    # Lineage from lock file: which `change_source` tags applied to to_version?
    locks = _read_lock_lineage(repo_root)
    to_version_lineage: dict[str, dict] = {}
    for entity in entities:
        key = f"{entity}/{to_version}"
        if key in locks:
            to_version_lineage[entity] = {
                "change_source": locks[key].get("change_source", []),
                "locked_against": locks[key].get("locked_against"),
                "first_locked_at": locks[key].get("first_locked_at"),
            }

    return GapResult(
        from_version=from_version,
        to_version=to_version,
        period=period,
        trio_delta=trio_delta,
        trio_per_entity=trio_per_entity,
        bucket_delta=bucket_delta,
        driver_deltas=driver_deltas,
        to_version_lineage=to_version_lineage,
        notes=notes,
    )
