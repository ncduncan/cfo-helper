"""
Backward-compat shim. The XLSX tooling moved to `scripts.xlsx`; the four
public functions that historic callers rely on are re-exported here so
`from scripts import format as fmt` continues to work.

New code should `from scripts import xlsx` (or import submodules directly:
`from scripts.xlsx import builders, qa, recalc`).
"""

from scripts.xlsx import (
    new_close_pack,
    render_exec_summary,
    write_table,
    write_value_with_provenance,
)

__all__ = [
    "new_close_pack",
    "render_exec_summary",
    "write_table",
    "write_value_with_provenance",
]
