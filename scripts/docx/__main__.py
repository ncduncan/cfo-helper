"""CLI entry point for the DOCX builders.

Usage:
    python -m scripts.docx ceo_letter --spec <path.json> --output <path.docx>

Spec JSON conforms to CEOLetterPayload. Path fields (table_xlsx_path)
are coerced to Path objects.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from scripts.docx.ceo_letter import CEOLetterPayload, build_ceo_letter

_BUILDERS = {
    "ceo_letter": (CEOLetterPayload, build_ceo_letter),
}

_PATH_FIELDS = {"table_xlsx_path"}


def _coerce(payload_cls, data: dict) -> Any:
    field_names = {f.name for f in fields(payload_cls)}
    cleaned = {k: v for k, v in data.items() if k in field_names}
    for name in _PATH_FIELDS:
        if name in cleaned and cleaned[name]:
            cleaned[name] = Path(cleaned[name])
    return payload_cls(**cleaned)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a cfo-helper Word document from a spec JSON.")
    parser.add_argument("kind", choices=list(_BUILDERS), help="Doc type")
    parser.add_argument("--spec", type=Path, required=True, help="Path to spec JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output .docx path")
    args = parser.parse_args(argv)

    payload_cls, builder = _BUILDERS[args.kind]
    data = json.loads(args.spec.read_text())
    payload = _coerce(payload_cls, data)
    result = builder(payload, args.output)
    out = result[0] if isinstance(result, tuple) else result
    claim_ids = result[1] if isinstance(result, tuple) else []
    print(json.dumps({"output": str(out), "exists": out.exists(),
                       "size_bytes": out.stat().st_size,
                       "claim_ids": list(claim_ids)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
