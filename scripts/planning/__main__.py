"""CLI: python -m scripts.planning {build|refresh|gap|trio|strategic|walk} ...

  build     — read a driver workbook, write per-entity assumption workbooks,
              update manifest, run ingest with change_source annotations.
  refresh   — outlook-refresh compute (no rows written) or lock (write + ingest).
  gap       — gap-to-stretch between two version IDs, write artifact + memo.
  trio      — compute sales / EBIT / FCF for one version (per-entity or consolidated).
  strategic — strategic-plan-build: compile percent-driven workbook → plan_3yr_fy{YY}.
  walk      — strategic-plan-walk: Y1→Y3 stitched walk for board materials.

Path resolution
---------------
Every subcommand accepts either ``--task <id>`` (preferred — e.g.
``--task plan-fy26``) or ``--period <YYYY-MM>`` (back-compat — resolves to
``tasks/close-<period>/``). Planning task ids follow the convention in
``scripts._task_path``:

    plan-fy{YY}             annual operational plan
    outlook-q{N}-{YYYY}     quarterly outlook refresh
    strategic-fy{YY}        annual 3-year strategic plan

The ``build``, ``strategic``, and ``refresh lock`` subcommands call
``init_planning_task`` to create the task skeleton + stub manifest the first
time a planning task id is seen. The helper is idempotent.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from scripts._task_path import (
    _resolve_task_dir,
    init_planning_task,
    is_planning_task,
)

REPO = Path(__file__).resolve().parents[2]


def _resolve_or_init(task: str | None, period: str | None) -> Path:
    """Resolve a task dir, initializing planning-task skeletons on first use."""
    if task and is_planning_task(task):
        init_planning_task(task)
    return _resolve_task_dir(period, task)


def _parse_bucket_items(arg: str | None) -> list[dict]:
    """Parse "sga:1000000" or "sga:1000000,cogs:-200000" into list of items."""
    if not arg:
        return []
    out: list[dict] = []
    for piece in arg.split(","):
        piece = piece.strip()
        if not piece:
            continue
        bucket, amount = piece.split(":")
        out.append({"bucket": bucket.strip().lower(), "amount_usd": float(amount)})
    return out


def _build(args) -> int:
    import os as _os

    from .plan_build import build, write_per_entity_workbooks
    from scripts.ingest import ingest, annotate_lock

    rows = build(
        driver_workbook=Path(args.drivers),
        version=args.version,
        sheet=args.sheet,
        fy_year=args.fy,
    )
    if rows.empty:
        print(f"No rows produced for {args.version!r}.")
        return 2

    task_dir = _resolve_or_init(args.task, args.period)
    inputs_dir = task_dir / "inputs"
    paths = write_per_entity_workbooks(rows, inputs_dir, args.workbook_stem)

    # Manifest update (append per-version entries)
    manifest_path = inputs_dir / "manifest.yaml"
    with manifest_path.open() as f:
        manifest = yaml.safe_load(f) or {}
    manifest.setdefault("entities", {})
    for entity, path in paths.items():
        ent = manifest["entities"].setdefault(entity, {})
        asm = ent.setdefault("assumptions", [])
        if not any(e.get("version") == args.version for e in asm):
            asm.append({
                "workbook": path.name,
                "sheet": "Detail",
                "header_row": 1,
                "version": args.version,
            })
    with manifest_path.open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    # Resolve the period string the connectors will see. For close tasks the
    # CLI carries it; for planning tasks the manifest stub holds it.
    period = args.period or manifest.get("period")
    if not period:
        raise RuntimeError(
            f"No period resolvable for task {args.task!r}. "
            "Pass --period or ensure the manifest carries 'period:'."
        )
    # Connectors read inputs from CFO_HELPER_TASK_DIR when set.
    _os.environ["CFO_HELPER_TASK_DIR"] = str(task_dir.resolve())

    # Ingest + annotate
    ingest(period, task_dir)
    sources = args.change_source.split(",") if args.change_source else []
    sources = [s.strip() for s in sources if s.strip()]
    if sources:
        for entity in paths:
            key = f"{entity}/{args.version}"
            annotate_lock(
                key,
                add_change_source=sources,
                set_locked_against=(f"{entity}/{args.locked_against}"
                                    if args.locked_against else None),
            )
    print(f"Built {args.version!r} for entities {list(paths.keys())} from {args.drivers}.")
    return 0


def _refresh(args) -> int:
    from .outlook_refresh import compute, lock

    if args.action == "compute":
        proposal = compute(
            repo_root=REPO,
            base_version=args.base,
            target_version=args.target,
            fy_year=args.fy,
            quarter=args.quarter,
            corporate_challenges=_parse_bucket_items(args.challenge),
            operational_responses=_parse_bucket_items(args.response),
        )
        if args.outputs_dir:
            out_dir = Path(args.outputs_dir)
        elif args.task or args.period:
            task_dir = _resolve_or_init(args.task, args.period)
            out_dir = task_dir / "outputs" / "fpa" / "artifacts"
        else:
            # Last-resort fallback — write next to the FY/quarter folder under tasks/
            default_id = f"outlook-q{args.quarter}-{args.fy}"
            init_planning_task(default_id)
            out_dir = (REPO / "tasks" / default_id
                       / "outputs" / "fpa" / "artifacts")
        out_dir.mkdir(parents=True, exist_ok=True)
        proposal_path = out_dir / f"outlook_proposal_{args.target}.parquet"
        proposal.proposed_rows.to_parquet(proposal_path, index=False)
        delta_path = out_dir / f"outlook_delta_breakdown_{args.target}.parquet"
        if not proposal.delta_breakdown.empty:
            proposal.delta_breakdown.to_parquet(delta_path, index=False)
        print(f"Proposal written: {proposal_path}")
        print(f"Sources present: {proposal.change_sources_present}")
        print(f"Bucket-level deltas:")
        for k, v in proposal.summary.items():
            print(f"  {k:<28} {v:>+12,.0f}")
        for n in proposal.notes:
            print(f"  note: {n}")
        return 0

    if args.action == "lock":
        # Re-run compute and lock; in practice the dashboard would pass an
        # operator-modified proposal parquet, but for CLI we just rerun.
        proposal = compute(
            repo_root=REPO,
            base_version=args.base,
            target_version=args.target,
            fy_year=args.fy,
            quarter=args.quarter,
            corporate_challenges=_parse_bucket_items(args.challenge),
            operational_responses=_parse_bucket_items(args.response),
        )
        task_dir = _resolve_or_init(args.task, args.period)
        inputs_dir = task_dir / "inputs"
        stem = f"Assumptions_{args.target.replace('_', '_').title().replace('Fy', 'FY')}"
        lock_result = lock(
            proposal=proposal,
            repo_root=REPO,
            workbook_stem=stem,
            inputs_dir=inputs_dir,
        )
        print(f"Locked {args.target!r} for entities {list(lock_result.keys())}.")
        return 0

    raise ValueError(f"Unknown refresh action: {args.action}")


def _gap(args) -> int:
    from .gap_to_stretch import gap as run_gap

    result = run_gap(
        from_version=getattr(args, "from"),
        to_version=args.to,
        period=args.period,
        repo_root=REPO,
    )
    print(f"=== {result.from_version} → {result.to_version} ===")
    print(f"Trio (consolidated):")
    for k, v in result.trio_delta.items():
        print(f"  {k:<24} {v:>+12,.0f}")
    print(f"Bucket delta:")
    for k, v in result.bucket_delta.items():
        print(f"  {k:<10} {v:>+12,.0f}")
    print(f"Top drivers:")
    if not result.driver_deltas.empty:
        cols = ["entity", "account", "driver_value", "bucket",
                "from_amount_usd", "to_amount_usd", "delta_usd", "mechanism_hint"]
        print(result.driver_deltas[cols].head(20).to_string(index=False))
    print(f"Lineage:")
    for ent, ln in result.to_version_lineage.items():
        print(f"  {ent}: change_source={ln['change_source']}, locked_against={ln['locked_against']}")
    if args.outputs_dir:
        out_dir = Path(args.outputs_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"gap_{result.from_version}__to__{result.to_version}.parquet"
        if not result.driver_deltas.empty:
            result.driver_deltas.to_parquet(path, index=False)
            print(f"Driver deltas written: {path}")
    return 0


def _strategic(args) -> int:
    import os as _os

    from .strategic_plan_build import build
    from .plan_build import write_per_entity_workbooks
    from scripts.ingest import ingest, annotate_lock

    result = build(workbook=Path(args.workbook), version=args.version, repo_root=REPO,
                   sheet=args.sheet)
    if result.rows.empty:
        print("No rows produced.")
        return 2

    task_dir = _resolve_or_init(args.task, args.period)
    inputs_dir = task_dir / "inputs"
    paths = write_per_entity_workbooks(result.rows, inputs_dir, args.workbook_stem)

    # Manifest update
    manifest_path = inputs_dir / "manifest.yaml"
    with manifest_path.open() as f:
        manifest = yaml.safe_load(f) or {}
    manifest.setdefault("entities", {})
    for entity, path in paths.items():
        ent = manifest["entities"].setdefault(entity, {})
        asm = ent.setdefault("assumptions", [])
        if not any(e.get("version") == args.version for e in asm):
            asm.append({
                "workbook": path.name, "sheet": "Detail",
                "header_row": 1, "version": args.version,
            })
    with manifest_path.open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    period = args.period or manifest.get("period")
    if not period:
        raise RuntimeError(
            f"No period resolvable for task {args.task!r}. "
            "Pass --period or ensure the manifest carries 'period:'."
        )
    _os.environ["CFO_HELPER_TASK_DIR"] = str(task_dir.resolve())

    ingest(period, task_dir)
    sources = [s.strip() for s in args.change_source.split(",") if s.strip()]
    operational_anchor = args.version.replace("plan_3yr_", "plan_")
    for entity in paths:
        annotate_lock(
            f"{entity}/{args.version}",
            add_change_source=sources,
            set_locked_against=f"{entity}/{operational_anchor}",
        )
    print(f"Built {args.version!r} ({len(result.rows)} rows) anchored to {operational_anchor}.")
    if result.notes:
        for n in result.notes:
            print(f"  note: {n}")
    return 0


def _walk(args) -> int:
    from .strategic_plan_walk import walk
    w = walk(strategic_version=args.version, repo_root=REPO)
    print(f"=== {w.strategic_version}  anchored to  {w.operational_version}  (FY{w.fy_year}) ===")
    print()
    def _fmt(v):
        return f"{v:>12,.0f}" if v is not None else f"{'(unset)':>12}"
    rate = w.cash_tax_rate_used
    rate_str = f"{rate:.0%}" if rate is not None else "unset (FCF=None)"
    print(f"Walk by year (consolidated)  [ETR proxy: {rate_str}]")
    for year in ("Y1", "Y2", "Y3"):
        t = w.walk_by_year[year]
        print(f"  {year}: sales={_fmt(t['sales'])}  cogs={_fmt(t['cogs'])}  "
              f"ebit={_fmt(t['ebit'])}  fcf={_fmt(t['fcf'])}")
    print()
    if w.by_mechanism:
        print(f"By mechanism (Y2+Y3 totals):")
        for mech, b in w.by_mechanism.items():
            print(f"  {mech}: {b}")
    if w.notes:
        print(f"\nNotes:")
        for n in w.notes:
            print(f"  - {n}")
    return 0


def _trio(args) -> int:
    from .trio import compute_trio
    if args.consolidated:
        r = compute_trio(version=args.version, consolidated=True,
                         period=args.period, repo_root=REPO)
    else:
        r = compute_trio(version=args.version, entity=args.entity,
                         period=args.period, repo_root=REPO)
    print(f"=== {r.entity} {r.version} {r.period} ===")
    print(f"  Sales:  {r.sales_usd:>14,.0f}")
    print(f"  EBIT:   {r.ebit_usd:>14,.0f}")
    print(f"  FCF:    {r.fcf_usd:>14,.0f}")
    print(f"  Buckets: {r.bucket_totals}")
    print(f"  FCF components:")
    for k, v in r.fcf_components.items():
        print(f"    {k:<32} {v:>+14,.0f}")
    if r.notes:
        print(f"  Notes:")
        for n in r.notes:
            print(f"    - {n}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="scripts.planning")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="Build a version from a driver workbook")
    b.add_argument("--version", required=True)
    b.add_argument("--drivers", required=True, help="Path to driver workbook")
    b.add_argument("--task", default=None,
                   help="Task id (preferred; e.g. plan-fy26, strategic-fy26). "
                        "Initialises tasks/<id>/ with a stub manifest on first use.")
    b.add_argument("--period", default=None,
                   help="Back-compat: YYYY-MM resolves to tasks/close-<period>/.")
    b.add_argument("--sheet", default="Drivers")
    b.add_argument("--fy", type=int, help="Override fy_year if not in workbook")
    b.add_argument("--workbook-stem", required=True,
                   help="e.g. 'Assumptions_BottomsUp_FY26'")
    b.add_argument("--change-source", default="",
                   help="Comma-separated change_source tags for the lock annotation")
    b.add_argument("--locked-against", default=None,
                   help="Prior version (without entity prefix) to record as lineage")
    b.set_defaults(func=_build)

    r = sub.add_parser("refresh", help="Outlook-refresh compute or lock")
    r.add_argument("action", choices=("compute", "lock"))
    r.add_argument("--base", required=True)
    r.add_argument("--target", required=True)
    r.add_argument("--fy", type=int, required=True)
    r.add_argument("--quarter", type=int, required=True, choices=(1, 2, 3, 4))
    r.add_argument("--challenge", default="",
                   help="Comma-separated bucket:amount pairs (e.g. 'sga:1000000,cogs:-200000')")
    r.add_argument("--response", default="",
                   help="Comma-separated bucket:amount pairs")
    r.add_argument("--outputs-dir", default=None)
    r.add_argument("--task", default=None,
                   help="Task id (preferred; e.g. outlook-q2-2026).")
    r.add_argument("--period", default=None,
                   help="Back-compat: YYYY-MM resolves to tasks/close-<period>/. "
                        "Required for action=lock unless --task is given.")
    r.set_defaults(func=_refresh)

    g = sub.add_parser("gap", help="Three-layer delta between two versions")
    g.add_argument("--from", dest="from", required=True)
    g.add_argument("--to", required=True)
    g.add_argument("--period", required=True)
    g.add_argument("--outputs-dir", default=None)
    g.set_defaults(func=_gap)

    t = sub.add_parser("trio", help="Sales / EBIT / FCF for a version")
    t.add_argument("--version", required=True)
    t.add_argument("--period", required=True)
    t.add_argument("--entity", default=None)
    t.add_argument("--consolidated", action="store_true")
    t.set_defaults(func=_trio)

    s = sub.add_parser("strategic",
                       help="Compile a strategic 3-yr workbook → plan_3yr_fy{YY}")
    s.add_argument("--version", required=True, help="e.g. plan_3yr_fy26")
    s.add_argument("--workbook", required=True, help="Strategic workbook path")
    s.add_argument("--task", default=None,
                   help="Task id (preferred; e.g. strategic-fy26).")
    s.add_argument("--period", default=None,
                   help="Back-compat: YYYY-MM resolves to tasks/close-<period>/.")
    s.add_argument("--sheet", default="Strategic")
    s.add_argument("--workbook-stem", default="Assumptions_Plan_3yr",
                   help="Output workbook stem (suffixed with _<entity>.xlsx)")
    s.add_argument("--change-source", default="bottoms_up_submission",
                   help="Comma-separated change_source tags for the lock annotation")
    s.set_defaults(func=_strategic)

    w = sub.add_parser("walk",
                       help="Y1→Y3 walk for board materials")
    w.add_argument("--version", required=True, help="e.g. plan_3yr_fy26")
    w.set_defaults(func=_walk)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
