"""Outlook-refresh: compute + lock split.

`compute` produces a *proposal* — no assumption rows are written. The CFO
reviews the proposal at the dashboard checkpoint (`ready_for_checkpoint`)
and either accepts the default proportional distribution or overrides
specific rows. After approval, `lock` writes the proposed rows into per-
entity workbooks, updates the manifest, and runs ingest to hash-lock with
the right `change_source` annotations.

The compute step folds three sources into one proposed outlook:

1. **Actuals revision.** For periods that have closed (e.g., Q1 has finalized),
   the actual GL total per (entity, account, period) replaces the plan row's
   total. Driver mix is preserved as a ratio: each driver row's amount is
   scaled by `actual_total / plan_total`.
2. **Corporate challenge.** A list of `{bucket, amount_usd}` items. Each
   challenge distributes proportionally across the bucket's *future* cells
   (entity × product_line/functional_area × driver × month) weighted by
   current cell amount.
3. **Operational response.** Same shape as challenge; sign typically opposite
   (a cost-cut response has a negative amount).

Each row in the proposed outlook carries a `change_source` tag indicating
which mechanism(s) caused its delta vs. the base version. A single row may
have multiple sources (e.g. a Q3 SG&A row might reflect both Q2 actuals
revision and a Q3 corporate challenge — though in practice rows tend to
have one dominant source).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from connectors.assumptions import ASSUMPTION_COLUMNS, validate_version


@dataclass(frozen=True)
class OutlookProposal:
    base_version: str
    target_version: str
    fy_year: int
    quarter: int                          # quarter that just closed
    proposed_rows: pd.DataFrame
    delta_breakdown: pd.DataFrame         # one row per non-zero delta
    change_sources_present: list[str]
    summary: dict[str, float]             # bucket-level deltas
    notes: list[str] = field(default_factory=list)


def _bucket_for(account_class: str, pnl_line: str) -> str:
    cls = (account_class or "").lower()
    if cls == "revenue":
        return "revenue"
    if cls == "cogs":
        return "cogs"
    if cls == "opex":
        return "rd" if (pnl_line or "").startswith("Opex / R&D") else "sga"
    return "other"


def _quarter_periods(fy_year: int, quarter: int) -> tuple[list[str], list[str]]:
    """Return (closed_periods, future_periods) for a fiscal year.

    A Q1 outlook (quarter=1) means Jan-Mar are closed; Apr-Dec are future.
    """
    closed = [f"{fy_year}-{m:02d}" for m in range(1, quarter * 3 + 1)]
    future = [f"{fy_year}-{m:02d}" for m in range(quarter * 3 + 1, 13)]
    return closed, future


def _ytd_actuals(repo_root: Path, fy_year: int, quarter: int) -> dict[tuple[str, str, str], float]:
    """Return {(entity, account, period): amount_usd_actual} for closed periods."""
    import sys
    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433

    closed, _ = _quarter_periods(fy_year, quarter)
    out: dict[tuple[str, str, str], float] = {}
    for period in closed:
        try:
            entities = connectors.list_entities(period)
        except FileNotFoundError:
            # No manifest for that period — skip
            continue
        for entity in entities:
            try:
                gl = connectors.get_gl(period=period, entity=entity)
            except (KeyError, FileNotFoundError):
                continue
            gl = gl.copy()
            gl["account"] = gl["account"].astype(str).str.strip()
            grouped = gl.groupby("account")["amount_usd"].sum()
            for acct, amt in grouped.items():
                # Convert GL signed-amount to magnitude (cogs/opex are negative
                # in GL but stored positive in assumptions schema)
                out[(entity, str(acct), period)] = abs(float(amt))
    return out


def _apply_actuals_revision(
    base_rows: pd.DataFrame,
    actuals: dict[tuple[str, str, str], float],
    closed_periods: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """For each (entity, account, period) in closed_periods, scale plan-row
    amounts so the period total matches actual. Returns (revised_rows, deltas).
    """
    rows = base_rows.copy()
    # Numeric columns may load as int64 from Excel; subsequent assignments
    # are floats, which pandas (≥3.0) refuses to silently downcast.
    for col in ("period_amount_usd", "quantity", "unit_cost"):
        if col in rows.columns:
            rows[col] = pd.to_numeric(rows[col], errors="coerce").astype(float)
    deltas: list[dict] = []

    closed_mask = rows["period"].isin(closed_periods)
    for (entity, account, period), grp in rows[closed_mask].groupby(
        ["entity", "account", "period"]
    ):
        actual = actuals.get((entity, str(account), period))
        if actual is None:
            continue
        plan_total = float(grp["period_amount_usd"].sum())
        if plan_total == 0:
            continue
        scale = actual / plan_total
        for idx, row in grp.iterrows():
            new_amount = float(row["period_amount_usd"]) * scale
            delta = new_amount - float(row["period_amount_usd"])
            rows.at[idx, "period_amount_usd"] = new_amount
            if abs(delta) > 0.005:
                deltas.append({
                    "entity": entity, "account": account, "period": period,
                    "product_line": row.get("product_line"),
                    "functional_area": row.get("functional_area"),
                    "driver_dim": row.get("driver_dim"),
                    "driver_value": row.get("driver_value"),
                    "delta_usd": delta,
                    "change_source": "actuals_revision",
                })
    return rows, pd.DataFrame(deltas)


def _apply_bucket_distribution(
    rows: pd.DataFrame,
    *,
    items: list[dict],                # [{"bucket": "sga", "amount_usd": 1_000_000}]
    future_periods: list[str],
    change_source: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Distribute each item proportionally across the bucket's future cells,
    weighted by current cell amount.

    `items` are in user-input grain (bucket × annual amount); the algorithm
    spreads each one across all (entity × product_line/functional_area ×
    driver × period) future cells in the bucket.
    """
    rows = rows.copy()
    if "period_amount_usd" in rows.columns:
        rows["period_amount_usd"] = pd.to_numeric(rows["period_amount_usd"], errors="coerce").astype(float)
    rows["_bucket"] = rows.apply(
        lambda r: _bucket_for(r["account_class"], r.get("pnl_line", "")), axis=1
    )
    deltas: list[dict] = []

    for item in items:
        bucket = item["bucket"].strip().lower()
        amount = float(item["amount_usd"])
        future_mask = (rows["_bucket"] == bucket) & rows["period"].isin(future_periods)
        future_rows = rows[future_mask]
        total_future = float(future_rows["period_amount_usd"].sum())
        if total_future == 0:
            continue
        for idx, row in future_rows.iterrows():
            share = float(row["period_amount_usd"]) / total_future
            cell_delta = share * amount
            new_amount = float(row["period_amount_usd"]) + cell_delta
            rows.at[idx, "period_amount_usd"] = new_amount
            if abs(cell_delta) > 0.005:
                deltas.append({
                    "entity": row["entity"],
                    "account": row["account"],
                    "period": row["period"],
                    "product_line": row.get("product_line"),
                    "functional_area": row.get("functional_area"),
                    "driver_dim": row.get("driver_dim"),
                    "driver_value": row.get("driver_value"),
                    "delta_usd": cell_delta,
                    "change_source": change_source,
                })

    rows = rows.drop(columns=["_bucket"])
    return rows, pd.DataFrame(deltas)


