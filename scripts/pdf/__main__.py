"""CLI entry point for PDF conversion.

Usage:
    python -m scripts.pdf --input <path> --output <path.pdf>

Routes by extension:
    .md / .markdown / .html → WeasyPrint
    .docx / .xlsx / .pptx (etc.) → LibreOffice headless (must be installed)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.pdf import PdfConvertError, to_pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert a file to PDF.")
    parser.add_argument("--input", type=Path, required=True, help="Input file path")
    parser.add_argument("--output", type=Path, required=True, help="Output PDF path")
    args = parser.parse_args(argv)

    try:
        out = to_pdf(args.input, args.output)
    except PdfConvertError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2
    print(json.dumps({"output": str(out), "exists": out.exists(),
                       "size_bytes": out.stat().st_size}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
