"""CLI entry point for chart rendering.

Usage:
    python -m scripts.charts --spec <path.json> --output <path.png>

Spec JSON shape:
    {"kind": "pl_bridge|bbrr_waterfall|arr_snapshot|top10_movement|...",
     "title": "...", "claim_id": "...", "format": "png",
     "data": { ... kind-specific kwargs ... } }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.charts import render_chart


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a cfo-helper chart from a spec JSON.")
    parser.add_argument("--spec", type=Path, required=True, help="Path to spec JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output image path")
    args = parser.parse_args(argv)

    spec = json.loads(args.spec.read_text())
    out = render_chart(spec, args.output)
    print(json.dumps({"output": str(out), "exists": out.exists(),
                       "size_bytes": out.stat().st_size}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
