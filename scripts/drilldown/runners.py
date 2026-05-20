"""Deterministic runner for the drilldown skill — emits a work_product
describing per-driver subledger decomposition with claim-id provenance.

Mirrors the pattern in scripts/planning/runners.py: existing computation
in scripts.drilldown.runner.drilldown is preserved; this wrapper produces
the work_product so every numeric carries provenance (CLAUDE.md §8 rule 2).
"""

from __future__ import annotations

import os
from pathlib import Path

from scripts import workproduct as wp
from scripts.drilldown.runner import drilldown as _drilldown


_REPO = Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    return Path(os.environ.get("CFO_HELPER_ROOT", _REPO))


def run_drilldown(
    task_dir: Path,
    *,
    period: str,
    entity: str,
    account: str,
    materiality: float | None = None,
    phase: str = "P2",
) -> dict:
    """Decompose one (entity, account) GL line into subledger drivers."""
    repo_root = _repo_root()

    result = _drilldown(
        period=period,
        entity=entity,
        account=str(account),
        repo_root=repo_root,
        tolerance_usd=materiality,
    )

    script = "scripts/drilldown/runner.py"
    base = f"drilldown.{entity.lower()}.{account}"
    inputs_for_provenance = [
        f"connector:gl({entity},{period})",
        f"account:{account}",
    ]

    claims: list[dict] = []
    self_checks: list[dict] = []

    if result["status"] != "ok":
        # Emit a single status claim; nothing to decompose. Still ships a
        # work_product so the pipeline keeps a provenance trail.
        claims.append(wp.claim(
            id=f"{base}.status",
            label=f"Drilldown status for {entity}/{account}",
            value=result["status"], units="text",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                f"dispatch decision: {result['reason']}",
            ),
            period=period, entity=entity,
        ))
        wp.write_work_product(
            task_dir, agent="fpa", period=period,
            phase=phase,
            summary=f"Drilldown {entity}/{account}: {result['status']} — {result['reason']}",
            claims=claims,
            self_checks=self_checks,
        )
        return result

    bridge = result["bridge"]
    actual = float(bridge["actual_usd"])
    sub_total = float(bridge["subledger_total"])
    reconciling = float(bridge["reconciling_usd"])

    claims.extend([
        wp.claim(
            id=f"{base}.gl_actual_usd",
            label=f"GL actual for {entity}/{account}",
            value=actual, units="USD",
            provenance=wp.connector_provenance(
                "excel.gl", f"get_gl(period={period!r}, entity={entity!r})"
            ),
            period=period, entity=entity,
        ),
        wp.claim(
            id=f"{base}.subledger_total_usd",
            label=f"Subledger sum for {entity}/{account}",
            value=sub_total, units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "SUM(amount_usd) across dispatched subledgers",
            ),
            period=period, entity=entity,
        ),
        wp.claim(
            id=f"{base}.reconciling_usd",
            label=f"GL − subledger reconciling delta for {entity}/{account}",
            value=reconciling, units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "gl_actual_usd - subledger_total",
            ),
            period=period, entity=entity,
        ),
    ])

    for name, total in bridge.get("subledger_totals", {}).items():
        claims.append(wp.claim(
            id=f"{base}.subledger.{name}_usd",
            label=f"{name} subledger total for {entity}/{account}",
            value=float(total), units="USD",
            provenance=wp.connector_provenance(
                f"subledger.{name}", f"get_subledger({name!r}, period={period!r}, entity={entity!r})",
            ),
            period=period, entity=entity,
        ))

    drivers = result.get("drivers", []) or []
    for i, dr in enumerate(drivers):
        amt = dr.get("amount_usd", dr.get("delta_usd"))
        if amt is None:
            continue
        slug = (
            f"{dr.get('driver_dim','na')}.{dr.get('driver_value','na')}"
        ).lower()
        slug = "".join(c if c.isalnum() or c in "._" else "_" for c in slug)
        claims.append(wp.claim(
            id=f"{base}.driver.{slug or f'd{i}'}",
            label=f"Driver decomposition: {dr.get('driver_value','')}",
            value=float(amt), units="USD",
            provenance=wp.computed_provenance(
                script, inputs_for_provenance,
                "subledger amount_usd at driver grain (or version delta)",
            ),
            period=period, entity=entity,
        ))

    tieout_pass = bool(bridge.get("tieout_pass"))
    self_checks.append(wp.self_check(
        id="subledger_tieout",
        name=f"Subledger sum reconciles to GL for {entity}/{account} within tolerance",
        outcome="pass" if tieout_pass else "fail",
        expected=actual,
        actual=sub_total,
        tolerance=float(bridge.get("tieout_tolerance_usd", 0.0)),
        notes="; ".join(bridge.get("notes", [])[:3]) if bridge.get("notes") else "",
    ))

    summary = (f"Drilldown {entity}/{account}: GL={actual:,.0f}, "
               f"subledger sum={sub_total:,.0f}, reconciling={reconciling:+,.0f}.")

    wp.write_work_product(
        task_dir, agent="fpa", period=period,
        phase="drilldown",
        summary=summary,
        claims=claims,
        self_checks=self_checks,
    )
    return result


__all__ = ["run_drilldown"]
