"""
PDF utility for cfo-helper — ad-hoc "print this to PDF" helper.

# Pattern source: anthropics/skills/document-skills/pdf — their skill is
# read/extract/manipulate-heavy (qpdf, pdftotext, pdftk, reportlab). We
# don't currently have a PDF-primary deliverable, so this is a thin
# converter only: take a .docx / .xlsx / .pptx / .md / .html and produce a PDF.

Strategy:
- For .md and .html — render via WeasyPrint (clean typography, no external dep on Office).
- For .docx / .xlsx / .pptx — shell out to LibreOffice headless if available;
  if soffice isn't on PATH, raise with a clear error pointing the caller at the
  manual workflow.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


_OFFICE_EXTS = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}
_HTML_EXTS = {".html", ".htm"}
_MD_EXTS = {".md", ".markdown"}


class PdfConvertError(RuntimeError):
    """Raised when PDF conversion fails for a known/recoverable reason."""


def _soffice_path() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def _via_libreoffice(input_path: Path, output_path: Path, *, timeout: int = 90) -> Path:
    soffice = _soffice_path()
    if not soffice:
        raise PdfConvertError(
            f"Cannot convert {input_path.suffix} to PDF: LibreOffice (soffice) "
            f"not found on PATH. Install LibreOffice or open the file in Office "
            f"and File > Export > PDF manually."
        )
    cmd = [
        soffice, "--headless", "--norestore", "--nologo",
        "--convert-to", "pdf",
        "--outdir", str(output_path.parent),
        str(input_path),
    ]
    subprocess.run(cmd, check=True, timeout=timeout, capture_output=True)
    # LibreOffice names output as <input_stem>.pdf in --outdir
    produced = output_path.parent / (input_path.stem + ".pdf")
    if produced != output_path:
        produced.rename(output_path)
    return output_path


def _via_weasyprint_html(html: str, output_path: Path, *, base_url: Path | None = None) -> Path:
    from weasyprint import HTML
    HTML(string=html, base_url=str(base_url) if base_url else None).write_pdf(str(output_path))
    return output_path


def _via_weasyprint_markdown(input_path: Path, output_path: Path) -> Path:
    import markdown as md_mod
    text = input_path.read_text()
    html_body = md_mod.markdown(text, extensions=["tables", "fenced_code"])
    html_doc = (
        "<html><head><meta charset='utf-8'>"
        "<style>"
        "body { font-family: 'Helvetica Neue', Arial, sans-serif; "
        "       max-width: 7.5in; margin: 0.75in auto; color: #111; "
        "       font-size: 11pt; line-height: 1.5; }"
        "h1 { color: #1F4E79; border-bottom: 2px solid #1F4E79; padding-bottom: 0.2em; }"
        "h2 { color: #1F2937; margin-top: 1.2em; }"
        "table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }"
        "th, td { border: 1px solid #ccc; padding: 6px 10px; text-align: left; }"
        "th { background: #1F2937; color: #fff; }"
        "code { background: #f3f4f6; padding: 1px 4px; border-radius: 2px; }"
        ".claim-ref { color: #6B7280; font-style: italic; font-size: 9pt; }"
        "</style></head><body>" + html_body + "</body></html>"
    )
    return _via_weasyprint_html(html_doc, output_path, base_url=input_path.parent)


def to_pdf(input_path: Path, output_path: Path) -> Path:
    """Convert `input_path` to PDF at `output_path`. Returns output_path.

    Routes by extension:
    - .md / .markdown → WeasyPrint (markdown -> HTML -> PDF)
    - .html / .htm    → WeasyPrint
    - .docx / .xlsx / .pptx (etc.) → LibreOffice headless (must be installed)

    Raises `PdfConvertError` with a clear message if a required tool is missing.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()
    if suffix in _MD_EXTS:
        return _via_weasyprint_markdown(input_path, output_path)
    if suffix in _HTML_EXTS:
        return _via_weasyprint_html(input_path.read_text(), output_path,
                                    base_url=input_path.parent)
    if suffix in _OFFICE_EXTS:
        return _via_libreoffice(input_path, output_path)
    raise PdfConvertError(f"Unsupported input extension for PDF conversion: {suffix}")


__all__ = ["to_pdf", "PdfConvertError"]
