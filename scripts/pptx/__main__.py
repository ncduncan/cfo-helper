"""CLI entry point for the PPTX builders.

Usage:
    python -m scripts.pptx mor --spec <path.json> --output <path.pptx>
    python -m scripts.pptx parent_reportout --spec <path.json> --output <path.pptx>
    python -m scripts.pptx bsr --spec <path.json> --output <path.pptx>

The spec JSON must conform to the dataclass shape of the corresponding
Payload class (MORPayload / ParentReportoutPayload / BSRPayload). Path
fields (chart images, etc.) are taken as-is — the spec is responsible
for ensuring chart artifacts already exist on disk.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from scripts.pptx.bsr import BSRPayload, build_bsr_deck
from scripts.pptx.mor import MORPayload, build_mor_deck
from scripts.pptx.parent_reportout import (
    ParentReportoutPayload,
    build_parent_reportout_deck,
)

_BUILDERS = {
    "mor": (MORPayload, build_mor_deck),
    "parent_reportout": (ParentReportoutPayload, build_parent_reportout_deck),
    "bsr": (BSRPayload, build_bsr_deck),
}

_PATH_FIELDS = {
    "arr_chart_path", "bbrr_chart_path", "top10_chart_path",
    "deferred_rev_chart_path", "kpi_dashboard_path",
}


def _coerce(payload_cls, data: dict) -> Any:
    """Filter unknown keys; coerce path-like fields to Path objects."""
    field_names = {f.name for f in fields(payload_cls)}
    cleaned = {k: v for k, v in data.items() if k in field_names}
    for name in _PATH_FIELDS:
        if name in cleaned and cleaned[name]:
            cleaned[name] = Path(cleaned[name])
    return payload_cls(**cleaned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a cfo-helper PowerPoint deck from a spec JSON.")
    parser.add_argument("kind", choices=list(_BUILDERS), help="Deck type")
    parser.add_argument("--spec", type=Path, required=True, help="Path to spec JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output .pptx path")
    args = parser.parse_args(argv)

    payload_cls, builder = _BUILDERS[args.kind]
    data = json.loads(args.spec.read_text())
    payload = _coerce(payload_cls, data)
    out = builder(payload, args.output)
    print(json.dumps({"output": str(out), "exists": out.exists(),
                       "size_bytes": out.stat().st_size}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
