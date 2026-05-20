"""CLI for the gl-drilldown skill.

  python -m scripts.drilldown --period 2026-05 --entity UK --account 5150
  python -m scripts.drilldown --period 2026-05 --all-material
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]


def _format_summary(result: dict) -> str:
    if result["status"] != "ok":
        return f"  status: {result['status']}\n  reason: {result['reason']}"
    b = result["bridge"]
    lines = [
        f"  actual:           {b['actual_usd']:>12,.0f}",
        f"  subledger total:  {b['subledger_total']:>12,.0f}",
    ]
    for src, tot in b["subledger_totals"].items():
        lines.append(f"    {src:<16}{tot:>12,.0f}")
    lines.append(f"  reconciling:      {b['reconciling_usd']:>12,.0f}    "
                 f"tieout {'PASS' if b['tieout_pass'] else 'FAIL'}")
    if b["version_totals"]:
        lines.append("")
        lines.append("  Versions:")
        for v, t in b["version_totals"].items():
            d = b["deltas_to_versions"][v]
            lines.append(f"    {v:<22}total {t:>12,.0f}    delta {d:>+12,.0f}")
        if b["most_recent_outlook"]:
            lines.append(f"    (most-recent outlook: {b['most_recent_outlook']})")
    if result["dispatch"].get("missing_feeds"):
        lines.append(f"  missing feeds: {result['dispatch']['missing_feeds']}")
    if b.get("notes"):
        lines.append("  Notes:")
        for n in b["notes"]:
            lines.append(f"    - {n}")
    if result["drivers"]:
        lines.append("")
        lines.append("  Top drivers:")
        df = pd.DataFrame(result["drivers"])
        keep = ["driver_value", "source_subledger", "actual_usd"] + [
            c for c in df.columns if c.startswith("delta_to_")
        ]
        lines.append("    " + df.head(10)[keep].to_string(index=False).replace("\n", "\n    "))
    return "\n".join(lines)


def _persist(result: dict, outputs_dir: Path, account: str) -> Path | None:
    df = result.get("_drivers_df")
    if df is None or df.empty:
        return None
    outputs_dir.mkdir(parents=True, exist_ok=True)
    path = outputs_dir / f"drilldown_{account}.parquet"
    df.to_parquet(path, index=False)
    return path


def run_one(period: str, entity: str, account: str,
            outputs_dir: Path | None = None) -> dict:
    from . import drilldown as run_drilldown
    result = run_drilldown(
        period=period, entity=entity, account=str(account), repo_root=REPO,
    )
    if outputs_dir is not None:
        path = _persist(result, outputs_dir, str(account))
        if path is not None:
            result["artifact_path"] = str(path)
    return result


def main() -> int:
    from scripts._task_path import _resolve_task_dir

    ap = argparse.ArgumentParser(prog="scripts.drilldown")
    ap.add_argument("--period", default=None,
                    help="Back-compat: YYYY-MM resolves to tasks/close-<period>/.")
    ap.add_argument("--task", default=None,
                    help="Task id (preferred; e.g. close-2026-05).")
    ap.add_argument("--entity")
    ap.add_argument("--account")
    ap.add_argument("--all-material", action="store_true",
                    help="Iterate every (entity, account) in material_variances.parquet "
                         "produced by FP&A's variance phase.")
    ap.add_argument("--outputs-dir",
                    help="Directory to persist drilldown_<account>.parquet artifacts.")
    args = ap.parse_args()

    if not (args.period or args.task):
        ap.error("--period <YYYY-MM> or --task <id> is required")

    outputs_dir = Path(args.outputs_dir) if args.outputs_dir else None
    period = args.period or args.task.removeprefix("close-")

    if args.all_material:
        task_dir = _resolve_task_dir(args.period, args.task)
        mv_path = task_dir / "outputs" / "fpa" / "material_variances.parquet"
        if not mv_path.exists():
            sys.stderr.write(f"No material_variances.parquet at {mv_path}\n")
            return 2
        mv = pd.read_parquet(mv_path)
        if "entity" not in mv.columns:
            sys.stderr.write("material_variances.parquet missing 'entity' column.\n")
            return 2
        results: list[dict] = []
        for _, row in mv.iterrows():
            result = run_one(period, str(row["entity"]), str(row["account"]),
                             outputs_dir=outputs_dir)
            print(f"\n=== {row['entity']} {row['account']} {row.get('account_name', '')} ===")
            print(_format_summary(result))
            results.append({"entity": row["entity"], "account": row["account"], **result})
        return 0

    if not (args.entity and args.account):
        ap.error("--entity and --account are required unless --all-material is used")
    result = run_one(period, args.entity, str(args.account), outputs_dir=outputs_dir)
    print(f"=== {args.entity} {args.account} ===")
    print(_format_summary(result))
    return 0 if result["status"] == "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
