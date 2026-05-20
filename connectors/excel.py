"""
Excel connector — the only "real" connector today.

Reads source data from `tasks/<task-id>/inputs/`. Expects a discoverable
folder layout (one workbook per entity per domain) but tolerates the messy
real-world cases via a manifest file.

The manifest (`tasks/<task-id>/inputs/manifest.yaml`) is optional but
recommended. When present, it tells the connector exactly which workbook +
sheet + range backs each (entity, domain) pair. Without it, the connector
falls back to filename heuristics.

Manifest example:

    period: "2026-05"
    entities:
      UK:
        gl:       { workbook: "GL_UK_2026-05.xlsx",       sheet: "TB",     header_row: 1 }
        budget:   { workbook: "Budget_UK_FY26.xlsx",      sheet: "May",    header_row: 1 }
        forecast: { workbook: "Forecast_UK_v3.xlsx",      sheet: "May",    header_row: 1, version: "v3" }
        headcount:{ workbook: "HC_UK_2026-05.xlsx",       sheet: "Snap",   header_row: 1 }
      US:
        gl:       { workbook: "GL_US_2026-05.xlsx",       sheet: "TB",     header_row: 1 }
        ...
    shared:
      customers: { workbook: "Customers_2026-05.xlsx",    sheet: "Detail", header_row: 1 }
      deals:    { workbook: "Deals_2026-05.xlsx",         sheet: "Closed", header_row: 1 }
      fx:       { workbook: "FX_2026-05.xlsx",            sheet: "Rates",  header_row: 1 }

Subledger and assumptions entries (per-entity) follow the same pattern.
Assumptions are append-only by version, so the manifest holds a list of
per-version specs:

    entities:
      UK:
        ap:        { workbook: "AP_2026-05.xlsx",  sheet: "Detail", header_row: 1 }
        ibs:       { workbook: "IBS_2026-05.xlsx", sheet: "Detail", header_row: 1 }
        assumptions:
          - { workbook: "Assumptions_Plan_FY26.xlsx",       sheet: "Detail", header_row: 1, version: "plan_fy26" }
          - { workbook: "Assumptions_Outlook_Q1_2026.xlsx", sheet: "Detail", header_row: 1, version: "outlook_q1_2026" }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

# --- Canonical column schemas -------------------------------------------------

GL_COLUMNS = ["entity", "period", "account", "account_name", "debit", "credit",
              "currency", "amount_local", "amount_usd"]
BUDGET_COLUMNS = ["entity", "period", "account", "account_name", "amount_usd"]
FORECAST_COLUMNS = ["entity", "period", "version", "account", "account_name", "amount_usd"]
CUSTOMER_COLUMNS = ["customer_id", "customer_name", "period", "revenue_usd", "arr_usd",
                    "product", "region"]
DEAL_COLUMNS = ["deal_id", "customer_id", "customer_name", "period", "stage",
                "tcv_usd", "acv_usd", "product", "owner"]
HEADCOUNT_COLUMNS = ["entity", "period", "department", "function", "fte", "fully_loaded_cost_usd"]
FX_COLUMNS = ["currency", "period", "rate_to_usd_avg", "rate_to_usd_eop"]

# Columns expected to hold numeric (float-coercible) values, keyed by domain.
# Entries for domains without a reader yet (ap, ibs, assumptions) are kept for
# future use — they have no effect until the corresponding reader is wired.
NUMERIC_COLUMNS: dict[str, tuple[str, ...]] = {
    "gl":          ("debit", "credit", "amount_local", "amount_usd"),
    "budget":      ("amount_usd",),
    "forecast":    ("amount_usd",),
    "customers":   ("revenue_usd", "arr_usd"),
    "deals":       ("tcv_usd", "acv_usd"),
    "headcount":   ("fte", "fully_loaded_cost_usd"),
    "fx":          ("rate_to_usd_avg", "rate_to_usd_eop"),
    "ap":          ("amount_usd",),
    "ibs":         ("amount_usd",),
    "assumptions": ("period_amount_usd",),
}


# --- Manifest loading ---------------------------------------------------------

def _manifest(workspace: Path) -> dict[str, Any] | None:
    path = workspace / "inputs" / "manifest.yaml"
    if not path.exists():
        return None
    with path.open() as f:
        return yaml.safe_load(f)


def _resolve_workbook(workspace: Path, spec: dict[str, Any]) -> Path:
    wb = workspace / "inputs" / spec["workbook"]
    if not wb.exists():
        raise FileNotFoundError(
            f"Workbook not found: {wb}. Check tasks/<task-id>/inputs/manifest.yaml."
        )
    return wb


def _read_sheet(workspace: Path, spec: dict[str, Any],
                wb_path: Path | None = None) -> pd.DataFrame:
    if wb_path is None:
        wb_path = _resolve_workbook(workspace, spec)
    header = spec.get("header_row", 1) - 1
    df = pd.read_excel(wb_path, sheet_name=spec["sheet"], header=header, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]
    return df


# --- Domain readers -----------------------------------------------------------

def _entity_spec(workspace: Path, entity: str, domain: str) -> dict[str, Any]:
    m = _manifest(workspace)
    if not m:
        raise FileNotFoundError(
            f"No manifest at {workspace / 'inputs' / 'manifest.yaml'}; "
            "filename heuristics not yet implemented. Add a manifest to proceed."
        )
    try:
        return m["entities"][entity][domain]
    except KeyError as e:
        raise KeyError(
            f"Manifest missing entry for entity={entity!r} domain={domain!r}: {e}"
        )


def _shared_spec(workspace: Path, domain: str) -> dict[str, Any]:
    m = _manifest(workspace)
    if not m:
        raise FileNotFoundError(
            f"No manifest at {workspace / 'inputs' / 'manifest.yaml'}."
        )
    try:
        return m["shared"][domain]
    except KeyError as e:
        raise KeyError(f"Manifest missing shared.{domain}: {e}")


def _coerce(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Reindex to canonical columns, filling missing with NaN. Caller validates."""
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"Source data missing required columns: {missing}. "
            f"Got: {list(df.columns)}"
        )
    return df[columns].copy()


