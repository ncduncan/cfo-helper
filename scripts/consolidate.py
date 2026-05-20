"""
Consolidation: per-entity GL → consolidated TB and P&L view.

Steps:
  1. Map each entity's account to canonical chart via profile/memory/account_map.json.
  2. Sum amount_usd by canonical account across entities.
  3. Eliminate intercompany (account class flagged as 'intercompany' in account_map).
  4. Project a P&L view using the canonical account → P&L line mapping.

Output: a dict with 'consolidated_tb' and 'pnl' DataFrames, plus the raw
account-level frame post-mapping for tie-out checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd


def _account_map(repo_root: Path) -> dict:
    with (repo_root / "profile" / "memory" / "account_map.json").open() as f:
        return json.load(f)


def consolidate(db_path: Path, repo_root: Path) -> dict:
    amap = _account_map(repo_root)
    entries = amap.get("entries", [])
    if not entries:
        # Pass-through if account map is empty: treat raw account as canonical
        with duckdb.connect(str(db_path), read_only=True) as con:
            gl = con.execute("SELECT * FROM gl").df()
        gl["account"] = gl["account"].astype(str)
        gl["canonical_account"] = gl["account"]
        gl["canonical_name"] = gl["account_name"]
        gl["account_class"] = "unmapped"
        gl["pnl_line"] = "Unmapped"
    else:
        with duckdb.connect(str(db_path), read_only=True) as con:
            gl = con.execute("SELECT * FROM gl").df()
        gl["account"] = gl["account"].astype(str)
        m = pd.DataFrame(entries)
        m["account"] = m["account"].astype(str)
        # Match on (entity, account) where present, else (account)
        gl = gl.merge(
            m[["entity", "account", "canonical_account", "canonical_name",
               "account_class", "pnl_line"]],
            on=["entity", "account"], how="left",
        )
        # Fallback: any missing canonical → treat raw as canonical
        mask = gl["canonical_account"].isna()
        gl.loc[mask, "canonical_account"] = gl.loc[mask, "account"]
        gl.loc[mask, "canonical_name"] = gl.loc[mask, "account_name"]
        gl.loc[mask, "account_class"] = gl.loc[mask, "account_class"].fillna("unmapped")
        gl.loc[mask, "pnl_line"] = gl.loc[mask, "pnl_line"].fillna("Unmapped")

    # Eliminate intercompany
    pre_elim = gl.copy()
    elim_mask = gl["account_class"] == "intercompany"
    eliminated_total = float(gl.loc[elim_mask, "amount_usd"].sum())
    gl_post = gl.loc[~elim_mask].copy()

    consolidated_tb = (
        gl_post.groupby(["canonical_account", "canonical_name"], as_index=False)["amount_usd"]
        .sum()
        .rename(columns={"canonical_account": "account", "canonical_name": "account_name"})
        .sort_values("account")
        .reset_index(drop=True)
    )

    pnl = (
        gl_post[gl_post["account_class"].isin(["revenue", "cogs", "opex", "other_income", "tax"])]
        .groupby("pnl_line", as_index=False)["amount_usd"].sum()
        .rename(columns={"amount_usd": "amount_usd"})
        .sort_values("pnl_line")
        .reset_index(drop=True)
    )

    return {
        "consolidated_tb": consolidated_tb,
        "pnl": pnl,
        "pre_elim": pre_elim,
        "intercompany_eliminated_usd": eliminated_total,
    }
