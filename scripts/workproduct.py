"""
Helpers to emit and load work products with schema validation.

Every agent uses this module to write its `work_product.json`. Validation runs
on write — if the schema fails, the write fails. This is the single
choke-point that enforces the provenance contract.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def _atomic_write_json(path: Path, doc: dict) -> None:
    """Write JSON atomically: dump to a sibling tmp file, fsync, rename over target.

    If the write is interrupted (process kill, exception), the target file is
    left in its prior state. Any tmp file is cleaned up on exception.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _validate_agent_name(agent: str) -> None:
    if not _AGENT_NAME_RE.match(agent):
        raise ValueError(
            f"Invalid agent name {agent!r}: must match {_AGENT_NAME_RE.pattern}"
        )

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WP_SCHEMA_PATH = _REPO_ROOT / "agents" / "work_product.schema.json"
_RV_SCHEMA_PATH = _REPO_ROOT / "agents" / "review_findings.schema.json"


def _load_schema(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_work_product(
    workspace: Path,
    agent: str,
    period: str,
    phase: str,
    *,
    summary: str = "",
    claims: list[dict] | None = None,
    artifacts: list[dict] | None = None,
    self_checks: list[dict] | None = None,
    open_questions: list[dict] | None = None,
    requests: list[dict] | None = None,
    status: str = "ready_for_checkpoint",
) -> Path:
    """Write outputs/<agent>/work_product.json after schema validation."""
    _validate_agent_name(agent)
    doc = {
        "agent": agent,
        "period": period,
        "phase": phase,
        "produced_at": now(),
        "status": status,
        "summary": summary,
        "claims": claims or [],
        "artifacts": artifacts or [],
        "self_checks": self_checks or [],
        "open_questions": open_questions or [],
        "requests": requests or [],
    }
    schema = _load_schema(_WP_SCHEMA_PATH)
    jsonschema.validate(doc, schema)
    out_dir = workspace / "outputs" / agent
    out = out_dir / "work_product.json"
    _atomic_write_json(out, doc)
    return out


def load_work_product(workspace: Path, agent: str) -> dict:
    _validate_agent_name(agent)
    path = workspace / "outputs" / agent / "work_product.json"
    with path.open() as f:
        doc = json.load(f)
    schema = _load_schema(_WP_SCHEMA_PATH)
    try:
        jsonschema.validate(doc, schema)
    except jsonschema.ValidationError as e:
        # Pre-2026-05 work_products allowed `null` claim.value; the schema
        # tightened to reject null. Surface a migration-actionable error
        # instead of a generic validation failure.
        for c in doc.get("claims", []):
            if c.get("value") is None:
                raise ValueError(
                    f"work_product at {path} has claim {c.get('id')!r} with "
                    f"value=null, which is no longer permitted by the schema. "
                    f"Re-run the producing phase to regenerate, or hand-edit "
                    f"the value to a number/string."
                ) from e
        raise
    return doc


def claim(
    id: str,
    label: str,
    value,
    units: str,
    provenance: dict,
    *,
    period: str | None = None,
    entity: str | None = None,
    confidence: str = "high",
    notes: str = "",
) -> dict:
    """Build a claim dict in the schema's expected shape."""
    c = {
        "id": id,
        "label": label,
        "value": value,
        "units": units,
        "provenance": provenance,
        "confidence": confidence,
    }
    if period:
        c["period"] = period
    if entity:
        c["entity"] = entity
    if notes:
        c["notes"] = notes
    return c


def computed_provenance(script: str, inputs: list[str], formula: str) -> dict:
    return {
        "kind": "computed",
        "script": script,
        "inputs": inputs,
        "formula": formula,
        "ran_at": now(),
    }


def source_cell_provenance(workbook: str, sheet: str, range: str | None = None) -> dict:
    p = {"kind": "source_cell", "workbook": workbook, "sheet": sheet}
    if range:
        p["range"] = range
    return p


def connector_provenance(connector: str, call: str) -> dict:
    return {"kind": "connector", "connector": connector, "call": call, "as_of": now()}


def self_check(id: str, name: str, outcome: str, *,
               expected=None, actual=None, tolerance=None,
               evidence_path: str = "", notes: str = "") -> dict:
    sc = {"id": id, "name": name, "outcome": outcome}
    if expected is not None:
        sc["expected"] = expected
    if actual is not None:
        sc["actual"] = actual
    if tolerance is not None:
        sc["tolerance"] = tolerance
    if evidence_path:
        sc["evidence_path"] = evidence_path
    if notes:
        sc["notes"] = notes
    return sc


# --- Reviewer findings --------------------------------------------------------

def write_findings(
    workspace: Path,
    period: str,
    *,
    sign_off: str,
    summary: str,
    findings: list[dict],
    independent_recomputations: list[dict],
    provenance_audit: dict | None = None,
) -> Path:
    doc = {
        "agent": "reviewer",
        "period": period,
        "produced_at": now(),
        "sign_off": sign_off,
        "summary": summary,
        "findings": findings,
        "independent_recomputations": independent_recomputations,
    }
    if provenance_audit is not None:
        doc["provenance_audit"] = provenance_audit
    jsonschema.validate(doc, _load_schema(_RV_SCHEMA_PATH))
    out = workspace / "review" / "findings.json"
    _atomic_write_json(out, doc)
    return out


def load_findings(workspace: Path) -> dict:
    path = workspace / "review" / "findings.json"
    with path.open() as f:
        doc = json.load(f)
    jsonschema.validate(doc, _load_schema(_RV_SCHEMA_PATH))
    return doc