def _validate_numeric(df: pd.DataFrame, domain: str, workbook: Path) -> pd.DataFrame:
    """For each column declared numeric in NUMERIC_COLUMNS[domain], attempt
    float coercion. Raise ValueError naming the workbook, column, and a sample
    of bad cells so the analyst can fix the source file immediately.

    Two failure modes are caught:
    1. String values with leading/trailing whitespace (e.g. "1234.5 ") —
       pd.to_numeric strips leading/trailing whitespace before coercing, so a
       value like "1234.5 " would silently succeed without this explicit check.
       We reject these because they indicate dirty source data (likely
       text-formatted in Excel or pasted from CSV) that should be flagged at
       the boundary.
    2. Values that cannot be coerced to numeric at all (e.g. "$500K", "N/A").
    """
    cols = NUMERIC_COLUMNS.get(domain, ())
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            continue
        series = out[col]
        # Flag strings that have untrimmed whitespace — dirty source data.
        whitespace_mask = series.apply(
            lambda v: isinstance(v, str) and v != v.strip()
        )
        # Flag values that fail numeric coercion entirely.
        coerced = pd.to_numeric(series, errors="coerce")
        coerce_fail_mask = coerced.isna() & series.notna() & ~whitespace_mask
        bad_mask = whitespace_mask | coerce_fail_mask
        if bad_mask.any():
            sample = series.loc[bad_mask].head(3).tolist()
            row_idx = series.index[bad_mask].tolist()[:3]
            raise ValueError(
                f"Non-numeric value(s) in {workbook.name} column '{col}'. "
                f"Sample bad cells (rows {row_idx}): {sample!r}. "
                f"Common cause: trailing space, currency symbol, or text in a numeric column."
            )
        out[col] = coerced
    return out


def _read_typed(workspace: Path, spec: dict[str, Any], columns: list[str], domain: str) -> pd.DataFrame:
    """Read a sheet, coerce to canonical columns, then validate numeric columns.

    Drop-in replacement for the inline `_coerce(_read_sheet(...))` pattern used
    in each public reader. The legacy pattern remains valid for internal callers
    that haven't been migrated yet, but all public readers should use this.

    The workbook path is resolved once here and passed to both _read_sheet and
    _validate_numeric, avoiding a double I/O call and keeping the path consistent
    in error messages."""
    wb_path = _resolve_workbook(workspace, spec)
    df = _read_sheet(workspace, spec, wb_path=wb_path)
    df = _coerce(df, columns)
    return _validate_numeric(df, domain, wb_path)


