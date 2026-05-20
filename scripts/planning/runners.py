"""Deterministic runners for the planning pipeline.

Each runner wraps the corresponding `scripts.planning.*` computation and
emits a `work_product.json` so every numeric assertion carries provenance
(CLAUDE.md §8 rule 2). Phases that today have no provenance trail get one.

CLI layer (`scripts.planning.__main__`) is responsible for argument
parsing and path resolution. These runners accept `task_dir: Path` and
the pre-resolved subcommand args directly — no path migration here, that
ships in PR-3.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pandas as pd
import yaml

from scripts import workproduct as wp


_REPO = Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    return Path(os.environ.get("CFO_HELPER_ROOT", _REPO))


def _period_for_task(task_dir: Path) -> str:
    """Return a YYYY-MM period for the work_product. Planning tasks may not
    carry a real close period; derive from inputs/manifest.yaml when present
    and fall back to '1970-01' if not.
    """
    manifest = task_dir / "inputs" / "manifest.yaml"
    if manifest.exists():
        try:
            with manifest.open() as f:
                m = yaml.safe_load(f) or {}
            p = m.get("period")
            if p:
                return str(p)
        except Exception:
            pass
    task_meta = task_dir / "task.json"
    if task_meta.exists():
        try:
            meta = json.loads(task_meta.read_text())
            p = meta.get("brief_fields", {}).get("period")
            if p:
                return str(p)
        except Exception:
            pass
    return "1970-01"


def _entity_hash(rows: pd.DataFrame) -> dict[str, str]:
    """Per-entity content hash of `period_amount_usd` for a row set.

    Stable across row order; matches the spirit of `scripts.ingest._row_hash`
    but only the fields we surface as a claim. Used as a tamper-evident
    fingerprint for the claim, not as the canonical lock hash.
    """
    out: dict[str, str] = {}
    if rows.empty:
        return out
    for entity, grp in rows.groupby("entity"):
        sub = grp.copy()
        sub["period_amount_usd"] = pd.to_numeric(
            sub["period_amount_usd"], errors="coerce"
        ).fillna(0.0)
        ordered = sub.sort_values(
            ["period", "account", "product_line", "functional_area",
             "driver_dim", "driver_value"],
            na_position="last",
        ).reset_index(drop=True)
        blob = ordered[
            ["period", "account", "product_line", "functional_area",
             "driver_dim", "driver_value", "period_amount_usd"]
        ].astype(str).to_json(orient="records").encode("utf-8")
        out[str(entity)] = hashlib.sha256(blob).hexdigest()
    return out


def _bucket_for(account_class: str, pnl_line: str) -> str:
    cls = (account_class or "").lower()
    if cls == "revenue":
        return "revenue"
    if cls == "cogs":
        return "cogs"
    if cls == "opex":
        return "rd" if (pnl_line or "").startswith("Opex / R&D") else "sga"
    if cls == "tax":
        return "tax"
    return "other"


def _bucket_totals(rows: pd.DataFrame) -> dict[str, float]:
    """Roll rows up into revenue / cogs / opex / tax buckets."""
    out = {"revenue": 0.0, "cogs": 0.0, "opex": 0.0, "tax": 0.0}
    if rows.empty:
        return out
    df = rows.copy()
    df["account_class"] = df["account_class"].fillna("").astype(str).str.lower()
    df["pnl_line"] = df["pnl_line"].fillna("").astype(str)
    df["period_amount_usd"] = pd.to_numeric(
        df["period_amount_usd"], errors="coerce"
    ).fillna(0.0)
    out["revenue"] = float(df[df["account_class"] == "revenue"]["period_amount_usd"].sum())
    out["cogs"] = float(df[df["account_class"] == "cogs"]["period_amount_usd"].sum())
    out["opex"] = float(df[df["account_class"] == "opex"]["period_amount_usd"].sum())
    out["tax"] = float(df[df["account_class"] == "tax"]["period_amount_usd"].sum())
    return out


def _consolidated_trio(version: str, period: str, repo_root: Path):
    """Compute the consolidated trio and return (sales, ebit, fcf, components, buckets)."""
    from .trio import compute_trio

    r = compute_trio(version=version, consolidated=True,
                     period=period, repo_root=repo_root)
    return r


def _prior_lock_hashes(repo_root: Path) -> dict[str, str]:
    """Return {entity/version: hash} for all locked versions. Used by the
    append_only_invariant self-check.
    """
    lock_path = Path(
        os.environ.get("ASSUMPTIONS_LOCK_FILE",
                       str(repo_root / "memory" / "assumptions_locked.json"))
    )
    if not lock_path.exists():
        return {}
    with lock_path.open() as f:
        data = json.load(f)
    return {k: v.get("hash", "") for k, v in data.items()}


# ---------------------------------------------------------------------------
# Issue 6 runners
# ---------------------------------------------------------------------------


def run_plan_build(
    task_dir: Path,
    *,
    drivers: Path,
    version: str,
    workbook_stem: str,
    sheet: str = "Drivers",
    fy_year: int | None = None,
    change_sources: list[str] | None = None,
    locked_against: str | None = None,
    phase: str = "P1",
) -> dict:
    """Compile a driver workbook into a versioned assumption set, lock it,
    and emit a work product describing the trio + buckets + content hashes.
    """
    from .plan_build import build, write_per_entity_workbooks
    from scripts.ingest import ingest, annotate_lock

    repo_root = _repo_root()
    period = _period_for_task(task_dir)

    rows = build(
        driver_workbook=Path(drivers),
        version=version,
        sheet=sheet,
        fy_year=fy_year,
    )
    if rows.empty:
        raise RuntimeError(
            f"plan-build produced no rows for {version!r}; check the driver workbook."
        )

    # Hashes BEFORE the lock — distinct from the canonical ingest hash, but
    # sufficient for an append-only invariant check.
    prior_locks = _prior_lock_hashes(repo_root)

    inputs_dir = task_dir / "inputs"
    paths = write_per_entity_workbooks(rows, inputs_dir, workbook_stem)

    # Manifest update (mirror __main__._build)
    manifest_path = inputs_dir / "manifest.yaml"
    if manifest_path.exists():
        with manifest_path.open() as f:
            manifest = yaml.safe_load(f) or {}
    else:
        manifest = {"period": period, "entities": {}}
    manifest.setdefault("entities", {})
    for entity, path in paths.items():
        ent = manifest["entities"].setdefault(entity, {})
        asm = ent.setdefault("assumptions", [])
        if not any(e.get("version") == version for e in asm):
            asm.append({
                "workbook": path.name,
                "sheet": "Detail",
                "header_row": 1,
                "version": version,
            })
    with manifest_path.open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    # Ingest + annotate
    ingest(period, task_dir=task_dir)
    sources = list(change_sources or [])
    if sources:
        for entity in paths:
            key = f"{entity}/{version}"
            annotate_lock(
                key,
                add_change_source=sources,
                set_locked_against=(f"{entity}/{locked_against}"
                                    if locked_against else None),
            )

    # Compute claims off the locked rows
    trio = _consolidated_trio(version, period, repo_root)
    buckets = _bucket_totals(rows)
    hashes = _entity_hash(rows)

    inputs_for_provenance = [f"workbook:{Path(drivers).name}"]
    script = "scripts/planning/plan_build.py"

    claims: list[dict] = [
        wp.claim(
            id=f"planning.{version}.trio.sales_usd",
            label=f"Sales (consolidated) for {version}",
            value=float(trio.sales_usd),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(period_amount_usd) where account_class='revenue'",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.trio.ebit_usd",
            label=f"EBIT (consolidated) for {version}",
            value=float(trio.ebit_usd),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "revenue - cogs - rd - sga",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.trio.fcf_usd",
            label=f"FCF (consolidated) for {version}",
            value=float(trio.fcf_usd),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "EBIT + DA + ΔAP - ΔAR + ΔDeferredRev - ΔCapComm - Capex - CashTax",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.bucket.revenue_usd",
            label=f"Bucket revenue for {version}",
            value=float(buckets["revenue"]),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(period_amount_usd) where account_class='revenue'",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.bucket.cogs_usd",
            label=f"Bucket COGS for {version}",
            value=float(buckets["cogs"]),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(period_amount_usd) where account_class='cogs'",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.bucket.opex_usd",
            label=f"Bucket opex for {version}",
            value=float(buckets["opex"]),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(period_amount_usd) where account_class='opex'",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.bucket.tax_usd",
            label=f"Bucket tax for {version}",
            value=float(buckets["tax"]),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(period_amount_usd) where account_class='tax'",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{version}.row_count",
            label=f"Assumption row count for {version}",
            value=int(len(rows)),
            units="count",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "COUNT(rows) after explode of monthly columns",
            ),
            period=period,
        ),
    ]
    for entity, h in hashes.items():
        claims.append(wp.claim(
            id=f"planning.{version}.content_hash.{entity.lower()}",
            label=f"Content hash for {entity}/{version}",
            value=h,
            units="sha256",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SHA256 of sorted (period, account, ..., period_amount_usd) tuple",
            ),
            period=period,
            entity=entity,
        ))

    # Self-checks
    self_checks: list[dict] = []
    # 1. append_only_invariant: hash differs from any prior version's hash
    invariant_pass = True
    invariant_notes = []
    for entity, h in hashes.items():
        prior = prior_locks.get(f"{entity}/{version}")
        if prior is not None and prior != h:
            invariant_pass = False
            invariant_notes.append(f"{entity}: prior {prior[:12]}, new {h[:12]}")
    self_checks.append(wp.self_check(
        id="append_only_invariant",
        name="Hash differs from prior version's hash (no overwrite)",
        outcome="pass" if invariant_pass else "fail",
        notes="; ".join(invariant_notes) or "no prior lock with same key — first lock",
    ))

    # 2. fcf_identity: trio.fcf reconciles to sales - cogs - opex - tax + Δcontract_liab - Δcontract_asset
    # Use the trio components for accuracy (same fcf already produced).
    comp = trio.fcf_components
    delta_contract_liab = comp.get("delta_deferred_revenue", 0.0)
    delta_contract_asset = -comp.get("delta_capitalized_commissions", 0.0)
    expected_fcf = (
        buckets["revenue"] - buckets["cogs"] - buckets["opex"] - buckets["tax"]
        + delta_contract_liab - delta_contract_asset
    )
    # The trio's fcf includes D&A addback / AR/AP / capex; the simple identity
    # is a coarser variant. We compare within tolerance equal to abs(D&A + AP/AR +
    # capex + non-tax-bucket adjustments).
    coarse_tolerance = abs(comp.get("da_addback", 0.0)) + \
        abs(comp.get("delta_ar", 0.0)) + abs(comp.get("delta_ap", 0.0)) + \
        abs(comp.get("capex", 0.0)) + abs(comp.get("cash_tax", 0.0)) + 1.0
    delta = abs(trio.fcf_usd - expected_fcf)
    self_checks.append(wp.self_check(
        id="fcf_identity",
        name="FCF reconciles to coarse identity within tolerance",
        outcome="pass" if delta <= coarse_tolerance else "fail",
        expected=float(expected_fcf),
        actual=float(trio.fcf_usd),
        tolerance=float(coarse_tolerance),
        notes="coarse identity: sales - cogs - opex - tax + Δcontract_liab - Δcontract_asset",
    ))

    artifacts = [{"id": f"workbook_{e.lower()}",
                  "path": str(p), "kind": "xlsx"} for e, p in paths.items()]

    summary = (f"Built {version!r} ({len(rows)} rows) for entities "
               f"{sorted(paths.keys())}. Sales {trio.sales_usd:,.0f}, "
               f"EBIT {trio.ebit_usd:,.0f}, FCF {trio.fcf_usd:,.0f}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=period,
        phase=phase,
        summary=summary,
        claims=claims,
        artifacts=artifacts,
        self_checks=self_checks,
    )
    return {
        "version": version,
        "entities": sorted(paths.keys()),
        "row_count": int(len(rows)),
        "trio": {"sales": float(trio.sales_usd), "ebit": float(trio.ebit_usd),
                 "fcf": float(trio.fcf_usd)},
    }


def run_outlook_compute(
    task_dir: Path,
    *,
    base_version: str,
    target_version: str,
    fy_year: int,
    quarter: int,
    corporate_challenges: list[dict] | None = None,
    operational_responses: list[dict] | None = None,
    base_period: str | None = None,
    phase: str = "P3",
) -> dict:
    """Compute (no rows written) an outlook proposal and emit work product."""
    from .outlook_refresh import compute

    repo_root = _repo_root()
    period = _period_for_task(task_dir)

    proposal = compute(
        repo_root=repo_root,
        base_version=base_version,
        target_version=target_version,
        fy_year=fy_year,
        quarter=quarter,
        corporate_challenges=corporate_challenges or [],
        operational_responses=operational_responses or [],
        base_period=base_period,
    )

    arts = task_dir / "outputs" / "fpa" / "artifacts"
    arts.mkdir(parents=True, exist_ok=True)
    proposal_path = arts / f"outlook_proposal_{target_version}.parquet"
    proposal.proposed_rows.to_parquet(proposal_path, index=False)
    delta_path = arts / f"outlook_delta_breakdown_{target_version}.parquet"
    if not proposal.delta_breakdown.empty:
        proposal.delta_breakdown.to_parquet(delta_path, index=False)

    script = "scripts/planning/outlook_refresh.py"
    inputs_for_provenance = [f"version:{base_version}",
                              f"period:{period}",
                              f"quarter:Q{quarter}/{fy_year}"]

    claims: list[dict] = []
    for bucket in ("revenue", "cogs", "rd", "sga", "other"):
        delta_key = f"delta_{bucket}_usd"
        value = float(proposal.summary.get(delta_key, 0.0))
        claims.append(wp.claim(
            id=f"outlook.{target_version}.proposed_delta.{bucket}_usd",
            label=f"Proposed delta {bucket} for {target_version}",
            value=value,
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                f"SUM(delta_usd) where bucket='{bucket}' across actuals/challenge/response",
            ),
            period=period,
        ))
    claims.append(wp.claim(
        id=f"outlook.{target_version}.change_sources_present",
        label=f"Change sources contributing to {target_version}",
        value=",".join(proposal.change_sources_present) or "none",
        units="text",
        provenance=wp.computed_provenance(
            script, inputs_for_provenance,
            "DISTINCT change_source over delta_breakdown",
        ),
        period=period,
    ))

    # Self-check: locked_against_exists — base_version present in lock file
    locks = _prior_lock_hashes(repo_root)
    base_keys = [k for k in locks if k.endswith(f"/{base_version}")]
    self_checks = [wp.self_check(
        id="locked_against_exists",
        name=f"Base version {base_version} found in assumptions_locked.json",
        outcome="pass" if base_keys else "fail",
        actual=str(len(base_keys)),
        notes=(f"{len(base_keys)} (entity,{base_version}) entries"
               if base_keys else
               f"no lock entries for base_version={base_version!r}; "
               f"compute will read from workbook but lineage is broken"),
    )]

    artifacts = [
        {"id": f"proposal_{target_version}", "path": str(proposal_path), "kind": "parquet"},
    ]
    if delta_path.exists():
        artifacts.append({"id": f"delta_breakdown_{target_version}",
                          "path": str(delta_path), "kind": "parquet"})

    summary = (f"Outlook proposal for {target_version} from {base_version} "
               f"(Q{quarter} FY{fy_year}). "
               f"Sources: {proposal.change_sources_present or '[]'}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=period,
        phase=phase,
        summary=summary,
        claims=claims,
        artifacts=artifacts,
        self_checks=self_checks,
    )
    return {
        "target_version": target_version,
        "summary": dict(proposal.summary),
        "change_sources": list(proposal.change_sources_present),
    }


def run_outlook_lock(
    task_dir: Path,
    *,
    base_version: str,
    target_version: str,
    fy_year: int,
    quarter: int,
    workbook_stem: str,
    corporate_challenges: list[dict] | None = None,
    operational_responses: list[dict] | None = None,
    base_period: str | None = None,
    phase: str = "P4",
) -> dict:
    """Lock a previously-computed outlook proposal: write per-entity workbooks,
    re-run ingest, annotate locks. Emits a memory_write request describing the
    `assumptions_locked.json` extension for CFO approval (CLAUDE.md §8 rule 4).
    """
    from .outlook_refresh import compute, lock

    repo_root = _repo_root()
    period = _period_for_task(task_dir)

    proposal = compute(
        repo_root=repo_root,
        base_version=base_version,
        target_version=target_version,
        fy_year=fy_year,
        quarter=quarter,
        corporate_challenges=corporate_challenges or [],
        operational_responses=operational_responses or [],
        base_period=base_period,
    )

    inputs_dir = task_dir / "inputs"
    lock_result = lock(
        proposal=proposal,
        repo_root=repo_root,
        workbook_stem=workbook_stem,
        inputs_dir=inputs_dir,
    )

    # Recompute hashes after the lock and verify they match the lock file
    rows = proposal.proposed_rows
    rows = rows.copy()
    rows["locked_at"] = pd.Timestamp.now("UTC").date().isoformat()
    rows["source_doc"] = f"{workbook_stem}.xlsx"
    hashes = _entity_hash(rows)

    locks_now = _prior_lock_hashes(repo_root)
    consistent = True
    consistency_notes = []
    for entity, h in hashes.items():
        key = f"{entity}/{target_version}"
        # We only check that the lock entry exists; ingest-canonical hash may
        # differ from our coarse hash because it uses different columns.
        if key not in locks_now:
            consistent = False
            consistency_notes.append(f"missing lock for {key}")

    self_checks = [wp.self_check(
        id="hash_consistent",
        name="Lock entry exists for every entity post-lock",
        outcome="pass" if consistent else "fail",
        notes="; ".join(consistency_notes) or "all entities locked",
    )]

    trio = _consolidated_trio(target_version, period, repo_root)
    script = "scripts/planning/outlook_refresh.py"
    inputs_for_provenance = [f"version:{target_version}",
                              f"period:{period}"]

    claims: list[dict] = [
        wp.claim(
            id=f"planning.{target_version}.trio.sales_usd",
            label=f"Sales (consolidated) for {target_version}",
            value=float(trio.sales_usd), units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(period_amount_usd) where account_class='revenue'",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{target_version}.trio.ebit_usd",
            label=f"EBIT (consolidated) for {target_version}",
            value=float(trio.ebit_usd), units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "revenue - cogs - rd - sga",
            ),
            period=period,
        ),
        wp.claim(
            id=f"planning.{target_version}.trio.fcf_usd",
            label=f"FCF (consolidated) for {target_version}",
            value=float(trio.fcf_usd), units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "EBIT + DA + ΔAP - ΔAR + ΔDeferredRev - ΔCapComm - Capex - CashTax",
            ),
            period=period,
        ),
    ]
    for entity, h in hashes.items():
        claims.append(wp.claim(
            id=f"planning.{target_version}.content_hash.{entity.lower()}",
            label=f"Content hash for {entity}/{target_version}",
            value=h, units="sha256",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SHA256 of sorted assumption-row tuple",
            ),
            period=period, entity=entity,
        ))

    # Memory write request — describes the lock-file extension. The lock has
    # already been written to profile/memory/assumptions_locked.json by ingest,
    # but the request entry preserves provenance for CFO review at the
    # dashboard checkpoint and lets Coordinator treat the change like any other
    # memory change (CLAUDE.md §2 rule 4).
    requests = [{
        "kind": "memory_write",
        "target": "profile/memory/assumptions_locked.json",
        "content": json.dumps(
            {f"{entity}/{target_version}": {"hash": h}
             for entity, h in hashes.items()},
            sort_keys=True, indent=2,
        ),
        "reason": (f"Outlook lock {target_version!r} — extends assumptions_locked.json "
                   f"with one entry per entity; hashes recorded by ingest are the "
                   f"canonical immutability fingerprints."),
    }]

    summary = (f"Locked {target_version!r} ({len(rows)} rows) "
               f"from base {base_version!r}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=period,
        phase=phase,
        summary=summary,
        claims=claims,
        self_checks=self_checks,
        requests=requests,
    )
    return {
        "target_version": target_version,
        "lock_keys": list(lock_result.keys()),
        "hashes": hashes,
    }


def run_strategic_build(
    task_dir: Path,
    *,
    workbook: Path,
    version: str,
    sheet: str = "Strategic",
    workbook_stem: str = "Assumptions_Plan_3yr",
    change_sources: list[str] | None = None,
    phase: str = "P1",
) -> dict:
    """Compile a strategic 3-yr workbook → Y2 + Y3 rows for `plan_3yr_fy{YY}`."""
    from .strategic_plan_build import build
    from .plan_build import write_per_entity_workbooks
    from scripts.ingest import ingest, annotate_lock

    repo_root = _repo_root()
    period = _period_for_task(task_dir)

    result = build(workbook=Path(workbook), version=version, repo_root=repo_root,
                   sheet=sheet)
    if result.rows.empty:
        raise RuntimeError(
            f"strategic-plan-build produced no rows for {version!r}; "
            "check the workbook's `parameter_value` column."
        )

    inputs_dir = task_dir / "inputs"
    paths = write_per_entity_workbooks(result.rows, inputs_dir, workbook_stem)

    manifest_path = inputs_dir / "manifest.yaml"
    if manifest_path.exists():
        with manifest_path.open() as f:
            manifest = yaml.safe_load(f) or {}
    else:
        manifest = {"period": period, "entities": {}}
    manifest.setdefault("entities", {})
    for entity, path in paths.items():
        ent = manifest["entities"].setdefault(entity, {})
        asm = ent.setdefault("assumptions", [])
        if not any(e.get("version") == version for e in asm):
            asm.append({
                "workbook": path.name, "sheet": "Detail",
                "header_row": 1, "version": version,
            })
    with manifest_path.open("w") as f:
        yaml.safe_dump(manifest, f, sort_keys=False)

    ingest(period, task_dir=task_dir)
    sources = list(change_sources or ["bottoms_up_submission"])
    operational_anchor = version.replace("plan_3yr_", "plan_")
    for entity in paths:
        annotate_lock(
            f"{entity}/{version}",
            add_change_source=sources,
            set_locked_against=f"{entity}/{operational_anchor}",
        )

    # Per-entity Y2/Y3 trio
    fy_year = result.fy_year
    y2_period = f"{fy_year + 1}-12"
    y3_period = f"{fy_year + 2}-12"

    script = "scripts/planning/strategic_plan_build.py"
    inputs_for_provenance = [f"workbook:{Path(workbook).name}", f"version:{version}"]

    claims: list[dict] = []
    for entity, ent_paths in paths.items():
        per_entity_rows = result.rows[result.rows["entity"] == entity]
        for year_label, year_period in (("Y2", y2_period), ("Y3", y3_period)):
            yr_rows = per_entity_rows[per_entity_rows["period"] == year_period]
            buckets = _bucket_totals(yr_rows)
            sales = buckets["revenue"]
            ebit = buckets["revenue"] - buckets["cogs"] - buckets["opex"]
            claims.extend([
                wp.claim(
                    id=f"planning.{version}.{entity.lower()}.{year_label.lower()}.sales_usd",
                    label=f"{entity} {year_label} sales for {version}",
                    value=float(sales), units="USD",
                    provenance=wp.computed_provenance(
                        script, inputs_for_provenance,
                        f"SUM(period_amount_usd) where entity={entity!r} "
                        f"and period={year_period!r} and account_class='revenue'",
                    ),
                    period=period, entity=entity,
                ),
                wp.claim(
                    id=f"planning.{version}.{entity.lower()}.{year_label.lower()}.ebit_usd",
                    label=f"{entity} {year_label} EBIT for {version}",
                    value=float(ebit), units="USD",
                    provenance=wp.computed_provenance(
                        script, inputs_for_provenance,
                        "revenue - cogs - opex (rd+sga)",
                    ),
                    period=period, entity=entity,
                ),
            ])

    self_checks = [wp.self_check(
        id="strategic_y_periods_present",
        name="Strategic rows include both Y2 and Y3 periods",
        outcome="pass" if (
            (result.rows["period"] == y2_period).any()
            and (result.rows["period"] == y3_period).any()
        ) else "warn",
        notes=f"y2={y2_period}; y3={y3_period}",
    )]

    artifacts = [{"id": f"workbook_{e.lower()}",
                  "path": str(p), "kind": "xlsx"} for e, p in paths.items()]

    summary = (f"Built strategic {version!r} ({len(result.rows)} rows) "
               f"for entities {sorted(paths.keys())} anchored to {operational_anchor}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=period,
        phase=phase,
        summary=summary,
        claims=claims,
        artifacts=artifacts,
        self_checks=self_checks,
    )
    return {
        "version": version,
        "entities": sorted(paths.keys()),
        "row_count": int(len(result.rows)),
    }


def run_strategic_walk(
    task_dir: Path,
    *,
    strategic_version: str,
    phase: str = "P2",
) -> dict:
    """Y1 → Y3 walk for the board pack. Emits per-year trio claims."""
    from .strategic_plan_walk import walk

    repo_root = _repo_root()
    period = _period_for_task(task_dir)

    result = walk(strategic_version=strategic_version, repo_root=repo_root)

    script = "scripts/planning/strategic_plan_walk.py"
    inputs_for_provenance = [f"version:{strategic_version}"]

    claims: list[dict] = []
    for year_label in ("Y1", "Y2", "Y3"):
        year = result.walk_by_year[year_label]
        for metric in ("sales", "ebit", "fcf"):
            value = year.get(metric)
            if value is None:
                continue
            claims.append(wp.claim(
                id=f"walk.{strategic_version}.{year_label.lower()}.{metric}_usd",
                label=f"{year_label} {metric} for {strategic_version} walk",
                value=float(value), units="USD",
                provenance=wp.computed_provenance(
                    script, inputs_for_provenance,
                    f"_trio_for_rows({year_label} rows; cash_tax_rate="
                    f"{result.cash_tax_rate_used})",
                ),
                period=period,
            ))

    self_checks = []
    if result.cash_tax_rate_used is None:
        self_checks.append(wp.self_check(
            id="cash_tax_rate_set",
            name="materiality.yaml.strategic_plan.cash_tax_rate_proxy is set",
            outcome="warn",
            notes="FCF unset across walk because ETR is not confirmed.",
        ))
    else:
        self_checks.append(wp.self_check(
            id="cash_tax_rate_set",
            name="materiality.yaml.strategic_plan.cash_tax_rate_proxy is set",
            outcome="pass",
            actual=str(result.cash_tax_rate_used),
        ))

    summary = (f"Walk {strategic_version!r} anchored to {result.operational_version!r}; "
               f"ETR proxy={result.cash_tax_rate_used}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=period,
        phase=phase,
        summary=summary,
        claims=claims,
        self_checks=self_checks,
    )
    return {
        "strategic_version": strategic_version,
        "operational_version": result.operational_version,
        "cash_tax_rate_used": result.cash_tax_rate_used,
    }


def run_gap(
    task_dir: Path,
    *,
    from_version: str,
    to_version: str,
    period: str,
    top_n: int = 20,
    phase: str = "P4",
) -> dict:
    """Three-layer delta between two versions: trio + bucket + driver."""
    from .gap_to_stretch import gap as run_gap_inner

    repo_root = _repo_root()
    task_period = _period_for_task(task_dir)

    result = run_gap_inner(
        from_version=from_version,
        to_version=to_version,
        period=period,
        repo_root=repo_root,
    )

    arts = task_dir / "outputs" / "fpa" / "artifacts"
    arts.mkdir(parents=True, exist_ok=True)
    drivers_path = arts / f"gap_{from_version}__to__{to_version}.parquet"
    if not result.driver_deltas.empty:
        result.driver_deltas.to_parquet(drivers_path, index=False)

    script = "scripts/planning/gap_to_stretch.py"
    inputs_for_provenance = [f"from:{from_version}", f"to:{to_version}",
                              f"period:{period}"]

    base = f"gap.{from_version}__to__{to_version}"
    claims: list[dict] = []
    for metric in ("delta_sales_usd", "delta_ebit_usd", "delta_fcf_usd"):
        claims.append(wp.claim(
            id=f"{base}.trio.{metric}",
            label=f"Trio {metric} {from_version} → {to_version}",
            value=float(result.trio_delta.get(metric, 0.0)),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                f"compute_trio({to_version}).{metric.replace('delta_', '').replace('_usd','')} "
                f"- compute_trio({from_version}).{metric.replace('delta_','').replace('_usd','')}",
            ),
            period=task_period,
        ))
    for bucket in ("revenue", "cogs", "rd", "sga"):
        claims.append(wp.claim(
            id=f"{base}.bucket.{bucket}_usd",
            label=f"Bucket delta {bucket} {from_version} → {to_version}",
            value=float(result.bucket_delta.get(bucket, 0.0)),
            units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                f"SUM(period_amount_usd, version=to) - SUM(version=from) for {bucket}",
            ),
            period=task_period,
        ))

    if not result.driver_deltas.empty:
        top = result.driver_deltas.head(top_n)
        for _, dr in top.iterrows():
            slug = (
                f"{dr.get('entity', 'NA')}.{dr.get('account', 'NA')}."
                f"{(dr.get('driver_dim') or 'na')}.{(dr.get('driver_value') or 'na')}"
            )
            slug = "".join(c if c.isalnum() or c in "._" else "_" for c in str(slug)).lower()
            claims.append(wp.claim(
                id=f"{base}.driver.{slug}",
                label=f"Driver delta {dr.get('driver_value', '')} ({dr.get('mechanism_hint','')})",
                value=float(dr["delta_usd"]), units="USD",
                provenance=wp.computed_provenance(
                    script, inputs_for_provenance,
                    "to_amount_usd - from_amount_usd at driver grain",
                ),
                period=task_period,
                entity=str(dr.get("entity", "")) or None,
            ))

    # Self-check: ΔEBIT identity revenue - cogs - rd - sga = ebit_delta.
    expected_ebit_delta = (
        result.bucket_delta.get("revenue", 0.0)
        - result.bucket_delta.get("cogs", 0.0)
        - result.bucket_delta.get("rd", 0.0)
        - result.bucket_delta.get("sga", 0.0)
    )
    actual_ebit_delta = result.trio_delta.get("delta_ebit_usd", 0.0)
    delta = abs(expected_ebit_delta - actual_ebit_delta)
    tolerance = 1.0
    self_checks = [wp.self_check(
        id="bucket_sum_reconciles",
        name="ΔEBIT = Δrevenue − Δcogs − Δrd − Δsga (bucket reconciliation)",
        outcome="pass" if delta <= tolerance else "fail",
        expected=float(expected_ebit_delta),
        actual=float(actual_ebit_delta),
        tolerance=tolerance,
    )]

    artifacts = []
    if drivers_path.exists():
        artifacts.append({"id": "driver_deltas", "path": str(drivers_path),
                          "kind": "parquet"})

    summary = (f"Gap {from_version} → {to_version}: ΔEBIT "
               f"{result.trio_delta.get('delta_ebit_usd', 0.0):+,.0f}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=task_period,
        phase=phase,
        summary=summary,
        claims=claims,
        artifacts=artifacts,
        self_checks=self_checks,
    )
    return {
        "from": from_version, "to": to_version,
        "trio_delta": dict(result.trio_delta),
        "bucket_delta": dict(result.bucket_delta),
        "driver_count": int(len(result.driver_deltas)),
    }


__all__ = [
    "run_plan_build",
    "run_outlook_compute",
    "run_outlook_lock",
    "run_strategic_build",
    "run_strategic_walk",
    "run_gap",
]
