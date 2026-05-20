"""
Reconciliation / tie-out checks.

Run from Controller after ingest, and re-run independently by Reviewer from
source via connectors. All checks return a list of self_check dicts in the
work_product schema's shape.

Checks implemented:
    - tb_balanced_per_entity:   sum(debit) == sum(credit) per entity
    - sum_of_entities_matches:  consolidated total per account == sum across entities
    - intercompany_nets_zero:   intercompany account class nets to zero across entities
    - fx_completeness:          every non-USD currency in GL has an FX rate row
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

INTERCOMPANY_PREFIX = "13"   # canonical chart prefix for intercompany; override via account_map


def _con(db_path: Path) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(db_path), read_only=True)


def tb_balanced_per_entity(db_path: Path, tolerance_usd: float = 0.50) -> list[dict]:
    con = _con(db_path)
    df = con.execute(
        "SELECT entity, SUM(debit) AS dr, SUM(credit) AS cr FROM gl GROUP BY entity"
    ).df()
    con.close()
    out = []
    for _, row in df.iterrows():
        delta = float(row["dr"]) - float(row["cr"])
        out.append({
            "id": f"tb_balanced.{row['entity']}",
            "name": f"TB balanced for {row['entity']}",
            "outcome": "pass" if abs(delta) <= tolerance_usd else "fail",
            "expected": 0,
            "actual": delta,
            "tolerance": tolerance_usd,
        })
    return out


def sum_of_entities_matches_consolidated(db_path: Path,
                                          consolidated: pd.DataFrame,
                                          tolerance_usd: float = 1.00) -> list[dict]:
    """`consolidated` is Controller's consolidated TB with columns [account, amount_usd]."""
    con = _con(db_path)
    by_account = con.execute(
        "SELECT CAST(account AS VARCHAR) AS account, SUM(amount_usd) AS sum_entities "
        "FROM gl GROUP BY account"
    ).df()
    con.close()
    consolidated = consolidated.copy()
    consolidated["account"] = consolidated["account"].astype(str)
    merged = by_account.merge(
        consolidated.rename(columns={"amount_usd": "consolidated"}),
        on="account", how="outer"
    ).fillna(0)
    out = []
    failures = merged[(merged["sum_entities"] - merged["consolidated"]).abs() > tolerance_usd]
    out.append({
        "id": "sum_of_entities_matches",
        "name": "Sum of entities equals consolidated per account",
        "outcome": "pass" if failures.empty else "fail",
        "expected": 0,
        "actual": int(len(failures)),
        "tolerance": tolerance_usd,
        "notes": f"{len(failures)} accounts off",
    })
    return out


def intercompany_nets_zero(db_path: Path, prefix: str = INTERCOMPANY_PREFIX,
                            tolerance_usd: float = 1.00) -> list[dict]:
    con = _con(db_path)
    total = con.execute(
        "SELECT COALESCE(SUM(amount_usd), 0) AS t FROM gl WHERE CAST(account AS VARCHAR) LIKE ?",
        [f"{prefix}%"],
    ).fetchone()[0]
    con.close()
    return [{
        "id": "intercompany_nets_zero",
        "name": f"Intercompany (account prefix {prefix}) nets to zero",
        "outcome": "pass" if abs(float(total)) <= tolerance_usd else "fail",
        "expected": 0,
        "actual": float(total),
        "tolerance": tolerance_usd,
    }]


def fx_completeness(db_path: Path) -> list[dict]:
    con = _con(db_path)
    missing = con.execute("""
        SELECT DISTINCT g.currency
        FROM gl g
        LEFT JOIN fx f ON f.currency = g.currency
        WHERE g.currency != 'USD' AND f.currency IS NULL
    """).df()
    con.close()
    return [{
        "id": "fx_completeness",
        "name": "All non-USD currencies have FX rates",
        "outcome": "pass" if missing.empty else "fail",
        "expected": 0,
        "actual": int(len(missing)),
        "notes": ", ".join(missing["currency"].tolist()) if len(missing) else "",
    }]


def run_all(db_path: Path, consolidated: pd.DataFrame) -> list[dict]:
    checks: list[dict] = []
    checks.extend(tb_balanced_per_entity(db_path))
    checks.extend(sum_of_entities_matches_consolidated(db_path, consolidated))
    checks.extend(intercompany_nets_zero(db_path))
    checks.extend(fx_completeness(db_path))
    return checks