def get_gl(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    spec = _entity_spec(workspace, entity, "gl")
    df = _read_typed(workspace, spec, list(GL_COLUMNS), "gl")
    df["period"] = df["period"].astype(str)
    return df


def get_budget(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    spec = _entity_spec(workspace, entity, "budget")
    df = _read_typed(workspace, spec, list(BUDGET_COLUMNS), "budget")
    df["period"] = df["period"].astype(str)
    return df


def get_forecast(period: str, entity: str, version: str, workspace: Path) -> pd.DataFrame:
    spec = _entity_spec(workspace, entity, "forecast")
    df = _read_typed(workspace, spec, list(FORECAST_COLUMNS), "forecast")
    df["period"] = df["period"].astype(str)
    if version != "latest":
        df = df[df["version"] == version].copy()
    return df


def get_customers(period: str, workspace: Path) -> pd.DataFrame:
    spec = _shared_spec(workspace, "customers")
    return _read_typed(workspace, spec, list(CUSTOMER_COLUMNS), "customers")


def get_deals(period: str, workspace: Path) -> pd.DataFrame:
    spec = _shared_spec(workspace, "deals")
    return _read_typed(workspace, spec, list(DEAL_COLUMNS), "deals")


def get_headcount(period: str, entity: str, workspace: Path) -> pd.DataFrame:
    spec = _entity_spec(workspace, entity, "headcount")
    return _read_typed(workspace, spec, list(HEADCOUNT_COLUMNS), "headcount")


def get_fx(period: str, workspace: Path) -> pd.DataFrame:
    spec = _shared_spec(workspace, "fx")
    return _read_typed(workspace, spec, list(FX_COLUMNS), "fx")


def list_entities(period: str, workspace: Path) -> list[str]:
    m = _manifest(workspace)
    if not m:
        raise FileNotFoundError(f"No manifest at {workspace / 'inputs' / 'manifest.yaml'}.")
    return sorted(m.get("entities", {}).keys())


# --- Subledger and assumptions readers ---------------------------------------

def _maybe_entity_spec(workspace: Path, entity: str, domain: str) -> dict[str, Any] | list | None:
    """Like _entity_spec but returns None instead of raising when the entry
    is missing. Used for subledgers/assumptions which are optional feeds."""
    m = _manifest(workspace)
    if not m:
        return None
    return m.get("entities", {}).get(entity, {}).get(domain)


def read_subledger(name: str, period: str, entity: str, workspace: Path,
                   columns: list[str]) -> pd.DataFrame | None:
    """Read a per-entity subledger from Excel via the manifest.

    Returns None when no manifest entry exists for (entity, name); caller
    treats that as 'feed not wired'. Returns a DataFrame coerced to the
    given column contract otherwise. Numeric columns declared in
    NUMERIC_COLUMNS[name] are validated and coerced to float.
    """
    spec = _maybe_entity_spec(workspace, entity, name)
    if spec is None:
        return None
    if isinstance(spec, list):
        raise ValueError(
            f"Manifest entry entities.{entity}.{name} is a list; "
            f"expected a single workbook spec for subledger {name!r}."
        )
    df = _read_typed(workspace, spec, columns, name)
    if "period" in df.columns:
        df["period"] = df["period"].astype(str)
    return df


def read_assumptions(period: str, entity: str, workspace: Path,
                     columns: list[str], version: str = "all") -> pd.DataFrame:
    """Read assumptions across one or all versions for the entity.

    The manifest entry for assumptions is a list (one spec per version).
    `version='all'` concatenates them; a specific version filters to that
    one. Returns an empty DataFrame (with `columns`) when no manifest
    entry exists.
    """
    spec = _maybe_entity_spec(workspace, entity, "assumptions")
    if spec is None:
        return pd.DataFrame(columns=columns)
    if not isinstance(spec, list):
        raise ValueError(
            f"Manifest entry entities.{entity}.assumptions must be a list "
            f"(one spec per version). Got {type(spec).__name__}."
        )
    frames: list[pd.DataFrame] = []
    for v_spec in spec:
        v = v_spec.get("version")
        if not v:
            raise ValueError(
                f"Assumption manifest entry missing 'version' key: {v_spec}"
            )
        if version != "all" and v != version:
            continue
        df = _read_typed(workspace, v_spec, columns, "assumptions")
        if "period" in df.columns:
            df["period"] = df["period"].astype(str)
        # Trust the manifest's version over whatever's in the workbook
        df["version"] = v
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=columns)
    return pd.concat(frames, ignore_index=True)