def compute(
    *,
    repo_root: Path,
    base_version: str,
    target_version: str,
    fy_year: int,
    quarter: int,
    corporate_challenges: list[dict] | None = None,
    operational_responses: list[dict] | None = None,
    base_period: str | None = None,
) -> OutlookProposal:
    """Build a proposed outlook. Writes nothing — caller persists after approval.

    `base_period` is the period string the base-version manifest carries
    (e.g., '2026-05'). Defaults to the most recent task under ``tasks/`` whose
    ``inputs/manifest.yaml`` declares the version.
    """
    validate_version(base_version)
    validate_version(target_version)
    if not 1 <= quarter <= 4:
        raise ValueError(f"quarter must be 1..4; got {quarter}")

    import os as _os
    import sys
    import yaml as _yaml

    sys.path.insert(0, str(repo_root))
    import connectors  # noqa: WPS433

    closed, future = _quarter_periods(fy_year, quarter)

    # Resolve which task hosts the base-version manifest.
    if base_period is None:
        tasks_root = repo_root / "tasks"
        if not tasks_root.exists():
            raise RuntimeError(
                "No tasks/ directory under repo root. Initialise a planning "
                "task with `python -m scripts.planning build --task plan-fy<YY> ...` "
                "or pass --task / --period explicitly. "
                "See runbooks/post_close_deliverables.md for the planning lifecycle."
            )
        candidates: list[tuple[str, Path, str]] = []
        for d in sorted(tasks_root.iterdir()):
            mf = d / "inputs" / "manifest.yaml"
            if not (d.is_dir() and mf.exists()):
                continue
            try:
                with mf.open() as fh:
                    m = _yaml.safe_load(fh) or {}
            except Exception:  # noqa: BLE001
                continue
            entities_block = m.get("entities") or {}
            has_version = any(
                any(a.get("version") == base_version
                    for a in (ent.get("assumptions") or []))
                for ent in entities_block.values()
            )
            if not has_version:
                continue
            period = m.get("period")
            if not period:
                continue
            candidates.append((d.name, d, str(period)))
        if not candidates:
            raise RuntimeError(
                f"No tasks/<task-id>/inputs/manifest.yaml declares "
                f"base_version={base_version!r}. Lock the base version first "
                "with `python -m scripts.planning build --task plan-fy<YY> ...`. "
                "See runbooks/post_close_deliverables.md."
            )
        # Prefer most-recently-modified task dir
        candidates.sort(key=lambda c: c[1].stat().st_mtime, reverse=True)
        base_task_id, base_task_dir, base_period = candidates[0]
        # Tell connectors to read inputs from this task directory.
        _os.environ["CFO_HELPER_TASK_DIR"] = str(base_task_dir.resolve())

    entities = connectors.list_entities(base_period)
    base_frames: list[pd.DataFrame] = []
    for entity in entities:
        f = connectors.get_assumptions(period=base_period, entity=entity, version=base_version)
        if not f.empty:
            base_frames.append(f)
    if not base_frames:
        raise RuntimeError(
            f"No assumption rows for base_version={base_version!r} in "
            f"tasks/<task-id>/inputs/manifest.yaml (period={base_period}). "
            "Cannot compute an outlook from an empty base. "
            "See runbooks/post_close_deliverables.md for the planning lifecycle."
        )
    base_rows = pd.concat(base_frames, ignore_index=True)

    # 1. Actuals revision for closed periods
    actuals = _ytd_actuals(repo_root, fy_year, quarter)
    revised_rows, actuals_deltas = _apply_actuals_revision(base_rows, actuals, closed)

    # 2. Corporate challenges
    challenges = corporate_challenges or []
    revised_rows, challenge_deltas = _apply_bucket_distribution(
        revised_rows, items=challenges, future_periods=future,
        change_source="quarterly_corporate_challenge",
    )

    # 3. Operational responses
    responses = operational_responses or []
    revised_rows, response_deltas = _apply_bucket_distribution(
        revised_rows, items=responses, future_periods=future,
        change_source="quarterly_operational_response",
    )

    # Stamp the new version onto every row
    revised_rows = revised_rows.copy()
    revised_rows["version"] = target_version

    # Recompute period_amount_usd → quantity × unit_cost where both columns
    # are still meaningful (post-scale, the volume × price decomposition no
    # longer holds; treat quantity/unit_cost as historical and rely on
    # period_amount_usd for downstream math).
    # For now, leave qty/unit_cost as-is and trust period_amount_usd.

    delta_frames = [actuals_deltas, challenge_deltas, response_deltas]
    delta_breakdown = pd.concat(
        [d for d in delta_frames if not d.empty], ignore_index=True
    ) if any(not d.empty for d in delta_frames) else pd.DataFrame(columns=[
        "entity", "account", "period", "product_line", "functional_area",
        "driver_dim", "driver_value", "delta_usd", "change_source",
    ])

    sources_present = sorted(delta_breakdown["change_source"].unique().tolist()) \
        if not delta_breakdown.empty else []

    # Bucket-level summary of deltas
    summary: dict[str, float] = {}
    if not delta_breakdown.empty:
        merged = delta_breakdown.merge(
            base_rows[["entity", "account", "period", "account_class", "pnl_line"]].drop_duplicates(),
            on=["entity", "account", "period"], how="left",
        )
        merged["_bucket"] = merged.apply(
            lambda r: _bucket_for(r["account_class"], r.get("pnl_line", "")), axis=1
        )
        for bucket, grp in merged.groupby("_bucket"):
            summary[f"delta_{bucket}_usd"] = float(grp["delta_usd"].sum())

    notes: list[str] = []
    if not actuals:
        notes.append(
            f"No YTD actuals found for closed periods {closed}. Outlook "
            "proposes plan amounts unchanged for those months."
        )
    return OutlookProposal(
        base_version=base_version,
        target_version=target_version,
        fy_year=fy_year,
        quarter=quarter,
        proposed_rows=revised_rows[ASSUMPTION_COLUMNS].copy(),
        delta_breakdown=delta_breakdown,
        change_sources_present=sources_present,
        summary=summary,
        notes=notes,
    )


