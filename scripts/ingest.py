"""
Ingest source workbooks for a period into a per-period DuckDB database.

Usage:
    python -m scripts.ingest --period 2026-05

Writes:
    tasks/close-<period>/working/ingest.duckdb
    tasks/close-<period>/working/ingest_summary.json   (row counts, FX as-of, entities)

Idempotent: running again replaces tables in place. Tables produced:
    gl, budget, forecast, customers, deals, headcount, fx,
    subledger_ap, subledger_ibs, assumptions

Append-only enforcement for assumptions: each (entity, version) pair is
content-hashed on first sight and recorded in profile/memory/assumptions_locked.json.
Subsequent ingests that change the rows for an already-locked version are
rejected. Use `--unlock <entity>/<version>` to clear a single lock (only
appropriate before any close has consumed the version).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import duckdb
import pandas as pd

# Make `connectors` importable when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import connectors  # noqa: E402
from connectors.assumptions import (  # noqa: E402
    natural_key_columns, validate_version, validate_change_sources,
)
from scripts._task_path import REPO, _period_from_args, _resolve_task_dir  # noqa: E402

LOCK_FILE = Path(
    os.environ.get("ASSUMPTIONS_LOCK_FILE",
                   str(REPO / "profile" / "memory" / "assumptions_locked.json"))
)

_ASSUMPTION_HASH_COLS = natural_key_columns() + [
    "pnl_line", "account_class",
    "quantity", "unit_cost", "period_amount_usd",
    "locked_at", "source_doc",
]


_NUMERIC_HASH_COLS = {"quantity", "unit_cost", "period_amount_usd"}


def _row_hash(df: pd.DataFrame) -> str:
    """Canonical content hash of an assumption-version's rows.

    Stable across:
      - row order (rows sorted on natural key)
      - NaN representation (normalized to empty string)
      - int vs float inference (numeric columns coerced to fixed-precision floats)

    The numeric normalization is critical: pandas may infer the same Excel
    cell as int64 in one read and float64 in another (e.g., when another
    cell in the column has a fractional value or NaN). Stringifying without
    normalization produces "100000" vs "100000.0" → different hashes for
    identical content.
    """
    nk = natural_key_columns()
    sub = df[_ASSUMPTION_HASH_COLS].copy()
    for c in sub.columns:
        if c in _NUMERIC_HASH_COLS:
            # Coerce to float, render with fixed precision; NaN → empty
            numeric = pd.to_numeric(sub[c], errors="coerce")
            sub[c] = numeric.apply(lambda v: "" if pd.isna(v) else f"{float(v):.4f}")
        else:
            sub[c] = sub[c].astype(str).fillna("")
    sub = sub.sort_values(nk).reset_index(drop=True)
    blob = sub.to_json(orient="records").encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _load_locks() -> dict:
    if not LOCK_FILE.exists():
        return {}
    with LOCK_FILE.open() as f:
        return json.load(f)


def _save_locks(locks: dict) -> None:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as f:
        json.dump(locks, f, indent=2, sort_keys=True)


def enforce_assumption_immutability(
    assumptions: pd.DataFrame,
    annotations: dict[str, dict] | None = None,
) -> dict:
    """Validate version regex; lock new versions; reject changes to locked versions.

    `annotations` is an optional mapping `"<entity>/<version>" → {change_source,
    locked_against}` recorded on first lock for lineage tracking. Existing
    locks are not retroactively annotated by this function — use `annotate_lock`
    for that.

    Returns the (possibly updated) lock map.
    """
    annotations = annotations or {}
    # Validate any annotations passed in before doing anything destructive.
    for key, ann in annotations.items():
        cs = ann.get("change_source") or []
        if cs:
            validate_change_sources(cs)

    locks = _load_locks()
    new_locks = dict(locks)
    rejections: list[str] = []

    for (entity, version), grp in assumptions.groupby(["entity", "version"]):
        validate_version(version)  # raises on malformed version names
        h = _row_hash(grp)
        key = f"{entity}/{version}"
        if key in locks:
            if locks[key]["hash"] != h:
                rejections.append(
                    f"  - {key}: locked hash {locks[key]['hash'][:12]}…, "
                    f"new hash {h[:12]}… ({len(grp)} rows in this load, "
                    f"{locks[key]['row_count']} rows when locked)"
                )
        else:
            entry = {
                "hash": h,
                "first_locked_at": pd.Timestamp.now("UTC").isoformat(),
                "row_count": int(len(grp)),
            }
            ann = annotations.get(key)
            if ann:
                if ann.get("change_source"):
                    entry["change_source"] = list(ann["change_source"])
                if ann.get("locked_against"):
                    entry["locked_against"] = ann["locked_against"]
            new_locks[key] = entry

    if rejections:
        raise RuntimeError(
            "Assumption immutability violation — refusing to ingest. "
            "Once a (entity, version) pair is locked, its rows cannot change.\n"
            + "\n".join(rejections) + "\n\n"
            "If this is intentional (e.g., correcting a typo before any close "
            "has consumed the version), run "
            "`python -m scripts.ingest --unlock <entity>/<version>` first."
        )

    if new_locks != locks:
        _save_locks(new_locks)
    return new_locks


def annotate_lock(
    key: str,
    *,
    add_change_source: list[str] | None = None,
    set_locked_against: str | None = None,
) -> dict:
    """Attach lineage annotations to an already-locked version.

    `add_change_source` appends to the existing list (deduplicated, never
    removes). `set_locked_against` is settable only once — calling again with
    a different value is rejected so lineage stays auditable. Hash and row
    count are unchanged.
    """
    locks = _load_locks()
    if key not in locks:
        raise KeyError(f"No lock for {key!r}; nothing to annotate.")
    entry = dict(locks[key])

    if add_change_source:
        validate_change_sources(add_change_source)
        existing = entry.get("change_source", [])
        merged = list(dict.fromkeys(existing + add_change_source))  # ordered set
        entry["change_source"] = merged

    if set_locked_against is not None:
        prior = entry.get("locked_against")
        if prior and prior != set_locked_against:
            raise ValueError(
                f"{key} already has locked_against={prior!r}; "
                f"cannot reset to {set_locked_against!r}."
            )
        entry["locked_against"] = set_locked_against

    locks[key] = entry
    _save_locks(locks)
    return entry


def ingest(period: str, task_dir: Path) -> dict:
    working = task_dir / "working"
    working.mkdir(parents=True, exist_ok=True)
    db_path = working / "ingest.duckdb"
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))

    entities = connectors.list_entities(period)

    frames: dict[str, list[pd.DataFrame]] = {
        "gl": [], "budget": [], "forecast": [], "headcount": [],
        "subledger_ap": [], "subledger_ibs": [], "assumptions": [],
    }
    for entity in entities:
        frames["gl"].append(connectors.get_gl(period=period, entity=entity))
        frames["budget"].append(connectors.get_budget(period=period, entity=entity))
        try:
            frames["forecast"].append(connectors.get_forecast(period=period, entity=entity))
        except (KeyError, FileNotFoundError):
            pass
        frames["headcount"].append(connectors.get_headcount(period=period, entity=entity))
        # Optional drilldown subledgers — empty when no manifest entry, no error.
        frames["subledger_ap"].append(connectors.get_subledger("ap",  period=period, entity=entity))
        frames["subledger_ibs"].append(connectors.get_subledger("ibs", period=period, entity=entity))
        frames["assumptions"].append(connectors.get_assumptions(period=period, entity=entity))

    def _concat_or_empty(parts: list[pd.DataFrame], cols: list[str]) -> pd.DataFrame:
        if not parts:
            return pd.DataFrame(columns=cols)
        return pd.concat(parts, ignore_index=True)

    gl = _concat_or_empty(frames["gl"], connectors.excel.GL_COLUMNS)
    budget = _concat_or_empty(frames["budget"], connectors.excel.BUDGET_COLUMNS)
    forecast = _concat_or_empty(frames["forecast"], connectors.excel.FORECAST_COLUMNS)
    headcount = _concat_or_empty(frames["headcount"], connectors.excel.HEADCOUNT_COLUMNS)
    subledger_ap = _concat_or_empty(frames["subledger_ap"], connectors.subledger.AP_SUBLEDGER_COLUMNS)
    subledger_ibs = _concat_or_empty(frames["subledger_ibs"], connectors.ibs.IBS_COLUMNS)
    assumptions = _concat_or_empty(frames["assumptions"], connectors.assumptions.ASSUMPTION_COLUMNS)

    # Append-only enforcement: hashes new (entity, version) pairs into
    # memory/assumptions_locked.json on first sight; rejects any subsequent
    # ingest that changes the locked rows.
    if not assumptions.empty:
        enforce_assumption_immutability(assumptions)

    customers = connectors.get_customers(period=period)
    deals = connectors.get_deals(period=period)
    fx = connectors.get_fx(period=period)

    con.register("gl_df", gl); con.execute("CREATE TABLE gl AS SELECT * FROM gl_df")
    con.register("budget_df", budget); con.execute("CREATE TABLE budget AS SELECT * FROM budget_df")
    con.register("forecast_df", forecast); con.execute("CREATE TABLE forecast AS SELECT * FROM forecast_df")
    con.register("headcount_df", headcount); con.execute("CREATE TABLE headcount AS SELECT * FROM headcount_df")
    con.register("customers_df", customers); con.execute("CREATE TABLE customers AS SELECT * FROM customers_df")
    con.register("deals_df", deals); con.execute("CREATE TABLE deals AS SELECT * FROM deals_df")
    con.register("fx_df", fx); con.execute("CREATE TABLE fx AS SELECT * FROM fx_df")
    con.register("subledger_ap_df",  subledger_ap)
    con.execute("CREATE TABLE subledger_ap AS SELECT * FROM subledger_ap_df")
    con.register("subledger_ibs_df", subledger_ibs)
    con.execute("CREATE TABLE subledger_ibs AS SELECT * FROM subledger_ibs_df")
    con.register("assumptions_df",   assumptions)
    con.execute("CREATE TABLE assumptions AS SELECT * FROM assumptions_df")

    summary = {
        "period": period,
        "entities": entities,
        "row_counts": {
            "gl": len(gl), "budget": len(budget), "forecast": len(forecast),
            "headcount": len(headcount), "customers": len(customers),
            "deals": len(deals), "fx": len(fx),
            "subledger_ap": len(subledger_ap), "subledger_ibs": len(subledger_ibs),
            "assumptions": len(assumptions),
        },
        "assumption_versions": (
            sorted(assumptions["version"].dropna().unique().tolist())
            if not assumptions.empty else []
        ),
        "db_path": str(db_path),
    }
    with (working / "ingest_summary.json").open("w") as f:
        json.dump(summary, f, indent=2)

    con.close()
    return summary


def unlock(key: str) -> None:
    """Remove a single (entity/version) lock so the next ingest can re-record it.

    Only appropriate when correcting a typo before any close has consumed
    the version. Production should never need this.
    """
    locks = _load_locks()
    if key not in locks:
        sys.stderr.write(f"No lock present for {key!r}; nothing to unlock.\n")
        return
    del locks[key]
    _save_locks(locks)
    sys.stderr.write(f"Removed lock for {key!r}. Next ingest will re-lock with the workbook's current rows.\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", help="YYYY-MM (required for ingest, omit for --unlock)")
    ap.add_argument("--task", metavar="TASK_ID",
                    help="Task id (e.g. close-2026-05); alternative to --period.")
    ap.add_argument("--unlock", metavar="ENTITY/VERSION",
                    help="Clear an assumption lock (e.g. UK/plan_fy26) and exit.")
    args = ap.parse_args()
    if args.unlock:
        unlock(args.unlock)
        return 0
    if not args.period and not args.task:
        ap.error("--period or --task is required unless --unlock is given")
    period = _period_from_args(args.period, args.task)
    task_dir = _resolve_task_dir(args.period, args.task)
    # Tell connectors to read inputs from this task directory.
    os.environ["CFO_HELPER_TASK_DIR"] = str(task_dir)
    summary = ingest(period, task_dir)
    entities_str = ", ".join(summary["entities"])
    gl_rows = summary["row_counts"].get("gl", 0)
    budget_rows = summary["row_counts"].get("budget", 0)
    print(f"Ingest complete. {len(summary['entities'])} entities ({entities_str}), "
          f"{gl_rows} GL rows, {budget_rows} budget rows.")
    print(f"  DB: {summary['db_path']}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
