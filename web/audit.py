"""Deliverable audit helpers — claim-id discipline, findings, memory writes.

Invoked when a step is completed to enforce CLAUDE.md §8 rules 2, 4, and 9
end-to-end:

- Rule 2 — no number without provenance. AI deliverables for the
  controller/fpa/commercial/reporting/reviewer roles must include a
  ``work_product.json`` whose ``claims[]`` is non-empty and every claim has
  a ``provenance`` block. ``audit_claim_ids`` enforces this.
- Rule 4 — memory writes require approval. ``extract_memory_writes`` pulls
  any ``requests[].kind == "memory_write"`` entries; the route handler
  stages each one into ``profile/db/memory_proposals.json`` for the CFO to
  approve before the task can complete.
- Reviewer findings — ``extract_findings`` reads ``findings.json`` when a
  Reviewer-role step writes one; the route persists ``findings_ref`` on
  the step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Roles whose deliverables must carry claim-id provenance.
NUMERIC_ROLES = {"controller", "fpa", "commercial", "reporting", "reviewer", "tps_lean"}


def _find_work_product(deliverable_paths: list[str], repo_root: Path) -> Path | None:
    for rel in deliverable_paths:
        if rel.endswith("work_product.json"):
            p = (repo_root / rel).resolve()
            try:
                p.relative_to(repo_root.resolve())
            except ValueError:
                continue
            if p.exists():
                return p
    return None


def _find_findings(deliverable_paths: list[str], repo_root: Path) -> Path | None:
    for rel in deliverable_paths:
        if rel.endswith("findings.json"):
            p = (repo_root / rel).resolve()
            try:
                p.relative_to(repo_root.resolve())
            except ValueError:
                continue
            if p.exists():
                return p
    return None


def _find_kaizen_recommendations(
    deliverable_paths: list[str], repo_root: Path
) -> Path | None:
    for rel in deliverable_paths:
        if rel.endswith("kaizen_recommendations.json"):
            p = (repo_root / rel).resolve()
            try:
                p.relative_to(repo_root.resolve())
            except ValueError:
                continue
            if p.exists():
                return p
    return None


def audit_claim_ids(
    deliverable_paths: list[str],
    repo_root: Path,
    *,
    required: bool = True,
) -> dict[str, Any]:
    """Inspect deliverables for a ``work_product.json`` with valid claims.

    Returns ``{"ok": bool, "issues": [...]}``. If ``required=False`` (e.g.
    non-numeric roles), absence of a work_product.json is allowed.
    """
    wp_path = _find_work_product(deliverable_paths, repo_root)
    issues: list[str] = []
    if wp_path is None:
        if required:
            issues.append("missing work_product.json among deliverables")
        return {"ok": not issues, "issues": issues}

    try:
        wp = json.loads(wp_path.read_text())
    except json.JSONDecodeError as exc:
        return {"ok": False, "issues": [f"work_product.json is not valid JSON: {exc}"]}

    claims = wp.get("claims") or []
    if not claims:
        issues.append("work_product.json has empty claims[]")
    for i, c in enumerate(claims):
        if not c.get("id"):
            issues.append(f"claims[{i}] missing id")
        prov = c.get("provenance")
        if not prov:
            issues.append(f"claims[{i}] ({c.get('id') or '?'}) missing provenance")
        elif isinstance(prov, dict) and not prov:
            issues.append(
                f"claims[{i}] ({c.get('id') or '?'}) has empty provenance"
            )
    return {"ok": not issues, "issues": issues}


def extract_findings(
    deliverable_paths: list[str], repo_root: Path
) -> dict[str, Any] | None:
    """Return the parsed findings.json content if present, else None."""
    p = _find_findings(deliverable_paths, repo_root)
    if p is None:
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def extract_lean_recommendations(
    deliverable_paths: list[str], repo_root: Path
) -> dict[str, Any] | None:
    """Return the parsed kaizen_recommendations.json content if present, else None.

    Parallel to ``extract_findings`` — used by the task-completion route to
    surface TPS Lean recommendations on the dashboard via the
    ``lean_recommendations_ref`` field on the step instance.
    """
    p = _find_kaizen_recommendations(deliverable_paths, repo_root)
    if p is None:
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def extract_memory_writes(
    deliverable_paths: list[str], repo_root: Path
) -> list[dict[str, Any]]:
    """Pull ``requests[]`` entries with ``kind == "memory_write"``."""
    wp_path = _find_work_product(deliverable_paths, repo_root)
    if wp_path is None:
        return []
    try:
        wp = json.loads(wp_path.read_text())
    except json.JSONDecodeError:
        return []
    requests = wp.get("requests") or []
    return [r for r in requests if r.get("kind") == "memory_write"]