def lock(
    *,
    proposal: OutlookProposal,
    repo_root: Path,
    workbook_stem: str,                # e.g. 'Assumptions_Outlook_Q1_2026'
    inputs_dir: Path,
) -> dict:
    """Persist a CFO-approved outlook proposal: per-entity workbooks, manifest
    update, and ingest re-run with `change_source` annotations.

    Returns the lock-file entry for the new version.
    """
    from .plan_build import write_per_entity_workbooks
    from scripts.ingest import ingest, annotate_lock

    # Update locked_at on all rows to now (the lock moment)
    rows = proposal.proposed_rows.copy()
    rows["locked_at"] = pd.Timestamp.now("UTC").date().isoformat()
    rows["source_doc"] = f"{workbook_stem}.xlsx"

    paths = write_per_entity_workbooks(rows, inputs_dir, workbook_stem)

    # Manifest update — append per-entity outlook entries
    import os as _os

    import yaml
    manifest_path = inputs_dir / "manifest.yaml"
    with manifest_path.open() as f:
        manifest = yaml.safe_load(f) or {}
    manifest.setdefault("entities", {})
    for entity, path in paths.items():
        ent_block = manifest["entities"].setdefault(entity, {})
        asm = ent_block.setdefault("assumptions", [])
        # Avoid duplicating an existing entry for this version
        if not any(e.get("version") == proposal.target_version for e in asm):
            asm.append({
                "workbook": path.name,
                "sheet": "Detail",
                "header_row": 1,
                "version": proposal.target_version,
            })
    with manifest_path.open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    # Ingest period derived from the *first future* period of the outlook.
    # `inputs_dir` is `tasks/<task-id>/inputs/`; ingest writes to its sibling
    # `working/` directory under the same task.
    first_future = f"{proposal.fy_year}-{proposal.quarter * 3 + 1:02d}"
    task_dir = inputs_dir.parent
    _os.environ["CFO_HELPER_TASK_DIR"] = str(task_dir.resolve())
    ingest(first_future, task_dir)

    # Annotate the new locks with change_source + locked_against
    sources = proposal.change_sources_present or ["actuals_revision"]
    out: dict[str, dict] = {}
    for entity in paths:
        key = f"{entity}/{proposal.target_version}"
        out[key] = annotate_lock(
            key,
            add_change_source=sources,
            set_locked_against=f"{entity}/{proposal.base_version}",
        )
    return out
